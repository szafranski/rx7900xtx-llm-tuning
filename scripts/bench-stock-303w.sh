#!/bin/bash
# Faza 11B: fabryczny cap 303 W razem z -75 mV i ASPM performance. Punkt maksymalnej
# wydajnosci, nigdy nie zmierzony - cap 272 W byl nasza decyzja z fazy 8, nie fabryka.
# Bez capa SCLK, bez podnoszenia MCLK. 303 W = power1_cap_default, wiec zero overclocku.
# Faza 7 przy 303 W bez undervoltu dala junction 94 C, dlatego tu jest soak, nie dwa przeloty.
# Uzycie: ./bench-stock-303w.sh [soak_sek]   (domyslnie 1800)
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
CAP=$H/power1_cap
POL=/sys/module/pcie_aspm/parameters/policy
LNK=/sys/bus/pci/devices/0000:08:00.0/link
OUT=results/stock-303w.jsonl
SOAKOUT=results/stock-303w-soak
PPLOUT=results/A5-faza11b-ppl.tsv
PPL=/home/user/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-perplexity
MODEL=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
CHUNKS=${CHUNKS:-20}
PPL_REF=5.9335
MV=-75
SOAK=${1:-1800}
JT_ABORT=98
CAP_OLD=$(cat $CAP)
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
eval "$(grep '^Q=' bench-power-cap.sh)"
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 36); do [ "$(jt)" -le 55 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }
polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
restore(){ [ -w "$CAP" ] && echo "$CAP_OLD" > $CAP 2>/dev/null
  [ -w "$OD" ] && { echo r > "$OD" 2>/dev/null; echo auto > "$PL" 2>/dev/null; }
  [ -w "$POL" ] && echo default > $POL 2>/dev/null
  echo "PRZYWROCONO cap=$(( $(cat $CAP)/1000000 ))W perf=$(cat $PL) vo=$(grep -oE '\-?[0-9]+mV' $OD | tail -1) aspm=$(polstate)" | tee -a $OUT; }
ppl(){ local log="logs/f11b-ppl-$1.log" t0=$SECONDS
  $PPL -m $MODEL -f wikitext-2-raw/wiki.test.raw -c 4096 -fa on -ngl 99 -ub 1024 -b 4096 \
       -ctk q8_0 -ctv q8_0 --chunks $CHUNKS -t 6 > "$log" 2>&1
  local p=$(grep -oE "Final estimate: PPL = [0-9.]+" "$log" | grep -oE "[0-9.]+$"); [ -z "$p" ] && p="FAIL"
  printf "%s\tEN\t%s\t%s\t%s\n" "$1" "$p" "$CHUNKS" "$((SECONDS-t0))" >> $PPLOUT
  echo "$p"
}
dmesg_check(){ local n=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
  echo "DMESG $1 amdgpu-incydenty=$n" | tee -a $OUT; [ "${n:-0}" = "0" ]; }
# straznik termiczny: przy junction >= JT_ABORT zabija serwer i przywraca 272 W
watchdog(){ while sleep 10; do t=$(jt); [ "$t" -ge "$JT_ABORT" ] && {
    echo "STRAZNIK: junction=$t C >= $JT_ABORT, przerywam i wracam na $(( CAP_OLD/1000000 ))W" | tee -a $OUT
    kill_srv; echo "$CAP_OLD" > $CAP 2>/dev/null; return 0; }; done; }
[ -s "$PPLOUT" ] || printf "wariant\tkorpus\tppl\tchunks\tsek\n" > $PPLOUT
[ -w "$CAP" ] || { echo "BLAD: $CAP nie do zapisu. Potrzebny 'sudo chmod 666 $CAP'."; exit 1; }
trap 'kill_srv; restore' EXIT
TAG="f11b-303w-uv75-aspm"
echo performance > $POL || { echo "BLAD: polityka ASPM odrzucona"; exit 1; }
[ "$(polstate)" = "performance" ] || { echo "BLAD: polityka to $(polstate)"; exit 1; }
echo r > "$OD" || exit 1
echo manual > "$PL" || exit 1
echo "vo $MV" > "$OD" || { echo "vo odrzucony"; exit 1; }
echo c > "$OD" || { echo "commit odrzucony"; exit 1; }
GV=$(grep -oE '\-?[0-9]+mV' "$OD" | tail -1 | tr -d 'mV')
[ "$GV" = "$MV" ] || { echo "ROZBIEZNOSC: vo=${GV}mV a nie $MV"; exit 1; }
echo 303000000 > "$CAP" || { echo "cap odrzucony"; exit 1; }
GC=$(( $(cat $CAP)/1000000 ))
[ "$GC" = "303" ] || { echo "ROZBIEZNOSC: cap=${GC}W a nie 303"; exit 1; }
echo "=== $TAG === vo=${GV}mV cap=${GC}W perf=$(cat $PL) aspm=$(polstate) l1=$(cat $LNK/l1_aspm) sclk_max=$(sed -n '/OD_SCLK/,/OD_MCLK/p' $OD | grep -oE '^1: [0-9]+')"
p=$(ppl "$TAG"); echo "PPL $TAG EN=$p ref=$PPL_REF" | tee -a $OUT
[ "$p" = "$PPL_REF" ] || { echo "STOP: bramka determinizmu padla na zimno (PPL=$p)." | tee -a $OUT; dmesg_check "$TAG"; exit 1; }
kill_srv; cool
SRV_LOG="logs/f11b-$TAG.log" ./srv.sh $BASE $SPEC $REAS || { echo "SRVFAIL $TAG" | tee -a $OUT; exit 1; }
watchdog & WD=$!
for rep in 1 2; do
  python3 pw.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
    --reasoning medium --tag "$TAG/r$rep" --idle-w 12.7 --out $OUT >/dev/null 2>&1 \
    && echo "  ok $TAG/r$rep junction=$(jt) C" || echo "  FAIL $TAG/r$rep"
done
if [ "$SOAK" -gt 0 ]; then
  echo "=== soak ${SOAK}s, straznik na junction >= $JT_ABORT C ==="
  python3 soak.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 --reasoning medium \
    --secs "$SOAK" --out "${SOAKOUT}.jsonl" --tsv "${SOAKOUT}.tsv" 2>&1 | tail -n 20
  echo "  junction po soaku=$(jt) C, bramka na goracej karcie:"
  p2=$(ppl "$TAG-po-soak"); echo "PPL $TAG po soaku EN=$p2 (przed: $p)" | tee -a $OUT
fi
kill -TERM $WD 2>/dev/null
kill_srv
echo "  junction po=$(jt) C"
dmesg_check "$TAG" || echo "UWAGA: incydenty amdgpu" | tee -a $OUT
echo "F11B DONE" | tee -a $OUT
