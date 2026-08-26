#!/bin/bash
# start llama-server, wait for health, run $CMD, stop server
BIN=/home/user/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-server
MODEL=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
LOG="${SRV_LOG:-logs/srv-$(date +%H%M%S).log}"
echo "CMDLINE: $BIN -m $MODEL $*" > "$LOG"
$BIN -m "$MODEL" --host 127.0.0.1 --port 8099 "$@" >> "$LOG" 2>&1 &
PID=$!
for i in $(seq 1 240); do
  curl -sf http://127.0.0.1:8099/health >/dev/null 2>&1 && break
  kill -0 $PID 2>/dev/null || { echo "SERVER DIED, patrz $LOG"; tail -20 "$LOG"; exit 1; }
  sleep 1
done
echo "SERVER UP (pid $PID, log $LOG)"
