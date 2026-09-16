from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


def _load_summary(job_dir: Path) -> list[dict]:
    csv_path = job_dir / "summary.csv"
    if csv_path.is_file():
        with csv_path.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    # Fallback: scan reward.json
    rows = []
    for reward in job_dir.glob("*/verifier/reward.json"):
        data = json.loads(reward.read_text(encoding="utf-8"))
        task = reward.parent.parent.name.split("__", 1)[0].removeprefix("task_")
        rows.append(
            {
                "task_id": task,
                "reward": data.get("reward", ""),
                "public_passed": (data.get("public") or {}).get("passed", ""),
                "private_passed": (data.get("private") or {}).get("passed", ""),
                "private_collected": (data.get("private") or {}).get("collected", ""),
            }
        )
    return rows


def _pass_rate(rows: list[dict]) -> float | None:
    vals = []
    for row in rows:
        try:
            vals.append(float(row.get("reward", "")))
        except (TypeError, ValueError):
            continue
    if not vals:
        return None
    return sum(vals) / len(vals)


def _scientist_tokens(job_dir: Path) -> dict[str, float]:
    total_prompt = total_completion = 0.0
    n = 0
    for path in (job_dir / "scientist").glob("*/scientist_usage.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("prompt_tokens") is not None:
            total_prompt += float(data["prompt_tokens"])
            total_completion += float(data.get("completion_tokens") or 0)
            n += 1
    return {
        "scientist_tasks": n,
        "scientist_prompt_tokens": total_prompt,
        "scientist_completion_tokens": total_completion,
    }


def compare_jobs(job_dirs: list[Path]) -> str:
    lines = ["# Comparison", ""]
    lines.append("| job | n | Pass@1 (mean reward) | scientist prompt tok | scientist completion tok |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")

    by_task: dict[str, dict[str, str]] = defaultdict(dict)

    for job_dir in job_dirs:
        rows = _load_summary(job_dir)
        rate = _pass_rate(rows)
        sci = _scientist_tokens(job_dir)
        rate_s = f"{rate:.3f}" if rate is not None else "n/a"
        lines.append(
            f"| `{job_dir.name}` | {len(rows)} | {rate_s} | "
            f"{int(sci['scientist_prompt_tokens'])} | {int(sci['scientist_completion_tokens'])} |"
        )
        for row in rows:
            tid = str(row.get("task_id") or "").removeprefix("task_")
            if tid:
                by_task[tid][job_dir.name] = str(row.get("reward", ""))

    lines.extend(["", "## Per-task reward", ""])
    job_names = [p.name for p in job_dirs]
    header = "| task_id | " + " | ".join(job_names) + " |"
    sep = "| --- | " + " | ".join(["---"] * len(job_names)) + " |"
    lines.extend([header, sep])
    for tid in sorted(by_task):
        cells = [by_task[tid].get(name, "") for name in job_names]
        lines.append("| " + tid + " | " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Pass@1 proxy = mean binary `reward` from the release grader",
            "  (public AND private all pass).",
            "- Engineer/single-agent tokens depend on Pier logs; fill manually if missing.",
            "- Interpret SE vs B1 before claiming multi-agent benefit.",
            "",
        ]
    )
    return "\n".join(lines)
