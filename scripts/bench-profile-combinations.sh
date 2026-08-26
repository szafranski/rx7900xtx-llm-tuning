#!/bin/bash
# Faza 10 krok 2: kombinacja ASPM + undervolt. Uzycie: ./bench-profile-combinations.sh performance -75 [soak_sek]
# Trzeci argument wlacza soak w stanie ustalonym (np. 1800).
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
POL=/sys/module/pcie_aspm/parameters/policy
LNK=/sys/bus/pci/devices/0000:08:00.0/link
OUT=results/profile-combinations.jsonl
SOAKOUT=results/A1-faza10-komb-soak
PPLOUT=results/A0-faza10-ppl.tsv
PPL=/home/user/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-perplexity
MODEL=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
CHUNKS=${CHUNKS:-20}
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
eval "$(grep '^Q=' bench-power-cap.sh)"
POLICY=${1:?podaj polityke ASPM, np performance}
MV=${2:?podaj offset mV, np -75}
SOAK=${3:-0}
TAG="komb-${POLICY}-uv${MV}"
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 36); do [ "$(jt)" -le 50 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }
lnkstate(){ echo "l1_aspm=$(cat $LNK/l1_aspm 2>/dev/null) clkpm=$(cat $LNK/clkpm 2>/dev/null)"; }
polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
set_vo(){ local mv=$1
  [ "$mv" -le 0 ] || { echo "ODMOWA: offset dodatni ($mv)"; return 1; }
  [ "$mv" -ge -450 ] || { echo "ODMOWA: $mv poza OD_RANGE"; return 1; }
  echo r > "$OD" && echo manual > "$PL" && echo "vo $mv" > "$OD" && echo c > "$OD" || { echo "rytual OD odrzucony"; return 1; }
  local got=$(grep -oE '\-?[0-9]+mV' "$OD" | tail -1 | tr -d 'mV')
  echo "  offset zapisany=$mv odczytany=${got}mV perf=$(cat $PL)"
  [ "$got" = "$mv" ] || { echo "  ROZBIEZNOSC"; return 1; }
}
restore(){ [ -w "$OD" ] && { echo r > "$OD" 2>/dev/null; echo auto > "$PL" 2>/dev/null; }
  [ -w "$POL" ] && echo default > $POL 2>/dev/null
  echo "PRZYWROCONO perf=$(cat $PL) offset=$(grep -oE '\-?[0-9]+mV' $OD | tail -1) polityka=$(polstate)" | tee -a $OUT; }
ppl(){ local log="logs/f10-ppl-$1.log" t0=$SECONDS
  $PPL -m $MODEL -f wikitext-2-raw/wiki.test.raw -c 4096 -fa on -ngl 99 -ub 1024 -b 4096 \
       -ctk q8_0 -ctv q8_0 --chunks $CHUNKS -t 6 > "$log" 2>&1
  local p=$(grep -oE "Final estimate: PPL = [0-9.]+" "$log" | grep -oE "[0-9.]+$"); [ -z "$p" ] && p="FAIL"
  printf "%s\tEN\t%s\t%s\t%s\n" "$1" "$p" "$CHUNKS" "$((SECONDS-t0))" >> $PPLOUT
  echo "$p"
}
dmesg_check(){ local n=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
  echo "DMESG $1 amdgpu-incydenty=$n" | tee -a $OUT; [ "${n:-0}" = "0" ]; }
trap 'kill_srv; restore' EXIT
echo "=== $TAG ==="
echo "$POLICY" > $POL || { echo "BLAD: polityka odrzucona"; exit 1; }
[ "$(polstate)" = "$POLICY" ] || { echo "BLAD: polityka to $(polstate)"; exit 1; }
set_vo "$MV" || exit 1
echo "  polityka=$(polstate) $(lnkstate)"
p=$(ppl "$TAG"); echo "PPL $TAG EN=$p" | tee -a $OUT
kill_srv; cool
SRV_LOG="logs/f10-$TAG.log" ./srv.sh $BASE $SPEC $REAS || { echo "SRVFAIL"; exit 1; }
for rep in 1 2; do
  python3 pw.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
    --reasoning medium --tag "$TAG/r$rep" --idle-w 12.7 --out $OUT >/dev/null 2>&1 \
    && echo "  ok $TAG/r$rep" || echo "  FAIL $TAG/r$rep"
done
if [ "$SOAK" -gt 0 ]; then
  echo "=== soak ${SOAK}s w stanie ustalonym ==="
  python3 soak.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 --reasoning medium --secs "$SOAK" --out "${SOAKOUT}.jsonl" --tsv "${SOAKOUT}.tsv" 2>&1 | tail -n 20
  echo "  bramka na goracej karcie:"
  p2=$(ppl "$TAG-po-soak"); echo "PPL $TAG po soaku EN=$p2 (przed: $p)" | tee -a $OUT
fi
kill_srv
echo "  junction po=$(jt) C $(lnkstate)"
dmesg_check "$TAG" || echo "UWAGA: incydenty amdgpu" | tee -a $OUT
echo "F10-KOMB DONE" | tee -a $OUT
