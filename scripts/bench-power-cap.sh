#!/bin/bash
# Faza 8: sweep power1_cap. Wymaga zapisywalnego power1_cap (chmod 666 od uzytkownika).
# Zapisuje TYLKO power1_cap, w zakresie wymuszonym przez sterownik. Na koncu przywraca 303 W.
set -u
OUT=results/power-cap-sweep.jsonl
CAPF=/sys/class/drm/card1/device/hwmon/hwmon1/power1_cap
DEFAULT=303000000
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
Q="Napisz po polsku szczegolowa, rzeczowa notatke techniczna o tym, jak dziala pamiec podreczna procesora: poziomy L1/L2/L3, polityki zapisu, spojnosc miedzy rdzeniami, wplyw lokalnosci odwolan na wydajnosc. Rozwin kazdy watek."

kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
jt(){ echo $(($(cat /sys/class/drm/card1/device/hwmon/hwmon1/temp2_input)/1000)); }
cool(){ for i in $(seq 1 36); do [ "$(jt)" -le 50 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }

setcap(){ # $1 uW ; zwraca 1 gdy nie udalo sie ustawic
  echo "$1" > "$CAPF" 2>/dev/null || { echo "CAPWRITE_FAIL $1 (brak uprawnien?)" | tee -a $OUT; return 1; }
  local got=$(cat "$CAPF")
  [ "$got" = "$1" ] || { echo "CAPMISMATCH chcialem=$1 jest=$got" | tee -a $OUT; return 1; }
  echo "cap ustawiony na $((got/1000000)) W"; return 0
}

restore(){ echo "$DEFAULT" > "$CAPF" 2>/dev/null; echo "PRZYWROCONO cap=$(($(cat $CAPF)/1000000)) W" | tee -a $OUT; }
[ -w "$CAPF" ] || { echo "BLAD: $CAPF nie jest zapisywalny. Uruchom chmod 666." | tee -a $OUT; exit 1; }

trap 'kill_srv; restore' EXIT


run_at(){ # $1 tag  $2 extra-spec
  local tag=$1; shift
  kill_srv; cool
  SRV_LOG="logs/f8-$tag.log" ./srv.sh $BASE "$@" $REAS \
    || { echo "SRVFAIL $tag" | tee -a $OUT; return 0; }
  for rep in 1 2; do
    python3 pw.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
      --reasoning medium --tag "$tag/r$rep" --idle-w 12.7 --out $OUT >/dev/null 2>&1 \
      && echo "  ok $tag/r$rep" || echo "  FAIL $tag/r$rep"
  done
  kill_srv
}

# sonda: czy sterownik naprawde pilnuje power1_cap_min (deklaruje 272 W)
echo "=== sonda 250 W (spodziewane odrzucenie, cap_min=$(($(cat ${CAPF}_min)/1000000)) W) ==="
if setcap 250000000; then
  echo "SONDA250 PRZYJETE - sterownik nie pilnuje cap_min, mierze ten punkt" | tee -a $OUT
  CAPS="303 288 272 250"
else
  echo "SONDA250 ODRZUCONE - 272 W to twardy dol, zgodnie z cap_min" | tee -a $OUT
  CAPS="303 288 272"
fi
setcap "$DEFAULT" >/dev/null

for cap in $CAPS; do
  echo "=== cap ${cap} W ==="
  setcap "${cap}000000" || continue
  run_at "cap${cap}" $SPEC
done

# kontrola: czy przy najnizszym capie n-max 3 nadal bije n-max 2
echo "=== kontrola n-max 2 przy 272 W ==="
setcap 272000000 && run_at "cap272-nmax2" --spec-type draft-mtp --spec-draft-n-max 2 --spec-draft-p-min 0.60

echo "FAZA8 DONE" | tee -a $OUT
