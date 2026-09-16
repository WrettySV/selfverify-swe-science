#!/usr/bin/env python3
"""Run Scientist→Engineer (or B0/B1) on a materialized SWE-bench Science selection.

This is the generation-time role-split experiment reported as a side comparison
in REPORT.md §5 Table 3. It is not part of the A/B cross-candidate verification
protocol (`scripts/run_study.py`).

Example (after materializing tasks and starting vLLM):

  .venv/bin/python scripts/run_se_experiment.py --condition se \\
    --tasks work/tasks-scientist-engineer-9 \\
    --env-file model.env \\
    --job-name se-qwen38-main9-n2 \\
    --scientist-model Qwen3.8-27B \\
    --model Qwen3.8-27B \\
    --n-concurrent 8 --n-attempts 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from selfverify.scientist_engineer import RESULTS_DIR, WORK_DIR
from selfverify.scientist_engineer.env_file import apply_env_file
from selfverify.scientist_engineer.pier_runner import run_batch
from selfverify.scientist_engineer.prepare import prepare_condition_tree
from selfverify.scientist_engineer.revise import collect_public_feedback
from selfverify.scientist_engineer.scientist import revise_scientist, run_scientist


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", choices=("b0", "b1", "se"), required=True)
    parser.add_argument(
        "--tasks",
        type=Path,
        default=WORK_DIR / "tasks-scientist-engineer-9",
        help="Materialized task tree (task_*/instruction.md).",
    )
    parser.add_argument("--agent", default="codex")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=ROOT / "model.env",
    )
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--n-concurrent", type=int, default=1)
    parser.add_argument("--n-attempts", type=int, default=2)
    parser.add_argument("--model", action="append", default=None)
    parser.add_argument("--scientist-model", default=None)
    parser.add_argument(
        "--scientist-only",
        action="store_true",
        help="For condition=se, only write scientist briefs (skip Pier).",
    )
    parser.add_argument(
        "--force-scientist",
        action="store_true",
        help="Regenerate scientist briefs even if scientist_brief.json exists.",
    )
    parser.add_argument(
        "--no-inventory",
        action="store_true",
        help="Skip Docker read-only repo inventory for Scientist.",
    )
    parser.add_argument(
        "--no-verify-brief",
        action="store_true",
        help="Skip second-LLM brief verification loop.",
    )
    parser.add_argument(
        "--revise-rounds",
        type=int,
        default=0,
        help="After Pier, revise briefs on public fail and re-run Engineer (SE only).",
    )
    parser.add_argument(
        "--revise-n-attempts",
        type=int,
        default=1,
        help="Pier n_attempts for each revise round (default 1).",
    )
    args = parser.parse_args()

    if not args.tasks.is_dir():
        raise SystemExit(
            f"missing materialized tasks: {args.tasks} "
            "(materialize via SWE-bench-Science huggingface/scripts/materialize.py "
            "or scripts/materialize_tasks.py)"
        )

    env_file = args.env_file if args.env_file.is_file() else None
    if args.env_file and not args.env_file.is_file():
        print(f"warning: env-file not found: {args.env_file}", flush=True)
    loaded = apply_env_file(env_file)
    scientist_model = (
        args.scientist_model
        or loaded.get("MODEL")
        or os.environ.get("MODEL")
        or "Qwen3.8-27B"
    )

    job_dir = RESULTS_DIR / args.job_name
    job_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "condition": args.condition,
        "agent": args.agent,
        "tasks": str(args.tasks),
        "env_file": str(env_file) if env_file else None,
        "scientist_model": scientist_model if args.condition == "se" else None,
        "force_scientist": args.force_scientist,
        "with_inventory": not args.no_inventory,
        "verify_brief": not args.no_verify_brief,
        "revise_rounds": args.revise_rounds if args.condition == "se" else 0,
        "revise_n_attempts": args.revise_n_attempts,
        "enhanced": args.condition == "se"
        and (not args.no_inventory or args.revise_rounds > 0),
        "experiment": "scientist_engineer_side_comparison",
    }
    (job_dir / "experiment.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    briefs_dir = job_dir / "scientist"
    prepared = WORK_DIR / f"tasks-{args.job_name}"

    if args.condition == "se":
        from concurrent.futures import ThreadPoolExecutor, as_completed

        todo: list[tuple[str, Path, Path]] = []
        for task_dir in sorted(args.tasks.glob("task_*")):
            task_id = task_dir.name.removeprefix("task_")
            out = briefs_dir / task_id
            if (out / "scientist_brief.json").is_file() and not args.force_scientist:
                print(f"skip existing brief {task_id}", flush=True)
                continue
            todo.append((task_id, task_dir, out))

        def _one(task_id: str, task_dir: Path, out: Path) -> str:
            print(f"scientist -> {task_id}", flush=True)
            run_scientist(
                task_dir=task_dir,
                task_id=task_id,
                model=scientist_model,
                out_dir=out,
                with_inventory=not args.no_inventory,
                verify=not args.no_verify_brief,
            )
            return task_id

        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=max(1, args.n_concurrent)) as pool:
            futs = {pool.submit(_one, *item): item[0] for item in todo}
            for fut in as_completed(futs):
                tid = futs[fut]
                try:
                    print(f"scientist done {fut.result()}", flush=True)
                except Exception as exc:
                    failures.append(tid)
                    print(f"scientist FAILED {tid}: {exc!r}", flush=True)
        if failures:
            raise SystemExit(f"scientist failed for tasks: {sorted(failures)}")
        if args.scientist_only:
            print(f"scientist briefs written under {briefs_dir}")
            return 0

    prepare_condition_tree(
        source_tasks=args.tasks,
        dest_tasks=prepared,
        condition=args.condition,
        briefs_dir=briefs_dir if args.condition == "se" else None,
    )

    code = run_batch(
        tasks_path=prepared,
        agent=args.agent,
        jobs_dir=RESULTS_DIR,
        job_name=args.job_name,
        env_file=args.env_file,
        n_concurrent=args.n_concurrent,
        n_attempts=args.n_attempts,
        model=args.model,
    )

    if args.condition != "se" or args.revise_rounds <= 0:
        return code

    from selfverify.scientist_engineer.revise import (
        latest_trials_by_task,
        load_reward,
        public_passed,
    )

    for round_i in range(1, args.revise_rounds + 1):
        scan_dirs = [job_dir] + [
            RESULTS_DIR / f"{args.job_name}-r{i}" for i in range(1, round_i)
        ]
        merged: dict[str, Path] = {}
        for scan in scan_dirs:
            if not scan.is_dir():
                continue
            for tid, trial in latest_trials_by_task(scan).items():
                prev = merged.get(tid)
                if prev is None or trial.stat().st_mtime >= prev.stat().st_mtime:
                    merged[tid] = trial
        need = {
            tid: trial
            for tid, trial in merged.items()
            if public_passed(load_reward(trial)) is False
            or (
                public_passed(load_reward(trial)) is None
                and (trial / "exception.txt").is_file()
            )
        }

        if not need:
            print(f"revise round {round_i}: nothing to revise", flush=True)
            break

        print(f"revise round {round_i}: {sorted(need)}", flush=True)
        for task_id, trial in sorted(need.items()):
            task_dir = args.tasks / f"task_{task_id}"
            out = briefs_dir / task_id
            prior_path = out / "scientist_brief.json"
            prior = json.loads(prior_path.read_text(encoding="utf-8"))
            feedback = collect_public_feedback(trial)
            print(f"scientist revise -> {task_id} (from {trial.name})", flush=True)
            revise_scientist(
                task_dir=task_dir,
                task_id=task_id,
                model=scientist_model,
                out_dir=out,
                prior_brief=prior,
                public_feedback=feedback,
            )

        revise_job = f"{args.job_name}-r{round_i}"
        revise_prepared = WORK_DIR / f"tasks-{revise_job}"
        prepare_condition_tree(
            source_tasks=args.tasks,
            dest_tasks=revise_prepared,
            condition="se",
            briefs_dir=briefs_dir,
            only_task_ids=set(need),
        )
        rcode = run_batch(
            tasks_path=revise_prepared,
            agent=args.agent,
            jobs_dir=RESULTS_DIR,
            job_name=revise_job,
            env_file=args.env_file,
            n_concurrent=args.n_concurrent,
            n_attempts=args.revise_n_attempts,
            model=args.model,
        )
        if rcode != 0:
            code = rcode

    return code


if __name__ == "__main__":
    raise SystemExit(main())
