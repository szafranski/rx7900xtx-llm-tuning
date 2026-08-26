#!/bin/bash
# Faza 10 krok 1: polityka ASPM PCIe. Nie rusza napiecia, taktow ani capa.
# Weryfikacja, ze zapis faktycznie zmienil stan linku: /sys/bus/pci/devices/.../link/{l1_aspm,clkpm}
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
H=$D/hwmon/hwmon1
POL=/sys/module/pcie_aspm/parameters/policy
LNK=/sys/bus/pci/devices/0000:08:00.0/link
OUT=results/aspm-sweep-early.jsonl
PPLOUT=results/A0-faza10-ppl.tsv
PPL=/home/user/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-perplexity
MODEL=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
CHUNKS=${CHUNKS:-20}
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
eval "$(grep '^Q=' bench-power-cap.sh)"   # dokladnie ten sam prompt co fazy 8 i 9
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 36); do [ "$(jt)" -le 50 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }
lnkstate(){ echo "l1_aspm=$(cat $LNK/l1_aspm 2>/dev/null) clkpm=$(cat $LNK/clkpm 2>/dev/null)"; }
polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
set_aspm(){ # $1 = default|performance|powersave
  local want=$1 before after
  before=$(lnkstate)
  echo "$want" > $POL || { echo "zapis polityki odrzucony"; return 1; }
  local got=$(polstate)
  [ "$got" = "$want" ] || { echo "  ROZBIEZNOSC: polityka to $got, nie $want"; return 1; }
  sleep 2; after=$(lnkstate)
  echo "  polityka=$got link przed: $before  po: $after"
  [ "$before" = "$after" ] && echo "  UWAGA: stan linku sie nie zmienil"
  return 0
}
restore(){ [ -w "$POL" ] && echo default > $POL 2>/dev/null
  echo "PRZYWROCONO polityka=$(polstate) $(lnkstate)" | tee -a $OUT; }
ppl(){ local log="logs/f10-ppl-$1.log" t0=$SECONDS
  $PPL -m $MODEL -f wikitext-2-raw/wiki.test.raw -c 4096 -fa on -ngl 99 -ub 1024 -b 4096 \
       -ctk q8_0 -ctv q8_0 --chunks $CHUNKS -t 6 > "$log" 2>&1
  local p=$(grep -oE "Final estimate: PPL = [0-9.]+" "$log" | grep -oE "[0-9.]+$")
  [ -z "$p" ] && p="FAIL"
  printf "%s\tEN\t%s\t%s\t%s\n" "$1" "$p" "$CHUNKS" "$((SECONDS-t0))" >> $PPLOUT
  echo "$p"
}
run_at(){ local tag=$1
  kill_srv; cool
  SRV_LOG="logs/f10-$tag.log" ./srv.sh $BASE $SPEC $REAS \
    || { echo "SRVFAIL $tag" | tee -a $OUT; return 1; }
  for rep in 1 2; do
    python3 pw.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
      --reasoning medium --tag "$tag/r$rep" --idle-w 12.7 --out $OUT >/dev/null 2>&1 \
      && echo "  ok $tag/r$rep" || echo "  FAIL $tag/r$rep"
  done
  kill_srv
  echo "  junction po przelocie=$(jt) C  $(lnkstate)"
}
dmesg_check(){ local n=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
  echo "DMESG $1 amdgpu-incydenty=$n" | tee -a $OUT; [ "${n:-0}" = "0" ]; }
[ -s "$PPLOUT" ] || printf "wariant\tkorpus\tppl\tchunks\tsek\n" > $PPLOUT
trap 'kill_srv; restore' EXIT
# stan wejsciowy musi byc fabryczny: napiecie 0 mV, perf auto
[ "$(cat $D/power_dpm_force_performance_level)" = "auto" ] || { echo "BLAD: perf level nie auto"; exit 1; }
echo "=== stan wejsciowy: polityka=$(polstate) $(lnkstate) perf=$(cat $D/power_dpm_force_performance_level)"
for v in default performance powersave; do
  echo "=== ASPM $v ==="
  set_aspm $v || { echo "ASPM $v SETFAIL" | tee -a $OUT; continue; }
  [ "$v" = "performance" ] && { p=$(ppl aspm-performance); echo "PPL aspm-performance EN=$p" | tee -a $OUT; }
  run_at "aspm-$v"
  dmesg_check "aspm-$v" || echo "UWAGA: incydenty amdgpu przy ASPM $v" | tee -a $OUT
done
echo "F10-ASPM DONE" | tee -a $OUT
