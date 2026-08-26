#!/usr/bin/env bash
# FAZA 16g - gdzie lezy prog odswiezania.
#
# f16f pokazal, ze tor obrazu kosztuje ~11 W na ukladach (GPU 7.9 W + pakiet CPU
# 3.0 W, ten drugi to kompozytor kwin przemalowujacy pulpit 143 razy na sekunde).
# 60 Hz odzyskuje ~5.2 W z tych 11. Sterownik AMD nie skaluje jednak plynnie -
# podnosi takty domen fclk/socclk/dcefclk skokowo po przekroczeniu progu
# przepustowosci. Pytanie brzmi wiec nie "czy warto zejsc", tylko GDZIE JEST PROG.
#
# Drabina: 143.86 -> 119.88 -> 59.95 Hz. Jesli prog lezy miedzy 120 a 143,
# zejscie na 120 kosztuje niewiele plynnosci i daje calosc oszczednosci.
#
# Loguje takty domen wyswietlania, zeby powiedziec DLACZEGO, a nie tylko ile.
#
# Powod: historia z gniazdka (HA) pokazuje, ze 14.08 o 13:00 pobor calego PC spadl
# o 16 W i wrocil 21.08. Uzytkownik pamieta, ze mogl wtedy przelaczyc monitor na
# inne zrodlo. Monitor jest jeden (DP-1), mclk na biegu jalowym stoi na 96 MHz,
# wiec klasyczna wada wielomonitorowa odpada. Zostaje sam tor obrazu: 2560x1440
# przy 143.86 Hz z HDR.
#
# Trzy ramiona: takt bazowy, 60 Hz, ekran zgaszony. Dwa przeloty w odwrotnej
# kolejnosci - drugi przelot tego samego ramienia daje pare zerowa, czyli podloge
# szumu. Jesli roznica miedzy ramionami bedzie mniejsza niz rozrzut ramienia
# bazowego wobec samego siebie, wynikiem jest "nie ma efektu", a nie "jest maly".
#
# NIE rusza napiecia, taktu karty ani limitu mocy. Faza 13 pokazala, ze offset
# napiecia nie siega biegu jalowego, a cap taktu nie trzyma zegarow w spoczynku.
set -u
cd "$(dirname "$0")"

OUT=results/display-refresh-idle.jsonl
SEC=${SEC:-120}
SETTLE=${SETTLE:-25}
DEV=DP-1
MODE_BASE=${MODE_BASE:-3}    # 2560x1440@143.86
MODE_120=${MODE_120:-4}      # 2560x1440@119.88
MODE_60=${MODE_60:-1}        # 2560x1440@59.95

export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

kd(){ kscreen-doctor "$@" >/dev/null 2>&1; }
tryb(){ kscreen-doctor -o 2>/dev/null | grep -o '[0-9]*x[0-9]*@[0-9.]*\*' | tr -d '*'; }
dpmsstan(){ cat /sys/class/drm/card1-$DEV/dpms 2>/dev/null; }
DEVSYS=/sys/class/drm/card1/device
# poziom aktywny (z gwiazdka) w danej domenie zegarowej
lvl(){ awk '/\*/{gsub(/Mhz.*/,"",$2); print $2; exit}' "$DEVSYS/pp_dpm_$1" 2>/dev/null; }
takty(){ echo "fclk=$(lvl fclk) socclk=$(lvl socclk) dcefclk=$(lvl dcefclk) mclk=$(lvl mclk)"; }

przywroc(){
  kd --dpms on
  kd output.$DEV.mode.$MODE_BASE
  sleep 2
  echo "PRZYWROCONO tryb=$(tryb) dpms=$(dpmsstan)"
}
trap 'echo "PRZERWANE - przywracam ekran"; przywroc; exit 130' INT TERM

# --- bramki wejsciowe ---------------------------------------------------------
pgrep -f "[l]lama-server" >/dev/null && { echo "BLAD: llama-server dziala, bieg jalowy bylby zaklamany"; exit 1; }

