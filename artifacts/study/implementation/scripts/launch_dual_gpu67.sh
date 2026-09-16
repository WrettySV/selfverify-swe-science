#!/usr/bin/env bash
# Launch two TP=1 Qwen3.8 vLLM servers (GPU6→:8000, GPU7→:8001), then
# baseline + selfverify Pier jobs in nohup.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$ROOT/work/logs"
TASKS="${TASKS:-$ROOT/work/tasks-12}"
N_ATTEMPTS="${N_ATTEMPTS:-3}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-262144}"
SWE_SCIENCE_ROOT="${SWE_SCIENCE_ROOT:-/home/lukina/SWE-bench-Science/huggingface}"
RUN_VLLM="${RUN_VLLM:-/data/users/mazin/vllm-glm53-cybersecurity/scripts/run-qwen38-vllm.sh}"
IMAGE_NAME="${IMAGE_NAME:-vllm-qwen38-27b:0.28.0-cu129}"

mkdir -p "$LOG" "$ROOT/results/main"
chmod 600 /home/lukina/.config/swe-bench-science/vllm-qwen38-8000.env \
          /home/lukina/.config/swe-bench-science/vllm-qwen38-8001.env 2>/dev/null || true

export SWE_SCIENCE_ROOT
export PATH="${HOME}/.local/share/uv/tools/datacurve-pier/bin:${PATH}"
export PYTHONPATH="${ROOT}/src:${SWE_SCIENCE_ROOT}:${PYTHONPATH:-}"

wait_http() {
  local port="$1" name="$2" tries="${3:-180}"
  local i=0
  echo "Waiting for $name on :$port ..."
  while (( i < tries )); do
    if curl -sf "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1; then
      echo "OK: $name ready"
      curl -s "http://127.0.0.1:${port}/v1/models" | head -c 400; echo
      return 0
    fi
    sleep 5
    i=$((i + 1))
  done
  echo "ERROR: $name on :$port not ready after $((tries * 5))s" >&2
  return 1
}

if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
  echo "ERROR: image $IMAGE_NAME missing. Build first:" >&2
  echo "  bash /data/users/mazin/vllm-glm53-cybersecurity/scripts/build-qwen38-image.sh" >&2
  exit 1
fi

if [[ ! -d "$TASKS" ]] || [[ ! -f "$TASKS/selection.json" ]]; then
  echo "Materializing tasks → $TASKS"
  python3 "$ROOT/scripts/materialize_tasks.py" \
    --selection "$ROOT/selections/main-12.json" \
    --output "$TASKS" \
    --force \
    --swe-science-root "$SWE_SCIENCE_ROOT"
fi

# Start two independent TP=1 replicas (one agent-serving process per GPU).
start_one() {
  local gpu="$1" port="$2" name="$3"
  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    echo "Removing existing container $name"
    docker rm -f "$name" >/dev/null
  fi
  echo "Starting $name on GPU $gpu → :$port"
  CUDA_VISIBLE_DEVICES="$gpu" \
    DATA_PARALLEL_SIZE=1 TENSOR_PARALLEL_SIZE=1 \
    HOST_PORT="$port" CONTAINER_NAME="$name" \
    MAX_MODEL_LEN="$MAX_MODEL_LEN" \
    MAX_NUM_SEQS=4 \
    MTP_TOKENS=0 \
    bash "$RUN_VLLM"
}

start_one 6 8000 vllm-qwen38-gpu6-8000
start_one 7 8001 vllm-qwen38-gpu7-8001

wait_http 8000 "baseline-vLLM" 240
wait_http 8001 "selfverify-vLLM" 240

# Pier jobs — one condition per GPU/server.
echo "Launching baseline on :8000 (nohup)"
nohup python3 "$ROOT/scripts/run_experiment.py" \
  --condition baseline \
  --path "$TASKS" \
  --env-file /home/lukina/.config/swe-bench-science/vllm-qwen38-8000.env \
  --jobs-dir "$ROOT/results/main" \
  --job-name baseline-main12-n${N_ATTEMPTS} \
  --n-attempts "$N_ATTEMPTS" \
  --n-concurrent 1 \
  --model-context-window "$MAX_MODEL_LEN" \
  --swe-science-root "$SWE_SCIENCE_ROOT" \
  >"$LOG/baseline-main12.nohup.log" 2>&1 &
echo $! >"$LOG/baseline-main12.pid"
echo "baseline_pid=$(cat "$LOG/baseline-main12.pid")"

echo "Launching selfverify on :8001 (nohup)"
nohup python3 "$ROOT/scripts/run_experiment.py" \
  --condition selfverify \
  --path "$TASKS" \
  --env-file /home/lukina/.config/swe-bench-science/vllm-qwen38-8001.env \
  --jobs-dir "$ROOT/results/main" \
  --job-name selfverify-main12-n${N_ATTEMPTS} \
  --n-attempts "$N_ATTEMPTS" \
  --n-concurrent 1 \
  --verification-mode public-only \
  --max-verify-rounds 2 \
  --max-loop-seconds 4800 \
  --codex-stage-timeout-sec 3600 \
  --finalize-reserve-sec 180 \
  --model-context-window "$MAX_MODEL_LEN" \
  --swe-science-root "$SWE_SCIENCE_ROOT" \
  >"$LOG/selfverify-main12.nohup.log" 2>&1 &
echo $! >"$LOG/selfverify-main12.pid"
echo "selfverify_pid=$(cat "$LOG/selfverify-main12.pid")"

echo
echo "=== launched ==="
echo "logs: $LOG/"
echo "  baseline:   tail -f $LOG/baseline-main12.nohup.log"
echo "  selfverify: tail -f $LOG/selfverify-main12.nohup.log"
echo "  vLLM:       docker logs -f vllm-qwen38-gpu6-8000"
echo "              docker logs -f vllm-qwen38-gpu7-8001"
echo "stop jobs:    kill \$(cat $LOG/baseline-main12.pid) \$(cat $LOG/selfverify-main12.pid)"
echo "stop vLLM:    docker rm -f vllm-qwen38-gpu6-8000 vllm-qwen38-gpu7-8001"
