"""Structured JSONL logging under the task workdir."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunLogger:
    def __init__(self, workdir: Path) -> None:
        self.path = workdir / "selfverify" / "run_log.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.saw_done = False

    def log(self, stage: str, **fields: Any) -> None:
        if stage == "done":
            self.saw_done = True
        record = {"timestamp": utc_now(), "stage": stage, **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
