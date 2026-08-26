#!/bin/bash
# Faza 14: koszt ASPM performance na pakiecie CPU POD OBCIAZENIEM.
# Faza 13 dala +3.17 W na biegu jalowym. Pod obciazeniem IO die pracuje i tak,
# wiec delta moze byc inna. Jedyna zmienna: pcie_aspm.policy. Reszta stala
# (vo -75 mV, cap 272 W, bez capa SCLK), zeby sie skrocila w roznicy.
# Kolejnosc wariantow odwrocona w przebiegu 2 - dryf termiczny nie moze udawac efektu.
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
POL=/sys/module/pcie_aspm/parameters/policy
LNK=/sys/bus/pci/devices/0000:08:00.0/link
RAPL=/sys/class/powercap/intel-rapl:0/energy_uj
OUT=results/aspm-cpu-package.jsonl
MV=-75
IDLESEC=${IDLESEC:-30}
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
eval "$(grep '^Q=' f8.sh)"

jt(){ echo $(($(cat $H/temp2_input)/1000)); }
polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 24); do [ "$(jt)" -le 55 ] && break; sleep 5; done; }

set_uv(){ # vo bez capa SCLK, z weryfikacja odczytu
  echo r > "$OD" || return 1
  echo manual > "$PL" || return 1
  echo "vo $MV" > "$OD" || { echo "vo odrzucony"; return 1; }
  echo c > "$OD" || { echo "commit odrzucony"; return 1; }
  local gv=$(grep -oE '\-?[0-9]+mV' "$OD" | tail -1 | tr -d 'mV')
  [ "$gv" = "$MV" ] || { echo "  ROZBIEZNOSC: odczyt vo=${gv}mV"; return 1; }
}
idle_pkg(){ # moc pakietu na biegu jalowym z licznika, jako kotwica do fazy 13
  local e0 t0 e1 t1
  e0=$(cat $RAPL); t0=$(date +%s.%N); sleep "$IDLESEC"; e1=$(cat $RAPL); t1=$(date +%s.%N)
  python3 -c "
d=$e1-$e0
if d<0: d+=65532610987
print(round(d/1e6/($t1-$t0),2))"
}
restore(){ echo r > "$OD" 2>/dev/null; echo auto > "$PL" 2>/dev/null; echo default > $POL 2>/dev/null
  echo "PRZYWROCONO perf=$(cat $PL) vo=$(grep -oE '\-?[0-9]+mV' $OD | tail -1) aspm=$(polstate) l1=$(cat $LNK/l1_aspm)" | tee -a $OUT; }
trap 'kill_srv; restore' EXIT

kill_srv
echo 272000000 > "$H/power1_cap"
for pass in 1 2; do
  if [ "$pass" = 1 ]; then V="default performance"; else V="performance default"; fi
  for pol in $V; do
    tag="p${pass}-aspm${pol}"
    echo "=== $tag ==="
    echo "$pol" > $POL || { echo "BLAD polityki" | tee -a $OUT; continue; }
    [ "$(polstate)" = "$pol" ] || { echo "BLAD: polityka to $(polstate)" | tee -a $OUT; continue; }
    set_uv || { echo "SETFAIL $tag" | tee -a $OUT; continue; }
    cool
    ip=$(idle_pkg)
    echo "{\"tag\":\"$tag/idle\",\"aspm\":\"$(polstate)\",\"l1_aspm\":$(cat $LNK/l1_aspm),\"clkpm\":$(cat $LNK/clkpm),\"cpu_pkg_w\":$ip,\"jt\":$(jt)}" | tee -a $OUT
    SRV_LOG="logs/f14-$tag.log" ./srv.sh $BASE $SPEC $REAS || { echo "SRVFAIL $tag" | tee -a $OUT; continue; }
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
echo "F14 DONE" | tee -a $OUT
