#!/usr/bin/env python3
"""Offline evaluation of self-generated invariant suites as bug discriminators.

The self-verify loop accepts a patch when every "valid" invariant test passes.
Trial logs show that gate is always green (good=5, weak=0) while the private
oracle says most of those patches are wrong, so the gate has no measured
discriminative power. This tool measures it directly, without any LLM call:

  pool    inventory candidate patches (with recorded rewards) and the invariant
          suites embedded in self-verify patches
  run     cross-run every suite against every candidate patch of the same task
          inside the task environment image (plus the unpatched baseline)
  oracle  score an arbitrary patch with the task verifier image (ground truth)
  report  turn the cross matrix into signal-quality metrics

A suite is only a real discriminator if it fails on the unpatched baseline,
passes on correct patches, and fails on incorrect ones. "Passes on its own
patch" measures self-consistency only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "analysis" / "crosscheck"
DEFAULT_TASKS = REPO_ROOT / "work" / "tasks-12"

# Job directories holding scored trials. Patches from a different pipeline are
# still valid candidates for the same task, which is what gives us negatives
# near the correct fix.
DEFAULT_SOURCES = [
    "/home/lukina/selfverify-swe-science/results/main",
    "/home/lukina/swe-science-scientist-engineer/results",
]

# Compiled tasks need a full project rebuild after applying a patch, which the
# environment image does not do for us.
NATIVE_TASKS = {"004"}

SUITE_FILE = re.compile(r"^selfverify/invariants/[^/]+\.(py|json)$")
TRIAL_DIR = re.compile(r"^task_(\d+)__(.+)$")


@dataclass
class Candidate:
    task: str
    trial: str
    source: str
    job: str
    patch: str
    reward: int | None
    patch_bytes: int
    suite_scripts: list[str] = field(default_factory=list)


def merge_write(path: Path, data: dict[str, Any], nested: bool) -> None:
    """Persist results after folding in whatever another process already wrote.

    Stages are run concurrently per task, so a plain overwrite loses the cells
    a sibling process finished in the meantime.
    """
    merged: dict[str, Any] = {}
    if path.is_file():
        try:
            merged = json.loads(path.read_text())
        except Exception:
            merged = {}
    for key, value in data.items():
        if nested and isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(merged, indent=2) + "\n")
    tmp.replace(path)


def _run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, text=True, capture_output=True, timeout=timeout, check=False
    )


# --------------------------------------------------------------------------- #
# pool
# --------------------------------------------------------------------------- #


def parse_new_files(patch_text: str, wanted: re.Pattern[str]) -> dict[str, str]:
    """Reconstruct new-file contents from a git diff for matching paths.

    Suites are always new files relative to the task baseline commit, so the
    added lines are the whole file.
    """
    files: dict[str, list[str]] = {}
    path: str | None = None
    in_hunk = False
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            path, in_hunk = None, False
            match = re.match(r"diff --git a/(.+) b/(.+)$", line)
            if match and wanted.match(match.group(2)):
                path = match.group(2)
                files.setdefault(path, [])
            continue
        if path is None:
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if line.startswith("GIT binary patch"):
            path, in_hunk = None, False
            continue
        if not in_hunk:
            continue
        if line.startswith("+"):
            files[path].append(line[1:])
        elif line.startswith("\\"):
            continue
    return {p: "\n".join(lines) + "\n" for p, lines in files.items() if lines}


def build_pool(sources: list[Path], out_dir: Path, include_archive: bool) -> dict[str, Any]:
    suites_root = out_dir / "suites"
    suites_root.mkdir(parents=True, exist_ok=True)
    candidates: list[Candidate] = []

    for source in sources:
        if not source.is_dir():
            print(f"! missing source {source}", file=sys.stderr)
            continue
        pattern = "**/task_*__*" if include_archive else "*/task_*__*"
        for trial_dir in sorted(source.glob(pattern)):
            job = trial_dir.parent.name
            if not include_archive and "archive" in trial_dir.parts:
                continue
            match = TRIAL_DIR.match(trial_dir.name)
            if not match:
                continue
            task = match.group(1)
            patch = trial_dir / "artifacts" / "model.patch"
            if not patch.is_file() or patch.stat().st_size == 0:
                continue
            reward = None
            reward_json = trial_dir / "verifier" / "reward.json"
            if reward_json.is_file():
                try:
                    reward = int(json.loads(reward_json.read_text())["reward"])
                except Exception:
                    reward = None
            text = patch.read_text(errors="ignore")
            suite = parse_new_files(text, SUITE_FILE)
            # Newer trials keep the suite in the trial logs instead of the
            # worktree, so it no longer shows up inside model.patch.
            for script in sorted(
                (trial_dir / "agent" / "selfverify_worktree" / "invariants").glob("*")
            ):
                if script.suffix in {".py", ".json"}:
                    suite.setdefault(
                        f"selfverify/invariants/{script.name}",
                        script.read_text(errors="ignore"),
                    )
            scripts: list[str] = []
            if any(p.endswith(".py") for p in suite):
                dest = suites_root / task / trial_dir.name
                dest.mkdir(parents=True, exist_ok=True)
                for path, content in sorted(suite.items()):
                    target = dest / Path(path).name
                    target.write_text(content, encoding="utf-8")
                    if path.endswith(".py"):
                        scripts.append(target.name)
            candidates.append(
                Candidate(
                    task=task,
                    trial=trial_dir.name,
                    source=str(trial_dir),
                    job=job,
                    patch=str(patch),
                    reward=reward,
                    patch_bytes=patch.stat().st_size,
                    suite_scripts=sorted(scripts),
                )
            )

    # Old job names are kept as symlinks, so a recursive scan reaches the same
    # trial twice. Trial ids are unique, so collapse on (task, trial) and keep
    # the shortest path, which is the live job rather than an alias.
    unique: dict[tuple[str, str], Candidate] = {}
    for cand in sorted(candidates, key=lambda c: len(Path(c.source).parts)):
        unique.setdefault((cand.task, cand.trial), cand)
    candidates = sorted(unique.values(), key=lambda c: (c.task, c.trial))

    by_task: dict[str, dict[str, Any]] = {}
    for cand in candidates:
        entry = by_task.setdefault(
            cand.task, {"candidates": [], "n_pos": 0, "n_neg": 0, "n_suites": 0}
        )
        entry["candidates"].append(asdict(cand))
        if cand.reward == 1:
            entry["n_pos"] += 1
        elif cand.reward == 0:
            entry["n_neg"] += 1
        if cand.suite_scripts:
            entry["n_suites"] += 1

    pool = {"tasks": dict(sorted(by_task.items()))}
    (out_dir / "pool.json").write_text(json.dumps(pool, indent=2) + "\n")
    return pool


# --------------------------------------------------------------------------- #
# docker helpers
# --------------------------------------------------------------------------- #


def task_images(tasks_dir: Path, task: str) -> tuple[str, str]:
    toml = (tasks_dir / f"task_{task}" / "task.toml").read_text()
    images = re.findall(r'docker_image\s*=\s*"([^"]+)"', toml)
    if len(images) < 2:
        raise SystemExit(f"task_{task}: expected env+verifier images, got {images}")
    return images[0], images[1]


APPLY_AND_RUN = r"""
set -u
workdir=/app/task_{task}
cd "$workdir"
git config --global --add safe.directory "$workdir" 2>/dev/null || true
git reset --hard HEAD >/dev/null 2>&1
git clean -fd >/dev/null 2>&1
applied=skipped
if [ -s /patch/model.patch ]; then
  if git apply --binary --whitespace=nowarn {excludes} /patch/model.patch 2>/tmp/apply.err; then
    applied=ok
  elif git apply --binary --whitespace=nowarn --3way {excludes} /patch/model.patch 2>>/tmp/apply.err; then
    applied=ok_3way
  else
    applied=failed
  fi
