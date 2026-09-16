# Adaptive Verification for SWE-bench Science

The default `contract` mode creates small requirement-based tests on the
original source **before seeing a candidate patch**, freezes the tests, and
repairs the candidate using concrete failures. Tests that pass on the original
code remain regression checks. Infrastructure failures are not semantic evidence.

`requirements → frozen tests → saved candidate or draft → verify → repair → verify → selected patch`

See [docs/contract-verification.md](docs/contract-verification.md) for the current
protocol, budgets, saved-baseline pilot and reporting commands. Effectiveness is
not yet established. The experimental [`review` mode](docs/review-verification.md)
audits an existing patch even when tests pass, then attempts a checked repair. The older `public-only`, `adaptive` and `full` modes remain
available for comparisons; offline foreign-suite selection is separate.

This repo does **not** fork the benchmark. It wraps
[OpenMOSS/SWE-bench-Science](https://github.com/OpenMOSS/SWE-bench-Science)
through Pier’s `--agent-import-path`.

Paper (benchmark): https://arxiv.org/abs/2608.19799  
Dataset: https://huggingface.co/datasets/OpenMOSS-Team/SWE-bench-Science

---

## Research question

Can independent, adaptive verification improve scientific patch selection per
unit of compute, and can the verifier identify when it should abstain?

The original question—whether an agent benefits from testing its own patch with
its own generated invariants—is retained as a negative/diagnostic ablation.
Existing trials showed internally green suites with official reward 0, while
suite generation and challenge consumed most of the wall time.

### Design choices

| Choice | Decision |
| --- | --- |
| Initial sample | **4 tasks × 1 trial**, expand only after a positive signal |
| Online default | Frozen requirement tests + candidate verification + bounded repair |
| Offline adaptive signal | Trusted foreign suites with explicit abstention |
| Full SV | Preserved as an ablation, not the default |
| Base class | `ScienceBenchCodex` (amd64 Codex install fix) |
| Model | **Qwen3.8-27B** via local vLLM |
| Analysis slices | **Domain** (and language) only — no paradigm claims |
| Context window | vLLM `max_model_len` **and** Codex `model_context_window` = **262144** |

See [docs/context-window.md](docs/context-window.md) and
[docs/pier-lifecycle.md](docs/pier-lifecycle.md).

---

## Layout

```text
src/selfverify/
  agent.py              # SelfVerifyCodex(ScienceBenchCodex)
  provider_overlay.py   # config.toml + model_context_window
  parser.py / logging.py
  contract.py           # frozen tests, feedback, candidate selection
  contract_runtime.py   # isolated original/candidate checks
  metrics.py            # token totals across all conversations
  stages/               # legacy invariant run helpers
  prompts/              # invariant_generation.md, feedback.md
scripts/                # materialize, run, compare
selections/main-12.json
configs/
analysis/
docs/
```

---

## Setup

```bash
# 1) Benchmark tools (existing clone is fine)
#    /home/lukina/SWE-bench-Science/huggingface
export SWE_SCIENCE_ROOT=/home/lukina/SWE-bench-Science/huggingface

uv tool install --python 3.12 "datacurve-pier==0.3.0"
docker login

# 2) This project — Pier loads the agent via PYTHONPATH (set by run_experiment.py).
#    Editable install is optional:
#      pip install -e .   # needs network for build deps
cd /home/lukina/selfverify-swe-science
export PYTHONPATH="/home/lukina/selfverify-swe-science/src:${SWE_SCIENCE_ROOT}:${PYTHONPATH}"

# 3) Provider profile (outside the repo)
mkdir -p ~/.config/swe-bench-science
cp profiles/vllm-qwen38.env.example ~/.config/swe-bench-science/vllm-qwen38.env
chmod 600 ~/.config/swe-bench-science/vllm-qwen38.env
# edit CODEX_BASE_URL / MODEL if needed
```

### Start vLLM (Qwen3.8-27B)

```bash
CUDA_VISIBLE_DEVICES=6,7 \
  DATA_PARALLEL_SIZE=2 TENSOR_PARALLEL_SIZE=1 HOST_PORT=8001 \
  MAX_MODEL_LEN=262144 \
  bash /data/users/mazin/vllm-glm53-cybersecurity/scripts/run-qwen38-vllm.sh
```

**Both** `--max-model-len` and Codex `model_context_window` must be 262144
(or the same lower value if VRAM forces it). Do not leave Codex on the
~258400 fallback while vLLM is at 128k.

---

## How to run

```bash
# 1. Materialize 12 tasks
python3 scripts/materialize_tasks.py \
  --selection selections/main-12.json \
  --output work/tasks-12 \
  --force

# 2. Baseline (ScienceBenchCodex, no self-verify)
python3 scripts/run_experiment.py \
  --condition baseline \
  --path work/tasks-12 \
  --env-file ~/.config/swe-bench-science/vllm-qwen38.env \
  --jobs-dir results/main \
  --job-name baseline-main12-n3 \
  --n-attempts 3

# 3. Earlier public-only comparison (explicit mode)
python3 scripts/run_experiment.py \
  --condition selfverify \
  --path work/tasks-12 \
  --env-file ~/.config/swe-bench-science/vllm-qwen38.env \
  --jobs-dir results/main \
  --job-name public-only-main12-n3 \
  --n-attempts 3 \
  --verification-mode public-only \
  --max-loop-seconds 4800 \
  --codex-stage-timeout-sec 3600

# Original expensive loop (ablation only)
python3 scripts/run_experiment.py \
  --condition selfverify \
  --path work/tasks-12 \
  --env-file ~/.config/swe-bench-science/vllm-qwen38.env \
  --job-name sv-full-ablation \
  --verification-mode full \
  --max-verify-rounds 3 \
  --max-loop-seconds 9000 \
  --agent-timeout-multiplier 2.0

# 4. Compare Pass@1 + tokens
python3 scripts/compare_conditions.py \
  --baseline results/main/baseline-main12-n3 \
  --selfverify results/main/selfverify-main12-n3 \
  --out results/main/compare.json
```

Pilot (4 tasks):

```bash
python3 scripts/materialize_tasks.py \
  --selection selections/pilot-4.json \
  --output work/tasks-pilot4 --force
```

---

## Cost table (what we report)

| Condition | Pass@1 | Total tokens | Tokens per solve |
| --- | --- | --- | --- |
| Baseline | p_B | T_B | T_B / n_solves_B |
| Public-only | p_P | T_P | T_P / n_solves_P |
| SV-full ablation | p_S | T_S | T_S / n_solves_S |
| Adaptive selector | p_A | verifier coverage | abstention rate |

No extra budget sweeps — just compute from Pier `result.json` /
trajectory metrics and state the tradeoff honestly.

---

## Pier wiring

```bash
# Baseline (run_batch default)
--agent-import-path scripts.pier_adapters:ScienceBenchCodex

# Earlier public-only comparison
--agent-import-path selfverify.agent:SelfVerifyCodex \
--agent-kwarg verification_mode=public-only
```

`model.patch` is still produced by Pier’s `pre_artifacts.sh` **after**
`SelfVerifyCodex.run()` returns (git diff of the workspace). Private tests
remain in the verifier image only.

---

## Disclosed LLMs

- Qwen3.8-27B (local vLLM gateway)
- Claude/GPT-class models may have been used to author this repository

## Limitations

- n=12 tasks, 3 trials — underpowered for strong claims
- Self-generated tests can reject the baseline yet accept incorrect foreign patches
- Selector metrics are exploratory and use historical labels for leave-one-out calibration
- Always read Pass@1 with tokens/solve, coverage, abstention, and tie counts
