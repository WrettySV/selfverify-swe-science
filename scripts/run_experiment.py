#!/usr/bin/env python3
"""Run baseline or self-verify via SWE-bench Science run_batch.py + Pier."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
from selfverify.provider_overlay import config_from_env_file, parse_dotenv  # noqa: E402

# Pier wrapper that prefers import_path over builtin agent name.
PIER_SV_BIN = ROOT / "scripts" / "pier-sv"


def default_swe_science_root() -> Path:
    env = os.environ.get("SWE_SCIENCE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    for path in (
        Path("/home/lukina/SWE-bench-Science/huggingface"),
        Path("/home/lukina/SWE-bench-Science"),
    ):
        if (path / "scripts" / "run_batch.py").is_file():
            return path
    raise SystemExit("Set SWE_SCIENCE_ROOT to the SWE-bench Science release root")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--condition",
        choices=("baseline", "selfverify"),
        required=True,
    )
    parser.add_argument("--path", type=Path, required=True, help="Materialized tasks dir")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--jobs-dir", type=Path, default=ROOT / "results" / "main")
    parser.add_argument("--job-name", type=str, default=None)
    parser.add_argument("--n-concurrent", type=int, default=1)
    parser.add_argument("--n-attempts", type=int, default=3)
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--max-verify-rounds", type=int, default=4)
    parser.add_argument(
        "--verification-mode",
        choices=("contract", "review", "continue", "public-only", "adaptive", "full"),
        default="contract",
        help="contract generates frozen requirement tests before seeing a patch; "
        "review audits the existing patch before repair; "
        "continue is an ordinary continuation control from the same saved patch.",
    )
    parser.add_argument(
        "--max-loop-seconds",
        type=int,
        default=4800,
        help="Total agent deadline including draft/public stages (default: 4800)",
    )
    parser.add_argument(
        "--codex-stage-timeout-sec",
        type=int,
        default=3600,
        help="Maximum duration of any single Codex turn (default: 3600)",
    )
    parser.add_argument(
        "--finalize-reserve-sec",
        type=int,
        default=180,
        help="Time kept inside the deadline for patch finalization (default: 180)",
    )
    parser.add_argument(
        "--keep-worktree-invariants",
        action="store_true",
        help="Leave selfverify/ in the worktree, where it becomes part of model.patch",
    )
    parser.add_argument(
        "--agent-timeout-multiplier",
        type=float,
        default=None,
        help="Pier agent-stage timeout multiplier (selfverify default: 2.0)",
    )
    parser.add_argument(
        "--model-context-window",
        type=int,
        default=None,
        help="Override CODEX_MODEL_CONTEXT_WINDOW (must match vLLM --max-model-len)",
    )
    parser.add_argument("--initial-patches", type=Path, help="Host directory containing task_NNN.patch (contract/continue/review)")
    parser.add_argument("--test-design-timeout-sec", type=int, default=900)
    parser.add_argument("--suite-context", choices=("blind", "candidate"), default="blind")
    parser.add_argument("--test-design-focus", choices=("default", "analytic", "boundary"), default="default")
    parser.add_argument("--draft-timeout-sec", type=int, default=1500)
    parser.add_argument("--repair-timeout-sec", type=int, default=900)
    parser.add_argument("--max-repair-rounds", type=int, default=1)
    parser.add_argument("--review-timeout-sec", type=int, default=360)
    parser.add_argument("--review-recheck-timeout-sec", type=int, default=180)
    parser.add_argument("--regression-suites", type=Path, help="Frozen existing tests in task_NNN subdirectories (review mode)")
    parser.add_argument("--verify-timeout-sec", type=int, default=120)
    parser.add_argument("--skip-pull", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--swe-science-root", type=Path, default=None)
    args = parser.parse_args()
    if args.max_loop_seconds <= args.finalize_reserve_sec:
        parser.error("--max-loop-seconds must exceed --finalize-reserve-sec")
    if args.codex_stage_timeout_sec <= 0:
        parser.error("--codex-stage-timeout-sec must be positive")

    if args.initial_patches and (args.condition != "selfverify" or args.verification_mode not in {"contract", "continue", "review"}):
        parser.error("--initial-patches requires selfverify contract/continue/review")
    if args.max_repair_rounds < 0:
        parser.error("max_repair_rounds must be nonnegative")
    if args.suite_context == "candidate" and (args.condition != "selfverify" or args.verification_mode != "contract" or not args.initial_patches):
        parser.error("candidate suite context requires selfverify contract with an initial patch")
    for name in ("test_design_timeout_sec", "draft_timeout_sec", "repair_timeout_sec", "verify_timeout_sec", "review_timeout_sec", "review_recheck_timeout_sec"):
        if getattr(args, name) <= 0:
            parser.error(f"{name} must be positive")
    if args.initial_patches:
        for task in args.path.glob("task_*"):
            if not (args.initial_patches / (task.name + ".patch")).is_file():
                parser.error(f"missing initial patch for {task.name}")

    if args.regression_suites:
        if args.verification_mode != "review" or args.condition != "selfverify":
            parser.error("--regression-suites requires selfverify review")
        for task in args.path.glob("task_*"):
            if not (args.regression_suites / task.name / "manifest.json").is_file():
                parser.error(f"missing regression suite for {task.name}")

    swe_root = (args.swe_science_root or default_swe_science_root()).resolve()
    run_batch = swe_root / "scripts" / "run_batch.py"
    if not run_batch.is_file():
        raise SystemExit(f"run_batch.py not found: {run_batch}")

    env_file = args.env_file.expanduser().resolve()
    env_vals = parse_dotenv(env_file)
    model_from_env, config_toml, _ = config_from_env_file(env_file)
    if args.model_context_window is not None:
        from selfverify.provider_overlay import render_codex_config

        config_toml = render_codex_config(
            base_url=(
                env_vals.get("CODEX_BASE_URL")
                or env_vals.get("OPENAI_BASE_URL")
                or "http://172.17.0.1:8001/v1"
            ),
            wire_api=(env_vals.get("CODEX_WIRE_API") or "responses"),
            model_context_window=args.model_context_window,
        )

    models = list(args.model) or [model_from_env]
    job_name = args.job_name or f"{args.condition}-n{args.n_attempts}"

    cmd = [
        sys.executable,
        str(run_batch),
        "--path",
        str(args.path.resolve()),
        # Must stay a Pier builtin enum value (CLI validates --agent).
        "--agent",
        "codex",
        "--env-file",
        str(env_file),
        "--jobs-dir",
        str(args.jobs_dir.resolve()),
        "--job-name",
        job_name,
        "--n-concurrent",
        str(args.n_concurrent),
        "--n-attempts",
        str(args.n_attempts),
        # Supply config_toml ourselves so model_context_window is included;
        # run_batch skips its auto-rendered config when this kwarg is present.
        "--agent-kwarg",
        "config_toml=" + config_toml,
        "--agent-kwarg",
        "command_model_name=" + models[0],
    ]

    # Explicit reasoning/version from env (also covers non-auto-provider paths).
    reasoning = (env_vals.get("CODEX_REASONING_EFFORT") or "").strip()
    version = (env_vals.get("CODEX_VERSION") or "").strip()
    if reasoning:
        cmd.extend(["--agent-kwarg", f"reasoning_effort={reasoning}"])
    if version:
        cmd.extend(["--agent-kwarg", f"version={version}"])

    for model in models:
        cmd.extend(["--model", model])
    if args.skip_pull:
        cmd.append("--skip-pull")
    if args.dry_run:
        cmd.append("--dry-run")

    # Full SV needs several Codex turns. Lean modes stop themselves before the
    # stock task timeout and therefore do not need a 2x multiplier.
    agent_timeout_mult = args.agent_timeout_multiplier
    if agent_timeout_mult is None and args.condition == "selfverify":
        agent_timeout_mult = 2.0 if args.verification_mode == "full" else 1.0
    if agent_timeout_mult is not None:
        cmd.extend(["--agent-timeout-multiplier", str(agent_timeout_mult)])

    if args.condition == "baseline":
        # Stock ScienceBenchCodex via run_batch auto-adapter.
        pass
    else:
        if not PIER_SV_BIN.is_file():
            raise SystemExit(f"missing Pier wrapper: {PIER_SV_BIN}")
        # Stock Pier ignores import_path when --agent codex is set. Use our
        # wrapper so SelfVerifyCodex actually runs (see docs/pier-agent-import.md).
        cmd.extend(["--pier-bin", str(PIER_SV_BIN)])
        cmd.extend(
            [
                "--agent-import-path",
                "selfverify.agent:SelfVerifyCodex",
                "--agent-kwarg",
                f"max_verify_rounds={args.max_verify_rounds}",
                "--agent-kwarg",
                "enable_selfverify=true",
                "--agent-kwarg",
                f"verification_mode={args.verification_mode}",
                "--agent-kwarg",
                f"require_challenge_rewrite={'true' if args.verification_mode == 'full' else 'false'}",
                "--agent-kwarg",
                f"enable_ablation_gate={'true' if args.verification_mode == 'full' else 'false'}",
                "--agent-kwarg",
                f"max_loop_seconds={args.max_loop_seconds}",
                "--agent-kwarg",
                f"codex_stage_timeout_sec={args.codex_stage_timeout_sec}",
                "--agent-kwarg",
                f"finalize_reserve_sec={args.finalize_reserve_sec}",
                "--agent-kwarg",
                f"keep_worktree_invariants={'true' if args.keep_worktree_invariants else 'false'}",
            ]
        )

    if args.condition == "selfverify":
        for name in ("test_design_timeout_sec", "draft_timeout_sec", "repair_timeout_sec", "max_repair_rounds", "verify_timeout_sec", "review_timeout_sec", "review_recheck_timeout_sec"):
            cmd.extend(["--agent-kwarg", f"{name}={getattr(args, name)}"])
        if args.initial_patches:
            cmd.extend(["--agent-kwarg", f"initial_patches={args.initial_patches.resolve()}"])

    if args.condition == "selfverify":
        cmd.extend(["--agent-kwarg", f"suite_context={args.suite_context}",
                    "--agent-kwarg", f"test_design_focus={args.test_design_focus}"])

    if args.condition == "selfverify" and args.regression_suites:
        cmd.extend(["--agent-kwarg", f"regression_suites={args.regression_suites.resolve()}"])

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (
            str(SRC),
            str(swe_root),
            env.get("PYTHONPATH", ""),
        )
        if value
    )
    env.setdefault("SWE_SCIENCE_ROOT", str(swe_root))
    env["DOCKER_DEFAULT_PLATFORM"] = env.get("DOCKER_DEFAULT_PLATFORM", "linux/amd64")

    print("+", " ".join(cmd), flush=True)
    print(f"# PYTHONPATH={env['PYTHONPATH']}", flush=True)
    print("# model_context_window injected via config_toml (see docs/context-window.md)")
    if args.condition == "selfverify":
        print(
            f"# using pier wrapper {PIER_SV_BIN} so import_path wins over --agent codex",
            flush=True,
        )
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
