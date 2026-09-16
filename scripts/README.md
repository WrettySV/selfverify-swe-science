# Script guide

## Current nine-task study

Use **[run_study.py](run_study.py)** as the entry point. It either recalculates the published tables or, with `--new-tests`, generates and executes new verification. See [reproduction instructions](../docs/reproduction.md).

| File | Role |
|---|---|
| [run_study.py](run_study.py) | Coordinates execution and reporting |
| [analyze_results.py](analyze_results.py) | Verifies artifact hashes, applies the selector and computes tables |
| [run_verification.py](run_verification.py) | Prepares isolated task runs and executes verification jobs |
| [build_report.py](build_report.py) | Optional local utility to render a Markdown draft as PDF |

The study runner copies the recorded implementation from `artifacts/study/implementation/` into each new run directory. The paired A/B controller is `src/selfverify/paired.py` inside that implementation copy. This ensures that replay uses the implementation associated with the published results.

## Other experiment utilities

These tools remain available for development and earlier protocols; they are not extra steps required by `run_study.py`.

- `run_experiment.py`, `materialize_tasks.py`, `compare_conditions.py`: general task preparation, baseline/self-verification execution and comparison.
- `run_cross_pilot.py`, `resume_cross_pilot.py`, `evaluate_cross_pilot.py`: earlier cross-testing pilots.
- `crosscheck_suites.py`, `cross_candidate_audit.py`: archived-candidate analysis.
- `prepare_contract_pilot.py`, `report_contract_pilot.py`: contract-verification pilot tools.
- `pier-sv`, `pier_local_python`, `pier_prefer_import_path.py`: runtime adapters.
- `launch_*.sh`, `start_vllm_gpu67.sh`: local launch helpers whose paths and device assignments depend on the original host.

The development implementation is in `src/selfverify/`; reusable experiment settings and endpoint examples are in `configs/` and `profiles/`.
