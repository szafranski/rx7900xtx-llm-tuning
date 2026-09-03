# Committed as run, from the measurement host. Identical to srv-kv-reasoning.sh
# except for --reasoning-budget, which is a server flag and not a request
# parameter, so each budget needs its own server and its own 120K prefill.
#!/bin/bash
# Faza 8 (test D): tryb awarii budzetu rozumowania.
# Identyczny z f6-srv.sh Z JEDNA ROZNICA: --reasoning-budget 512 zamiast 8192.
# Budzet jest flaga SERWERA, nie parametrem zapytania, wiec ramiona wymagaja
# osobnych serwerow i osobnego prefillu 120k. Dlatego jedno ramie na bieg.
# --reasoning-budget-message zostaje pusty (domyslnie none) - chcemy zobaczyc
# zachowanie golego mechanizmu, zanim zaczniemy go podpowiadac.
set -e
TAG=$1
BUDGET=${2:-512}
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
  --reasoning on --reasoning-effort medium --reasoning-budget $BUDGET --reasoning-format deepseek \
  --image-min-tokens 1024 \
  --flash-attn on --jinja --cont-batching --cache-prompt --cache-reuse 256 \
  --timeout 300 --metrics -fit off \
  --host 127.0.0.1 --port 8098 -v > $D/f8-$TAG.log 2>&1 &
echo $! > $D/gate.pid
