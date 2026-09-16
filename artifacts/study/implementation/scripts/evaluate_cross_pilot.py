#!/usr/bin/env python3
"""Execute frozen suites against frozen candidates; select BEFORE joining rewards."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import shutil
from statistics import mean
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from selfverify.contract import freeze_suite
from selfverify.metrics import collect_session_usage
from cross_candidate_audit import observations, choose


def save(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def execute_cell(task, entry, suite, candidate, timeout=90):
    """Fresh task image per cell, with the same worker and source-mutation guard as refinement."""
    files, tests = (suite["files"], suite["tests"]) if suite else ({}, [])
    start = time.monotonic()
    name = "cross-pilot-cell-" + uuid.uuid4().hex[:16]
    with tempfile.TemporaryDirectory(prefix="cross-pilot-cell-") as tmp:
        folder = Path(tmp)
        config = {"action": "evaluate", "workdir": f"/app/task_{task}", "base": f"/app/task_{task}",
            "files": files, "tests": tests, "public": candidate is not None,
            "budget_seconds": (len(tests) + 1) * timeout + 30, "test_timeout_sec": timeout,
            "patch": "/input/candidate.patch" if candidate else None}
        if candidate:
            shutil.copyfile(candidate["frozen_patch"], folder / "candidate.patch")
        (folder / "config.json").write_text(json.dumps(config))
        code = ("import sys,json,tempfile; sys.path.insert(0,'/runtime'); "
                "from contract_runtime import operate; "
                "c=json.load(open('/input/config.json')); c['scratch']=tempfile.mkdtemp(); "
                "print(json.dumps(operate(c)))")
        cmd = ["docker", "run", "--rm", "--name", name, "--network", "none", "--cpus", "2", "--memory", "8g",
            "-v", f"{folder}:/input:ro", "-v", f"{ROOT / 'src/selfverify'}:/runtime:ro",
            "--entrypoint", "python3", entry["environment_image"], "-c", code]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=config["budget_seconds"] + 90)
            if proc.returncode:
                raise RuntimeError((proc.stdout + proc.stderr)[-3000:])
            value = json.loads(proc.stdout.strip().splitlines()[-1])
            return {"applied": "ok", "evaluation": value, "elapsed_seconds": time.monotonic() - start}
        except (subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            return {"applied": "unknown", "evaluation": {"public": {"status": "unknown"}, "results": []},
                    "error": str(exc)[-3000:], "elapsed_seconds": time.monotonic() - start}


def matrix_row(cell):
    ev = cell["evaluation"]
    return {"suite_trial": cell["suite_id"], "cand_trial": cell["candidate_id"], "self": cell["self"],
        "applied": cell["applied"], "public_rc": 0 if ev["public"]["status"] == "pass" else None,
        "results": [{"script": r["path"], "passed": r["status"] == "pass", "failure_class": r["status"]}
                    for r in ev["results"]]}


def select_task(cells, candidates, kind, strict=True):
    selected_cells = [c for c in cells if c["kind"] in (kind, "public")]
    baseline = {c["suite_id"]: {r["path"]: r["status"] for r in c["evaluation"]["results"]}
                for c in selected_cells if c["candidate_id"] == "BASELINE"}
    rows = []
    for cell in selected_cells:
        row = matrix_row(cell)
        if strict and cell["candidate_id"] != "BASELINE" and cell["kind"] != "public":
            before = baseline.get(cell["suite_id"], {})
            # Conservative whole-suite abstention. Kept explicit as a policy,
            # not a claim that every runtime exception is an invalid test.
            if any(r["failure_class"] not in {"pass", "assertion"} or
                   before.get(r["script"]) not in {"pass", "assertion"} for r in row["results"]):
                row["results"] = []
        rows.append(row)
    # Public cells precede suites in a deterministic candidate order.
    obs = observations(rows)
    return {"cross": choose(obs, "cross_vote"), "public_random": choose(obs, "public_random"),
            "first_public": choose(obs, "first_public")}


def main(out):
    manifest = read(out / "manifest.json")
    job_rows, suites = [], {}
    for job in manifest["jobs"]:
        trials = sorted(Path(job["result_dir"]).glob("task_*"))
        if len(trials) != 1:
            job_rows.append({"job": job["name"], "task": job["task"], "error": f"Expected one trial, found {len(trials)}"})
            continue
        trial = trials[0]
        summary = read(trial / "agent/selfverify_summary.json", {})
        state = summary.get("contract", {})
        initial = manifest["tasks"][job["task"]]["candidates"][job["candidate_index"]]
        row = {"job": job["name"], "task": job["task"], "kind": job["kind"], "candidate_index": job["candidate_index"],
            "trial": str(trial), "initial_matches": state.get("initial_patch_sha256") == initial["source_sha256"],
            "revisions": summary.get("revisions", 0), "candidates": state.get("candidates", []),
            "selected": state.get("selected"), "suite_error": state.get("suite_error"),
            "usage": collect_session_usage(trial / "agent"),
            "suite_sha256": (state.get("suite") or {}).get("sha256")}
        frozen = trial / "agent/contract/frozen_suite"
        if frozen.exists() and job["kind"] != "continue":
            try:
                suite = freeze_suite({p.name: p.read_text() for p in frozen.iterdir() if p.is_file()})
                if suite["sha256"] != row["suite_sha256"]:
                    raise ValueError("Frozen suite hash mismatch")
                suites[job["name"]] = suite
            except (ValueError, SyntaxError) as exc:
                row["suite_error"] = str(exc)
        job_rows.append(row)

    work = []
    for task, entry in manifest["tasks"].items():
        for c in entry["candidates"]:
            if sha256(Path(c["frozen_patch"]).read_bytes()).hexdigest() != c["source_sha256"]:
                raise ValueError("Candidate changed: " + c["trial"])
            work.append((task, entry, None, c, {"suite_id": "PUBLIC_ONLY", "kind": "public", "self": False}))
        for job in (j for j in manifest["jobs"] if j["task"] == task and j["name"] in suites):
            for c in [None, *entry["candidates"]]:
                meta = {"suite_id": job["name"], "kind": job["kind"],
                        "self": c is not None and job["kind"] == "candidate" and c["index"] == job["candidate_index"]}
                work.append((task, entry, suites[job["name"]], c, meta))

    def run_cell(item):
        task, entry, suite, candidate, meta = item
        candidate_id = candidate["trial"] if candidate else "BASELINE"
        dest = out / "matrix" / f"{task}--{meta['suite_id']}--{candidate_id}.json"
        if dest.exists():
            return read(dest)
        result = {"task": task, "candidate_id": candidate_id, **meta,
                  "suite_sha256": suite["sha256"] if suite else None,
                  "patch_sha256": candidate["source_sha256"] if candidate else None,
                  **execute_cell(task, entry, suite, candidate)}
        save(dest, result)
        print(json.dumps({"task": task, "suite": meta["suite_id"], "candidate": candidate_id,
                          "statuses": [r["status"] for r in result["evaluation"]["results"]],
                          "seconds": round(result["elapsed_seconds"], 2)}), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=4) as executor:
        matrix = list(executor.map(run_cell, work))
    decisions = {}
    for task, entry in manifest["tasks"].items():
        cells = [c for c in matrix if c["task"] == task]
        decisions[task] = {f"{kind}_{policy}": select_task(cells, entry["candidates"], kind, strict)
            for kind in ("candidate", "blind") for policy, strict in (("strict", True), ("nonzero", False))}
    save(out / "selection_without_rewards.json", decisions)

    # Only after frozen decisions have been persisted do we join hidden labels.
    scored = json.loads(json.dumps(decisions))
    for task, variants in scored.items():
        rewards = {c["trial"]: c["reward"] for c in manifest["tasks"][task]["candidates"]}
        for methods in variants.values():
            for choice in methods.values():
                choice["expected_reward"] = mean(rewards[c] for c in choice["picked"])
    for row in job_rows:
        if "trial" not in row:
            continue
        initial = manifest["tasks"][row["task"]]["candidates"][row["candidate_index"]]
        row["reward_before"] = initial["reward"]
        row["reward_after"] = read(Path(row["trial"]) / "verifier/reward.json", {}).get("reward")
        final = Path(row["trial"]) / "artifacts/model.patch"
        row["final_matches_selected"] = (sha256(final.read_bytes()).hexdigest() == (row["selected"] or {}).get("sha256")) if final.exists() else None
    aggregate = {variant: {method: mean(task[variant][method]["expected_reward"] for task in scored.values())
                          for method in ("cross", "public_random", "first_public")}
                 for variant in next(iter(scored.values()))}
    report = {"interpretation": "Development diagnostic on reused heterogeneous patches; not matched end-to-end budget",
        "attempted_jobs": len(manifest["jobs"]), "usable_suites": len(suites), "matrix_cells": len(matrix),
        "macro_expected_reward": aggregate, "selection": scored, "trials": job_rows,
        "oracle_pool_ceiling": mean(max(c["reward"] for c in entry["candidates"]) for entry in manifest["tasks"].values())}
    save(out / "report.json", report)
    lines = ["# Cross-verification development pilot", "", report["interpretation"], "",
             "| Variant | Cross selection | Public random | First public |", "|---|---:|---:|---:|"]
    for variant, methods in aggregate.items():
        lines.append(f"| {variant} | {methods['cross']:.2%} | {methods['public_random']:.2%} | {methods['first_public']:.2%} |")
    lines += ["", f"Usable suites: {len(suites)} / 16. Matrix cells: {len(matrix)}.", "",
        "| Task | Condition | Start candidate | Before | After | Repair turns | Initial hash verified |",
        "|---|---|---:|---:|---:|---:|---|"]
    for row in job_rows:
        if "trial" in row:
            lines.append(f"| {row['task']} | {row['kind']} | {row['candidate_index']} | {row['reward_before']} | {row['reward_after']} | {row['revisions']} | {row['initial_matches']} |")
    lines += ["", "Strict selection treats non-assertion failures (including on the original tree) as unknown. "
        "Nonzero selection is a sensitivity policy, not proof that these failures are valid scientific evidence. "
        "Ties/fallback are uniform expectations. Historical generation costs are not zero and are excluded "
        "from this incremental diagnostic only. Continuation has the same maximum additional model time "
        "as design+repair, not necessarily the same actual token/GPU budget.", ""]
    (out / "report.md").write_text("\n".join(lines))
    print(json.dumps({"report": str(out / "report.json"), "usable_suites": len(suites), "macro_expected_reward": aggregate}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    main(args.pilot.resolve())
