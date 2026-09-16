from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _task_id_from_trial_name(name: str) -> str | None:
    # trial names look like task_004__AbCdEfG
    if not name.startswith("task_"):
        return None
    body = name.removeprefix("task_")
    if "__" not in body:
        return None
    return body.split("__", 1)[0]


def load_reward(trial_dir: Path) -> dict[str, Any] | None:
    for rel in ("verifier/reward.json", "reward.json"):
        path = trial_dir / rel
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
    return None


def public_passed(reward: dict[str, Any] | None) -> bool | None:
    if not reward:
        return None
    public = reward.get("public") or {}
    if "passed" in public and "collected" in public:
        try:
            return int(public["passed"]) >= int(public["collected"]) and int(
                public["collected"]
            ) > 0
        except (TypeError, ValueError):
            return None
    if "public_reproduction_passed" in reward:
        return bool(reward["public_reproduction_passed"])
    return None


def collect_public_feedback(trial_dir: Path, *, max_chars: int = 6000) -> str:
    parts: list[str] = [f"trial: {trial_dir.name}"]
    reward = load_reward(trial_dir)
    if reward is not None:
        parts.append("## reward.json")
        parts.append(json.dumps(reward, indent=2))

    for rel in (
        "verifier/test-stdout.txt",
        "verifier/run.log",
        "agent/codex.txt",
        "exception.txt",
    ):
        path = trial_dir / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Prefer the public section when present.
        if "== public ==" in text and "== private ==" in text:
            text = text.split("== private ==", 1)[0]
        text = text.strip()
        if not text:
            continue
        parts.append(f"## {rel}")
        parts.append(text[: max_chars // 2])
        if len("\n".join(parts)) >= max_chars:
            break

    out = "\n".join(parts)
    return out[:max_chars]


def latest_trials_by_task(job_dir: Path) -> dict[str, Path]:
    """Map task_id -> newest trial directory (by mtime)."""
    latest: dict[str, Path] = {}
    mtimes: dict[str, float] = {}
    for child in job_dir.iterdir():
        if not child.is_dir() or not child.name.startswith("task_"):
            continue
        task_id = _task_id_from_trial_name(child.name)
        if task_id is None:
            continue
        mtime = child.stat().st_mtime
        if task_id not in latest or mtime > mtimes[task_id]:
            latest[task_id] = child
            mtimes[task_id] = mtime
    return latest


def tasks_needing_revise(job_dir: Path) -> dict[str, Path]:
    """Return task_id -> trial_dir for tasks whose latest public reproduce failed."""
    need: dict[str, Path] = {}
    for task_id, trial in latest_trials_by_task(job_dir).items():
        passed = public_passed(load_reward(trial))
        if passed is False:
            need[task_id] = trial
        elif passed is None:
            # No reward yet / crashed: still revise if exception exists.
            if (trial / "exception.txt").is_file():
                need[task_id] = trial
    return need
