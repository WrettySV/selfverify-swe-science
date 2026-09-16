"""Patch-aware review, optional counterexamples, and checked repair selection."""
from __future__ import annotations

import json
from pathlib import Path

from selfverify.contract import evaluate, finalize, freeze_suite, snapshot, worker
from selfverify.stages import load_prompt, write_remote_text


EMPTY_SUITE = {"files": {}, "tests": []}


def validate_review(report):
    requirements = report.get("requirements", [])
    if not isinstance(requirements, list) or not 1 <= len(requirements) <= 12:
        raise ValueError("review requires 1-12 explicit requirements")
    ids = set()
    for row in requirements:
        for key in ("id", "requirement", "basis", "evidence"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"requirement missing {key}")
        if row["id"] in ids or row.get("status") not in {"satisfied", "violated", "uncertain"}:
            raise ValueError("invalid requirement id or status")
        ids.add(row["id"])
    findings = report.get("findings", [])
    if not isinstance(findings, list) or len(findings) > 3:
        raise ValueError("review permits at most three findings")
    seen = set()
    for row in findings:
        for key in ("id", "requirement_id", "claim", "basis", "evidence", "suggested_change"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"finding missing {key}")
        if row["id"] in seen or row["requirement_id"] not in ids:
            raise ValueError("invalid finding id or requirement reference")
        seen.add(row["id"])
        if row.get("evidence_type") not in {"code", "experiment"}:
            raise ValueError("finding evidence_type must be code or experiment")
        if row["evidence_type"] == "experiment" and not isinstance(row.get("probe"), str):
            raise ValueError("experimental finding requires a probe filename")
    return report


def validate_recheck(report, findings):
    rows = report.get("findings", [])
    expected = {row["id"] for row in findings}
    if len(rows) != len(expected) or {row.get("id") for row in rows} != expected:
        raise ValueError("recheck must account for every original finding exactly once")
    for row in rows:
        if row.get("status") not in {"resolved", "unresolved", "uncertain"}:
            raise ValueError("invalid recheck status")
        if not isinstance(row.get("evidence"), str) or not row["evidence"].strip():
            raise ValueError("recheck must cite evidence")
    return report


def actionable_findings(report, probes):
    statuses = {row["path"]: row["status"] for row in probes["results"]}
    actionable, rejected = [], []
    for finding in report["findings"]:
        if finding["evidence_type"] == "experiment" and statuses.get(finding.get("probe")) != "assertion":
            rejected.append({"id": finding["id"], "reason": "counterexample did not reproduce an assertion failure"})
        else:
            # A code finding is a reviewer's claim, not an independently proven fact.
            actionable.append(finding)
    return actionable, rejected


def selection_decision(before_guard, after_guard, before_probes, after_probes, recheck):
    """Require resolved review findings and preserve all observed passing checks."""
    reasons = []
    if before_guard["public"]["status"] == "pass" and after_guard["public"]["status"] != "pass":
        reasons.append("public reproduction regressed")
    if after_guard["public"]["status"] != "pass":
        reasons.append("public reproduction is not passing")
    for label, before, after in (("regression", before_guard, after_guard),
                                 ("probe", before_probes, after_probes)):
        earlier = {row["path"]: row["status"] for row in before["results"]}
        later = {row["path"]: row["status"] for row in after["results"]}
        for name, status in earlier.items():
            new = later.get(name, "missing")
            if status == "pass" and new != "pass":
                reasons.append(f"{label} lost pass: {name}")
            if status in {"pass", "assertion"} and new not in {"pass", "assertion"}:
                reasons.append(f"{label} became unusable: {name}")
            if label == "probe" and status == "assertion" and new != "pass":
                reasons.append(f"counterexample remains: {name}")
    if not recheck or not recheck.get("findings"):
        reasons.append("missing completed review recheck")
    elif any(row["status"] != "resolved" for row in recheck["findings"]):
        reasons.append("review findings remain unresolved or uncertain")
    return {"accepted": not reasons, "reasons": reasons,
            "selection_basis": "review judgment plus executable regression checks; not a proof of correctness"}


def load_guard_suite(agent, task):
    if not agent.regression_suites:
        return EMPTY_SUITE
    root = Path(agent.regression_suites) / task
    files = {p.name: p.read_text() for p in root.iterdir()
             if p.is_file() and (p.suffix == ".py" or p.name == "manifest.json")}
    return freeze_suite(files)


