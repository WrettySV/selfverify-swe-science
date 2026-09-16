#!/usr/bin/env python3
"""Compare baseline vs self-verify: Pass@1 and tokens (cost-normalized)."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _task_id_from_dirname(name: str) -> str | None:
    # task_033__AbCdEfG
    if not name.startswith("task_"):
        return None
    body = name[len("task_") :]
    task_id = body.split("__", 1)[0]
    return task_id or None


def _reward(trial_dir: Path) -> float | None:
    payload = _load_json(trial_dir / "verifier" / "reward.json")
    if not payload:
        return None
    for key in ("reward", "score", "pass"):
        if key in payload:
            try:
                return float(payload[key])
            except (TypeError, ValueError):
                pass
    return None


def _tokens(trial_dir: Path) -> tuple[int | None, int | None, int | None]:
    """Return (prompt, completion, total) best-effort from result/trajectory."""
    result = _load_json(trial_dir / "result.json") or {}
    agent = result.get("agent") if isinstance(result.get("agent"), dict) else {}
    metrics = agent.get("metrics") if isinstance(agent.get("metrics"), dict) else {}

    prompt = metrics.get("prompt_tokens") or metrics.get("total_prompt_tokens")
    completion = metrics.get("completion_tokens") or metrics.get(
        "total_completion_tokens"
    )
    total = metrics.get("total_tokens")

    traj = _load_json(trial_dir / "agent" / "trajectory.json") or {}
    final_metrics = traj.get("final_metrics") if isinstance(traj, dict) else None
    if isinstance(final_metrics, dict):
        prompt = prompt or final_metrics.get("total_prompt_tokens")
        completion = completion or final_metrics.get("total_completion_tokens")
        extra = final_metrics.get("extra") if isinstance(final_metrics.get("extra"), dict) else {}
        total = total or extra.get("total_tokens")

    def _as_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    prompt_i, completion_i, total_i = _as_int(prompt), _as_int(completion), _as_int(total)
    if total_i is None and prompt_i is not None and completion_i is not None:
        total_i = prompt_i + completion_i
    return prompt_i, completion_i, total_i


def collect_job(job_dir: Path) -> dict[str, Any]:
    per_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trial_dir in sorted(job_dir.iterdir()):
        if not trial_dir.is_dir():
            continue
        task_id = _task_id_from_dirname(trial_dir.name)
        if not task_id:
            continue
        reward = _reward(trial_dir)
        prompt, completion, total = _tokens(trial_dir)
        per_task[task_id].append(
            {
                "trial": trial_dir.name,
                "reward": reward,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
                "passed": reward is not None and reward >= 1.0,
            }
        )

    task_rows: list[dict[str, Any]] = []
    for task_id, trials in sorted(per_task.items()):
        n = len(trials)
        n_pass = sum(1 for item in trials if item["passed"])
        pass_at_1 = n_pass / n if n else 0.0
        # Pass@k with k=n_attempts (any trial passes).
        pass_at_k = 1.0 if n_pass else 0.0
        tokens = [item["total_tokens"] for item in trials if item["total_tokens"] is not None]
        task_rows.append(
            {
                "task_id": task_id,
                "n_trials": n,
                "n_pass": n_pass,
                "pass_at_1": pass_at_1,
                "pass_at_k": pass_at_k,
                "mean_total_tokens": (sum(tokens) / len(tokens)) if tokens else None,
                "sum_total_tokens": sum(tokens) if tokens else None,
                "trials": trials,
            }
        )

    n_tasks = len(task_rows)
    mean_pass = (
        sum(row["pass_at_1"] for row in task_rows) / n_tasks if n_tasks else 0.0
    )
    total_tokens = sum(row["sum_total_tokens"] or 0 for row in task_rows)
    n_solves = sum(row["n_pass"] for row in task_rows)
    tokens_per_solve = (total_tokens / n_solves) if n_solves else None

    return {
        "job_dir": str(job_dir),
        "n_tasks": n_tasks,
        "mean_pass_at_1": mean_pass,
        "total_tokens": total_tokens,
        "n_solves": n_solves,
        "tokens_per_solve": tokens_per_solve,
        "tasks": task_rows,
    }


def wilcoxon_signed_rank(diffs: list[float]) -> float | None:
    """Two-sided Wilcoxon signed-rank p-value (exact for n<=20, no SciPy)."""
    nonzero = [d for d in diffs if d != 0]
    n = len(nonzero)
    if n < 1:
        return None
    ranked = sorted(range(n), key=lambda i: abs(nonzero[i]))
    ranks = [0.0] * n
    # Average ranks for ties in absolute value.
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(nonzero[ranked[j + 1]]) == abs(nonzero[ranked[i]]):
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[ranked[k]] = avg
        i = j + 1
    w_pos = sum(ranks[i] for i in range(n) if nonzero[i] > 0)
    w_neg = sum(ranks[i] for i in range(n) if nonzero[i] < 0)
    w = min(w_pos, w_neg)
    # Normal approximation with continuity correction.
    mean = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0
    if var <= 0:
        return None
    z = (w - mean + 0.5) / math.sqrt(var)
    # two-sided from normal CDF via erfc
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return float(p)


def compare(baseline: dict[str, Any], selfverify: dict[str, Any]) -> dict[str, Any]:
    b_map = {row["task_id"]: row for row in baseline["tasks"]}
    s_map = {row["task_id"]: row for row in selfverify["tasks"]}
    common = sorted(set(b_map) & set(s_map))
    diffs = [s_map[t]["pass_at_1"] - b_map[t]["pass_at_1"] for t in common]
    table = {
        "baseline": {
            "Pass@1": baseline["mean_pass_at_1"],
            "Total tokens": baseline["total_tokens"],
            "Tokens per solve": baseline["tokens_per_solve"],
        },
        "selfverify": {
            "Pass@1": selfverify["mean_pass_at_1"],
            "Total tokens": selfverify["total_tokens"],
            "Tokens per solve": selfverify["tokens_per_solve"],
        },
        "delta_pass_at_1": selfverify["mean_pass_at_1"] - baseline["mean_pass_at_1"],
        "token_ratio": (
            (selfverify["total_tokens"] / baseline["total_tokens"])
            if baseline["total_tokens"]
            else None
        ),
        "wilcoxon_p": wilcoxon_signed_rank(diffs) if common else None,
        "n_paired_tasks": len(common),
        "per_task": [
            {
                "task_id": task_id,
                "baseline_pass_at_1": b_map[task_id]["pass_at_1"],
                "selfverify_pass_at_1": s_map[task_id]["pass_at_1"],
                "delta": s_map[task_id]["pass_at_1"] - b_map[task_id]["pass_at_1"],
            }
            for task_id in common
        ],
    }
    return table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline job dir")
    parser.add_argument(
        "--selfverify", type=Path, required=True, help="Self-verify job dir"
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    baseline = collect_job(args.baseline.resolve())
    selfverify = collect_job(args.selfverify.resolve())
    report = {
        "baseline": baseline,
        "selfverify": selfverify,
        "compare": compare(baseline, selfverify),
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)

    c = report["compare"]
    print("=== Cost-normalized summary ===")
    print(
        f"{'Condition':<12} {'Pass@1':>8} {'Total tokens':>14} {'Tokens/solve':>14}"
    )
    for name in ("baseline", "selfverify"):
        row = c[name]
        tps = row["Tokens per solve"]
        tps_s = f"{tps:.1f}" if isinstance(tps, (int, float)) else "n/a"
        print(
            f"{name:<12} {row['Pass@1']:>8.3f} {row['Total tokens']:>14} {tps_s:>14}"
        )
    if c.get("wilcoxon_p") is not None:
        print(f"Wilcoxon signed-rank p (paired Pass@1): {c['wilcoxon_p']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
