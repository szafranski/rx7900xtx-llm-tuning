#!/bin/bash
# Faza 16 krok 2: bramka jakosci spekulacji wobec BRAKU spekulacji.
# Krok 3c fazy 15 pokazal, ze --spec-type none daje INNA odpowiedz niz kazdy
# wariant spekulacji przy temperature 0. Nie wiadomo bylo, czy gorsza, bo sha1
# mierzy powtarzalnosc, a nie poprawnosc, a llama-perplexity nie chodzi sciezka
# spekulacji. Tu 12 zadan z jednoznacznym kluczem odpowiedzi, ocena po tresci.
# "none" wyznacza sufit. Jesli spekulacja traci trafienia, to koszt jakosci
# CALEJ naszej konfiguracji od fazy 2, nie wada n-gramu.
set -u
cd "$(dirname "$0")"
OUT=${OUT:-results/quality-keyed.jsonl}
KL=${KL:-klucze16.json}
PR=prompts/Q16.txt
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
SPECBASE="--spec-draft-n-max 3 --spec-draft-p-min 0.60"
MAXTOK=${MAXTOK:-2600}  # faza 15: 900 nie wystarczalo, rozumowanie medium zjadalo caly budzet

kill_srv(){ pgrep -f "[l]lama-server.*8099" >/dev/null && { pkill -f "[l]lama-server.*8099"; sleep 5; }; return 0; }
jt(){ echo $(($(cat /sys/class/drm/card1/device/hwmon/hwmon1/temp2_input)/1000)); }
cool(){ for i in $(seq 1 24); do [ "$(jt)" -le 55 ] && break; sleep 5; done; }
spec(){ case "$1" in
  none)    echo "--spec-type none" ;;
  mtp)     echo "--spec-type draft-mtp $SPECBASE" ;;
  ngmapk)  echo "--spec-type draft-mtp,ngram-map-k $SPECBASE" ;;
esac; }

[ -f "$PR" ] || python3 gen_quality_corpus.py prompts/P50K.txt "$PR" "$KL" || exit 1
trap 'kill_srv' EXIT
kill_srv
for pass in 1 2; do
  if [ "$pass" = 1 ]; then V="none mtp ngmapk"; else V="ngmapk mtp none"; fi
  for v in $V; do
    tag="p${pass}-$v"
    echo "=== $tag ==="
    cool
    SRV_LOG="logs/f16b-$tag.log" ./srv.sh $BASE $(spec $v) $REAS \
      || { echo "SRVFAIL $tag" | tee -a $OUT; continue; }
    python3 -c "import json;[print(z['id']+'\t'+z['pytanie']) for z in json.load(open('$KL'))]" \
    | while IFS=$'\t' read -r zid q; do
        python3 run1.py --prompt "$PR" --question "$q" --max-tokens $MAXTOK \
          --reasoning medium --tag "$tag/$zid" --out $OUT >/dev/null 2>&1 \
          && echo "  ok $tag/$zid" || echo "  FAIL $tag/$zid"
      done
    kill_srv
  done
done
echo "F16B DONE" | tee -a $OUT
