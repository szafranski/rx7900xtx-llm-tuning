#!/bin/bash
# Faza 12: energia i czas na ODPOWIEDZ. Sprzet tylko do czytania - zaden zapis do sysfs.
# Uzupelnia luke fazy 7, gdzie kazda generacja byla ucieta na 1200 tokenach.
set -u
OUT=results/reasoning-energy-per-answer.jsonl
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
MAXTOK=12000
eval "$(grep '^Q=' bench-context-32k.sh)"   # to samo pytanie co faza 2b, zeby liczby byly porownywalne

kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
jt(){ echo $(($(cat /sys/class/drm/card1/device/hwmon/hwmon1/temp2_input)/1000)); }
cool(){ for i in $(seq 1 48); do [ "$(jt)" -le 50 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }

echo "=== stan sprzetu na wejsciu ===" | tee -a $OUT
echo "cap=$(( $(cat /sys/class/drm/card1/device/hwmon/hwmon1/power1_cap)/1000000 ))W perf=$(cat /sys/class/drm/card1/device/power_dpm_force_performance_level) vo=$(grep -A1 VDDGFX_OFFSET /sys/class/drm/card1/device/pp_od_clk_voltage | tail -1)" | tee -a $OUT

kill_srv
IDLE_W=$(python3 -c 'import e12; print(e12.idle(8.0))')
echo "idle_w=$IDLE_W" | tee -a $OUT

run_cfg(){ # $1 tag  $2 effort("" = brak)  $3... flagi serwera
  local tag=$1 effort=$2; shift 2
  echo "=== $tag ==="
  kill_srv; cool
  SRV_LOG="logs/f12-$tag.log" ./srv.sh $BASE $SPEC "$@" \
    || { echo "SRVFAIL $tag" | tee -a $OUT; return 0; }
  local ea=""; [ -n "$effort" ] && ea="--effort $effort"
  for rep in 1 2; do
    cool
    python3 energy_per_answer.py --prompt prompts/P20K.txt --question "$Q" --max-tokens $MAXTOK \
      $ea --tag "$tag/r$rep" --idle-w "$IDLE_W" --out $OUT >/dev/null 2>&1 \
      && echo "  ok $tag/r$rep" || echo "  FAIL $tag/r$rep"
  done
  kill_srv
}

run_cfg off      ""       --reasoning off
run_cfg med8192  medium   --reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek
run_cfg med2048  medium   --reasoning on --reasoning-effort medium --reasoning-budget 2048 --reasoning-format deepseek

echo "=== stan sprzetu na wyjsciu ===" | tee -a $OUT
echo "cap=$(( $(cat /sys/class/drm/card1/device/hwmon/hwmon1/power1_cap)/1000000 ))W perf=$(cat /sys/class/drm/card1/device/power_dpm_force_performance_level) jt=$(jt)C" | tee -a $OUT
echo "incydenty=$(dmesg 2>/dev/null | grep -ci 'amdgpu.*\(reset\|ring\|timeout\|fault\)')" | tee -a $OUT
echo "FAZA12 DONE" | tee -a $OUT
