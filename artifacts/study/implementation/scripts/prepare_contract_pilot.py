#!/usr/bin/env python3
"""Freeze existing baseline candidates and prepare small task shards; no inference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "results/main/baseline-main12-n3")
    parser.add_argument("--tasks", type=Path, default=ROOT / "work/tasks-12")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--task", action="append", default=[])
    args = parser.parse_args()
    task_ids = args.task or ["008", "094", "004", "017"]
    if args.out.exists():
        parser.error("output already exists; choose a new run directory")
    # Select deterministically without using correctness labels to choose a
    # trial. Rewards are recorded for offline comparison, never sent to Codex.
    selected = []
    for task in task_ids:
        trials = sorted(p for p in args.baseline.glob(f"task_{task}__*")
                        if (p / "artifacts/model.patch").is_file() and (p / "verifier/reward.json").is_file())
        if not trials:
            parser.error(f"no completed baseline candidate for {task}")
        trial = trials[0]
        patch = trial / "artifacts/model.patch"
        data = patch.read_bytes()
        if not data:
            parser.error(f"empty baseline candidate: {patch}")
        for line in data.decode().splitlines():
            if line.startswith("diff --git "):
                paths = shlex.split(line)[2:]
                if len(paths) != 2 or not paths[0].startswith("a/source/") or not paths[1].startswith("b/source/"):
                    parser.error(f"candidate changes non-source files; cannot reuse reward unchanged: {patch}")
        task_dir = (args.tasks / f"task_{task}").resolve()
        toml = (task_dir / "task.toml").read_bytes()
        selected.append({"task": task, "trial": trial.name, "patch_source": str(patch.resolve()),
                         "patch_sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                         "task_dir": str(task_dir), "task_toml_sha256": hashlib.sha256(toml).hexdigest(),
                         "recorded_reward": json.loads((trial / "verifier/reward.json").read_text())["reward"],
                         "images": re.findall(r'docker_image\s*=\s*"([^"]+)"', toml.decode())})
    args.out.mkdir(parents=True)
    (args.out / "patches").mkdir()
    for index, item in enumerate(selected):
        task = item["task"]
        (args.out / "patches" / f"task_{task}.patch").write_bytes(Path(item["patch_source"]).read_bytes())
        # Each shard runs one task at a time; first two are failed candidates,
        # the next two are controls for damaging previously successful repairs.
        shard = args.out / ("gpu6" if index % 2 == 0 else "gpu7")
        shard.mkdir(exist_ok=True)
        (shard / f"task_{task}").symlink_to(item["task_dir"], target_is_directory=True)
    (args.out / "manifest.json").write_text(json.dumps({
        "selection_rule": "lexicographically first completed nonempty baseline trial per task",
        "private_labels": "offline reporting only; not uploaded to the agent",
        "candidates": selected,
    }, indent=2) + "\n")
    print(json.dumps({"out": str(args.out.resolve()), "tasks": task_ids,
                      "initial_patches": str((args.out / "patches").resolve())}, indent=2))


if __name__ == "__main__":
    main()
