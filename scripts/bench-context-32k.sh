#!/bin/bash
# Faza 2: sweep MTP. UB/B podstawiane przez zwyciezce fazy 1.
set -u
UB=${UB:-512}; B=${B:-2048}
OUT=results/spec-mtp-early.jsonl
Q="Podsumuj w trzech zdaniach po angielsku, co robi ten kod. Then list 5 function names."
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub $UB -b $B --reasoning off --no-warmup"

runcfg() {  # $1 = tag, reszta = flagi serwera
  local tag="$1"; shift
  pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 4; }
  SRV_LOG="logs/f2-$tag.log" ./srv.sh $BASE "$@" || return 1
  python3 run1.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 512 \
    --tag "$tag" --out $OUT >/dev/null 2>&1 || echo "RUN FAIL $tag"
  grep -oiE "draft acceptance[^,]*|n_drafted[^,]*|accept[^,]*" "logs/f2-$tag.log" | tail -3 >> logs/f2-$tag.accept
  echo "DONE $tag: $(tail -1 $OUT)"
  pkill -f "llama-server.*8099"; sleep 4
}

for n in 2 3 4 5 6; do
  runcfg "nmax$n" --spec-type draft-mtp --spec-draft-n-max $n
done
echo "FAZA2-A DONE"
