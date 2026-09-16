# Reproduction

Run commands from the repository root. Tasks: 001, 007, 008, 017, 024, 039, 053, 094, 107.

## Recalculate the tables

Requires Python 3.12 or later.

```bash
python3 scripts/run_study.py --out work/study-results
```

Read `work/study-results/results.md` for the tables and `metrics.json` for the counts. This command uses saved results and does not call the model.

## Generate new tests

Requires Linux, Docker, Python 3.12, `uv`, the SWE-bench Science release and Qwen3.8-27B running through vLLM. The benchmark directory must contain `scripts/run_batch.py`.

Install the dependencies and copy the model configuration:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
uv tool install --python 3.12 'datacurve-pier==0.3.0'
cp profiles/vllm-qwen38.env.example model.env
chmod 600 model.env
```

In `model.env`, set `CODEX_BASE_URL` to the endpoint address reachable from Docker. Keep `CODEX_VERSION=0.154.0` and `CODEX_REASONING_EFFORT=xhigh`. The model server and agent must both use a 262,144-token context window. The model revision and vLLM settings are in `artifacts/model_config.json`.

```bash
.venv/bin/python scripts/run_study.py --new-tests \
  --science-root /path/to/SWE-bench-Science/huggingface \
  --env-file model.env \
  --out work/study-new-tests
```

Replace the benchmark path with your local directory. Use a new output directory for each run. Add `--task 007` for one task or `--check` to prepare without model calls.

Each task starts with three supplied repairs. The command generates new tests, runs them on the repairs, allows A to revise its answer and computes B's selection. Limits are 30 minutes for test generation, 15 minutes for one revision and 60 seconds per test. The complete limits and recorded token usage are in `artifacts/study/data.json`.

## Check the results

```bash
python3 -m unittest discover -s tests -p test_study.py -v
```

Optional local report rendering (`scripts/build_report.py`) is a development utility and is not part of the published repository contents.

## Scientist→Engineer side comparison (optional)

Same nine tasks; generation-time role split reported in REPORT.md §5 Table 3.
Packaged briefs and metrics: `artifacts/scientist_engineer/`.

```bash
.venv/bin/python -m pip install -e '.[scientist-engineer]'
# materialize tasks 001,007,008,017,024,039,053,094,107 into work/tasks-scientist-engineer-9
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 DATA_PARALLEL_SIZE=8 \
  ./scripts/start_vllm_qwen38_se.sh   # or any Qwen3.8 endpoint in model.env
.venv/bin/python scripts/run_se_experiment.py --condition se \
  --tasks work/tasks-scientist-engineer-9 \
  --env-file model.env \
  --job-name se-rerun \
  --scientist-model Qwen3.8-27B --model Qwen3.8-27B \
  --n-concurrent 8 --n-attempts 2
```

This path is separate from `run_study.py` (A/B verification).