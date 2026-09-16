# Context window alignment: Codex ↔ vLLM

## What went wrong in SE-enh

In the previous multi-agent pilot, every Codex rollout logged:

```text
model_context_window: 258400
```

That value is **not** from vLLM. For unknown / non-OpenAI model slugs, Codex
falls back to built-in metadata (~272k × ~95% effective ≈ 258400). Meanwhile
the local vLLM servers were started with `--max-model-len 131072`, and
`peak_context_tokens` in failed trials hit **exactly 131072**.

So Codex planned as if it had ~252k, and the server cut at 128k.

## Correct defaults for this project (Qwen3.8-27B)

| Layer | Setting | Value |
| --- | --- | ---: |
| vLLM | `--max-model-len` | **262144** |
| Codex `config.toml` | `model_context_window` | **262144** |

Yes: set **both** to 262144. Matching matters more than the exact number.
If VRAM forces a lower vLLM cap (e.g. 131072 on TP=1), set Codex to the
**same** lower number — never leave Codex on the 258400 fallback.

### Launch example (2 GPUs, DP=2, TP=1)

```bash
CUDA_VISIBLE_DEVICES=6,7 \
  DATA_PARALLEL_SIZE=2 TENSOR_PARALLEL_SIZE=1 HOST_PORT=8001 \
  MAX_MODEL_LEN=262144 \
  bash /data/users/mazin/vllm-glm53-cybersecurity/scripts/run-qwen38-vllm.sh
```

Or directly:

```bash
vllm serve /data/datasets/Qwen/Qwen3.8-27B \
  --served-model-name Qwen3.8-27B \
  --dtype bfloat16 \
  --tensor-parallel-size 1 \
  --data-parallel-size 2 \
  --max-model-len 262144 \
  --kv-cache-dtype fp8 \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_xml \
  --enable-auto-tool-choice
```

Without `--tool-call-parser` + `--enable-auto-tool-choice`, Qwen3.8 emits
`<tool_call>` as plain text and Codex never executes tools (empty patches).
SE’s Qwen3.6 recipe used `--tool-call-parser qwen3_coder` for the same reason.
Prefer `scripts/start_vllm_gpu67.sh`, which already sets the Qwen3.8 flags.

### Codex config.toml snippet

`scripts/run_experiment.py` renders config via
`selfverify.provider_overlay` and passes it as `--agent-kwarg config_toml=…`,
including `model_context_window` from `CODEX_MODEL_CONTEXT_WINDOW` (default
**262144**).

```toml
model_provider = "science_bench_gateway"
model_context_window = 262144

[model_providers.science_bench_gateway]
name = "SWE-bench Science Gateway"
base_url = "http://172.17.0.1:8001/v1"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
```

## How to verify after one trial

1. In the agent session JSONL `task_started` event, `model_context_window`
   should be **262144** (or your chosen matched value), not 258400.
2. `peak_context_tokens` must stay **≤** that value; if it pins exactly to
   131072 while Codex claims 262144, the vLLM server is still on the old cap —
   restart vLLM.
