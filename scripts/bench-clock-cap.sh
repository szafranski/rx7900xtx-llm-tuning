#!/bin/bash
# Faza 10 krok 3: krzywa J/token ponizej 272 W przez ograniczenie gornego SCLK.
# power1_cap_min = 272 W to podloga vbiosu, wiec jedyna droga nizej to zbicie karty z capa.
# Uzycie: ./bench-clock-cap.sh 3045 2400 2200 2000 1800   (pierwsza wartosc = kontrola fabryczna)
# Nie podnosi niczego: gorna granica zapisu to fabryczne 3045 MHz.
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
OUT=results/clock-cap-sweep.jsonl
PPLOUT=results/A0-faza10-ppl.tsv
PPL=/home/user/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-perplexity
MODEL=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
CHUNKS=${CHUNKS:-20}
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
eval "$(grep '^Q=' bench-power-cap.sh)"
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 36); do [ "$(jt)" -le 52 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }
set_sclk(){ local mhz=$1
  [ "$mhz" -ge 500 ] && [ "$mhz" -le 3045 ] || { echo "ODMOWA: $mhz poza 500-3045, nie podnosimy powyzej fabryki"; return 1; }
  echo r > "$OD" || { echo "reset odrzucony"; return 1; }
  echo manual > "$PL" || { echo "manual odrzucony"; return 1; }
  echo "s 1 $mhz" > "$OD" || { echo "s 1 $mhz odrzucony"; return 1; }
  echo c > "$OD" || { echo "commit odrzucony"; return 1; }
  local got=$(sed -n '/OD_SCLK/,/OD_MCLK/p' "$OD" | grep -oE '^1: [0-9]+' | grep -oE '[0-9]+$')
  echo "  sclk max zapisany=$mhz odczytany=${got}MHz perf=$(cat $PL)"
  [ "$got" = "$mhz" ] || { echo "  ROZBIEZNOSC: sterownik nie przyjal $mhz"; return 1; }
}
restore(){ [ -w "$OD" ] && { echo r > "$OD" 2>/dev/null; echo auto > "$PL" 2>/dev/null; }
  echo "PRZYWROCONO perf=$(cat $PL) sclk=$(sed -n '/OD_SCLK/,/OD_MCLK/p' $OD | grep -E '^1:')" | tee -a $OUT; }
ppl(){ local log="logs/f10-ppl-$1.log" t0=$SECONDS
  $PPL -m $MODEL -f wikitext-2-raw/wiki.test.raw -c 4096 -fa on -ngl 99 -ub 1024 -b 4096 \
       -ctk q8_0 -ctv q8_0 --chunks $CHUNKS -t 6 > "$log" 2>&1
  local p=$(grep -oE "Final estimate: PPL = [0-9.]+" "$log" | grep -oE "[0-9.]+$"); [ -z "$p" ] && p="FAIL"
  printf "%s\tEN\t%s\t%s\t%s\n" "$1" "$p" "$CHUNKS" "$((SECONDS-t0))" >> $PPLOUT
  echo "$p"
}
dmesg_check(){ local n=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
  echo "DMESG $1 amdgpu-incydenty=$n" | tee -a $OUT; [ "${n:-0}" = "0" ]; }
run_at(){ local tag=$1
  kill_srv; cool
  SRV_LOG="logs/f10-$tag.log" ./srv.sh $BASE $SPEC $REAS || { echo "SRVFAIL $tag" | tee -a $OUT; return 1; }
  for rep in 1 2; do
    python3 pw.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
      --reasoning medium --tag "$tag/r$rep" --idle-w 12.7 --out $OUT >/dev/null 2>&1 \
      && echo "  ok $tag/r$rep" || echo "  FAIL $tag/r$rep"
  done
  kill_srv
  echo "  junction po przelocie=$(jt) C sclk_teraz=$(cat $D/pp_dpm_sclk 2>/dev/null | grep '\*' | tr -d ' ')"
}
[ -s "$PPLOUT" ] || printf "wariant\tkorpus\tppl\tchunks\tsek\n" > $PPLOUT
trap 'kill_srv; restore' EXIT
echo "=== stan wejsciowy: perf=$(cat $PL) ==="
for mhz in "$@"; do
  echo "=== sclk max ${mhz} MHz ==="
  set_sclk "$mhz" || { echo "SCLK ${mhz} SETFAIL" | tee -a $OUT; continue; }
  run_at "sclk-${mhz}"
  dmesg_check "sclk-${mhz}" || echo "UWAGA: incydenty amdgpu przy ${mhz} MHz" | tee -a $OUT
done
echo "F10-SCLK DONE" | tee -a $OUT
