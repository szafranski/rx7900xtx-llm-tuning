#!/bin/bash
# Faza 11A: glebszy undervolt POD capem SCLK. Hipoteza: granica stabilnosci to wlasciwosc
# pary napiecie-zegar, wiec -150 mV ktore poległo na 3045 MHz moze przejsc na 2200 MHz.
# Uzycie: ./bench-undervolt-capped.sh 2200 -100 -125 -150 -175 -200
# Pierwszy argument = cap SCLK, dalej lista offsetow. Stop na pierwszym rozjechanym PPL.
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
POL=/sys/module/pcie_aspm/parameters/policy
LNK=/sys/bus/pci/devices/0000:08:00.0/link
OUT=results/undervolt-sweep-capped.jsonl
PPLOUT=results/A4-faza11a-ppl.tsv
PPL=/home/user/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-perplexity
MODEL=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
CHUNKS=${CHUNKS:-20}
PPL_REF=5.9335
SCLK=$1; shift
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
eval "$(grep '^Q=' bench-power-cap.sh)"
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 24); do [ "$(jt)" -le 55 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }
polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
set_all(){ local mv=$1
  [ "$mv" -le 0 ] && [ "$mv" -ge -250 ] || { echo "ODMOWA: $mv poza 0..-250 mV"; return 1; }
  [ "$SCLK" -ge 500 ] && [ "$SCLK" -le 3045 ] || { echo "ODMOWA: $SCLK poza 500-3045"; return 1; }
  echo r > "$OD" || return 1
  echo manual > "$PL" || return 1
  echo "vo $mv" > "$OD" || { echo "vo odrzucony"; return 1; }
  echo "s 1 $SCLK" > "$OD" || { echo "s 1 odrzucony"; return 1; }
  echo c > "$OD" || { echo "commit odrzucony"; return 1; }
  local gv=$(grep -oE '\-?[0-9]+mV' "$OD" | tail -1 | tr -d 'mV')
  local gs=$(sed -n '/OD_SCLK/,/OD_MCLK/p' "$OD" | grep -oE '^1: [0-9]+' | grep -oE '[0-9]+$')
  echo "  zapisano vo=$mv sclk=$SCLK | odczyt vo=${gv}mV sclk=${gs}MHz perf=$(cat $PL) aspm=$(polstate) l1=$(cat $LNK/l1_aspm)"
  [ "$gv" = "$mv" ] && [ "$gs" = "$SCLK" ] || { echo "  ROZBIEZNOSC: sterownik nie przyjal obu wartosci"; return 1; }
}
restore(){ [ -w "$OD" ] && { echo r > "$OD" 2>/dev/null; echo auto > "$PL" 2>/dev/null; }
  [ -w "$POL" ] && echo default > $POL 2>/dev/null
  echo "PRZYWROCONO perf=$(cat $PL) vo=$(grep -oE '\-?[0-9]+mV' $OD | tail -1) aspm=$(polstate)" | tee -a $OUT; }
ppl(){ local log="logs/f11a-ppl-$1.log" t0=$SECONDS
  $PPL -m $MODEL -f wikitext-2-raw/wiki.test.raw -c 4096 -fa on -ngl 99 -ub 1024 -b 4096 \
       -ctk q8_0 -ctv q8_0 --chunks $CHUNKS -t 6 > "$log" 2>&1
  local p=$(grep -oE "Final estimate: PPL = [0-9.]+" "$log" | grep -oE "[0-9.]+$"); [ -z "$p" ] && p="FAIL"
  printf "%s\tEN\t%s\t%s\t%s\n" "$1" "$p" "$CHUNKS" "$((SECONDS-t0))" >> $PPLOUT
  echo "$p"
}
dmesg_check(){ local n=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
  echo "DMESG $1 amdgpu-incydenty=$n" | tee -a $OUT; [ "${n:-0}" = "0" ]; }
[ -s "$PPLOUT" ] || printf "wariant\tkorpus\tppl\tchunks\tsek\n" > $PPLOUT
trap 'kill_srv; restore' EXIT
echo performance > $POL || { echo "BLAD: polityka ASPM odrzucona"; exit 1; }
[ "$(polstate)" = "performance" ] || { echo "BLAD: polityka to $(polstate)"; exit 1; }
for mv in "$@"; do
  tag="f11a-sclk${SCLK}-uv${mv}"
  echo "=== $tag ==="
  set_all "$mv" || { echo "$tag SETFAIL" | tee -a $OUT; break; }
  p=$(ppl "$tag"); echo "PPL $tag EN=$p ref=$PPL_REF" | tee -a $OUT
  if [ "$p" != "$PPL_REF" ]; then
    echo "STOP: bramka determinizmu padla przy $mv mV (PPL=$p). Nie schodzimy glebiej." | tee -a $OUT
    dmesg_check "$tag"
    break
  fi
  kill_srv; cool
  SRV_LOG="logs/f11a-$tag.log" ./srv.sh $BASE $SPEC $REAS || { echo "SRVFAIL $tag" | tee -a $OUT; break; }
  for rep in 1 2; do
    python3 pw.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
      --reasoning medium --tag "$tag/r$rep" --idle-w 12.7 --out $OUT >/dev/null 2>&1 \
      && echo "  ok $tag/r$rep" || echo "  FAIL $tag/r$rep"
  done
  kill_srv
  echo "  junction po=$(jt) C"
  p2=$(ppl "$tag-po-obciazeniu"); echo "PPL $tag na goracej karcie EN=$p2" | tee -a $OUT
  [ "$p2" = "$PPL_REF" ] || { echo "STOP: bramka padla na goracej karcie przy $mv mV (PPL=$p2)." | tee -a $OUT; dmesg_check "$tag"; break; }
  dmesg_check "$tag" || echo "UWAGA: incydenty amdgpu przy $tag" | tee -a $OUT
done
echo "F11A DONE" | tee -a $OUT
