#!/usr/bin/env bash
# Launch baseline (:8000/GPU6) + selfverify (:8001/GPU7) assuming vLLM already up,
# OR start vLLM first with scripts/start_vllm_gpu67.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$ROOT/work/logs"
TASKS="${TASKS:-$ROOT/work/tasks-12}"
N_ATTEMPTS="${N_ATTEMPTS:-3}"
SWE_SCIENCE_ROOT="${SWE_SCIENCE_ROOT:-/home/lukina/SWE-bench-Science/huggingface}"
mkdir -p "$LOG" "$ROOT/results/main"
export SWE_SCIENCE_ROOT
export PATH="${HOME}/.local/share/uv/tools/datacurve-pier/bin:${PATH}"
export PYTHONPATH="${ROOT}/src:${SWE_SCIENCE_ROOT}:${PYTHONPATH:-}"
export DOCKER_DEFAULT_PLATFORM=linux/amd64

for port in 8000 8001; do
  curl -sf "http://127.0.0.1:${port}/v1/models" >/dev/null || {
    echo "ERROR: vLLM not ready on :$port — run scripts/start_vllm_gpu67.sh first" >&2
    exit 1
  }
done

nohup python3 "$ROOT/scripts/run_experiment.py" \
  --condition baseline --path "$TASKS" \
  --env-file /home/lukina/.config/swe-bench-science/vllm-qwen38-8000.env \
  --jobs-dir "$ROOT/results/main" --job-name "baseline-main12-n${N_ATTEMPTS}" \
  --n-attempts "$N_ATTEMPTS" --n-concurrent 1 --model-context-window 262144 \
  --swe-science-root "$SWE_SCIENCE_ROOT" \
  >"$LOG/baseline-main12.nohup.log" 2>&1 &
echo $! >"$LOG/baseline-main12.pid"

nohup python3 "$ROOT/scripts/run_experiment.py" \
  --condition selfverify --path "$TASKS" \
  --env-file /home/lukina/.config/swe-bench-science/vllm-qwen38-8001.env \
  --jobs-dir "$ROOT/results/main" --job-name "selfverify-main12-n${N_ATTEMPTS}" \
  --n-attempts "$N_ATTEMPTS" --n-concurrent 1 \
  --verification-mode public-only --max-verify-rounds 2 \
  --max-loop-seconds 4800 --codex-stage-timeout-sec 3600 --finalize-reserve-sec 180 \
  --model-context-window 262144 --swe-science-root "$SWE_SCIENCE_ROOT" \
  >"$LOG/selfverify-main12.nohup.log" 2>&1 &
echo $! >"$LOG/selfverify-main12.pid"

echo "baseline_pid=$(cat "$LOG/baseline-main12.pid")"
echo "selfverify_pid=$(cat "$LOG/selfverify-main12.pid")"
echo "logs under $LOG/"
