#!/usr/bin/env bash
# Start local Qwen3.8-27B vLLM with explicit GPU/parallelism settings.
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-vllm-qwen38-27b:0.28.0-cu129}"
MODEL_DIR="${MODEL_DIR:-/data/datasets/Qwen/Qwen3.8-27B}"
CONTAINER_NAME="${CONTAINER_NAME:-vllm-qwen38-se-main9}"
HOST_PORT="${HOST_PORT:-8004}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-1}"
DATA_PARALLEL_SIZE="${DATA_PARALLEL_SIZE:-4}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-262144}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-16}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-32768}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.92}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-Qwen3.8-27B}"
MTP_TOKENS="${MTP_TOKENS:-3}"

if [[ -z "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  echo "ERROR: set CUDA_VISIBLE_DEVICES explicitly." >&2
  exit 1
fi

IFS=',' read -r -a gpu_array <<<"${CUDA_VISIBLE_DEVICES}"
expected_gpus=$((TENSOR_PARALLEL_SIZE * DATA_PARALLEL_SIZE))
if [[ "${#gpu_array[@]}" -ne "${expected_gpus}" ]]; then
  echo "ERROR: TP=${TENSOR_PARALLEL_SIZE} × DP=${DATA_PARALLEL_SIZE} needs ${expected_gpus} GPUs." >&2
  exit 1
fi
[[ -f "${MODEL_DIR}/config.json" ]] || { echo "ERROR: missing ${MODEL_DIR}/config.json" >&2; exit 1; }
docker image inspect "${IMAGE_NAME}" >/dev/null
if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "ERROR: container ${CONTAINER_NAME} already exists." >&2
  exit 1
fi

args=(
  --model /model
  --served-model-name "${SERVED_MODEL_NAME}"
  --host 0.0.0.0
  --port 8000
  --dtype bfloat16
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}"
  --data-parallel-size "${DATA_PARALLEL_SIZE}"
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}"
  --max-model-len "${MAX_MODEL_LEN}"
  --max-num-seqs "${MAX_NUM_SEQS}"
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}"
  --kv-cache-dtype fp8
  --enable-prefix-caching
  --reasoning-parser qwen3
  --tool-call-parser qwen3_xml
  --enable-auto-tool-choice
)
if [[ "${MTP_TOKENS}" -gt 0 ]]; then
  args+=(--speculative-config "{\"method\":\"qwen3_5_mtp\",\"num_speculative_tokens\":${MTP_TOKENS}}")
fi

echo "Qwen3.8: GPUs=${CUDA_VISIBLE_DEVICES}; TP=${TENSOR_PARALLEL_SIZE}; DP=${DATA_PARALLEL_SIZE}; port=${HOST_PORT}; context=${MAX_MODEL_LEN}"
exec docker run -d \
  --name "${CONTAINER_NAME}" \
  --gpus "\"device=${CUDA_VISIBLE_DEVICES}\"" \
  --ipc=host \
  --shm-size=16g \
  -e CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES}" \
  -p "${HOST_PORT}:8000" \
  -v "${MODEL_DIR}:/model:ro" \
  "${IMAGE_NAME}" \
  "${args[@]}"
