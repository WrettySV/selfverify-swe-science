#!/usr/bin/env python3
"""CPU-only, retrospective selection audit; never runs a model or a test suite.

Select using observable execution results, then join hidden rewards for scoring.
This is NOT a matched-budget experiment. The input pool has mixed provenance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean


METHODS = (
    "random", "public_random", "first_public", "cross_vote",
    "cross_baseline_split", "cross_baseline_split_assertion_only",
    "vote_including_self",
)


def observations(cells: list[dict]) -> list[dict]:
    """Allowlist the selector's input: no reward, job name, or label metadata."""
    return [
        {
            "suite": c["suite_trial"], "candidate": c["cand_trial"],
            "self": bool(c.get("self")) or c["suite_trial"] == c["cand_trial"],
            "applied": c.get("applied"), "public_pass": c.get("public_rc") == 0,
            "results": [
                {"passed": bool(r["passed"]), "failure_class": r.get("failure_class")}
                for r in c.get("results") or []
            ],
        }
        for c in cells
    ]


def verdict(row: dict, assertion_only: bool = False) -> str:
    if row["applied"] == "failed" or not row["results"]:
        return "unknown"
    failures = [r for r in row["results"] if not r["passed"]]
    if not failures:
        return "accept"
    if assertion_only and any(r["failure_class"] != "assertion" for r in failures):
        return "unknown"
    return "reject"


def choose(rows: list[dict], method: str) -> dict:
    """Return a distribution (uniform over picked IDs), without ground truth.

    Candidate order is the matrix's first-occurrence order, NOT a quality rank.
    Unknown cells cast no vote. No usable votes means uniform public fallback.
    """
    if method not in METHODS:
        raise ValueError(method)
    public = {}
    for row in rows:
        candidate = row["candidate"]
        if candidate != "BASELINE":
            public[candidate] = public.get(candidate, False) or row["public_pass"]
    ordered = list(public)
    pool = [c for c in ordered if public[c]] or ordered
    if not ordered:
        raise ValueError("Task has no candidate patches")
    if method in ("random", "public_random", "first_public"):
        picked = ordered if method == "random" else pool
        if method == "first_public":
            picked = picked[:1]
        return {"picked": picked, "decision": method}

    strict = method == "cross_baseline_split_assertion_only"
    include_self = method == "vote_including_self"
    baseline = {}
    foreign = {}
    for row in rows:
        suite = row["suite"]
        result = verdict(row, strict)
        if row["candidate"] == "BASELINE":
            baseline.setdefault(suite, []).append(result)
        elif not row["self"]:
            foreign.setdefault(suite, []).append(result)
    gated = method.startswith("cross_baseline_split")
    eligible_suites = {
        suite for suite, results in foreign.items()
        if not gated or (
            baseline.get(suite) and all(v == "reject" for v in baseline[suite])
            and "accept" in results and "reject" in results
        )
    }
    votes = {c: [] for c in pool}
    for row in rows:
        if row["candidate"] not in votes or row["suite"] not in eligible_suites:
            continue
        if row["self"] and not include_self:
            continue
        result = verdict(row, strict)
        if result != "unknown":
            votes[row["candidate"]].append(int(result == "accept"))
    scores = {c: mean(v) for c, v in votes.items() if v}
    if scores:
        best = max(scores.values())
        picked = [c for c, score in scores.items() if score == best]
    else:
        picked = pool
    return {
        "picked": picked, "decision": "vote" if scores else "public_random_fallback",
        "eligible_suites": sorted(eligible_suites), "scores": scores,
        "vote_counts": {c: len(v) for c, v in votes.items()},
    }


