#!/usr/bin/env bash
# Correct CUDA mapping: --gpus device=N + CUDA_VISIBLE_DEVICES=0 inside.
set -euo pipefail
IMAGE=vllm-qwen38-27b:0.28.0-cu129
MODEL=/data/datasets/Qwen/Qwen3.8-27B
MAX_MODEL_LEN=${MAX_MODEL_LEN:-262144}
start_one() {
  local phys="$1" port="$2" name="$3"
  docker rm -f "$name" 2>/dev/null || true
  docker run -d --name "$name" --gpus "device=${phys}" --ipc=host --shm-size=16g \
    -e CUDA_VISIBLE_DEVICES=0 -p "${port}:8000" -v "${MODEL}:/model:ro" "$IMAGE" \
    --model /model --served-model-name Qwen3.8-27B --host 0.0.0.0 --port 8000 \
    --dtype bfloat16 --tensor-parallel-size 1 --gpu-memory-utilization 0.92 \
    --max-model-len "$MAX_MODEL_LEN" --max-num-seqs 4 --kv-cache-dtype fp8 \
    --reasoning-parser qwen3 \
    --tool-call-parser qwen3_xml \
    --enable-auto-tool-choice
}
start_one 6 8000 vllm-qwen38-gpu6-8000
start_one 7 8001 vllm-qwen38-gpu7-8001
