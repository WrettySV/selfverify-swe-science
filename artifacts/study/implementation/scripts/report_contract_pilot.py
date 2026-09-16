#!/usr/bin/env python3
"""Compare saved starting candidates with official outcomes and all-session cost."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from selfverify.metrics import collect_session_usage


def read(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--job", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    manifest = read(args.pilot / "manifest.json", {})
    originals = {c["task"]: c for c in manifest["candidates"]}
    rows = []
    for job in args.job:
        for trial in sorted(job.glob("task_*")):
            task = trial.name.split("__")[0].removeprefix("task_")
            if task not in originals:
                continue
            before = originals[task]
            summary = read(trial / "agent/selfverify_summary.json", {})
            state = summary.get("contract", {})
            reward = read(trial / "verifier/reward.json", {}).get("reward")
            usage = collect_session_usage(trial / "agent")
            log = trial / "agent/selfverify/run_log.jsonl"
            events = []
            if log.exists():
                for line in log.read_text().splitlines():
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        pass
            initial = state.get("initial_patch_sha256")
            same_candidate = initial == before["patch_sha256"] if initial else None
            artifact = trial / "artifacts/model.patch"
            selected = state.get("selected", {})
            final_hash = hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact.exists() else None
            rows.append({"task": task, "job": job.name, "trial": trial.name,
                         "reward_before": before["recorded_reward"], "reward_after": reward,
                         "same_initial_candidate": same_candidate,
                         "final_matches_selected": final_hash == selected.get("sha256") if final_hash and selected else None,
                         "last_event": events[-1] if events else None,
                         "repair_turns": sum(e.get("stage") in {"contract_repair", "review_repair"} and e.get("status") == "begin" for e in events),
                         "review": state.get("review"),
                         "initial_assessment": (state.get("candidates") or [{}])[0].get("assessment"),
                         "selected_assessment": state.get("selected_assessment"),
                         "suite_sha256": (state.get("suite") or {}).get("sha256"),
                         "tokens": usage["totals"], "usage_complete": usage["complete"],
                         "n_sessions": usage["n_sessions"]})
    scored = [r for r in rows if r["reward_after"] in (0, 1) and r["same_initial_candidate"]]
    result = {"trials": rows, "n_scored_matching_candidates": len(scored),
              "improved_0_to_1": sum(r["reward_before"] == 0 and r["reward_after"] == 1 for r in scored),
              "regressed_1_to_0": sum(r["reward_before"] == 1 and r["reward_after"] == 0 for r in scored),
              "not_started": sorted(set(originals) - {r["task"] for r in rows}),
              "note": "Pilot diagnosis only. A continuation control at equal additional budget is needed for attribution."}
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