async def inspect_candidate(agent, environment, env, logger, candidate, stage, prompt, timeout):
    from selfverify.agent import AgentBudgetExceeded
    state = agent.artifacts["contract"]
    dest = f"{state['scratch']}/{stage}"
    prepared = await worker(agent, environment, "review_prepare", base=state["base"],
                            patch=candidate["path"], dest=dest)
    logger.log(stage, status="begin", candidate_sha256=candidate["sha256"])
    completion = state["review"].setdefault("stage_completion", {})
    completion[stage] = False
    try:
        await agent._codex_exec(environment, instruction=prompt, env=env, stage=stage,
                                output_name=f"codex_{stage}.txt", cwd=dest, timeout_sec=timeout)
        completion[stage] = True
    except (AgentBudgetExceeded, RuntimeError) as exc:
        logger.log(stage, status="incomplete", error=str(exc))
    raw = await worker(agent, environment, "review_collect", workdir=dest)
    host = agent.logs_dir / "review" / stage
    host.mkdir(parents=True, exist_ok=True)
    (host / "report.raw.json").write_text(raw["report"] or "")
    # Preserve even invalid/partial probes, so a failed phase does not waste them.
    for name, code in raw["suite"]["files"].items():
        (host / name).write_text(code)
    if raw["source_sha256"] != prepared["source_sha256"]:
        raise ValueError("review changed source instead of inspecting the candidate")
    report = json.loads(raw["report"] or "null")
    if not isinstance(report, dict):
        raise ValueError("review did not save a JSON object")
    logger.log(stage, status="collected")
    return report, raw["suite"]["files"]


async def run_review_loop(agent, environment, env, logger, current):
    from selfverify.agent import AgentBudgetExceeded
    state = agent.artifacts["contract"]
    review = {"initial_patch_sha256": current["sha256"], "repair_turns": 0}
    state["review"] = review
    guards = load_guard_suite(agent, Path(state["workdir"]).name)
    review["guard_suite"] = guards
    before_guard = await evaluate(agent, environment, guards, current)
    review["guard_before"] = before_guard
    try:
        report, files = await inspect_candidate(
            agent, environment, env, logger, current, "review_audit",
            load_prompt("review_audit.md"), agent.review_timeout_sec)
        report = validate_review(report)
    except (ValueError, SyntaxError, TypeError) as exc:
        review["stop_reason"] = "unusable_review"
        review["error"] = str(exc)
        logger.log("done", reason="unusable_review", error=str(exc))
        return
    review["audit"] = report
    probes = EMPTY_SUITE
    if files:
        try:
            probes = freeze_suite(files)
        except (ValueError, SyntaxError, TypeError) as exc:
            review["probe_error"] = str(exc)
    review["probe_suite"] = probes
    before_probes = await evaluate(agent, environment, probes, current, public=False)
    review["probes_before"] = before_probes
    findings, rejected = actionable_findings(report, before_probes)
    review["actionable_findings"] = findings
    review["rejected_findings"] = rejected
    # Reviewer work happens on a copy; restore the selected checkpoint in case
    # its commands accidentally wandered outside that directory.
    await finalize(agent, environment, logger)
    if not findings:
        complete = review.get("stage_completion", {}).get("review_audit", False)
        covered = all(row["status"] == "satisfied" for row in report["requirements"])
        review["stop_reason"] = "clean_review" if complete and covered else "inconclusive_review"
        logger.log("done", reason=review["stop_reason"])
        return

    evidence = {"findings": findings, "probe_results": before_probes,
                "existing_checks": before_guard, "frozen_probes": probes["files"]}
    for name, code in probes["files"].items():
        await write_remote_text(environment, f"{state['workdir']}/selfverify/invariants/{name}", code)
    logger.log("review_repair", status="begin", n_findings=len(findings))
    review["repair_turns"] += 1
    agent.artifacts["revisions"] += 1
    try:
        await agent._codex_exec(
            environment, instruction=load_prompt("review_repair.md") + "\n\nEvidence:\n" + json.dumps(evidence),
            env=env, output_name="codex_review_repair.txt", stage="review_repair", cwd=state["workdir"],
            timeout_sec=agent.repair_timeout_sec,
            reserve_sec=agent.review_recheck_timeout_sec +
                (len(guards["tests"]) + len(probes["tests"]) + 1) * agent.verify_timeout_sec + 60)
    except (AgentBudgetExceeded, RuntimeError) as exc:
        logger.log("review_repair", status="incomplete", error=str(exc))
    candidate = await snapshot(agent, environment, "review_candidate")
    review["candidate"] = candidate
    if candidate["sha256"] == current["sha256"]:
        review["stop_reason"] = "unchanged_patch"
        logger.log("done", reason="unchanged_patch")
        return
    after_guard = await evaluate(agent, environment, guards, candidate)
    after_probes = await evaluate(agent, environment, probes, candidate, public=False)
    review["guard_after"] = after_guard
    review["probes_after"] = after_probes
    recheck = None
    try:
        result, _ = await inspect_candidate(
            agent, environment, env, logger, candidate, "review_recheck",
            load_prompt("review_recheck.md") + "\n\nOriginal review findings:\n" + json.dumps(findings),
            agent.review_recheck_timeout_sec)
        recheck = validate_recheck(result, findings)
    except (ValueError, SyntaxError, TypeError) as exc:
        review["recheck_error"] = str(exc)
    review["recheck"] = recheck
    decision = selection_decision(before_guard, after_guard, before_probes, after_probes, recheck)
    review["decision"] = decision
    if decision["accepted"]:
        state["selected"] = candidate
    review["stop_reason"] = "review_complete"
    logger.log("done", reason="review_complete", **decision)
