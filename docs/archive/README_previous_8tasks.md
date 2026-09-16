# Adaptive Verification for SWE-bench Science

This repository studies whether generated tests from one repair attempt can
help select among other candidate patches for scientific software bugs.

The method runs frozen generated suites across a candidate matrix, excludes
self-votes, abstains on unusable failures, and falls back to public-test-only
selection when no verifier signal is available.

For the research question, method, results and limitations, read
[`REPORT.md`](REPORT.md).

## Main completed result

The retrospective audit covers 8 tasks, 76 candidates, 21 suites and 280
suite-candidate executions.

| Selector | Task-macro expected reward |
| --- | ---: |
| Uniform candidate | 29.85% |
| Public random | 30.68% |
| First public | 37.50% |
| Foreign-suite vote | **41.15%** |
| Oracle pool ceiling | 50.00% |

This is exploratory development evidence, not a held-out or equal-budget
result. See `REPORT.md` before interpreting the number.

## Evaluated tasks

The completed experiment evaluates:

`001, 004, 007, 008, 017, 024, 039, 094`

The set covers multiple scientific domains and deliberately retains all-fail,
mixed and all-correct candidate pools so selection is not evaluated only on
favorable cases. Per-task results are listed in `REPORT.md`.

## Requirements

- Python 3.12
- Docker
- Pier 0.3.0
- SWE-bench Science task images
- an OpenAI-compatible model endpoint

The experiments used Qwen3.8-27B from
`/data/datasets/Qwen/Qwen3.8-27B`, served with vLLM 0.28.0.

## Setup

```bash
cd /home/lukina/selfverify-swe-science

export SWE_SCIENCE_ROOT=/home/lukina/SWE-bench-Science/huggingface
export PYTHONPATH="$PWD/src:$SWE_SCIENCE_ROOT:${PYTHONPATH:-}"

uv tool install --python 3.12 "datacurve-pier==0.3.0"

mkdir -p ~/.config/swe-bench-science
cp profiles/vllm-qwen38.env.example \
  ~/.config/swe-bench-science/vllm-qwen38.env
chmod 600 ~/.config/swe-bench-science/vllm-qwen38.env
```

Edit `CODEX_BASE_URL` if the endpoint differs. Codex
`model_context_window` and vLLM `--max-model-len` must match; the reported runs
use 262144.

## Start the model

The exact two-replica launch used for the main experiments is:

```bash
bash scripts/start_vllm_gpu67.sh
```

It starts TP=1 replicas on GPU 6/7 and ports 8000/8001 with BF16 weights,
FP8 KV cache, `max_model_len=262144`, `max_num_seqs=4`,
`reasoning_parser=qwen3`, and `tool_call_parser=qwen3_xml`.

## Reproduce the completed main analysis

The main reported result is deterministic analysis of the saved matrix; it does
not make new model calls:

```bash
cd /home/lukina/selfverify-swe-science
python3 scripts/cross_candidate_audit.py
python3 -m unittest discover \
  -s tests -p 'test_cross_candidate_audit.py' -v
```

Outputs:

- `analysis/crosscheck/label_free_audit.json`
- `analysis/crosscheck/label_free_audit.md`

The input matrix hash recorded by the audit is
`701f1a8f9d2504d6f20d23515ff3c36972d1e68d7722d8254b452689bf0141b9`.

## Run a new baseline

```bash
python3 scripts/materialize_tasks.py \
  --selection selections/verification-python-9.json \
  --output work/tasks-verification-python9 \
  --force

python3 scripts/run_experiment.py \
  --condition baseline \
  --path work/tasks-verification-python9 \
  --env-file ~/.config/swe-bench-science/vllm-qwen38.env \
  --jobs-dir results/main \
  --job-name baseline-python9 \
  --n-attempts 1 \
  --n-concurrent 1
```

## Run the implemented verifier

For one bounded contract-verification attempt:

```bash
python3 scripts/run_experiment.py \
  --condition selfverify \
  --verification-mode contract \
  --path work/tasks-verification-python9 \
  --env-file ~/.config/swe-bench-science/vllm-qwen38.env \
  --jobs-dir results/main \
  --job-name contract-python9 \
  --n-attempts 1 \
  --n-concurrent 1 \
  --max-loop-seconds 6000 \
  --test-design-timeout-sec 1800 \
  --repair-timeout-sec 900 \
  --verify-timeout-sec 60 \
  --max-repair-rounds 1 \
  --agent-timeout-multiplier 2
```

## Repository layout

```text
src/selfverify/                  verifier and repair implementation
scripts/                         experiment and analysis entry points
selections/                      frozen task panels
analysis/crosscheck/             completed matrix and audit
docs/                            protocol and task-selection details
REPORT.md                        research report
```

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Disclosure

- Evaluated model: Qwen3.8-27B through local vLLM
- Agent runtime: Codex through Pier
- Cursor-assisted implementation and report drafting
- Private benchmark tests are used only by the final verifier
