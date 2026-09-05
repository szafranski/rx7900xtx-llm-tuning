#!/usr/bin/env bash
# Rownolegle zapytania do jednego serwera: ile slotow, jak dziala kolejka.
# $1 = scenariusz: 3req | warm | solo | 4req
# $2 = liczba slotow, z jaka serwer zostal wystartowany (tylko do etykiet)
#
# UWAGA: serwer NIE jest startowany przez ten skrypt. Mierzony byl dzialajacy
# serwer produkcyjny, ta sama linia co w README plus:
#   --ctx-size 147456 --parallel N --kv-unified
#   --cache-prompt --cache-reuse 256 --metrics --no-context-shift --timeout 900
# Liczba slotow zmieniana recznie i restart. Log potwierdza:
#   srv load_model: initializing, n_slots = N, n_ctx_slot = 147456, kv_unified = 'true'
#
# Ten test ma inny rygor niz reszta repo: jeden przebieg na konfiguracje,
# aktywny pulpit, brak telemetrii GPU, brak pary zerowej. Patrz docs/concurrency.md.
#
# Prompty podaje sie przez zmienne srodowiskowe. Oryginalne nie sa w repo:
# byly to lokalne pliki zrodlowe tego hosta ze sciezkami w srodku. Rozmiary,
# ktore mierzylismy, to 8390 / 55 / 2121 tokenow. Dowolne pliki o zblizonym
# rozmiarze daja ten sam ksztalt testu.
#
# Kolejnosc, w jakiej to bylo uruchamiane, ma znaczenie dla cache promptu:
#   ./bench-concurrency.sh 3req 2     # zimny cache po restarcie
#   ./bench-concurrency.sh warm 2     # te same prompty jeszcze raz
#   ./bench-concurrency.sh solo 2     # jedno zapytanie, cache trafiony
#   (restart serwera z --parallel 3)
#   ./bench-concurrency.sh 3req 3
#   ./bench-concurrency.sh 4req 3
# Na koniec: python3 scripts/concurrency_collect.py
set -uo pipefail
SCEN=${1:?scenariusz: 3req | warm | solo | 4req}
SLOTS=${2:?liczba slotow serwera}
PORT=${PORT:-8086}
P_MAIN=${P_MAIN:?ustaw P_MAIN na plik promptu, u nas 8390 tokenow}
P_WS=${P_WS:?ustaw P_WS na plik promptu, u nas 55 tokenow}
P_WM=${P_WM:?ustaw P_WM na plik promptu, u nas 2121 tokenow}
P_WS2=${P_WS2:-$P_WS}
mkdir -p results logs

# Sampler 1 Hz: VRAM z sysfs + liczniki z /metrics.
mon() {
  local V=/sys/class/drm/card1/device/mem_info_vram_used
  [[ -e $V ]] || V=$(ls /sys/class/drm/card*/device/mem_info_vram_used | head -1)
  while true; do
    local vram=$(( $(cat "$V") / 1024 / 1024 ))
    # Timeout 2 s: przy ciezkim prompt processing /metrics czasem nie odpowiada
    # i probka zostaje bez licznikow. To jest wynik, nie blad sampleera.
    local m
    m=$(curl -s --max-time 2 "localhost:$PORT/metrics" | awk '/^llamacpp:(requests_processing|requests_deferred|n_busy_slots_per_decode|prompt_tokens_total|tokens_predicted_total) /{printf "%s=%s ",$1,$2}')
    echo "$(date +%H:%M:%S) vram=${vram}MiB $m"
    sleep 1
  done
}

# $1 = etykieta, $2 = n_predict, $3 = plik z promptem
req() {
  local label=$1 np=$2 pf=$3 t0 t1
  t0=$(date +%s.%N)
  python3 - "$pf" "$np" > "results/body-$label.json" <<'PY'
import json, sys
p = open(sys.argv[1]).read()
json.dump({"model": "qwen3.8-27b-128k",
           "messages": [{"role": "user", "content": p}],
           "max_tokens": int(sys.argv[2]),
           "temperature": 0.6, "stream": False}, sys.stdout)
PY
  curl -s -X POST "localhost:$PORT/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d @"results/body-$label.json" -o "results/resp-$label.json"
  t1=$(date +%s.%N)
  echo "$label wall=$(echo "$t1-$t0" | bc)" > "results/wall-$label.txt"
}

# Sampler chodzi przez caly scenariusz. Jeden plik na liczbe slotow, wiec
# kolejne scenariusze przy tej samej liczbie slotow dopisuja sie do niego.
mon >> "logs/monitor-p$SLOTS.log" 2>&1 &
MON=$!
trap 'kill $MON 2>/dev/null' EXIT
sleep 2

case "$SCEN" in
  # Symulacja agenta kodowego: watek glowny z dlugim promptem, workery +2 s.
  3req) req "p${SLOTS}-main" 800 "$P_MAIN" & P1=$!
        sleep 2
        req "p${SLOTS}-worker-s" 400 "$P_WS" & P2=$!
        req "p${SLOTS}-worker-m" 400 "$P_WM" & P3=$!
        wait $P1 $P2 $P3 ;;
  # Te same prompty jeszcze raz, zeby zmierzyc trafienie cache promptu.
  warm) req "p${SLOTS}-main-warm" 800 "$P_MAIN" & P1=$!
        req "p${SLOTS}-worker-m-warm" 400 "$P_WM" & P2=$!
        wait $P1 $P2 ;;
  # Jedno zapytanie, zeby miec odniesienie bez rywalizacji o karte.
  solo) req "p${SLOTS}-solo" 400 "$P_WM" ;;
  # O jedno zapytanie wiecej niz slotow: prog kolejkowania.
  4req) req "p${SLOTS}-q1" 800 "$P_MAIN" & P1=$!
        req "p${SLOTS}-q2" 400 "$P_WS" & P2=$!
        req "p${SLOTS}-q3" 400 "$P_WM" & P3=$!
        req "p${SLOTS}-q4" 400 "$P_WS2" & P4=$!
        wait $P1 $P2 $P3 $P4 ;;
  *) echo "nieznany scenariusz: $SCEN" >&2; exit 2 ;;
esac

kill $MON 2>/dev/null
trap - EXIT

for f in results/resp-p${SLOTS}-*.json; do
  python3 - "$f" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
l = p.stem[len("resp-"):]
t = json.load(p.open())["timings"]
w = float(pathlib.Path(f"results/wall-{l}.txt").read_text().split("=")[1])
n = t["cache_n"] + t["prompt_n"]
print(f"{l:22} prompt={n:6} cache_n={t['cache_n']:6} "
      f"pp={t['prompt_ms']/1000:6.1f}s tg={t['predicted_per_second']:5.1f} tok/s "
      f"wall={w:5.1f}s")
PY
done
