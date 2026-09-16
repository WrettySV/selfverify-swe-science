#!/usr/bin/env bash
# Launch hardened Self-Verify n=2: hard (baseline-fail) tasks first, then rest.
# GPU6→:8000, GPU7→:8001. Detach-safe (intended under nohup).
set -euo pipefail

ROOT=/home/lukina/selfverify-swe-science
cd "$ROOT"
mkdir -p work/logs
export PYTHONPATH="$ROOT/src:/home/lukina/SWE-bench-Science/huggingface:${PYTHONPATH:-}"

run_one() {
  local path=$1 env=$2 job=$3 log=$4 pidfile=$5
  echo "[$(date -Is)] START $job path=$path" | tee -a work/logs/n2v2-launcher.log
  nohup python3 scripts/run_experiment.py \
    --condition selfverify \
    --path "$path" \
    --env-file "$env" \
    --jobs-dir results/main \
    --job-name "$job" \
    --n-attempts 2 \
    --n-concurrent 1 \
    --verification-mode public-only \
    --max-verify-rounds 2 \
    --max-loop-seconds 4800 \
    --codex-stage-timeout-sec 3600 \
    --finalize-reserve-sec 180 \
    --agent-timeout-multiplier 1.0 \
    --model-context-window 262144 \
    --swe-science-root /home/lukina/SWE-bench-Science/huggingface \
    --skip-pull \
    > "$log" 2>&1 &
  echo $! > "$pidfile"
  echo "[$(date -Is)] pid=$(cat "$pidfile") log=$log" | tee -a work/logs/n2v2-launcher.log
}

wait_pidfile() {
  local pidfile=$1 name=$2
  local pid
  pid=$(cat "$pidfile")
  echo "[$(date -Is)] waiting $name pid=$pid" | tee -a work/logs/n2v2-launcher.log
  # pid may be a sibling of a background waiter; do not use bash `wait`.
  while kill -0 "$pid" 2>/dev/null; do
    sleep 60
  done
  echo "[$(date -Is)] DONE $name pid=$pid (process exited)" | tee -a work/logs/n2v2-launcher.log
}

echo "[$(date -Is)] === WAVE1 hard (baseline μ=0) ===" | tee -a work/logs/n2v2-launcher.log
run_one work/tasks-n2v2-hard-gpu6 \
  /home/lukina/.config/swe-bench-science/vllm-qwen38-8000.env \
  selfverify-n2v2-hard-gpu6 \
  work/logs/selfverify-n2v2-hard-gpu6.nohup.log \
  work/logs/selfverify-n2v2-hard-gpu6.pid

run_one work/tasks-n2v2-hard-gpu7 \
  /home/lukina/.config/swe-bench-science/vllm-qwen38-8001.env \
  selfverify-n2v2-hard-gpu7 \
  work/logs/selfverify-n2v2-hard-gpu7.nohup.log \
  work/logs/selfverify-n2v2-hard-gpu7.pid

wait_pidfile work/logs/selfverify-n2v2-hard-gpu6.pid hard-gpu6 &
w1=$!
wait_pidfile work/logs/selfverify-n2v2-hard-gpu7.pid hard-gpu7 &
w2=$!
wait "$w1" "$w2"

echo "[$(date -Is)] === WAVE2 rest (007 + baseline passes) ===" | tee -a work/logs/n2v2-launcher.log
run_one work/tasks-n2v2-rest-gpu6 \
  /home/lukina/.config/swe-bench-science/vllm-qwen38-8000.env \
  selfverify-n2v2-rest-gpu6 \
  work/logs/selfverify-n2v2-rest-gpu6.nohup.log \
  work/logs/selfverify-n2v2-rest-gpu6.pid

run_one work/tasks-n2v2-rest-gpu7 \
  /home/lukina/.config/swe-bench-science/vllm-qwen38-8001.env \
  selfverify-n2v2-rest-gpu7 \
  work/logs/selfverify-n2v2-rest-gpu7.nohup.log \
  work/logs/selfverify-n2v2-rest-gpu7.pid

wait_pidfile work/logs/selfverify-n2v2-rest-gpu6.pid rest-gpu6 &
w3=$!
wait_pidfile work/logs/selfverify-n2v2-rest-gpu7.pid rest-gpu7 &
w4=$!
wait "$w3" "$w4"

echo "[$(date -Is)] === ALL WAVES COMPLETE ===" | tee -a work/logs/n2v2-launcher.log
