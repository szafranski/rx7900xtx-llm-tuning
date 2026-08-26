#!/bin/bash
# Faza 16 krok 1: czy n-gram miesci sie na 128K kontekstu.
# Faza 5 zmierzyla szczyt VRAM 22853 MiB (bez projektora) i 23741 MiB
# (z projektorem Q8_0) z 24560 MiB dostepnych. N-gram trzyma wlasne struktury
# dopasowania, ktorych nigdy nie mierzylem osobno. Jesli nie mieszcza sie,
# przyjeta flaga wysadza serwer w srodku dlugiej sesji agentowej.
#
# Poprawka wobec f5.sh: tam "vram_peak" bylo JEDNYM odczytem PO zakonczeniu
# przebiegu, wiec nie bylo szczytem. Tu chodzi probnik w tle co 0.5 s.
set -u
cd "$(dirname "$0")"
OUT=results/context-128k.jsonl
D=/sys/class/drm/card1/device
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 131072 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
SPECBASE="--spec-draft-n-max 3 --spec-draft-p-min 0.60"
MMPROJ=mmproj/mmproj-ggmlorg-BF16.gguf
Q="Odpowiedz po polsku. Podaj doslownie klucz kontrolny wystepujacy w tekscie oraz imie i nazwisko osoby, ktora go zapisala, wraz z lokalizacja."

kill_srv(){ pgrep -f "[l]lama-server.*8099" >/dev/null && { pkill -f "[l]lama-server.*8099"; sleep 5; }; return 0; }
vram(){ echo $(($(cat $D/mem_info_vram_used)/1048576)); }
gtt(){ echo $(($(cat $D/mem_info_gtt_used)/1048576)); }
jt(){ echo $(($(cat $D/hwmon/hwmon1/temp2_input)/1000)); }
cool(){ for i in $(seq 1 24); do [ "$(jt)" -le 55 ] && break; sleep 5; done; }
spec(){ case "$1" in
  mtp)       echo "--spec-type draft-mtp $SPECBASE" ;;
  ngmapk)    echo "--spec-type draft-mtp,ngram-map-k $SPECBASE" ;;
  ngsimple)  echo "--spec-type draft-mtp,ngram-simple $SPECBASE" ;;
esac; }
SPID=""
samp_start(){ # $1 plik na szczyt "vram gtt"
  echo "0 0" > "$1"
  ( m=0; g=0
    while :; do
      v=$(vram); t=$(gtt)
      [ "$v" -gt "$m" ] && m=$v; [ "$t" -gt "$g" ] && g=$t
      echo "$m $g" > "$1"; sleep 0.5
    done ) & SPID=$!
}
samp_stop(){ [ -n "$SPID" ] && kill $SPID 2>/dev/null; SPID=""; }
trap 'samp_stop; kill_srv' EXIT

dmesg0=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
kill_srv
echo "== A: 128K bez projektora ==" | tee -a $OUT
for v in mtp ngmapk ngsimple; do
  echo "=== $v ==="
  cool
  SRV_LOG="logs/f16a-$v.log" ./srv.sh $BASE $(spec $v) $REAS \
    || { echo "SRVFAIL $v (128K bez projektora)" | tee -a $OUT; continue; }
  echo "VRAM_idle $v = $(vram) MiB, GTT $(gtt) MiB" | tee -a $OUT
  samp_start /tmp/f16a-peak-$v
  for rep in 1 2 3; do
    python3 run1.py --prompt prompts/P98K.txt --question "$Q" --max-tokens 1200 \
      --reasoning medium --tag "$v/r$rep" --out $OUT >/dev/null 2>&1 \
      && echo "  ok $v/r$rep" || echo "  FAIL $v/r$rep"
  done
  samp_stop
  echo "VRAM_peak $v = $(cut -d' ' -f1 /tmp/f16a-peak-$v) MiB, GTT_peak $(cut -d' ' -f2 /tmp/f16a-peak-$v) MiB" | tee -a $OUT
  kill_srv
done

echo "== B: 128K + projektor BF16 (worst case, 1 przebieg) ==" | tee -a $OUT
for v in mtp ngmapk ngsimple; do
  echo "=== img-$v ==="
  cool
  SRV_LOG="logs/f16a-img-$v.log" ./srv.sh $BASE $(spec $v) $REAS --mmproj $MMPROJ --image-min-tokens 1024 \
    || { echo "SRVFAIL img-$v (128K + BF16)" | tee -a $OUT; continue; }
  echo "VRAM_idle img-$v = $(vram) MiB, GTT $(gtt) MiB" | tee -a $OUT
  samp_start /tmp/f16a-peak-img-$v
  python3 run1.py --prompt prompts/P98K.txt --question "$Q" --max-tokens 1200 \
    --reasoning medium --tag "img-$v/r1" --out $OUT >/dev/null 2>&1 \
    && echo "  ok img-$v/r1" || echo "  FAIL img-$v/r1"
  samp_stop
  echo "VRAM_peak img-$v = $(cut -d' ' -f1 /tmp/f16a-peak-img-$v) MiB, GTT_peak $(cut -d' ' -f2 /tmp/f16a-peak-img-$v) MiB" | tee -a $OUT
  kill_srv
done
dmesg1=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
echo "DMESG amdgpu-incydenty: przed=$dmesg0 po=$dmesg1" | tee -a $OUT
echo "F16A DONE" | tee -a $OUT
