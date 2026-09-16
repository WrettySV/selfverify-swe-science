#!/usr/bin/env python3
"""Prepare and run a bounded, four-GPU diagnostic on frozen historical patches."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
GPUS = {4: 8002, 5: 8003, 6: 8000, 7: 8001}


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def source_only(data):
    sections = re.split(r"(?=^diff --git )", data, flags=re.MULTILINE)
    selected = [s for s in sections if s.startswith("diff --git a/source/")]
    if not selected:
        raise ValueError("No source diff")
    return "".join(selected)


def prepare(out, task_ids=None):
    if out.exists():
        raise ValueError("Output exists; do not overwrite an experiment")
    pool = json.loads((ROOT / "analysis/crosscheck/pool.json").read_text())["tasks"]
    task_ids = task_ids or ["007", "017", "024", "039"]
    prepared = {}
    for task in task_ids:
        rows = pool[task]["candidates"]
        baseline = sorted((c for c in rows if c["job"] == "baseline-main12-n3"), key=lambda c: c["trial"])
        others = sorted((c for c in rows if c["job"] != "baseline-main12-n3"), key=lambda c: c["trial"])
        selected, hashes = [], set()
        for c in baseline + others:
            data = source_only(Path(c["patch"]).read_text())
            digest = sha256(data.encode()).hexdigest()
            if digest in hashes:
                continue
            hashes.add(digest)
            selected.append({**c, "source_sha256": digest, "source_text": data})
            if len(selected) == 3:
                break
        if len(selected) != 3 or len(baseline) < 2:
            raise ValueError(f"Expected 3 candidates and 2 baseline trials for {task}")
        prepared[task] = selected
    out.mkdir(parents=True)
    for folder in ("private", "status", "logs", "inputs", "shards", "matrix"):
        (out / folder).mkdir()
    (out / "private").chmod(0o700)
    implementation = out / "implementation"
    implementation.mkdir()
    for folder in ("src", "scripts", "configs", "tests"):
        shutil.copytree(ROOT / folder, implementation / folder,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "pyproject.toml", implementation / "pyproject.toml")
    code_hashes = {str(p.relative_to(implementation)): sha256(p.read_bytes()).hexdigest()
                   for p in sorted(implementation.rglob("*")) if p.is_file()}
    save(out / "implementation_sha256.json", code_hashes)
    profile = Path("/home/lukina/.config/swe-bench-science/vllm-qwen38-8000.env").read_text()
    for gpu, port in GPUS.items():
        lines = []
        for line in profile.splitlines():
            if re.match(r"(?:export\s+)?(?:CODEX_BASE_URL|OPENAI_BASE_URL)\s*=", line):
                line = line.replace(":8000", f":{port}")
            lines.append(line)
        dest = out / "private" / f"gpu{gpu}.env"
        dest.write_text("\n".join(lines) + "\n")
        dest.chmod(0o600)
    manifest = {"created_at": now(), "kind": "development diagnostic, NOT matched end-to-end inference budget",
        "task_selection": "Explicit task list supplied at preparation; historical pool composition is recorded per task",
        "candidate_selection": "stored baseline trials first, then other historical trials, lexicographic; exact source diff dedup; first three",
        "hidden_labels": "host reporting only; never supplied to agent, repair gate, or selector",
        "budgets": {"suite_seconds": 360, "repair_seconds": 360, "continuation_seconds": 720,
                    "test_seconds": 90, "agent_seconds": 1500, "repair_rounds": 1},
        "refinement": "donor candidates only; one feedback-driven repair, frozen-suite promotion gate; not forced if checks pass",
        "selector": "public preference, equal per-suite votes, diagonal omitted for donor, unknown abstains, uniform ties/fallback; legacy-nonzero sensitivity also reported",
        "gpu_ports": GPUS, "tasks": {}, "jobs": []}
    loads = {gpu: 0 for gpu in GPUS}
    for task, candidates in prepared.items():
        task_dir = ROOT / "work/tasks-12" / f"task_{task}"
        spec = tomllib.loads((task_dir / "task.toml").read_text())
        manifest["tasks"][task] = {"task_dir": str(task_dir), "task_toml_sha256": sha256((task_dir / "task.toml").read_bytes()).hexdigest(),
            "environment_image": spec["environment"]["docker_image"],
            "verifier_image": spec["verifier"]["environment"]["docker_image"], "candidates": []}
        for i, candidate in enumerate(candidates):
            folder = out / "inputs" / task / f"p{i}"
            folder.mkdir(parents=True)
            patch = folder / f"task_{task}.patch"
            patch.write_text(candidate.pop("source_text"))
            manifest["tasks"][task]["candidates"].append({**candidate, "frozen_patch": str(patch), "index": i})
        for kind, index in [("candidate", 0), ("blind", 0), ("candidate", 1), ("blind", 1), ("continue", 0)]:
            gpu = min(loads, key=lambda g: (loads[g], g))
            duration = 360 if kind == "blind" else 720
            loads[gpu] += duration
            job_name = f"{out.name}-{task}-{kind}-{index}"
            shard = out / "shards" / job_name
            shard.mkdir()
            (shard / task_dir.name).symlink_to(task_dir, target_is_directory=True)
            cmd = [sys.executable, str(implementation / "scripts/run_experiment.py"),
                "--condition", "selfverify", "--verification-mode", "continue" if kind == "continue" else "contract",
                "--path", str(shard), "--initial-patches", str(out / "inputs" / task / f"p{index}"),
                "--env-file", str(out / "private" / f"gpu{gpu}.env"),
                "--jobs-dir", str(ROOT / "results/main"), "--job-name", job_name,
                "--n-attempts", "1", "--n-concurrent", "1", "--skip-pull",
                "--max-loop-seconds", "1500", "--test-design-timeout-sec", "360",
                "--repair-timeout-sec", "720" if kind == "continue" else "360",
                "--verify-timeout-sec", "90", "--max-repair-rounds", "0" if kind == "blind" else "1"]
            if kind != "continue":
                cmd += ["--suite-context", kind, "--test-design-focus", "analytic" if index == 0 else "boundary"]
            manifest["jobs"].append({"name": job_name, "task": task, "kind": kind, "candidate_index": index,
                "gpu": gpu, "result_dir": str(ROOT / "results/main" / job_name), "command": cmd})
    manifest["maximum_model_seconds_by_gpu"] = loads
    save(out / "manifest.json", manifest)
    print(json.dumps({"out": str(out), "jobs": len(manifest["jobs"]), "model_minutes_by_gpu": {g: s / 60 for g, s in loads.items()}}, indent=2))


def run(out):
    manifest = json.loads((out / "manifest.json").read_text())
    for relative, expected in json.loads((out / "implementation_sha256.json").read_text()).items():
        if sha256((out / "implementation" / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen implementation changed: {relative}")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port in GPUS.values():
        with opener.open(f"http://127.0.0.1:{port}/v1/models", timeout=10) as response:
            models = json.load(response)["data"]
            if not any(m["id"] == "Qwen3.8-27B" for m in models):
                raise ValueError(f"Unexpected model at {port}")
    save(out / "run_status.json", {"state": "running", "started_at": now(), "pid": os.getpid()})
    env = os.environ.copy()
    env["PIER_PY"] = str(out / "implementation/scripts/pier_local_python")

    def lane(gpu):
        for job in (j for j in manifest["jobs"] if j["gpu"] == gpu):
            status_path = out / "status" / (job["name"] + ".json")
            if status_path.exists():
                previous = json.loads(status_path.read_text())
                if previous.get("state") == "finished":
                    continue
                raise ValueError(f"Ambiguous previous job state; inspect before rerun: {job['name']}")
            started = time.monotonic()
            status = {"name": job["name"], "gpu": gpu, "state": "running", "started_at": now()}
            save(status_path, status)
            print(json.dumps(status), flush=True)
            with (out / "logs" / (job["name"] + ".log")).open("wb") as log:
                proc = subprocess.Popen(job["command"], cwd=out / "implementation", env=env, stdout=log,
                                        stderr=subprocess.STDOUT, start_new_session=True)
                status["pid"] = proc.pid
                save(status_path, status)
                try:
                    rc = proc.wait(timeout=3600)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    rc = 124
            status.update(state="finished", returncode=rc, finished_at=now(), elapsed_seconds=time.monotonic() - started)
            save(status_path, status)
            print(json.dumps(status), flush=True)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lane, GPUS))
    save(out / "run_status.json", {"state": "generation_finished", "finished_at": now()})
    evaluator = out / "implementation/scripts/evaluate_cross_pilot.py"
    subprocess.run([sys.executable, str(evaluator), "--pilot", str(out)], check=True)
    save(out / "run_status.json", {"state": "finished", "finished_at": now()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "run"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--task", action="append", default=[])
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.out.resolve(), args.task or None)
    else:
        if args.task:
            parser.error("--task is only valid for prepare")
        run(args.out.resolve())