fi
echo "APPLIED=$applied"
if [ "$applied" = failed ]; then
  echo "APPLY_ERR_BEGIN"; tail -c 800 /tmp/apply.err; echo "APPLY_ERR_END"
  exit 0
fi
mkdir -p "$workdir/selfverify"
rm -rf "$workdir/selfverify/invariants"
cp -a /suite "$workdir/selfverify/invariants"
if [ "{run_public}" = "1" ]; then
  if [ -f "$workdir/reproduce.py" ]; then
    ( cd "$workdir" && timeout {timeout} python3 reproduce.py >/tmp/pub.out 2>&1 )
    echo "PUBLIC_RC=$?"
  else
    echo "PUBLIC_RC=missing"
  fi
fi
for script in "$workdir"/selfverify/invariants/*.py; do
  [ -f "$script" ] || continue
  ( cd "$workdir" && timeout {timeout} python3 "$script" >/tmp/inv.out 2>&1 )
  rc=$?
  echo "INV_BEGIN $(basename "$script") rc=$rc"
  tail -c 700 /tmp/inv.out
  echo ""
  echo "INV_END"
done
"""


def run_suite_in_env(
    *,
    image: str,
    task: str,
    suite_dir: Path,
    patch: Path | None,
    timeout: int,
    run_public: bool,
    excludes: bool = True,
) -> dict[str, Any]:
    exclude_flags = (
        "--exclude=selfverify/* --exclude=artifacts/* --exclude=*/selfverify/*"
        if excludes
        else ""
    )
    script = APPLY_AND_RUN.format(
        task=task,
        excludes=exclude_flags,
        timeout=timeout,
        run_public="1" if run_public else "0",
    )
    with tempfile.TemporaryDirectory() as tmp:
        patch_dir = Path(tmp) / "patch"
        patch_dir.mkdir()
        target = patch_dir / "model.patch"
        if patch is not None:
            shutil.copyfile(patch, target)
        else:
            target.write_text("")
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--platform",
            "linux/amd64",
            "-v",
            f"{patch_dir}:/patch:ro",
            "-v",
            f"{suite_dir}:/suite:ro",
            "--entrypoint",
            "/bin/sh",
            image,
            "-c",
            script,
        ]
        proc = _run(cmd, timeout=timeout * 12 + 300)
    return parse_env_output(proc)


def parse_env_output(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    out = (proc.stdout or "") + (proc.stderr or "")
    applied = None
    public_rc: Any = None
    results: list[dict[str, Any]] = []
    apply_err: list[str] = []
    lines = out.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("APPLIED="):
            applied = line.split("=", 1)[1].strip()
        elif line.startswith("PUBLIC_RC="):
            raw = line.split("=", 1)[1].strip()
            public_rc = int(raw) if raw.isdigit() else raw
        elif line == "APPLY_ERR_BEGIN":
            idx += 1
            while idx < len(lines) and lines[idx] != "APPLY_ERR_END":
                apply_err.append(lines[idx])
                idx += 1
        elif line.startswith("INV_BEGIN "):
            header = line[len("INV_BEGIN ") :]
            name, _, rc_part = header.rpartition(" rc=")
            body: list[str] = []
            idx += 1
            while idx < len(lines) and lines[idx] != "INV_END":
                body.append(lines[idx])
                idx += 1
            rc = int(rc_part) if rc_part.strip().isdigit() else None
            tail = "\n".join(body).strip()
            results.append(
                {
                    "script": name.strip(),
                    "exit_code": rc,
                    "passed": rc == 0,
                    "failure_class": classify_failure(rc, tail),
                    "tail": tail[-700:],
                }
            )
        idx += 1
    return {
        "applied": applied,
        "apply_error": "\n".join(apply_err)[-800:] or None,
        "public_rc": public_rc,
        "results": results,
        "docker_rc": proc.returncode,
        "raw_tail": out[-1500:] if applied is None else None,
    }


def classify_failure(rc: int | None, tail: str) -> str:
    """Distinguish a real invariant violation from a broken test.

    The self-verify gate treats any non-zero exit on the unpatched tree as
    proof that a test detects the bug. An ImportError or a missing symbol is
    not evidence about the science, so the two must be separated.
    """
    if rc == 0:
        return "pass"
    if rc == 124:
        return "timeout"
    if "AssertionError" in tail:
        return "assertion"
    for marker, label in (
        ("ModuleNotFoundError", "import_error"),
        ("ImportError", "import_error"),
        ("AttributeError", "missing_symbol"),
        ("NameError", "missing_symbol"),
        ("SyntaxError", "broken_test"),
        ("IndentationError", "broken_test"),
        ("FileNotFoundError", "missing_file"),
        ("TypeError", "runtime_error"),
        ("ValueError", "runtime_error"),
    ):
        if marker in tail:
            return label
    return "other_nonzero"


def run_oracle(
    *, image: str, patch: Path | None, timeout: int, scratch: Path | None = None
) -> dict[str, Any]:
    """Score a patch with the task verifier image (ground truth reward)."""
    root = scratch or Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=root, prefix="oracle-"))
    try:
        logs = tmp / "logs"
        (logs / "artifacts").mkdir(parents=True)
        target = logs / "artifacts" / "model.patch"
        if patch is not None:
            shutil.copyfile(patch, target)
        else:
            target.write_text("")
        logs.chmod(0o777)
        (logs / "artifacts").chmod(0o777)
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--platform",
            "linux/amd64",
            "-v",
            f"{logs}:/logs",
            image,
        ]
        proc = _run(cmd, timeout=timeout)
        reward_json = logs / "verifier" / "reward.json"
        payload: dict[str, Any] = {"docker_rc": proc.returncode}
        if reward_json.is_file():
            try:
                payload["reward_json"] = json.loads(reward_json.read_text())
            except Exception:
                payload["reward_json"] = None
        payload["reward"] = (payload.get("reward_json") or {}).get("reward")
        payload["stdout_tail"] = ((proc.stdout or "") + (proc.stderr or ""))[-1200:]
        return payload
    finally:
        # The verifier writes /logs as root, so removal needs root as well.
        _run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-v",
                f"{tmp}:/scratch",
                "--entrypoint",
                "/bin/sh",
                image,
                "-c",
                "rm -rf /scratch/logs",
            ],
            timeout=120,
        )
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #


def stage_run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    pool = json.loads((out_dir / "pool.json").read_text())
    tasks = args.task or sorted(pool["tasks"])
    matrix_path = out_dir / "matrix.json"
    matrix: dict[str, Any] = {}
    if matrix_path.is_file() and not args.overwrite:
        matrix = json.loads(matrix_path.read_text())

    for task in tasks:
        entry = pool["tasks"].get(task)
        if entry is None:
            print(f"! task {task} not in pool", file=sys.stderr)
            continue
        if task in NATIVE_TASKS and not args.include_native:
            print(f"- task {task}: skipped (needs native rebuild)")
            continue
        suites = [c for c in entry["candidates"] if c["suite_scripts"]]
        if not suites:
            print(f"- task {task}: no invariant suite in any patch")
            continue
        env_image, _ = task_images(Path(args.tasks_dir), task)
        cells = matrix.setdefault(task, {})
        for suite in suites:
            suite_dir = out_dir / "suites" / task / suite["trial"]
            for cand in entry["candidates"]:
                key = f"{suite['trial']}|{cand['trial']}"
                if key in cells and not args.overwrite:
                    continue
                print(f"  [{task}] suite {suite['trial']} vs patch {cand['trial']}", flush=True)
                cells[key] = {
                    "suite_trial": suite["trial"],
                    "suite_job": suite["job"],
                    "cand_trial": cand["trial"],
                    "cand_job": cand["job"],
                    "cand_reward": cand["reward"],
                    "self": suite["trial"] == cand["trial"],
                    **run_suite_in_env(
                        image=env_image,
                        task=task,
                        suite_dir=suite_dir,
                        patch=Path(cand["patch"]),
                        timeout=args.timeout,
                        run_public=args.public,
                    ),
                }
                merge_write(matrix_path, matrix, nested=True)
            key = f"{suite['trial']}|BASELINE"
            if key not in cells or args.overwrite:
                print(f"  [{task}] suite {suite['trial']} vs BASELINE (no patch)", flush=True)
                cells[key] = {
                    "suite_trial": suite["trial"],
                    "suite_job": suite["job"],
                    "cand_trial": "BASELINE",
                    "cand_job": "baseline",
                    "cand_reward": 0,
                    "self": False,
                    **run_suite_in_env(
                        image=env_image,
                        task=task,
                        suite_dir=suite_dir,
                        patch=None,
                        timeout=args.timeout,
                        run_public=args.public,
                    ),
                }
                merge_write(matrix_path, matrix, nested=True)
    print(f"wrote {matrix_path}")
    return 0


def stage_oracle(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    pool = json.loads((out_dir / "pool.json").read_text())
    path = out_dir / "oracle.json"
    scored = json.loads(path.read_text()) if path.is_file() else {}
    for task in args.task or sorted(pool["tasks"]):
        if task in NATIVE_TASKS and not args.include_native:
            continue
        _, verifier_image = task_images(Path(args.tasks_dir), task)
        for cand in pool["tasks"][task]["candidates"]:
            key = f"{task}|{cand['trial']}"
            if key in scored and not args.overwrite:
                continue
            print(f"  oracle [{task}] {cand['trial']}", flush=True)
            scored[key] = {
                "task": task,
                "trial": cand["trial"],
                "recorded_reward": cand["reward"],
                **run_oracle(
                    image=verifier_image,
                    patch=Path(cand["patch"]),
                    timeout=args.timeout * 6,
                    scratch=out_dir / "_scratch",
                ),
            }
            merge_write(path, scored, nested=False)
    print(f"wrote {path}")
    return 0


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #


def suite_verdict(cell: dict[str, Any]) -> str:
    if cell.get("applied") == "failed":
        return "apply_failed"
    results = cell.get("results") or []
    if not results:
        return "no_results"
    return "accept" if all(r["passed"] for r in results) else "reject"


def stage_report(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    matrix = json.loads((out_dir / "matrix.json").read_text())
    rows: list[dict[str, Any]] = []
    for task, cells in matrix.items():
        for cell in cells.values():
            rows.append({"task": task, "verdict": suite_verdict(cell), **cell})

    def count(pred) -> int:
        return sum(1 for r in rows if pred(r))

    summary: dict[str, Any] = {"n_cells": len(rows)}
    summary["self_accept"] = {
        "accept": count(lambda r: r["self"] and r["verdict"] == "accept"),
        "total": count(lambda r: r["self"]),
    }
    summary["baseline_reject"] = {
        "reject": count(
            lambda r: r["cand_trial"] == "BASELINE" and r["verdict"] == "reject"
        ),
        "total": count(lambda r: r["cand_trial"] == "BASELINE"),
    }
    # Only assertion-class failures on the unpatched tree are evidence that a
    # test is about the bug rather than about a symbol the patch introduced.
    baseline_cells = [r for r in rows if r["cand_trial"] == "BASELINE"]
    classes: dict[str, int] = {}
    for row in baseline_cells:
        for res in row.get("results") or []:
            classes[res["failure_class"]] = classes.get(res["failure_class"], 0) + 1
    summary["baseline_failure_classes"] = dict(sorted(classes.items()))

    foreign = [r for r in rows if not r["self"] and r["cand_trial"] != "BASELINE"]
    pos = [r for r in foreign if r["cand_reward"] == 1]
    neg = [r for r in foreign if r["cand_reward"] == 0]
    summary["foreign"] = {
        "n": len(foreign),
        "accept_on_correct": {
            "accept": sum(1 for r in pos if r["verdict"] == "accept"),
            "total": len(pos),
        },
        "accept_on_incorrect": {
            "accept": sum(1 for r in neg if r["verdict"] == "accept"),
            "total": len(neg),
        },
    }
    tp = summary["foreign"]["accept_on_correct"]["accept"]
    fp = summary["foreign"]["accept_on_incorrect"]["accept"]
    summary["precision_at_accept"] = (tp / (tp + fp)) if (tp + fp) else None
    summary["base_rate_correct"] = (len(pos) / len(foreign)) if foreign else None

    per_task: dict[str, Any] = {}
    for task in sorted(matrix):
        task_rows = [r for r in rows if r["task"] == task]
        f = [r for r in task_rows if not r["self"] and r["cand_trial"] != "BASELINE"]
        # Two trust tests computable without the private oracle.
        # 1. split: a suite that accepts (or rejects) every candidate carries no
        #    information about which candidate to keep.
        # 2. agreement: independent suites for the same task should agree, and the
        #    loop already generates a second suite in its challenge stage.
        by_suite: dict[str, dict[str, str]] = {}
        for row in f:
            by_suite.setdefault(row["suite_trial"], {})[row["cand_trial"]] = row["verdict"]
        splits = {}
        for suite, verdicts in by_suite.items():
            accepts = sum(1 for v in verdicts.values() if v == "accept")
            baseline_verdicts = [
                r["verdict"]
                for r in task_rows
                if r["suite_trial"] == suite and r["cand_trial"] == "BASELINE"
            ]
            splits[suite] = {
                "accepts": accepts,
                "n": len(verdicts),
                "splits_pool": 0 < accepts < len(verdicts),
                "baseline_reject": bool(baseline_verdicts)
                and all(v == "reject" for v in baseline_verdicts),
            }
        pairs: list[dict[str, Any]] = []
        names = sorted(by_suite)
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                common = set(by_suite[left]) & set(by_suite[right])
                if not common:
                    continue
                same = sum(1 for c in common if by_suite[left][c] == by_suite[right][c])
                pairs.append(
                    {
                        "suites": [left, right],
                        "agreement": same / len(common),
                        "n_common": len(common),
                    }
                )
        per_task[task] = {
            "suite_splits_pool": splits,
            "inter_suite_agreement": pairs,
            "trusted": (
                any(
                    s["splits_pool"] and s["baseline_reject"]
                    for s in splits.values()
                )
                and all(p["agreement"] == 1.0 for p in pairs)
            ),
            "cells": len(task_rows),
            "accept_on_correct": [
                (r["suite_trial"], r["cand_trial"], r["verdict"])
                for r in f
                if r["cand_reward"] == 1
            ],
            "accept_rate_incorrect": (
                sum(1 for r in f if r["cand_reward"] == 0 and r["verdict"] == "accept")
                / max(1, sum(1 for r in f if r["cand_reward"] == 0))
            ),
            "baseline_verdict": [
                r["verdict"] for r in task_rows if r["cand_trial"] == "BASELINE"
            ],
        }
    summary["per_task"] = per_task

    path = out_dir / "report.json"
    path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {path}")
    return 0


# --------------------------------------------------------------------------- #


@dataclass
class FileBlock:
    header: list[str]
    path: str
    hunks: list[list[str]]
    binary: bool = False


def parse_diff(patch_text: str) -> list[FileBlock]:
    blocks: list[FileBlock] = []
    current: FileBlock | None = None
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+) b/(.+)$", line)
            current = FileBlock(header=[line], path=match.group(2) if match else "?", hunks=[])
            blocks.append(current)
            continue
        if current is None:
            continue
        if line.startswith("GIT binary patch"):
            current.binary = True
            current.header.append(line)
            continue
        if line.startswith("@@") and not current.binary:
            current.hunks.append([line])
            continue
        if current.hunks and not current.binary:
            current.hunks[-1].append(line)
        else:
            current.header.append(line)
    return blocks


def emit_diff(blocks: list[FileBlock], drop: dict[str, Any] | None) -> str:
    """Render a patch, optionally reverting one mutation unit.

    ``drop`` is ``{"path": p, "hunk": i}`` for a whole hunk or additionally
    ``{"run": (start, end)}`` for one contiguous change run inside it.
    """
    out: list[str] = []
    for block in blocks:
        if block.binary or not block.hunks:
            continue
        kept: list[list[str]] = []
        for index, hunk in enumerate(block.hunks):
            if drop and drop["path"] == block.path and drop["hunk"] == index:
                if "run" in drop:
                    start, end = drop["run"]
                    body = [hunk[0]]
                    skip_marker = False
                    for pos, line in enumerate(hunk[1:], start=1):
                        if line.startswith("\\"):
                            if not skip_marker:
                                body.append(line)
                            skip_marker = False
                            continue
                        if start <= pos <= end:
                            if line.startswith("-"):
                                body.append(" " + line[1:])
                                skip_marker = False
                            else:
                                skip_marker = True
                            continue
                        body.append(line)
                        skip_marker = False
                    kept.append(body)
                continue
            kept.append(hunk)
        if not kept:
            continue
        out.extend(block.header)
        for hunk in kept:
            out.extend(hunk)
    return "\n".join(out) + "\n" if out else ""


def mutation_units(blocks: list[FileBlock], granularity: str) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for block in blocks:
        if block.binary or block.path.startswith(("selfverify/", "artifacts/")):
            continue
        for index, hunk in enumerate(block.hunks):
            if granularity == "hunk":
                units.append({"path": block.path, "hunk": index, "label": f"hunk{index}"})
                continue
            run_start = None
            for pos, line in enumerate(hunk[1:], start=1):
                is_change = line.startswith(("-", "+"))
                if is_change and run_start is None:
                    run_start = pos
                elif not is_change and run_start is not None:
                    units.append(
                        {
                            "path": block.path,
                            "hunk": index,
                            "run": (run_start, pos - 1),
                            "label": f"hunk{index}_run{run_start}",
                        }
                    )
                    run_start = None
            if run_start is not None:
                units.append(
                    {
                        "path": block.path,
                        "hunk": index,
                        "run": (run_start, len(hunk) - 1),
                        "label": f"hunk{index}_run{run_start}",
                    }
                )
    return units


def stage_mutants(args: argparse.Namespace) -> int:
    """Measure suite sensitivity against oracle-labelled partial repairs.

    Dropping one change unit from a patch that the private oracle accepts gives
    a negative that is arbitrarily close to the correct fix, which is the case
    the file-level ablation gate in the live loop cannot construct.
    """
    out_dir = Path(args.out)
    pool = json.loads((out_dir / "pool.json").read_text())
    path = out_dir / (args.store or "mutants.json")
    store = json.loads(path.read_text()) if path.is_file() else {}

    for task in args.task or sorted(pool["tasks"]):
        entry = pool["tasks"].get(task)
        if entry is None or (task in NATIVE_TASKS and not args.include_native):
            continue
        suites = [c for c in entry["candidates"] if c["suite_scripts"]]
        if args.self_only:
            # Run-time view of the gate: mutate a patch and re-run the suite its
            # own author wrote. No private oracle is needed to see whether the
            # suite notices that part of the repair is gone.
            bases = suites
        else:
            bases = [c for c in entry["candidates"] if c["reward"] == 1]
        if not suites or not bases:
            print(f"- task {task}: need a suite and a base patch")
            continue
        env_image, verifier_image = task_images(Path(args.tasks_dir), task)
        mut_dir = out_dir / "mutants" / task
        mut_dir.mkdir(parents=True, exist_ok=True)
        for base in bases:
            blocks = parse_diff(Path(base["patch"]).read_text(errors="ignore"))
            units = mutation_units(blocks, args.granularity)
            print(f"[{task}] {base['trial']}: {len(units)} mutation units ({args.granularity})")
            for unit in units:
                safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{unit['path']}__{unit['label']}")
                key = f"{task}|{base['trial']}|{safe}"
                if key in store and not args.overwrite:
                    continue
                text = emit_diff(blocks, unit)
                if not text.strip():
                    continue
                mutant = mut_dir / f"{base['trial']}__{safe}.patch"
                mutant.write_text(text)
                print(f"  mutant {safe}", flush=True)
                record: dict[str, Any] = {
                    "task": task,
                    "base_trial": base["trial"],
                    "unit": {k: v for k, v in unit.items() if k != "run"} | (
                        {"run": list(unit["run"])} if "run" in unit else {}
                    ),
                    "patch": str(mutant),
                }
                record["oracle"] = (
                    {"reward": None, "skipped": True}
                    if args.no_oracle
                    else run_oracle(
                        image=verifier_image,
                        patch=mutant,
                        timeout=args.timeout * 6,
                        scratch=out_dir / "_scratch",
                    )
                )
                record["suites"] = {}
                judges = [base] if args.self_only else suites
                for suite in judges:
                    suite_dir = out_dir / "suites" / task / suite["trial"]
                    cell = run_suite_in_env(
                        image=env_image,
                        task=task,
                        suite_dir=suite_dir,
                        patch=mutant,
                        timeout=args.timeout,
                        run_public=args.public,
                    )
                    record["suites"][suite["trial"]] = {
                        "verdict": suite_verdict(cell),
                        "applied": cell["applied"],
                        "public_rc": cell["public_rc"],
                        "n_passed": sum(1 for r in cell["results"] if r["passed"]),
                        "n_total": len(cell["results"]),
                        "failure_classes": sorted(
                            {r["failure_class"] for r in cell["results"] if not r["passed"]}
                        ),
                    }
                store[key] = record
                merge_write(path, store, nested=False)

    # Sensitivity of the suite on oracle-labelled near-miss patches.
    rows = list(store.values())
    stats: dict[str, Any] = {"n_mutants": len(rows)}
    for label, want in (("oracle_broken", 0), ("oracle_still_correct", 1)):
        subset = [r for r in rows if r["oracle"].get("reward") == want]
        verdicts: dict[str, int] = {}
        for row in subset:
            for cell in row["suites"].values():
                verdicts[cell["verdict"]] = verdicts.get(cell["verdict"], 0) + 1
        stats[label] = {"n_mutants": len(subset), "suite_verdicts": verdicts}
    broken = stats["oracle_broken"]["suite_verdicts"]
    total = sum(broken.values())
    stats["mutation_score"] = (broken.get("reject", 0) / total) if total else None
    stats["public_smoke_catches_broken"] = sum(
        1
        for r in rows
        if r["oracle"].get("reward") == 0
        and any(c.get("public_rc") not in (0, None) for c in r["suites"].values())
    )
    # Sensitivity without any oracle: does a suite notice a missing hunk?
    verdicts: dict[str, int] = {}
    per_base: dict[str, dict[str, int]] = {}
    for row in rows:
        for cell in row["suites"].values():
            verdicts[cell["verdict"]] = verdicts.get(cell["verdict"], 0) + 1
            key = f"{row['task']}|{row['base_trial']}"
            per_base.setdefault(key, {})
            per_base[key][cell["verdict"]] = per_base[key].get(cell["verdict"], 0) + 1
    stats["all_mutants_verdicts"] = verdicts
    stats["per_base"] = per_base
    total_any = sum(verdicts.values())
    stats["hunk_sensitivity"] = (
        verdicts.get("reject", 0) / total_any if total_any else None
    )
    (out_dir / (Path(args.store or "mutants.json").stem + "_report.json")).write_text(
        json.dumps(stats, indent=2) + "\n"
    )
    print(json.dumps(stats, indent=2))
    return 0


def stage_select(args: argparse.Namespace) -> int:
    """Leave-one-trial-out selection using only calibrated foreign suites.

    For each target candidate, a suite is calibrated on *other* labeled
    candidates from the same task. It must reject the baseline, split the
    calibration pool, contain both classes, and beat chance balanced accuracy.
    If no suite qualifies, the selector abstains and falls back to the first
    public-passing candidate (or first candidate when public was not run).
    """
    out_dir = Path(args.out)
    matrix = json.loads((out_dir / "matrix.json").read_text())
    per_task: dict[str, Any] = {}
    vote_truth: list[tuple[bool, bool]] = []

    for task, cells in sorted(matrix.items()):
        rows = list(cells.values())
        candidates: dict[str, dict[str, Any]] = {}
        ordered_candidates: list[str] = []
        by_suite: dict[str, dict[str, dict[str, Any]]] = {}
        baseline_reject: dict[str, bool] = {}

        for cell in rows:
            suite = cell["suite_trial"]
            candidate = cell["cand_trial"]
            verdict = suite_verdict(cell)
            if candidate == "BASELINE":
                baseline_reject[suite] = (
                    baseline_reject.get(suite, True) and verdict == "reject"
                )
                continue
            if candidate not in candidates:
                ordered_candidates.append(candidate)
                candidates[candidate] = {
                    "reward": cell.get("cand_reward"),
                    "job": cell.get("cand_job"),
                    "public_pass": cell.get("public_rc") == 0,
                }
            elif cell.get("public_rc") == 0:
                candidates[candidate]["public_pass"] = True
            if not cell.get("self") and suite != candidate:
                by_suite.setdefault(suite, {})[candidate] = {
                    "verdict": verdict,
                    "reward": cell.get("cand_reward"),
                }

        if not candidates:
            continue

        scores: dict[str, dict[str, Any]] = {}
        for target, meta in candidates.items():
            accepts = 0
            trusted = 0
            calibration: dict[str, Any] = {}
            for suite, verdicts in by_suite.items():
                if suite == target or target not in verdicts:
                    continue
                train = [
                    row
                    for candidate, row in verdicts.items()
                    if candidate != target and row["reward"] in (0, 1)
                ]
                positives = [r for r in train if r["reward"] == 1]
                negatives = [r for r in train if r["reward"] == 0]
                train_accepts = sum(r["verdict"] == "accept" for r in train)
                sensitivity = (
                    sum(r["verdict"] == "accept" for r in positives) / len(positives)
                    if positives
                    else None
                )
                specificity = (
                    sum(r["verdict"] == "reject" for r in negatives) / len(negatives)
                    if negatives
                    else None
                )
                balanced_accuracy = (
                    (sensitivity + specificity) / 2
                    if sensitivity is not None and specificity is not None
                    else None
                )
                qualifies = (
                    baseline_reject.get(suite, False)
                    and bool(positives)
                    and bool(negatives)
                    and 0 < train_accepts < len(train)
                    and balanced_accuracy is not None
                    and balanced_accuracy > 0.5
                )
                calibration[suite] = {
                    "qualifies": qualifies,
                    "n_train": len(train),
                    "n_positive": len(positives),
                    "n_negative": len(negatives),
                    "balanced_accuracy": balanced_accuracy,
                }
                if qualifies:
                    accepted = verdicts[target]["verdict"] == "accept"
                    accepts += int(accepted)
                    trusted += 1
                    if meta["reward"] in (0, 1):
                        vote_truth.append((accepted, bool(meta["reward"])))
            scores[target] = {
                **meta,
                "trusted_accepts": accepts,
                "trusted_suites": trusted,
                "score": accepts / trusted if trusted else None,
                "calibration": calibration,
            }

        eligible = [
            trial
            for trial, score in scores.items()
            if score["trusted_suites"] > 0 and score["public_pass"]
        ]
        if not eligible:
            eligible = [
                trial for trial, score in scores.items() if score["trusted_suites"] > 0
            ]

        abstained = not eligible
        if eligible:
            best = max(scores[trial]["score"] for trial in eligible)
            picked = [trial for trial in eligible if scores[trial]["score"] == best]
            decision = "trusted_foreign_suites"
        else:
            public = [
                trial for trial in ordered_candidates if candidates[trial]["public_pass"]
            ]
            picked = [(public or ordered_candidates)[0]]
            decision = "public_fallback" if public else "first_candidate_fallback"

        known_rewards = [
            value["reward"] for value in candidates.values() if value["reward"] in (0, 1)
        ]
        public_rewards = [
            value["reward"]
            for value in candidates.values()
            if value["public_pass"] and value["reward"] in (0, 1)
        ]
        picked_rewards = [
            scores[trial]["reward"]
            for trial in picked
            if scores[trial]["reward"] in (0, 1)
        ]
        per_task[task] = {
            "n_candidates": len(candidates),
            "pass1_random_pick": (
                sum(known_rewards) / len(known_rewards) if known_rewards else None
            ),
            "pass1_public_random_pick": (
                sum(public_rewards) / len(public_rewards) if public_rewards else None
            ),
            "abstained": abstained,
            "decision": decision,
            "picked": picked,
            "selected_expected_reward": (
                sum(picked_rewards) / len(picked_rewards) if picked_rewards else None
            ),
            "n_tied": len(picked),
            "scores": scores,
        }

    usable = [
        value
        for value in per_task.values()
        if value["pass1_random_pick"] is not None
        and value["selected_expected_reward"] is not None
    ]
    covered = [value for value in usable if not value["abstained"]]
    tp = sum(pred and truth for pred, truth in vote_truth)
    fp = sum(pred and not truth for pred, truth in vote_truth)
    fn = sum(not pred and truth for pred, truth in vote_truth)
    tn = sum(not pred and not truth for pred, truth in vote_truth)
    summary = {
        "per_task": per_task,
        "mean_pass1_random_pick": (
            sum(v["pass1_random_pick"] for v in usable) / len(usable) if usable else None
        ),
        "mean_pass1_public_random_pick": (
            sum(
                v["pass1_public_random_pick"]
                if v["pass1_public_random_pick"] is not None
                else v["pass1_random_pick"]
                for v in usable
            )
            / len(usable)
            if usable
            else None
        ),
        "mean_selected_reward": (
            sum(v["selected_expected_reward"] for v in usable) / len(usable) if usable else None
        ),
        "n_tasks": len(usable),
        "coverage": len(covered) / len(usable) if usable else None,
        "n_covered": len(covered),
        "n_abstained": len(usable) - len(covered),
        "trusted_vote_confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "trusted_vote_precision": tp / (tp + fp) if tp + fp else None,
        "trusted_vote_recall": tp / (tp + fn) if tp + fn else None,
    }
    path = out_dir / "select.json"
    path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=("pool", "run", "oracle", "report", "select", "mutants"))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--tasks-dir", default=str(DEFAULT_TASKS))
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--task", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--public", action="store_true", help="also run reproduce.py")
    parser.add_argument("--include-native", action="store_true")
    parser.add_argument("--include-archive", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--granularity", choices=("hunk", "run"), default="hunk")
    parser.add_argument(
        "--self-only",
        action="store_true",
        help="mutate each suite author's own patch and judge with its own suite",
    )
    parser.add_argument("--no-oracle", action="store_true")
    parser.add_argument("--store", default=None, help="output file name for mutants")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.stage == "pool":
        sources = [Path(s) for s in (args.source or DEFAULT_SOURCES)]
        pool = build_pool(sources, out_dir, args.include_archive)
        for task, entry in pool["tasks"].items():
            print(
                f"task {task}: {len(entry['candidates'])} patches "
                f"(pos={entry['n_pos']} neg={entry['n_neg']}) suites={entry['n_suites']}"
            )
        return 0
    if args.stage == "run":
        return stage_run(args)
    if args.stage == "oracle":
        return stage_oracle(args)
    if args.stage == "select":
        return stage_select(args)
    if args.stage == "mutants":
        return stage_mutants(args)
    return stage_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
