#!/usr/bin/env bash
# Faza 16 krok 3b: pobor na BIEGU JALOWYM dla trzech polityk ASPM.
# Faza 13 zmierzyla tylko default (24.25 W pakiet CPU) i performance (27.42 W).
# powersave nie byl mierzony na idle nigdy, a pod obciazeniem byl nieodrozniale
# rowny default (58.05 kontra 58.07 tok/s, faza 10 krok 1). Jesli schodzi na idle
# ponizej default, to jest oszczednosc bez ceny. Tego nie da sie wywnioskowac
# z posiadanych danych, bo idle i obciazenie to inne stany linku PCIe.
#
# Reszta nastaw docelowych (vo, cap taktu, cap mocy) NIE jest tu ustawiana celowo:
# faza 13 pokazala, ze na biegu jalowym offset napiecia nie dosiega (mv=54 przy
# kazdym wariancie), a cap taktu nie trzyma taktow (sclk=0). Caly efekt szedl
# za polityka ASPM i tylko ona jest tu zmienna.
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
POL=/sys/module/pcie_aspm/parameters/policy
LNK=/sys/bus/pci/devices/0000:08:00.0/link
OUT=results/aspm-idle.jsonl
SEC=${SEC:-120}
SETTLE=${SETTLE:-25}
LOADMAX=${LOADMAX:-0.40}
BUSYMAX=${BUSYMAX:-3.0}   # procent zajetosci CPU, prog wlasciwy
polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
capw(){ echo $(($(cat $H/power1_cap)/1000000)); }
load1(){ cut -d" " -f1 /proc/loadavg; }
# Zajetosc CPU z /proc/stat, nie loadavg. Load srednia liczy tez zadania w stanie
# nieprzerywalnym (zapisy btrfs po buildzie) i procesy niced, wiec potrafi stac na
# 1.4 przy procesorze bezczynnym w 92%. Blokowalaby pomiar bez powodu, a krotkie
# szarpniecie CPU przepuscilaby, bo nie zdazy podniesc sredniej. Pobor pakietu idzie
# za faktyczna zajetoscia i to ja trzeba progowac.
busy(){ python3 -c '
import time
def rd():
    v = list(map(int, open("/proc/stat").readline().split()[1:]))
    return sum(v), v[3] + v[4]          # total, idle+iowait
a = rd(); time.sleep(4); b = rd()
tot = b[0] - a[0]
print("%.1f" % (100.0 * (tot - (b[1] - a[1])) / tot if tot else 0.0))
'; }
loadok(){ awk -v m="$BUSYMAX" -v b="$(busy)" 'BEGIN{exit !(b<=m)}'; }
waitload(){ # $1 = ile sekund czekac na wyciszenie maszyny
  local n=$(( ${1:-600} / 10 )) i
  for i in $(seq 1 $n); do loadok && return 0
    [ $((i % 6)) = 1 ] && echo "  czekam na wyciszenie: cpu=$(busy)% > $BUSYMAX%, load1=$(load1)"
    sleep 10
  done
  return 1; }
dmesg_n(){ dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)"; }
restore(){ [ -w "$POL" ] && echo default > $POL 2>/dev/null
  echo "PRZYWROCONO polityka=$(polstate) perf=$(cat $PL) cap=$(capw)W"; }
[ -w "$POL" ] || { echo "BLAD: $POL nie do zapisu (chmod 666 ginie przy restarcie)."; exit 1; }
trap 'restore' EXIT
srv=$(pgrep -cf "[l]lama-server" || true)
[ "${srv:-0}" = "0" ] || { echo "PRZERWANE: llama-server dziala ($srv), to nie bylby idle"; exit 1; }
# Bramka obciazenia. Glownym kanalem jest licznik energii pakietu CPU, a szukamy
# tam roznic rzedu 3 W przy tle 24 W - dowolny build, indeksowanie czy aktualizacja
# utopi sygnal i, co gorsza, wynik bedzie wygladal wiarygodnie.
waitload 1800 || { echo "PRZERWANE: maszyna nie wyciszyla sie w 30 min (cpu=$(busy)% load1=$(load1))"; exit 1; }
echo "  na starcie: cpu=$(busy)% load1=$(load1) (prog $BUSYMAX%)"
[ "$(cat $PL)" = "auto" ] || { echo "BLAD: perf level to $(cat $PL), nie auto"; exit 1; }
echo "=== FAZA 16e start: incydenty=$(dmesg_n) SEC=$SEC SETTLE=$SETTLE cap=$(capw)W ==="
for pass in 1 2; do
  # odwrotna kolejnosc w drugim przelocie, zeby dryf termiczny nie udawal efektu
  if [ "$pass" = 1 ]; then V="default powersave performance"; else V="performance powersave default"; fi
  for v in $V; do
    echo "$v" > $POL || { echo "  SETFAIL $v"; continue; }
    [ "$(polstate)" = "$v" ] || { echo "  ROZBIEZNOSC: $(polstate) a nie $v"; continue; }
    echo "  $v/p$pass: l1_aspm=$(cat $LNK/l1_aspm) clkpm=$(cat $LNK/clkpm)"
    waitload 900 || { echo "  POMINIETY $v/p$pass: cpu=$(busy)% load1=$(load1)"; continue; }
    sleep "$SETTLE"
    L0="$(busy)%/$(load1)"
    python3 idle_sampler.py --sec "$SEC" --tag "$v/p$pass" --out "$OUT" \
      | python3 -c 'import json,sys; o=json.load(sys.stdin); print("   %-16s gpu_trapz=%5.2fW cpu_pkg=%6.2fW mv=%s busy=%s%% l1=%s clkpm=%s" % (o["tag"], o["gpu_w_trapz"], o["cpu_pkg_w"], o["mv_med"], o["busy_avg"], o["l1_aspm"], o["clkpm"]))'
    L1="$(busy)%/$(load1)"
    echo "     cpu/load przed=$L0 po=$L1"
    loadok || echo "     UWAGA: obciazenie wzroslo w trakcie okna, ta probka jest podejrzana"
  done
done
echo "=== FAZA 16e DONE, incydenty=$(dmesg_n) ==="
