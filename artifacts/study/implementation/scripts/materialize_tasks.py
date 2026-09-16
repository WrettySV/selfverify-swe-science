#!/usr/bin/env python3
"""Materialize an explicit task selection via SWE-bench Science tools."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def default_swe_science_root() -> Path:
    env = os.environ.get("SWE_SCIENCE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    candidates = [
        Path("/home/lukina/SWE-bench-Science/huggingface"),
        Path("/home/lukina/SWE-bench-Science"),
    ]
    for path in candidates:
        if (path / "scripts" / "materialize.py").is_file():
            return path
    raise SystemExit(
        "Could not find SWE-bench Science release. Set SWE_SCIENCE_ROOT to the "
        "directory that contains scripts/materialize.py"
    )


def load_selection(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    task_ids = [str(item) for item in payload.get("task_ids", [])]
    if not task_ids:
        raise SystemExit(f"no task_ids in {path}")
    return task_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path("selections/main-12.json"),
        help="JSON selection file (default: selections/main-12.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("work/tasks-12"),
        help="Materialized task directory",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--swe-science-root",
        type=Path,
        default=None,
        help="Override SWE_SCIENCE_ROOT",
    )
    args = parser.parse_args()

    root = (args.swe_science_root or default_swe_science_root()).resolve()
    script = root / "scripts" / "materialize.py"
    if not script.is_file():
        raise SystemExit(f"materialize.py not found under {root}")

    task_ids = load_selection(args.selection.resolve())
    cmd = [
        sys.executable,
        str(script),
        "--output",
        str(args.output.resolve()),
        "--task-id",
        ",".join(task_ids),
    ]
    if args.force:
        cmd.append("--force")
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
