#!/bin/bash
# Server for the reasoning arm test. Unlike srv-kv-128k.sh this one carries the
# SHIPPED profile's sampling and cache flags, because the question is about the
# configuration in use, not about a comparable-to-earlier-phases baseline.
# Faza 6: serwer USTAWIONY JAK PRODUKCJA, nie jak poprzednie fazy.
# Rozne od f3-srv.sh: probkowanie produkcyjne (temp/top-p/top-k/min-p),
# --cache-reuse 256, --cache-prompt, -fit off, --timeout 300, --metrics.
# Zostaje port 8098 i -v, zeby log dal sie czytac tak jak wczesniej.
# Produkcja ma jeszcze --sleep-idle-seconds 720; tu pominiete, bo test nie moze
# zasnac w polowie biegu.
set -e
TAG=$1
D=$HOME/gate
B=$HOME/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-server
M=$HOME/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
MM=$HOME/llm/models/unsloth/Qwen3.8-27B-GGUF/mmproj-Q8_0.gguf
export RADV_PERFTEST=nogttspill
unset GGML_VK_DISABLE_MMVQ
$B --model $M --mmproj $MM --alias g --ctx-size 131072 --n-gpu-layers 99 \
  --cache-type-k q8_0 --cache-type-v turbo4 --cache-type-k-draft q8_0 --cache-type-v-draft turbo4 \
  --batch-size 4096 --ubatch-size 1024 --parallel 1 --threads 10 \
  --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0.05 \
  --spec-type draft-mtp,ngram-map-k --spec-draft-n-max 3 --spec-draft-p-min 0.60 \
  --reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek \
  --image-min-tokens 1024 \
  --flash-attn on --jinja --cont-batching --cache-prompt --cache-reuse 256 \
  --timeout 300 --metrics -fit off \
  --host 127.0.0.1 --port 8098 -v > $D/f6-$TAG.log 2>&1 &
echo $! > $D/gate.pid
