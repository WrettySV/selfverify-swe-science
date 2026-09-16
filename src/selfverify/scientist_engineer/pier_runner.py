from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from . import swe_science_root


def run_batch(
    *,
    tasks_path: Path,
    agent: str,
    jobs_dir: Path,
    job_name: str,
    env_file: Path | None = None,
    n_concurrent: int = 1,
    n_attempts: int = 1,
    model: list[str] | None = None,
    extra_args: list[str] | None = None,
) -> int:
    script = swe_science_root() / "scripts" / "run_batch.py"
    if not script.is_file():
        raise FileNotFoundError(script)

    cmd = [
        sys.executable,
        str(script),
        "--path",
        str(tasks_path),
        "--agent",
        agent,
        "--jobs-dir",
        str(jobs_dir),
        "--job-name",
        job_name,
        "--n-concurrent",
        str(n_concurrent),
        "--n-attempts",
        str(n_attempts),
    ]
    if env_file is not None:
        cmd.extend(["--env-file", str(env_file)])
    if model:
        for item in model:
            cmd.extend(["--model", item])
    if extra_args:
        cmd.extend(extra_args)

    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def materialize(
    *,
    task_ids: list[str],
    output: Path,
    force: bool = False,
) -> dict:
    script = swe_science_root() / "scripts" / "materialize.py"
    cmd = [
        sys.executable,
        str(script),
        "--output",
        str(output),
        "--task-id",
        ",".join(task_ids),
    ]
    if force:
        cmd.append("--force")
    print("+", " ".join(cmd), flush=True)
    code = subprocess.call(cmd)
    if code != 0:
        raise RuntimeError(f"materialize failed with code {code}")
    return json.loads((output / "selection.json").read_text(encoding="utf-8"))
