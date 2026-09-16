"""Pier Codex adapter with an in-session self-verification loop.

Inherits ``scripts.pier_adapters:ScienceBenchCodex`` so amd64 Codex install
fixes are preserved. Overrides ``run()`` because the stock ``Codex.run``:
  1. issues a single ``codex exec``;
  2. deletes ``$CODEX_HOME`` in ``finally``.

Stages share ``CODEX_HOME`` but each exec starts a fresh conversation.
Later stages receive the original task instruction explicitly. ``model.patch`` is still collected by Pier's ``pre_artifacts.sh``
*after* ``run()`` returns (git diff of the workspace) — we do not invent an
emit-patch API.

``feedback`` is a *stage inside this loop*, not a separate agent.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time
from typing import Any

from pier.agents.installed.base import with_prompt_template
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext
from pier.models.trial.paths import EnvironmentPaths

from selfverify.logging import RunLogger
from selfverify.stages import (
    clear_worktree_selfverify,
    discover_workdir,
    format_ablation_summary,
    format_failed_tests,
    format_weak_tests,
    load_prompt,
    persist_invariants,
    render_prompt,
    restore_snapshot_if_lost,
    run_ablation_probe,
    run_discriminator_gate,
    run_public_reproduction,
    run_verification,
    snapshot_worktree_patch,
    write_remote_text,
)


def _resolve_science_bench_codex():
    """Prefer the release adapter; fall back to an identical local mirror."""
    try:
        from scripts.pier_adapters import ScienceBenchCodex  # type: ignore

        return ScienceBenchCodex
    except ImportError:
        from pier.agents.installed.codex import Codex

        class ScienceBenchCodex(Codex):
            """Mirror of scripts.pier_adapters:ScienceBenchCodex (amd64 npm fix)."""

            def install_spec(self):
                spec = super().install_spec()
                for step in spec.steps:
                    step.run = step.run.replace(
                        "npm install -g @openai/codex",
                        "npm install -g --include=optional @openai/codex",
                    )
                return spec

        return ScienceBenchCodex


ScienceBenchCodex = _resolve_science_bench_codex()


class AgentBudgetExceeded(TimeoutError):
    """Raised when an internal stage reaches the agent's safe deadline."""


