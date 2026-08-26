#!/bin/bash
# Faza 15 krok 3c: kalibracja bramki sha1 wobec braku spekulacji.
# Powod: dane fazy 2 pokazuja, ze samo MTP daje inne sha1 przy innej glebokosci
# draftu (nmax2/3 -> 6f002e259308, nmax4/5/6 -> 546395a70615) i przy innym p-min.
# Czyli w tej kompilacji wyjscie zalezy od parametrow draftu nawet dla sciezki,
# ktora uzywamy w produkcji od fazy 2. Wniosek "chain jest zepsuty, bo zmienia
# sha1" byl wiec bledny: to samo robi konfiguracja przyjeta.
# Jedyny sensowny punkt odniesienia to BRAK spekulacji. Mierzymy, jak daleko od
# niego jest kazdy wariant, i czy warianty n-grama sa dalej niz to, co juz mamy.
set -u
cd "$(dirname "$0")"
OUT=results/spec-vs-none.jsonl
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
SPECBASE="--spec-draft-n-max 3 --spec-draft-p-min 0.60"
kill_srv(){ pgrep -f "[l]lama-server.*8099" >/dev/null && { pkill -f "[l]lama-server.*8099"; sleep 5; }; return 0; }
spec(){ case "$1" in
  none)     echo "" ;;
  mtp)      echo "--spec-type draft-mtp $SPECBASE" ;;
  chain)    echo "--spec-type draft-mtp --spec-chain 1 $SPECBASE" ;;
  ngmod)    echo "--spec-type draft-mtp,ngram-mod $SPECBASE" ;;
  ngsimple) echo "--spec-type draft-mtp,ngram-simple $SPECBASE" ;;
  ngmapk)   echo "--spec-type draft-mtp,ngram-map-k $SPECBASE" ;;
esac; }
eval "$(grep '^Q=' bench-power-cap.sh)"
trap 'kill_srv' EXIT
kill_srv
for v in none mtp chain ngmod ngsimple ngmapk; do
  echo "=== $v ==="
  SRV_LOG="logs/f15e-$v.log" ./srv.sh $BASE $(spec $v) $REAS || { echo "SRVFAIL $v"; continue; }
  python3 run1.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
    --reasoning medium --tag "$v" --out $OUT >/dev/null && echo "  ok $v" || echo "  FAIL $v"
  kill_srv
done
python3 - <<'PY'
import json
rows = {r["tag"]: r for r in (json.loads(l) for l in open("results/spec-vs-none.jsonl"))}
for v, r in rows.items():
    for k in ("content", "reasoning_content"):
        json.dump([r[k]], open(f"results/f15e-{v}-{k}.json", "w"), ensure_ascii=False)
    print(f"{v:9s} dec={r['decode_tps']:6.2f} sha={r['sha1']} n={r['predicted_n']}")
PY
for v in mtp chain ngmod ngsimple ngmapk; do
  echo "=== none kontra $v (tresc) ==="
  python3 diff_outputs.py results/f15e-none-content.json results/f15e-$v-content.json | grep -E "tura|blokow|podobienstwo"
done
echo "F15E DONE"
