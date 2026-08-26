#!/usr/bin/env bash
# Faza 13: pobor mocy na biegu jalowym w funkcji nastaw, ktore w zasadzie moglyby
# go zmienic (ASPM, undervolt, cap taktu, cap mocy). Dwa przebiegi w odwrotnej
# kolejnosci, zeby kolejnosc wariantow nie udawala efektu.
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
POL=/sys/module/pcie_aspm/parameters/policy
LNK=/sys/bus/pci/devices/0000:08:00.0/link
OUT=results/idle-power.jsonl
SEC=${SEC:-120}
SETTLE=${SETTLE:-25}

polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
capw(){ echo $(($(cat $H/power1_cap)/1000000)); }

reset_all(){
  echo r > "$OD"; echo auto > "$PL"; echo default > "$POL"
  echo 272000000 > "$H/power1_cap"
}
set_vo(){ local mv=$1
  [ "$mv" -le 0 ] || { echo "ODMOWA: offset dodatni ($mv)"; return 1; }
  [ "$mv" -ge -450 ] || { echo "ODMOWA: $mv poza OD_RANGE"; return 1; }
  echo manual > "$PL" && echo "vo $mv" > "$OD" && echo c > "$OD" || return 1
  local got=$(grep -oE '\-?[0-9]+mV' "$OD" | tail -1 | tr -d 'mV')
  [ "$got" = "$mv" ] || { echo "  ROZBIEZNOSC offsetu: $got vs $mv"; return 1; }
}
set_sclk(){ echo manual > "$PL" && echo "s 1 $1" > "$OD" && echo c > "$OD"; }

apply(){ # kazdy wariant skladany od czystego stanu, bez dziedziczenia po poprzednim
  reset_all
  case $1 in
    base)      ;;
    aspm)      echo performance > "$POL" ;;
    uv)        echo performance > "$POL"; set_vo -75 || return 1 ;;
    sclk2200)  echo performance > "$POL"; set_vo -75 || return 1; set_sclk 2200 || return 1 ;;
    cap303)    echo 303000000 > "$H/power1_cap" ;;
    *) echo "nieznany wariant $1"; return 1 ;;
  esac
  echo "  $1: polityka=$(polstate) l1_aspm=$(cat $LNK/l1_aspm) clkpm=$(cat $LNK/clkpm) perf=$(cat $PL) cap=$(capw)W offset=$(grep -oE '\-?[0-9]+mV' $OD | tail -1)"
}

dmesg_n(){ dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)"; }

trap 'echo "PRZYWRACAM"; reset_all; echo "perf=$(cat $PL) polityka=$(polstate) cap=$(capw)W"' EXIT

srv=$(ps -eo cmd | grep -E "llama-server" | grep -v grep | wc -l)
echo "=== FAZA 13 start: llama-server=$srv (ma byc 0), incydenty=$(dmesg_n), SEC=$SEC ==="
[ "$srv" = "0" ] || { echo "PRZERWANE: cos generuje, to nie bylby idle"; exit 1; }

for pass in 1 2; do
  if [ "$pass" = 1 ]; then V="base aspm uv sclk2200 cap303"; else V="cap303 sclk2200 uv aspm base"; fi
  for v in $V; do
    apply "$v" || { echo "  POMINIETY $v"; continue; }
    sleep "$SETTLE"
    python3 idle_sampler.py --sec "$SEC" --tag "$v/p$pass" --out "$OUT" | python3 -c 'import json,sys; o=json.load(sys.stdin); print("  %-14s gpu=%.2f W (med %.1f, sd %.2f) cpu_pkg=%.2f W mv=%.0f sclk=%.0f busy=%.2f%% jt=%.0fC" % (o["tag"],o["gpu_w_trapz"],o["gpu_w_med"],o["gpu_w_sd"],o["cpu_pkg_w"],o["mv_med"],o["sclk_med"],o["busy_avg"],o["jt_med"]))'
  done
done
echo "=== FAZA 13 DONE, incydenty=$(dmesg_n) ==="