class SelfVerifyCodex(ScienceBenchCodex):
    """Codex + self-verification stages on top of ScienceBenchCodex."""

    def __init__(
        self,
        *args: Any,
        max_verify_rounds: int = 3,
        verify_timeout_sec: int = 180,
        enable_selfverify: bool = True,
        require_challenge_rewrite: bool = True,
        enable_ablation_gate: bool = True,
        max_loop_seconds: int = 4800,
        codex_stage_timeout_sec: int = 3600,
        finalize_reserve_sec: int = 180,
        verification_mode: str = "contract",
        keep_worktree_invariants: bool = False,
        initial_patches: str | None = None,
        test_design_timeout_sec: int = 900,
        suite_context: str = "blind",
        test_design_focus: str = "default",
        draft_timeout_sec: int = 1500,
        repair_timeout_sec: int = 900,
        max_repair_rounds: int = 1,
        review_timeout_sec: int = 360,
        review_recheck_timeout_sec: int = 180,
        regression_suites: str | None = None,
        **kwargs: Any,
    ) -> None:
        # Pier passes agent-kwarg values as strings.
        if isinstance(max_verify_rounds, str):
            max_verify_rounds = int(max_verify_rounds)
        if isinstance(verify_timeout_sec, str):
            verify_timeout_sec = int(verify_timeout_sec)
        if isinstance(enable_selfverify, str):
            enable_selfverify = enable_selfverify.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if isinstance(require_challenge_rewrite, str):
            require_challenge_rewrite = require_challenge_rewrite.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if isinstance(enable_ablation_gate, str):
            enable_ablation_gate = enable_ablation_gate.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if isinstance(max_loop_seconds, str):
            max_loop_seconds = int(max_loop_seconds)
        if isinstance(codex_stage_timeout_sec, str):
            codex_stage_timeout_sec = int(codex_stage_timeout_sec)
        if isinstance(finalize_reserve_sec, str):
            finalize_reserve_sec = int(finalize_reserve_sec)
        if isinstance(keep_worktree_invariants, str):
            keep_worktree_invariants = keep_worktree_invariants.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        super().__init__(*args, **kwargs)
        verification_mode = verification_mode.strip().lower().replace("_", "-")
        if verification_mode not in {"public-only", "adaptive", "full", "contract", "continue", "review"}:
            raise ValueError(
                "verification_mode must be contract, review, continue, public-only, adaptive, or full"
            )
        self.initial_patches = initial_patches
        if suite_context not in {"blind", "candidate"}:
            raise ValueError("suite_context must be blind or candidate")
        if suite_context == "candidate" and (verification_mode != "contract" or not initial_patches):
            raise ValueError("candidate-conditioned suites require contract mode and an initial patch")
        if test_design_focus not in {"default", "analytic", "boundary"}:
            raise ValueError("unknown test_design_focus")
        self.suite_context = suite_context
        self.test_design_focus = test_design_focus
        self.review_timeout_sec = max(1, int(review_timeout_sec))
        self.review_recheck_timeout_sec = max(1, int(review_recheck_timeout_sec))
        self.regression_suites = regression_suites
        self.test_design_timeout_sec = max(1, int(test_design_timeout_sec))
        self.draft_timeout_sec = max(1, int(draft_timeout_sec))
        self.repair_timeout_sec = max(1, int(repair_timeout_sec))
        if int(max_repair_rounds) < 0:
            raise ValueError("max_repair_rounds must be nonnegative")
        self.max_repair_rounds = int(max_repair_rounds)
        if verification_mode in {"contract", "continue", "review"} and int(max_loop_seconds) <= int(finalize_reserve_sec):
            raise ValueError("contract/continue/review require a finite deadline with finalization reserve")
        if initial_patches and verification_mode not in {"contract", "continue", "review"}:
            raise ValueError("initial_patches is supported only by contract/continue/review")
        self.verification_mode = verification_mode
        self.max_loop_seconds = max(0, int(max_loop_seconds))
        self.codex_stage_timeout_sec = max(1, int(codex_stage_timeout_sec))
        self.finalize_reserve_sec = max(0, int(finalize_reserve_sec))
        self.keep_worktree_invariants = bool(keep_worktree_invariants)
        self.max_verify_rounds = max(1, int(max_verify_rounds))
        self.verify_timeout_sec = int(verify_timeout_sec)
        self.enable_selfverify = bool(enable_selfverify)
        self.require_challenge_rewrite = bool(require_challenge_rewrite)
        self.enable_ablation_gate = bool(enable_ablation_gate)
        self.artifacts: dict[str, Any] = {
            "invariants": [],
            "verify_runs": [],
            "public_runs": [],
            "revisions": 0,
            "history": [],
            "challenges": 0,
            "ablations": [],
            "draft_snapshot": None,
            "best_snapshot": None,
            "final_patch_guard": None,
            "worktree_cleanup": None,
            "verification_mode": verification_mode,
        }
        self._deadline: float | None = None
        self._active_stage = "setup"

    def populate_context_post_run(self, context: AgentContext) -> None:
        # Stock Pier requires one date directory and parses just one JSONL file.
        # Contract repair can span several conversations and UTC dates.
        from selfverify.metrics import collect_session_usage
        usage = collect_session_usage(self.logs_dir)
        (self.logs_dir / "session_metrics.json").write_text(json.dumps(usage, indent=2) + "\n")
        if not usage["n_with_usage"]:
            return
        totals = usage["totals"]
        context.n_input_tokens = totals["input_tokens"]
        context.n_cache_tokens = totals["cached_input_tokens"]
        context.n_output_tokens = totals["output_tokens"]
        context.peak_context_tokens = usage["peak_context_tokens"]
        context.metadata = {**(context.metadata or {}), "session_usage_complete": usage["complete"],
                            "n_sessions": usage["n_sessions"]}
        context.cost_usd = None  # no verified local-vLLM price model

    def _model_cli_name(self) -> str:
        if not self.model_name:
            raise ValueError("Model name is required")
        return self._command_model_name or self.model_name.split("/")[-1]

    async def _setup_codex_home(
        self, environment: BaseEnvironment, env: dict[str, str]
    ) -> None:
        remote_codex_home = self._REMOTE_CODEX_HOME.as_posix()
        remote_secrets_dir = self._REMOTE_CODEX_SECRETS_DIR.as_posix()
        remote_auth_path = (self._REMOTE_CODEX_SECRETS_DIR / "auth.json").as_posix()

        await self.exec_as_agent(
            environment,
            command=(
                f'mkdir -p "$CODEX_HOME" {shlex.quote(remote_secrets_dir)} '
                f"{shlex.quote(EnvironmentPaths.agent_dir.as_posix())}"
            ),
            env=env,
        )

        auth_json_path = self._resolve_auth_json_path()
        if auth_json_path:
            self.logger.debug("Codex auth: using auth.json from %s", auth_json_path)
            await environment.upload_file(auth_json_path, remote_auth_path)
            if environment.default_user is not None:
                await self.exec_as_root(
                    environment,
                    command=f"chown {environment.default_user} {remote_auth_path}",
                )
            setup_command = (
                f'ln -sf {shlex.quote(remote_auth_path)} "$CODEX_HOME/auth.json"\n'
            )
        else:
            self.logger.debug("Codex auth: using OPENAI_API_KEY")
            env.setdefault("OPENAI_API_KEY", self._get_env("OPENAI_API_KEY") or "")
            setup_command = (
                f"cat >{shlex.quote(remote_auth_path)} <<EOF\n"
                '{\n  "OPENAI_API_KEY": "${OPENAI_API_KEY}"\n}\nEOF\n'
                f"ln -sf {shlex.quote(remote_auth_path)} "
                '"$CODEX_HOME/auth.json"\n'
            )

        if openai_base_url := self._get_env("OPENAI_BASE_URL"):
            env["OPENAI_BASE_URL"] = openai_base_url

        config_toml_block = ""
        if openai_base_url:
            config_toml_block = (
                '\ncat >>"$CODEX_HOME/config.toml" <<TOML\n'
                'openai_base_url = "${OPENAI_BASE_URL}"\n'
                "TOML"
            )
        if self._config_toml:
            escaped_toml = shlex.quote(self._config_toml)
            config_toml_block += (
                f'\nprintf "%s\\n" {escaped_toml} >> "$CODEX_HOME/config.toml"\n'
            )
        setup_command += config_toml_block

        skills_command = self._build_register_skills_command()
        if skills_command:
            setup_command += f"\n{skills_command}"
        mcp_command = self._build_register_mcp_servers_command()
        if mcp_command:
            setup_command += f"\n{mcp_command}"

        if setup_command.strip():
            await self.exec_as_agent(environment, command=setup_command, env=env)

    async def _codex_exec(
        self,
        environment: BaseEnvironment,
        *,
        instruction: str,
        env: dict[str, str],
        output_name: str,
        stage: str,
        cwd: str | None = None,
        timeout_sec: float | None = None,
        reserve_sec: float = 0,
    ) -> None:
        if stage != "draft" and getattr(self, "_original_instruction", None):
            instruction = "Original task instruction:\n" + self._original_instruction + "\n\nCurrent stage:\n" + instruction
        model = self._model_cli_name()
        cli_flags = self.build_cli_flags()
        cli_flags_arg = (cli_flags + " ") if cli_flags else ""
        out_path = EnvironmentPaths.agent_dir / output_name
        self._active_stage = stage
        timeout = self._stage_timeout()
        if self._deadline is not None:
            timeout = min(timeout, self._deadline - time.monotonic() - self.finalize_reserve_sec - reserve_sec - 20)
        if timeout <= 0:
            raise AgentBudgetExceeded(f"no budget for {stage} after reserving evaluation time")
        if timeout_sec is not None:
            timeout = min(timeout, timeout_sec)
        instruction = (
            f"Stage time budget: at most {timeout:.0f} seconds. Save a runnable intermediate "
            "result early; leave time to execute focused checks and finish.\n\n" + instruction
        )
        escaped_instruction = shlex.quote(instruction)
        status_path = str(out_path) + ".exit"
        command = (
            "if [ -s ~/.nvm/nvm.sh ]; then . ~/.nvm/nvm.sh; fi; "
            f"timeout --signal=TERM --kill-after=10 {timeout:.1f}s codex exec "
            "--dangerously-bypass-approvals-and-sandbox "
            "--skip-git-repo-check "
            f"--model {shlex.quote(model)} "
            "--json "
            "--enable unified_exec "
            f"{cli_flags_arg}"
            "-- "
            f"{escaped_instruction} "
            f"2>&1 </dev/null | tee {shlex.quote(str(out_path))}; "
            f"printf '%s' \"${{PIPESTATUS[0]}}\" > {shlex.quote(status_path)}"
        )
        try:
            await asyncio.wait_for(
                self.exec_as_agent(environment, command=command, env=env, cwd=cwd),
                timeout=timeout + 20,
            )
        except TimeoutError as exc:
            raise AgentBudgetExceeded(
                f"{stage} exceeded its {timeout:.0f}s safe timeout"
            ) from exc

        result = await environment.exec(command=f"cat {shlex.quote(status_path)}", timeout_sec=10)
        code = (result.stdout or "").strip()
        if code in {"124", "137"}:
            raise AgentBudgetExceeded(f"{stage} exceeded its {timeout:.0f}s process timeout")
        if code != "0":
            raise RuntimeError(f"{stage}: codex exited with status {code!r}")

    def _stage_timeout(self) -> float:
        timeout = float(self.codex_stage_timeout_sec)
        if self._deadline is not None:
            remaining = self._deadline - time.monotonic() - self.finalize_reserve_sec
            if remaining <= 0:
                raise AgentBudgetExceeded("agent deadline reached")
            timeout = min(timeout, remaining)
        return max(1.0, timeout)

    async def _checkpoint(
        self,
        environment: BaseEnvironment,
        workdir: str,
        logger: RunLogger,
        *,
        stage: str,
    ) -> dict[str, Any]:
        snapshot = await snapshot_worktree_patch(
            environment, workdir, self._DRAFT_SNAPSHOT
        )
        self.artifacts["best_snapshot"] = snapshot
        if stage == "draft":
            self.artifacts["draft_snapshot"] = snapshot
        logger.log(
            "patch_checkpoint",
            source_stage=stage,
            status="done" if snapshot.get("ok") else "error",
            bytes=snapshot.get("bytes"),
            sha256=snapshot.get("sha256"),
            error=snapshot.get("error"),
        )
        return snapshot

    async def _persist_sessions(self, environment: BaseEnvironment, env: dict[str, str]) -> None:
        await self.exec_as_agent(
            environment,
            command=(
                f"mkdir -p {EnvironmentPaths.agent_dir.as_posix()}\n"
                'if [ -d "$CODEX_HOME/sessions" ]; then\n'
                f"  rm -rf {(EnvironmentPaths.agent_dir / 'sessions').as_posix()}\n"
                f'  cp -R "$CODEX_HOME/sessions" '
                f'{(EnvironmentPaths.agent_dir / "sessions").as_posix()}\n'
                "fi"
            ),
            env=env,
        )

    async def _cleanup_codex_home(
        self, environment: BaseEnvironment, env: dict[str, str]
    ) -> None:
        remote_secrets_dir = self._REMOTE_CODEX_SECRETS_DIR.as_posix()
        await self.exec_as_agent(
            environment,
            command=f'rm -rf {shlex.quote(remote_secrets_dir)} "$CODEX_HOME"',
            env=env,
        )

    _DRAFT_SNAPSHOT = "/tmp/selfverify_best.patch"

    async def _finalize_worktree(self, environment: BaseEnvironment, logger: RunLogger) -> None:
        """Leave the worktree in the state we actually want graded.

        Runs even after a timeout or exception, because ``pre_artifacts.sh``
        turns whatever is on disk into ``model.patch`` regardless of how the
        loop ended.
        """
        if self.verification_mode in {"contract", "continue", "review"}:
            from selfverify.contract import finalize
            await finalize(self, environment, logger)
            return
        try:
            workdir = await discover_workdir(environment)
        except Exception:
            self.logger.exception("Could not discover workdir for finalization")
            return

        try:
            await persist_invariants(
                environment,
                workdir,
                (EnvironmentPaths.agent_dir / "selfverify_worktree").as_posix(),
            )
        except Exception:
            self.logger.exception("Could not persist invariants to logs")

        snapshot = self.artifacts.get("best_snapshot")
        if isinstance(snapshot, dict) and snapshot.get("ok"):
            try:
                guard = await restore_snapshot_if_lost(environment, workdir, snapshot)
                self.artifacts["final_patch_guard"] = guard
                if guard.get("action") == "restored_snapshot":
                    logger.log(
                        "patch_guard",
                        status="restored_best",
                        ok=guard.get("ok"),
                        saved_bytes=guard.get("saved_bytes"),
                    )
            except Exception:
                self.logger.exception("Draft patch guard failed")

        if not self.keep_worktree_invariants:
            try:
                cleanup = await clear_worktree_selfverify(environment, workdir)
                self.artifacts["worktree_cleanup"] = cleanup
                logger.log("worktree_cleanup", status="done", **cleanup)
            except Exception:
                self.logger.exception("Could not clear selfverify/ from worktree")

    def _budget_exhausted(self) -> bool:
        if self._deadline is None:
            return False
        return time.monotonic() >= self._deadline - self.finalize_reserve_sec

    async def _write_host_summary(self) -> None:
        summary_path = self.logs_dir / "selfverify_summary.json"
        try:
            summary_path.write_text(
                json.dumps(self.artifacts, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            self.logger.debug("Could not write %s", summary_path)

    @with_prompt_template
    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        self._original_instruction = instruction
        remote_codex_home = self._REMOTE_CODEX_HOME.as_posix()
        env = self.build_process_env({"CODEX_HOME": remote_codex_home})

        # Host-side logger (Pier downloads agent logs after the trial).
        logger = RunLogger(self.logs_dir)
        logger.log(
            "start",
            enable_selfverify=self.enable_selfverify,
            verification_mode=self.verification_mode,
            max_verify_rounds=self.max_verify_rounds,
            require_challenge_rewrite=self.require_challenge_rewrite,
            enable_ablation_gate=self.enable_ablation_gate,
        )
        finished_cleanly = False
        self._deadline = (
            time.monotonic() + self.max_loop_seconds
            if self.max_loop_seconds
            else None
        )

        await self._setup_codex_home(environment, env)
        try:
            try:
                await self._run_selfverify_loop(
                    instruction=instruction,
                    environment=environment,
                    env=env,
                    logger=logger,
                )
                finished_cleanly = True
            except AgentBudgetExceeded as exc:
                logger.log(
                    "done",
                    reason="agent_budget_exhausted",
                    active_stage=self._active_stage,
                    error=str(exc),
                )
                self.artifacts["history"].append(
                    {
                        "stage": self._active_stage,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                finished_cleanly = True
            except asyncio.CancelledError:
                logger.log(
                    "done",
                    reason="agent_cancelled",
                    active_stage=self._active_stage,
                )
                self.artifacts["history"].append(
                    {"stage": self._active_stage, "error_type": "CancelledError"}
                )
                raise
            except Exception as exc:
                # Pier AgentTimeoutError and other failures previously left run_log
                # stuck on invariant_gen:begin while verifier still scored the patch.
                logger.log(
                    "done",
                    reason="agent_exception",
                    error_type=type(exc).__name__,
                    error=str(exc)[:1000],
                )
                self.artifacts["history"].append(
                    {
                        "stage": "exception",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:1000],
                    }
                )
                raise
        finally:
            if not finished_cleanly and not logger.saw_done:
                try:
                    logger.log("done", reason="incomplete_no_done_event")
                except Exception:
                    pass
            try:
                await self._finalize_worktree(environment, logger)
            except Exception:
                self.logger.exception("Worktree finalization failed")
            try:
                await self._persist_sessions(environment, env)
            except Exception:
                self.logger.exception("Failed to persist Codex sessions")
            try:
                await self._cleanup_codex_home(environment, env)
            except Exception:
                pass
            await self._write_host_summary()

    async def _run_selfverify_loop(
        self,
        *,
        instruction: str,
        environment: BaseEnvironment,
        env: dict[str, str],
        logger: RunLogger,
    ) -> None:
            if self.verification_mode in {"contract", "continue", "review"}:
                from selfverify.contract import run_contract_loop
                await run_contract_loop(self, instruction, environment, env, logger)
                return
            workdir = await discover_workdir(environment)

            # Stage 1: draft patch (standard Codex turn on the task instruction).
            # Tee as codex.txt so Pier's stock trajectory/log collectors still work;
            # also keep an explicit draft copy for analysis.
            logger.log("draft", status="begin")
            await self._codex_exec(
                environment,
                instruction=instruction,
                env=env,
                output_name="codex.txt",
                stage="draft",
            )
            await self.exec_as_agent(
                environment,
                command=(
                    f"cp -f {(EnvironmentPaths.agent_dir / 'codex.txt').as_posix()} "
                    f"{(EnvironmentPaths.agent_dir / 'codex_draft.txt').as_posix()} "
                    "2>/dev/null || true"
                ),
                env=env,
            )
            logger.log("draft", status="done")

            if not self.enable_selfverify:
                logger.log("done", reason="selfverify_disabled")
                return

            # Save every code-changing turn. Gates may reset the tree, and Pier
            # may cancel a later turn at any await point.
            await self._checkpoint(environment, workdir, logger, stage="draft")

            await write_remote_text(
                environment,
                f"{workdir}/selfverify/README.txt",
                "Self-verify artifacts for this trial.\n",
            )

            # Stage 1b: cheap public smoke gate before expensive invariants.
            logger.log("public_check", status="begin", attempt=0)
            public = await run_public_reproduction(
                environment, workdir, timeout_sec=self.verify_timeout_sec
            )
            self.artifacts["public_runs"] = [public]
            logger.log(
                "public_check",
                status="done",
                attempt=0,
                passed=public["passed"],
                exit_code=public.get("exit_code"),
            )
            if not public["passed"]:
                public_fb = render_prompt(
                    "public_revise.md",
                    exit_code=str(public.get("exit_code")),
                    command=str(public.get("command") or "python reproduce.py"),
                    stdout=str(public.get("stdout") or "")[:3000],
                    stderr=str(public.get("stderr") or "")[:1500],
                )
                logger.log("public_revise", status="begin")
                await self._codex_exec(
                    environment,
                    instruction=public_fb,
                    env=env,
                    output_name="codex_public_revise.txt",
                    stage="public_revise",
                )
                self.artifacts["revisions"] += 1
                logger.log("public_revise", status="done")
                await self._checkpoint(
                    environment, workdir, logger, stage="public_revise"
                )

                logger.log("public_check", status="begin", attempt=1)
                public = await run_public_reproduction(
                    environment, workdir, timeout_sec=self.verify_timeout_sec
                )
                self.artifacts["public_runs"].append(public)
                logger.log(
                    "public_check",
                    status="done",
                    attempt=1,
                    passed=public["passed"],
                    exit_code=public.get("exit_code"),
                )

            if not public["passed"]:
                # Do not burn invariant LLM rounds on a draft that fails smoke.
                logger.log("done", reason="public_failed_skip_invariants")
                self.artifacts["history"].append(
                    {"stage": "public_gate", "skipped_invariants": True, "public": public}
                )
                return

            if self.verification_mode in {"public-only", "adaptive"}:
                logger.log(
                    "done",
                    reason=(
                        "adaptive_online_complete"
                        if self.verification_mode == "adaptive"
                        else "public_only_complete"
                    ),
                    public_passed=True,
                )
                return

            # Discriminator + patch loop:
            #   GEN → VALIDATE (fail@pre) → VERIFY good@post
            #   → (first green) challenge rewrite → re-gate → re-verify
            #   → ablation probe → accept | ablation_reject rewrite
            need_gen = True
            good_scripts: list[str] = []
            challenge_done = not self.require_challenge_rewrite
            for round_idx in range(self.max_verify_rounds):
                # Stopping on our own terms keeps the draft; being killed by the
                # Pier agent timeout mid-generation is what produced empty patches.
                if self._budget_exhausted():
                    logger.log(
                        "done",
                        reason="loop_budget_exhausted",
                        round=round_idx,
                        max_loop_seconds=self.max_loop_seconds,
                    )
                    return
                if need_gen:
                    inv_prompt = load_prompt("invariant_generation.md")
                    gen_instruction = (
                        "The repository already contains your draft repair. "
                        "Do not revert unrelated work. Focus on generating metamorphic tests "
                        "that FAIL on pre-fix and PASS on a correct fix.\n\n"
                        + inv_prompt
                    )
                    logger.log("invariant_gen", round=round_idx, status="begin")
                    await self._codex_exec(
                        environment,
                        instruction=gen_instruction,
                        env=env,
                        output_name=f"codex_invariants_r{round_idx}.txt",
                        stage="invariant_gen",
                    )
                    logger.log("invariant_gen", round=round_idx, status="done")

                    logger.log("discriminator_gate", round=round_idx, status="begin")
                    gate = await run_discriminator_gate(
                        environment,
                        workdir,
                        timeout_sec=self.verify_timeout_sec,
                    )
                    self.artifacts.setdefault("discriminator_gates", []).append(gate)
                    self.artifacts["history"].append(
                        {"round": round_idx, "discriminator_gate": {
                            "status": gate.get("status"),
                            "n_good": gate.get("n_good"),
                            "n_weak": gate.get("n_weak"),
                            "n_banned": gate.get("n_banned"),
                            "error": gate.get("error"),
                        }}
                    )
                    logger.log(
                        "discriminator_gate",
                        round=round_idx,
                        status=gate.get("status") or ("ok" if gate.get("ok") else "error"),
                        n_good=gate.get("n_good"),
                        n_weak=gate.get("n_weak"),
                        n_banned=gate.get("n_banned"),
                        error=gate.get("error"),
                    )

                    if gate.get("pre_result"):
                        self.artifacts.setdefault("pre_verify_runs", []).append(
                            gate["pre_result"]
                        )

                    if not gate.get("ok"):
                        logger.log(
                            "done",
                            reason="discriminator_gate_error",
                            round=round_idx,
                            error=gate.get("error"),
                        )
                        return

                    if gate.get("status") == "no_tests_generated":
                        logger.log("done", reason="no_tests_generated", round=round_idx)
                        return

                    good_scripts = list(gate.get("good_scripts") or [])
                    if not good_scripts:
                        # All tests passed on pre-fix → rewrite TESTS, not claim patch OK.
                        if round_idx >= self.max_verify_rounds - 1:
                            logger.log(
                                "done",
                                reason="no_valid_tests",
                                round=round_idx,
                            )
                            return
                        rewrite = render_prompt(
                            "test_rewrite.md",
                            weak_test_results=format_weak_tests(gate.get("pre_result")),
                        )
                        logger.log("test_rewrite", round=round_idx, status="begin")
                        await self._codex_exec(
                            environment,
                            instruction=rewrite,
                            env=env,
                            output_name=f"codex_test_rewrite_r{round_idx}.txt",
                            stage="test_rewrite",
                        )
                        self.artifacts["revisions"] += 1
                        logger.log("test_rewrite", round=round_idx, status="done")

                        # Re-check discriminators on the rewritten suite (same round).
                        logger.log(
                            "discriminator_gate",
                            round=round_idx,
                            status="begin",
                            phase="after_rewrite",
                        )
                        gate = await run_discriminator_gate(
                            environment,
                            workdir,
                            timeout_sec=self.verify_timeout_sec,
                        )
                        self.artifacts.setdefault("discriminator_gates", []).append(gate)
                        logger.log(
                            "discriminator_gate",
                            round=round_idx,
                            status=gate.get("status")
                            or ("ok" if gate.get("ok") else "error"),
                            n_good=gate.get("n_good"),
                            n_weak=gate.get("n_weak"),
                            n_banned=gate.get("n_banned"),
                            phase="after_rewrite",
                        )
                        if gate.get("pre_result"):
                            self.artifacts.setdefault("pre_verify_runs", []).append(
                                gate["pre_result"]
                            )
                        good_scripts = list(gate.get("good_scripts") or [])
                        if not good_scripts:
                            need_gen = True
                            continue

                    need_gen = False

                # Stage: verify PATCH on post-fix using only discriminator-valid tests.
                verify_result = await run_verification(
                    environment,
                    workdir,
                    timeout_sec=self.verify_timeout_sec,
                    scripts=good_scripts,
                )
                verify_result = dict(verify_result)
                verify_result["good_scripts"] = list(good_scripts)
                verify_result["n_good"] = len(good_scripts)
                self.artifacts["verify_runs"].append(verify_result)
                self.artifacts["history"].append(
                    {"round": round_idx, "verify_result": verify_result}
                )
                status = verify_result.get("status") or (
                    "all_passed" if verify_result.get("all_passed") else "failed"
                )
                logger.log(
                    "verify_post",
                    round=round_idx,
                    status=status,
                    n_passed=verify_result["n_passed"],
                    n_failed=verify_result["n_failed"],
                    n_total=verify_result["n_total"],
                    all_passed=verify_result["all_passed"],
                )

                if verify_result["all_passed"]:
                    # Do not accept the first green wave — require an independent rewrite.
                    if not challenge_done:
                        if round_idx >= self.max_verify_rounds - 1:
                            logger.log(
                                "done",
                                reason="challenge_rewrite_not_completed",
                                round=round_idx,
                            )
                            return
                        challenge = load_prompt("challenge_rewrite.md")
                        logger.log("challenge_rewrite", round=round_idx, status="begin")
                        await self._codex_exec(
                            environment,
                            instruction=challenge,
                            env=env,
                            output_name=f"codex_challenge_r{round_idx}.txt",
                            stage="challenge_rewrite",
                        )
                        self.artifacts["revisions"] += 1
                        self.artifacts["challenges"] += 1
                        logger.log("challenge_rewrite", round=round_idx, status="done")
                        challenge_done = True
                        # challenge_rewrite already replaces the suite. Re-gate it
                        # directly next round instead of paying for another GEN.
                        gate = await run_discriminator_gate(
                            environment,
                            workdir,
                            timeout_sec=self.verify_timeout_sec,
                        )
                        self.artifacts.setdefault("discriminator_gates", []).append(gate)
                        if gate.get("pre_result"):
                            self.artifacts.setdefault("pre_verify_runs", []).append(
                                gate["pre_result"]
                            )
                        good_scripts = list(gate.get("good_scripts") or [])
                        logger.log(
                            "discriminator_gate",
                            round=round_idx,
                            phase="after_challenge",
                            status=gate.get("status")
                            or ("ok" if gate.get("ok") else "error"),
                            n_good=gate.get("n_good"),
                            n_weak=gate.get("n_weak"),
                            error=gate.get("error"),
                        )
                        if not gate.get("ok"):
                            logger.log(
                                "done",
                                reason="challenge_gate_error",
                                round=round_idx,
                                error=gate.get("error"),
                            )
                            return
                        need_gen = not bool(good_scripts)
                        continue

                    # Harness ablation gate: reject suites that survive dropping one fix file.
                    if self.enable_ablation_gate:
                        logger.log("ablation_gate", round=round_idx, status="begin")
                        ablation = await run_ablation_probe(
                            environment,
                            workdir,
                            good_scripts,
                            timeout_sec=self.verify_timeout_sec,
                        )
                        self.artifacts["ablations"].append(
                            {
                                "round": round_idx,
                                "survived": ablation.get("survived"),
                                "ablated_file": ablation.get("ablated_file"),
                                "status": ablation.get("status"),
                                "error": ablation.get("error"),
                            }
                        )
                        logger.log(
                            "ablation_gate",
                            round=round_idx,
                            status=ablation.get("status")
                            or ("ok" if ablation.get("ok") else "error"),
                            survived=ablation.get("survived"),
                            ablated_file=ablation.get("ablated_file"),
                            error=ablation.get("error"),
                        )
                        if ablation.get("ok") and ablation.get("survived"):
                            if round_idx >= self.max_verify_rounds - 1:
                                logger.log(
                                    "done",
                                    reason="ablation_survived_max_rounds",
                                    round=round_idx,
                                    ablated_file=ablation.get("ablated_file"),
                                )
                                return
                            reject = render_prompt(
                                "ablation_reject.md",
                                ablation_summary=format_ablation_summary(ablation),
                            )
                            logger.log("ablation_reject", round=round_idx, status="begin")
                            await self._codex_exec(
                                environment,
                                instruction=reject,
                                env=env,
                                output_name=f"codex_ablation_reject_r{round_idx}.txt",
                                stage="ablation_reject",
                            )
                            self.artifacts["revisions"] += 1
                            logger.log("ablation_reject", round=round_idx, status="done")
                            need_gen = True
                            continue

                    logger.log(
                        "done",
                        reason="all_valid_invariants_passed",
                        round=round_idx,
                        challenge_done=challenge_done,
                        ablation_checked=self.enable_ablation_gate,
                    )
                    return

                if round_idx >= self.max_verify_rounds - 1:
                    logger.log("done", reason="max_rounds_exhausted", round=round_idx)
                    return

                # Valid discriminators still failing post-fix → fix the PATCH.
                feedback = render_prompt(
                    "feedback.md",
                    failed_test_results=format_failed_tests(verify_result),
                )
                logger.log("feedback", round=round_idx, status="begin")
                await self._codex_exec(
                    environment,
                    instruction=feedback,
                    env=env,
                    output_name=f"codex_feedback_r{round_idx}.txt",
                    stage="feedback",
                )
                self.artifacts["revisions"] += 1
                logger.log("feedback", round=round_idx, status="done")
                await self._checkpoint(environment, workdir, logger, stage="feedback")
                # Keep the same good tests; next round only re-verifies post-fix
                # unless a later policy sets need_gen True again.
                need_gen = False

            logger.log("done", reason="max_rounds_exhausted")