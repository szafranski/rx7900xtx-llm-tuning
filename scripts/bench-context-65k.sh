#!/bin/bash
# Faza 5: walidacja koncowa - VRAM per kontekst, P98K przy reasoning medium, worst-case 128K+obraz.
set -u
OUT=results/context-128k-cache-types.jsonl
MMPROJ=${MMPROJ:-mmproj/mmproj-ggmlorg-Q8_0.gguf}
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
Q_NEEDLE="Odpowiedz po polsku. Podaj doslownie klucz kontrolny wystepujacy w tekscie oraz imie i nazwisko osoby, ktora go zapisala, wraz z lokalizacja."

kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
vram(){ echo $(($(cat /sys/class/drm/card1/device/mem_info_vram_used)/1048576)); }

probe(){ # $1 tag  $2 ctx  $3 kv  $4 ub  $5 bb  $6 extra
  kill_srv
  SRV_LOG="logs/f5-$1.log" ./srv.sh -ngl 99 -c "$2" -fa on -ctk q8_0 -ctv "$3" \
    -ctkd q8_0 -ctvd "$3" -np 1 -ub "$4" -b "$5" $SPEC $REAS --no-warmup $6 \
    || { echo "SRVFAIL $1" | tee -a $OUT; return 0; }
  echo "VRAM_idle $1 ctx=$2 ctv=$3 ub=$4 = $(vram) MiB" | tee -a $OUT
  if [ "$2" -ge 131072 ]; then
    python3 run1.py --prompt prompts/P98K.txt --question "$Q_NEEDLE" \
      --max-tokens 1024 --tag "$1/P98K" --out $OUT >/dev/null 2>&1 \
      && echo "DONE $1/P98K vram_peak=$(vram)" || echo "FAIL $1/P98K"
  fi
  kill_srv
}

for ctx in 32768 65536 131072; do
  probe "c${ctx}-q8"     $ctx q8_0   1024 4096 ""
  probe "c${ctx}-turbo4" $ctx turbo4 1024 4096 ""
done
# worst case: 128K + projektor + obraz
probe "c131072-q8-mmproj" 131072 q8_0 1024 4096 "--mmproj $MMPROJ --image-min-tokens 1024"
kill_srv
SRV_LOG="logs/f5-worst.log" ./srv.sh -ngl 99 -c 131072 -fa on -ctk q8_0 -ctv q8_0 \
  -ctkd q8_0 -ctvd q8_0 -np 1 -ub 288 -b 2048 $SPEC $REAS --no-warmup \
  --mmproj "$MMPROJ" --image-min-tokens 1024 \
 && { echo "VRAM_idle worst-ub288 = $(vram) MiB" | tee -a $OUT
      python3 run1.py --prompt prompts/P98K.txt --image images/pl-tabela.png \
        --question "$Q_NEEDLE Dodatkowo opisz zalaczona tabele." \
        --max-tokens 1024 --tag "worst-ub288/P98K+img" --out $OUT >/dev/null 2>&1 \
        && echo "DONE worst-ub288 vram_peak=$(vram)" || echo "FAIL worst-ub288"; }
kill_srv
echo "FAZA5 DONE" | tee -a $OUT