def audit(matrix: dict) -> dict:
    per_task = {}
    stats = Counter()
    failure_classes = Counter()
    for task, keyed_cells in sorted(matrix.items()):
        cells = list(keyed_cells.values())
        rows = observations(cells)
        # Freeze every decision BEFORE reading any rewards.
        decisions = {method: choose(rows, method) for method in METHODS}
        rewards = {}
        for cell, row in zip(cells, rows):
            stats["cells"] += 1
            for result in row["results"]:
                if not result["passed"]:
                    failure_classes[result["failure_class"]] += 1
            candidate = cell["cand_trial"]
            if candidate == "BASELINE":
                continue
            reward = cell.get("cand_reward")
            if reward not in (0, 1):
                raise ValueError(f"Missing/bad reward: {task}/{candidate}")
            if candidate in rewards and rewards[candidate] != reward:
                raise ValueError(f"Conflicting rewards: {task}/{candidate}")
            rewards[candidate] = reward
            group = "self" if row["self"] else "foreign"
            truth = "correct" if reward else "incorrect"
            stats[f"{group}_{truth}_total"] += 1
            if verdict(row) == "accept":
                stats[f"{group}_{truth}_accepted"] += 1
        for decision in decisions.values():
            decision["expected_reward"] = mean(rewards[c] for c in decision["picked"])
            decision["n_tied"] = len(decision["picked"])
        per_task[task] = {
            "n_candidates": len(rewards), "n_correct": sum(rewards.values()),
            "n_suites": len({r["suite"] for r in rows}),
            "oracle_pool_ceiling": max(rewards.values()), "methods": decisions,
        }
    if not per_task:
        raise ValueError("Empty matrix")
    return {
        "interpretation": "Retrospective; heterogeneous pool; NOT matched inference budget",
        "tie_policy": "Uniform over picked IDs; scores are expectations, not realised solves",
        "fallback_policy": "Uniform public-passing candidate, or uniform all if none pass",
        "error_policies": {
            "cross_vote": "Every nonzero test result rejects; failed apply/empty suite unknown",
            "assertion_only": "Any non-assertion failure makes the entire suite unknown",
            "caution": "Runtime exceptions can expose the real bug; strict policy is a sensitivity analysis",
        },
        "n_tasks": len(per_task),
        "n_candidates": sum(t["n_candidates"] for t in per_task.values()),
        "n_suites": sum(t["n_suites"] for t in per_task.values()),
        "macro_expected_reward": {
            method: mean(t["methods"][method]["expected_reward"] for t in per_task.values())
            for method in METHODS
        },
        "oracle_pool_ceiling": mean(t["oracle_pool_ceiling"] for t in per_task.values()),
        "execution_counts": dict(stats), "failure_classes": dict(failure_classes),
        "per_task": per_task,
    }


def render(result: dict) -> str:
    lines = [
        "# Retrospective cross-candidate audit", "",
        "No model calls or test re-execution. Selection reads an allowlist of observations; "
        "recorded hidden rewards are joined only after decisions are frozen.", "",
        f"Tasks: {result['n_tasks']}; candidates: {result['n_candidates']}; "
        f"suites: {result['n_suites']}; cells: {result['execution_counts']['cells']}.", "",
        "| Policy | Task-macro expected reward |", "|---|---:|",
    ]
    for method, value in result["macro_expected_reward"].items():
        lines.append(f"| {method} | {value:.2%} |")
    lines += [f"| oracle pool ceiling (uses hidden labels) | {result['oracle_pool_ceiling']:.2%} |", "",
        "| Task | Correct / candidates | Public random | First public | Cross vote | Strict sensitivity |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for task, row in result["per_task"].items():
        values = [row["methods"][m]["expected_reward"] for m in
                  ("public_random", "first_public", "cross_vote", "cross_baseline_split_assertion_only")]
        lines.append(f"| {task} | {row['n_correct']} / {row['n_candidates']} | " +
                     " | ".join(f"{v:.2%}" for v in values) + " |")
    lines += ["",
        "Ties use uniform expected reward, not a realised selected patch. First-public follows "
        "matrix insertion order; it is an order sensitivity baseline. Unknown cells do not vote.", "",
        "The strict policy makes a whole suite unknown if any failing test is not classified "
        "as an assertion. This is not automatically a better validity rule: task 007 includes "
        "TypeErrors inside project source which may be the real defect. The optimistic and "
        "strict policies agree on every task except 007.", "",
        "This pool combines historical pipelines, versions, and budgets. Trials are not necessarily "
        "independent or distinct source patches. Donor suites may have been adapted to donor patches. "
        "The eight tasks are development data already inspected; these are exploratory results. "
        "Cells and suites are correlated, not 280 independent evaluation examples.", "",
        "The legacy select.json calibrates each suite using hidden rewards of other candidates of "
        "the SAME task. Its score is diagnostic rather than a deployable test-task policy. "
        "Here the same headline value can be obtained without that calibration, using cross_vote. "
        "This post-hoc reproduction does not establish a held-out improvement.", "",
        f"Input matrix SHA256: `{result['matrix_sha256']}`.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=root / "analysis/crosscheck/matrix.json")
    parser.add_argument("--out", type=Path, default=root / "analysis/crosscheck/label_free_audit.json")
    args = parser.parse_args()
    raw = args.matrix.read_bytes()
    result = audit(json.loads(raw))
    result["matrix_path"] = str(args.matrix.resolve())
    result["matrix_sha256"] = sha256(raw).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    args.out.with_suffix(".md").write_text(render(result))
    print(json.dumps({"output": str(args.out), "macro_expected_reward": result["macro_expected_reward"],
                      "oracle_pool_ceiling": result["oracle_pool_ceiling"]}, indent=2))


if __name__ == "__main__":
    main()
