#!/bin/bash
# $1 = tag, $2 = v cache type   -- katalog roboczy ~/gate (nie /tmp, bo tmpfs)
set -e
TAG=$1; VT=$2
D=$HOME/gate
B=$HOME/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-server
M=$HOME/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
MM=$HOME/llm/models/unsloth/Qwen3.8-27B-GGUF/mmproj-Q8_0.gguf
export RADV_PERFTEST=nogttspill
$B --model $M --mmproj $MM --alias g --ctx-size 131072 --n-gpu-layers 99 \
  --cache-type-k q8_0 --cache-type-v $VT --cache-type-k-draft q8_0 --cache-type-v-draft $VT \
  --batch-size 4096 --ubatch-size 1024 --parallel 1 --threads 10 \
  --spec-type draft-mtp,ngram-map-k --spec-draft-n-max 3 --spec-draft-p-min 0.60 \
  --reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek \
  --flash-attn on --jinja --cont-batching --host 127.0.0.1 --port 8098 -v > $D/f3-$TAG.log 2>&1 &
echo $! > $D/gate.pid
