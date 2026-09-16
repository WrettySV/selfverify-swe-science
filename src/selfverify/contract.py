"""Requirement-based checks, immutable suites and conservative patch selection."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import shlex
import time
import uuid

from selfverify.stages import discover_workdir, load_prompt, read_remote_text, write_remote_text


def freeze_suite(files):
    if sum(len(v.encode()) for v in files.values()) > 256_000:
        raise ValueError("suite exceeds 256 KB")
    manifest = json.loads(files.get("manifest.json", "{}"))
    tests = manifest.get("tests", [])
    if not 1 <= len(tests) <= 3:
        raise ValueError("manifest must contain 1-3 tests")
    seen = set()
    for name in files:
        if Path(name).name != name:
            raise ValueError("suite files must have flat names")
    for test in tests:
        name = test.get("path", "")
        if name in seen or not name.startswith("test_") or not name.endswith(".py") or name not in files:
            raise ValueError("invalid or duplicate test path")
        seen.add(name)
        for key in ("requirement", "basis", "expected", "input"):
            if not isinstance(test.get(key), str) or not test[key].strip():
                raise ValueError(f"{name}: missing {key}")
        tree = ast.parse(files[name])
        if not any(isinstance(n, ast.Assert) for n in ast.walk(tree)):
            raise ValueError(f"{name}: no explicit assertion")
    for name, code in files.items():
        if name.endswith(".py"):
            tree = ast.parse(code)
            # Comments are absent from the AST. Remove actual docstrings too:
            # documenting a public requirement must not count as invoking it.
            # Only this temporary tree changes; frozen source and hashes do not.
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if (node.body and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)
                            and isinstance(node.body[0].value.value, str)):
                        node.body[0] = ast.Pass()
            executable = ast.unparse(tree)
            imports_public = any(
                isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[0] == "reproduce"
                for node in ast.walk(tree)
            )
            if "reproduce.py" in executable or "import reproduce" in executable or imports_public:
                raise ValueError("tests must not call the public reproduction")
    payload = json.dumps(files, sort_keys=True).encode()
    return {"files": dict(files), "tests": tests, "sha256": hashlib.sha256(payload).hexdigest()}


def research_handoff(trace: str | None, limit: int = 18_000) -> str:
    """Extract a bounded, readable tail from a Codex JSONL research trace."""
    if not trace:
        return "No research trace was available."
    interactions = []
    for line in trace.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, ValueError):
            continue
        if event.get("type") != "item.completed":
            continue
        item = event.get("item") or {}
        if item.get("type") == "agent_message":
            text = (item.get("text") or "").strip()
            if text:
                interactions.append("RESEARCHER NOTE:\n" + text[:3_000])
        elif item.get("type") == "command_execution":
            output = (item.get("aggregated_output") or "").strip()
            if output:
                command = (item.get("command") or "").strip()
                interactions.append(
                    "RESEARCH COMMAND: " + command[:1_000] + "\nRESULT:\n" + output[:5_000]
                )
    selected, used = [], 0
    for block in reversed(interactions):
        if selected and used + len(block) > limit:
            continue
        selected.append(block)
        used += len(block)
        if used >= limit:
            break
    return "\n\n".join(reversed(selected)) or "The trace contained no completed research notes."


def assess(pre, post):
    """Preserve pass@pre tests; infrastructure failures never qualify a test."""
    pre_by_name = {r["path"]: r for r in pre["results"]}
    passed, failed, invalid, transitions = [], [], [], {}
    for row in post["results"]:
        name = row["path"]
        before = pre_by_name.get(name, {}).get("status", "missing")
        after = row["status"]
        if before not in {"pass", "assertion"} or after not in {"pass", "assertion"}:
            invalid.append(name)
            transitions[name] = "unusable"
        else:
            (passed if after == "pass" else failed).append(name)
            transitions[name] = {
                ("pass", "pass"): "preserved",
                ("pass", "assertion"): "regression",
                ("assertion", "pass"): "repaired",
                ("assertion", "assertion"): "still_failing",
            }[(before, after)]
    return {"passed": passed, "failed": failed, "invalid": invalid,
            "transitions": transitions, "public_pass": post["public"]["status"] == "pass"}


def improves(best, new):
    """Promote only observable improvement without losing previous passes."""
    if set(new["invalid"]) - set(best["invalid"]):
        return False
    if best["public_pass"] and not new["public_pass"]:
        return False
    if not set(best["passed"]).issubset(new["passed"]):
        return False
    return (set(best["passed"]) < set(new["passed"]) or
            (new["public_pass"] and not best["public_pass"]))


async def worker(agent, environment, action, *, budget=None, **fields):
    state = agent.artifacts["contract"]
    if budget is None:
        budget = 180
    config = {"action": action, "workdir": state["workdir"], **fields}
    path = state["scratch"] + "/request.json"
    await write_remote_text(environment, path, json.dumps(config))
    result = await environment.exec(
        command=f"python3 {shlex.quote(state['runtime'])} {shlex.quote(path)}",
        timeout_sec=int(budget) + 30,
    )
    try:
        response = json.loads((result.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError(f"contract worker failed: {result.stdout} {result.stderr}") from exc
    if result.return_code != 0 or not response["ok"]:
        raise RuntimeError(response.get("error", f"worker exit {result.return_code}"))
    return response["value"]


async def snapshot(agent, environment, label):
    state = agent.artifacts["contract"]
    result = await worker(agent, environment, "snapshot", baseline=state["baseline"],
                          dest=f"{state['scratch']}/{label}.patch")
    # Keep a host copy so a container failure does not destroy the candidate.
    host = agent.logs_dir / "contract" / f"{label}.patch"
    host.parent.mkdir(parents=True, exist_ok=True)
    await environment.download_file(result["path"], host)
    return result


async def evaluate(agent, environment, suite, patch, *, public=True):
    state = agent.artifacts["contract"]
    remaining = agent._deadline - time.monotonic() - agent.finalize_reserve_sec - 30
    if remaining <= 1:
        from selfverify.agent import AgentBudgetExceeded
        raise AgentBudgetExceeded("no evaluation budget remaining")
    budget = min(remaining, (len(suite["tests"]) + int(public)) * agent.verify_timeout_sec + 60)
    return await worker(agent, environment, "evaluate", budget=budget,
                        base=state["base"], scratch=state["scratch"],
                        files=suite["files"], tests=suite["tests"],
                        patch=patch["path"] if patch else None, public=public,
                        budget_seconds=budget, test_timeout_sec=agent.verify_timeout_sec)


async def finalize(agent, environment, logger):
    state = agent.artifacts.get("contract", {})
    selected = state.get("selected")
    if not selected:
        return
    result = await worker(agent, environment, "finalize", baseline=state["baseline"],
                          patch=selected["path"], check_path=state["scratch"] + "/final.patch")
    agent.artifacts["final_patch_guard"] = result
    logger.log("patch_selected", **result, checkpoint=selected["path"])


async def run_contract_loop(agent, instruction, environment, env, logger):
    from selfverify.agent import AgentBudgetExceeded

    workdir = await discover_workdir(environment)
    scratch = "/tmp/selfverify-contract-" + uuid.uuid4().hex
    state = {"workdir": workdir, "scratch": scratch, "base": scratch + "/base",
             "design": scratch + "/design", "runtime": scratch + "/runtime.py",
             "candidates": [], "suite": None}
    agent.artifacts["contract"] = state
    await write_remote_text(environment, state["runtime"],
                            Path(__file__).with_name("contract_runtime.py").read_text())
    prepared = await worker(agent, environment, "prepare", base=state["base"], design=state["design"])
    state.update(prepared)
    # An empty original checkpoint is a valid fallback, even if test design fails.
    state["selected"] = await snapshot(agent, environment, "original")

    suite = None
    if agent.verification_mode == "contract":
        context = getattr(agent, "suite_context", "blind")
        state["suite_context"] = context
        design_hash = prepared["source_sha256"]
        prompt = load_prompt("contract_tests.md")
        if context == "candidate":
            source = Path(agent.initial_patches) / (Path(workdir).name + ".patch")
            donor = scratch + "/donor.patch"
            await write_remote_text(environment, donor, source.read_text())
            state["design"] = scratch + "/design-candidate"
            observed = await worker(agent, environment, "review_prepare", base=state["base"],
                                    patch=donor, dest=state["design"])
            design_hash = observed["source_sha256"]
            prompt = load_prompt("candidate_tests.md")
        focus = getattr(agent, "test_design_focus", "default")
        state["test_design_focus"] = focus
        if focus == "analytic":
            prompt += "\nFocus: use small analytically solvable inputs and independent expected values."
        elif focus == "boundary":
            prompt += "\nFocus: use supported boundary cases, alternative shapes/signs, and preserved behavior."
        logger.log("contract_tests", status="begin", context=context, focus=focus)
        # Keep part of the design budget for a separate materialization turn.
        # Long scientific tasks often spend the entire first turn deriving an
        # oracle and get killed immediately before writing the already-designed
        # test. A fresh, short turn can consume that trace and persist the work
        # without increasing the configured total design budget.
        materialize_budget = min(300, max(1, agent.test_design_timeout_sec // 3))
        research_budget = max(1, agent.test_design_timeout_sec - materialize_budget)
        try:
            await agent._codex_exec(environment, instruction=prompt,
                                    env=env, output_name="codex_contract_tests.txt", stage="contract_tests",
                                    cwd=state["design"], timeout_sec=research_budget)
        except (AgentBudgetExceeded, RuntimeError) as exc:
            logger.log("contract_tests", status="incomplete", error=str(exc))
        raw = await worker(agent, environment, "suite", workdir=state["design"])
        first_error = None
        try:
            if raw["source_sha256"] != design_hash:
                raise ValueError("test-design stage changed its source snapshot")
            suite = freeze_suite(raw["files"])
        except (ValueError, SyntaxError) as exc:
            first_error = str(exc)

        if suite is None and raw["source_sha256"] == design_hash:
            logger.log("contract_tests", status="materialize", error=first_error,
                       budget_seconds=materialize_budget)
            trace = await read_remote_text(environment, "/logs/agent/codex_contract_tests.txt")
            materialize = load_prompt("contract_materialize.md") + (
                "\n\nResearch handoff (already extracted; do not reopen the trace):\n\n"
                + research_handoff(trace)
            )
            try:
                await agent._codex_exec(
                    environment, instruction=materialize, env=env,
                    output_name="codex_contract_materialize.txt",
                    stage="contract_materialize", cwd=state["design"],
                    timeout_sec=materialize_budget,
                )
            except (AgentBudgetExceeded, RuntimeError) as exc:
                logger.log("contract_materialize", status="incomplete", error=str(exc))
            raw = await worker(agent, environment, "suite", workdir=state["design"])
            try:
                if raw["source_sha256"] != design_hash:
                    raise ValueError("test-design stage changed its source snapshot")
                suite = freeze_suite(raw["files"])
            except (ValueError, SyntaxError) as exc:
                first_error = str(exc)

        if suite is None:
            logger.log("contract_tests", status="unusable", error=first_error)
            state["suite_error"] = first_error
        if suite:
            state["suite"] = suite
            host = agent.logs_dir / "contract/frozen_suite"
            host.mkdir(parents=True, exist_ok=True)
            for name, content in suite["files"].items():
                (host / name).write_text(content)
            logger.log("contract_tests", status="frozen", sha256=suite["sha256"], n_tests=len(suite["tests"]))

    # Restore the original candidate worktree even if the design turn wandered
    # outside its disposable directory. Expected values remain frozen on host.
    await finalize(agent, environment, logger)

    # The active candidate is loaded after design. Blind design never receives
    # the patch; candidate-conditioned design has seen a separate copy. Hidden
    # labels and pilot selection metadata remain on the host.
    if agent.initial_patches:
        source = Path(agent.initial_patches) / (Path(workdir).name + ".patch")
        data = source.read_text()
        remote = scratch + "/initial.patch"
        await write_remote_text(environment, remote, data)
        await worker(agent, environment, "apply", patch=remote)
        state["initial_patch_sha256"] = hashlib.sha256(data.encode()).hexdigest()
        logger.log("initial_patch", status="loaded", sha256=state["initial_patch_sha256"])
    else:
        logger.log("draft", status="begin")
        try:
            await agent._codex_exec(environment, instruction=instruction, env=env,
                                    output_name="codex.txt", stage="draft", cwd=workdir,
                                    timeout_sec=agent.draft_timeout_sec)
        except AgentBudgetExceeded as exc:
            logger.log("draft", status="timeout", error=str(exc))
        # A bounded draft may have left a useful partial patch; checkpoint and
        # evaluate it rather than abandoning all remaining repair time.
    current = await snapshot(agent, environment, "candidate_0")
    state["selected"] = current
    agent.artifacts["draft_snapshot"] = current
    logger.log("patch_checkpoint", source_stage="initial", **current)

    if agent.verification_mode == "review":
        from selfverify.review import run_review_loop
        await run_review_loop(agent, environment, env, logger, current)
        return

    if agent.verification_mode == "continue":
        logger.log("continuation", status="begin")
        try:
            await agent._codex_exec(environment,
                instruction="Review and improve the existing candidate repair using the original requirements. "
                "Run the public reproduction and any focused diagnostics you need. Only change source/.",
                env=env, output_name="codex_continuation.txt", stage="continuation", cwd=workdir,
                timeout_sec=agent.repair_timeout_sec)
        except AgentBudgetExceeded as exc:
            logger.log("continuation", status="timeout", error=str(exc))
        state["selected"] = await snapshot(agent, environment, "continuation")
        logger.log("done", reason="continuation_complete")
        return

    if not suite:
        logger.log("done", reason="no_usable_contract_suite", abstained=True)
        return
    pre = await evaluate(agent, environment, suite, None, public=False)
    state["pre"] = pre
    post = await evaluate(agent, environment, suite, current)
    assessment = assess(pre, post)
    state["candidates"].append({"snapshot": current, "evaluation": post, "assessment": assessment})
    state["selected_assessment"] = assessment
    logger.log("contract_verify", round=0, **assessment)
    if agent.max_repair_rounds == 0:
        logger.log("done", reason="verification_only")
        return
    for round_idx in range(1, agent.max_repair_rounds + 1):
        if not assessment["failed"] and assessment["public_pass"]:
            logger.log("done", reason="checks_passed" if not assessment["invalid"] else "partial_coverage",
                       abstained=bool(assessment["invalid"]))
            return
        if not assessment["passed"] and not assessment["failed"]:
            logger.log("done", reason="no_semantic_checks", abstained=True)
            return
        evidence = {"assessment": assessment, "results": post,
                    "suite_sha256": suite["sha256"], "requirements": suite["tests"]}
        logger.log("contract_repair", round=round_idx, status="begin")
        try:
            await agent._codex_exec(environment,
                instruction=load_prompt("contract_repair.md") + "\n\nEvidence:\n" + json.dumps(evidence, indent=2),
                env=env, output_name=f"codex_contract_repair_r{round_idx}.txt", stage="contract_repair",
                cwd=workdir, timeout_sec=agent.repair_timeout_sec,
                reserve_sec=(len(suite["tests"]) + 1) * agent.verify_timeout_sec + 90)
        except AgentBudgetExceeded as exc:
            logger.log("contract_repair", round=round_idx, status="timeout", error=str(exc))
        agent.artifacts["revisions"] += 1
        candidate = await snapshot(agent, environment, f"candidate_{round_idx}")
        post = await evaluate(agent, environment, suite, candidate)
        assessment = assess(pre, post)
        accepted = improves(state["selected_assessment"], assessment)
        state["candidates"].append({"snapshot": candidate, "evaluation": post,
                                    "assessment": assessment, "promoted": accepted})
        if accepted:
            state["selected"] = candidate
            state["selected_assessment"] = assessment
        logger.log("contract_verify", round=round_idx, promoted=accepted, **assessment)
        if not accepted:
            # Avoid repeatedly mutating a rejected candidate.
            await finalize(agent, environment, logger)
            logger.log("done", reason="no_verified_improvement")
            return
    logger.log("done", reason="repair_rounds_exhausted")
