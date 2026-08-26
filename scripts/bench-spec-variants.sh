#!/bin/bash
# Faza 15 krok 1: czy chained MTP drafting cokolwiek daje.
# Jedyna zmienna: flaga --spec-chain. Glebokosc draftu ta sama w obu wariantach
# (arg.cpp:4128 - "--spec-chain 1" jest truthy, wiec ustawia tylko chain, nie n_max),
# wiec n-max podajemy jawnie w obu, zeby nie mieszac dwoch efektow w jednym wariancie.
# Stan GPU fabryczny: auto, bez undervoltu, cap 303 W. Identyczny dla obu wariantow.
# Kolejnosc wariantow odwrocona w przebiegu 2 - dryf termiczny nie moze udawac efektu.
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
OUT=results/spec-variants-paired.jsonl
NMAX=3
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
eval "$(grep '^Q=' f8.sh)"
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 24); do [ "$(jt)" -le 55 ] && break; sleep 5; done; }
spec(){ # flagi spekulacji dla wariantu
  case "$1" in
    ctrl)  echo "--spec-type draft-mtp --spec-draft-n-max $NMAX --spec-draft-p-min 0.60" ;;
    chain) echo "--spec-type draft-mtp --spec-chain 1 --spec-draft-n-max $NMAX --spec-draft-p-min 0.60" ;;
  esac
}
trap 'kill_srv' EXIT
kill_srv
# stan fabryczny, jawnie, zeby nie odziedziczyc nastaw fazy 14
echo r > "$OD" 2>/dev/null; echo auto > "$PL"; echo 303000000 > "$H/power1_cap"
echo "STAN cap=$(cat $H/power1_cap) perf=$(cat $PL) vo=$(grep -oE '\-?[0-9]+mV' $OD | tail -1)" | tee -a $OUT
for pass in 1 2; do
  if [ "$pass" = 1 ]; then V="ctrl chain"; else V="chain ctrl"; fi
  for v in $V; do
    tag="p${pass}-$v"
    echo "=== $tag ==="
    cool
    SRV_LOG="logs/f15a-$tag.log" ./srv.sh $BASE $(spec $v) $REAS || { echo "SRVFAIL $tag" | tee -a $OUT; continue; }
    grep -m1 "CMDLINE" "logs/f15a-$tag.log"
    for rep in 1 2; do
      python3 power_sampler.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
        --reasoning medium --tag "$tag/r$rep" --idle-w 12.7 --out $OUT >/dev/null 2>&1 \
        && echo "  ok $tag/r$rep" || echo "  FAIL $tag/r$rep"
    done
    kill_srv
    n=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
    echo "DMESG $tag amdgpu-incydenty=$n" | tee -a $OUT
  done
done
echo "F15A DONE" | tee -a $OUT