BUSYMAX=${BUSYMAX:-3.0}
load1(){ cut -d" " -f1 /proc/loadavg; }
# Zajetosc CPU z /proc/stat, nie loadavg - patrz komentarz w bench-aspm-idle.sh.
busy(){ python3 -c '
import time
def rd():
    v = list(map(int, open("/proc/stat").readline().split()[1:]))
    return sum(v), v[3] + v[4]
a = rd(); time.sleep(4); b = rd()
tot = b[0] - a[0]
print("%.1f" % (100.0 * (tot - (b[1] - a[1])) / tot if tot else 0.0))
'; }
loadok(){ awk -v m="$BUSYMAX" -v b="$(busy)" 'BEGIN{exit !(b<=m)}'; }
waitload(){
  local n=$(( ${1:-600} / 10 )) i
  for i in $(seq 1 $n); do loadok && return 0
    [ $((i % 6)) = 1 ] && echo "  czekam na wyciszenie: cpu=$(busy)% > $BUSYMAX%, load1=$(load1)"
    sleep 10
  done
  return 1; }

kscreen-doctor -o >/dev/null 2>&1 || { echo "BLAD: brak dostepu do kscreen-doctor"; exit 1; }
TRYB0=$(tryb)
echo "tryb wyjsciowy=$TRYB0 dpms=$(dpmsstan)"
[ -n "$TRYB0" ] || { echo "BLAD: nie odczytalem trybu"; exit 1; }

waitload 1800 || { echo "PRZERWANE: maszyna nie wyciszyla sie cpu=$(busy)% load1=$(load1)"; exit 1; }
echo "na starcie: cpu=$(busy)% load1=$(load1)"
echo "=== FAZA 16g start: SEC=$SEC SETTLE=$SETTLE ==="

# --- ramiona ------------------------------------------------------------------
ustaw(){   # $1 = nazwa ramienia
  case "$1" in
    hz144) kd --dpms on; kd output.$DEV.mode.$MODE_BASE ;;
    hz120) kd --dpms on; kd output.$DEV.mode.$MODE_120 ;;
    hz60)  kd --dpms on; kd output.$DEV.mode.$MODE_60 ;;
    *) return 1 ;;
  esac
  sleep 3; }

for pass in 1 2; do
  if [ "$pass" = 1 ]; then V="hz144 hz120 hz60"; else V="hz60 hz120 hz144"; fi
  for v in $V; do
    ustaw "$v" || { echo "  SETFAIL $v"; continue; }
    echo "  $v/p$pass: tryb=$(tryb) dpms=$(dpmsstan) $(takty)"
    waitload 900 || { echo "  POMINIETY $v/p$pass: cpu=$(busy)%"; continue; }
    sleep "$SETTLE"
    D0=$(dpmsstan); L0="$(busy)%/$(load1)"
    python3 idle_sampler.py --sec "$SEC" --tag "$v/p$pass" --out "$OUT" | python3 -c '
import json,sys
for l in sys.stdin:
    l=l.strip()
    if not l.startswith("{"): continue
    o=json.loads(l)
    print("   %-12s gpu_trapz=%5.2fW cpu_pkg=%6.2fW mclk=%s sclk=%s dpms=%s busy=%s%%" % (
        o["tag"], o["gpu_w_trapz"], o["cpu_pkg_w"], o["mclk_med"], o["sclk_med"], o["dpms"], o["busy_avg"]))
'
    D1=$(dpmsstan); L1="$(busy)%/$(load1)"
    echo "     cpu/load przed=$L0 po=$L1  dpms przed=$D0 po=$D1"
    echo "     takty po oknie: $(takty)"
    [ "$D0" = "$D1" ] || echo "     UWAGA: dpms zmienil sie w trakcie okna (ruch myszy?), ta probka jest podejrzana"
    loadok || echo "     UWAGA: obciazenie wzroslo w trakcie okna, ta probka jest podejrzana"
  done
done

echo "=== FAZA 16g DONE ==="
przywroc
[ "$(tryb)" = "$TRYB0" ] || echo "UWAGA: tryb koncowy $(tryb) rozni sie od wyjsciowego $TRYB0"
