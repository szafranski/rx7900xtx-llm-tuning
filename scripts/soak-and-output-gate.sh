#!/bin/bash
# Faza 16 krok 3: soak nastawy DOCELOWEJ (spekulacja + GPU razem).
# Wszystkie soaki fazy 9-14 chodzily na czystym draft-mtp. Od fazy 15 nastawa
# docelowa ma tez ngram-map-k, a soak testuje konkretna kombinacje, nie warstwy
# osobno. Poprawki wobec bench-profile-combinations.sh i bench-stock-303w.sh:
#   1. kill_srv jest PRZED bramka po soaku - tam bylo po niej, wiec perplexity
#      walczylo o VRAM z zywym serwerem.
#   2. skrot sha1 kazdego przebiegu soaka (poprawka w soak.py), bo po fazie 14
#      wolno porownywac wyjscie bit w bit. Dla ngram-map-k punktem odniesienia
#      jest pierwszy przebieg tego samego soaka - skroty z draft-mtp nie
#      obowiazuja, bo inny ksztalt draftu daje inne wyjscie (faza 15, krok 3c).
# Uzycie: WARIANT=wydajnosc|oszczednosc SPEC=ngmapk|mtp ./soak-and-output-gate.sh [soak_sek]
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
CAP=$H/power1_cap
POL=/sys/module/pcie_aspm/parameters/policy
WARIANT=${WARIANT:-wydajnosc}
ASPMP=${ASPM:-performance}   # performance|default|powersave - osobne pokretlo, bo
                             # kosztuje +3.9 W stale na biegu jalowym za +1% pod obciazeniem
SPECV=${SPEC:-ngmapk}
SOAK=${1:-1800}
MV=${MV:--75}
CAPW=${CAPW:-272}
JT_ABORT=98
OUT=results/soak-$WARIANT-$SPECV-aspm${ASPM:-performance}.jsonl
SOAKOUT=results/soak-$WARIANT-$SPECV-aspm${ASPM:-performance}-runs
PPLOUT=results/soak-perplexity.tsv
PPL=/home/user/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-perplexity
MODEL=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
CHUNKS=${CHUNKS:-20}
PPL_REF=5.9335
CAP_OLD=$(cat $CAP)
SPECBASE="--spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
spec(){ case "$1" in
  mtp)    echo "--spec-type draft-mtp $SPECBASE" ;;
  ngmapk) echo "--spec-type draft-mtp,ngram-map-k $SPECBASE" ;;
esac; }
eval "$(grep '^Q=' bench-power-cap.sh)"
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
kill_srv(){ pgrep -f "[l]lama-server.*8099" >/dev/null && { pkill -f "[l]lama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 36); do [ "$(jt)" -le 55 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }
polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
POL_OLD=$(polstate)          # stan zastany, przywracany w restore()
ABORTF=$(mktemp -u /tmp/f16c-abort.XXXXXX)
restore(){ [ -w "$CAP" ] && echo "$CAP_OLD" > $CAP 2>/dev/null
  [ -w "$OD" ] && { echo r > "$OD" 2>/dev/null; echo auto > "$PL" 2>/dev/null; }
  [ -w "$POL" ] && echo "${POL_OLD:-default}" > $POL 2>/dev/null
  echo "PRZYWROCONO cap=$(( $(cat $CAP)/1000000 ))W perf=$(cat $PL) aspm=$(polstate)" | tee -a $OUT; }
ppl(){ local log="logs/f16c-ppl-$1.log" t0=$SECONDS
  $PPL -m $MODEL -f wikitext-2-raw/wiki.test.raw -c 4096 -fa on -ngl 99 -ub 1024 -b 4096 \
       -ctk q8_0 -ctv q8_0 --chunks $CHUNKS -t 6 > "$log" 2>&1
  local p=$(grep -oE "Final estimate: PPL = [0-9.]+" "$log" | grep -oE "[0-9.]+$"); [ -z "$p" ] && p="FAIL"
  printf "%s\t%s\t%s\t%s\n" "$1" "$p" "$CHUNKS" "$((SECONDS-t0))" >> $PPLOUT
  echo "$p"; }
dmesg_count(){ dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)"; }
DMESG0=$(dmesg_count)
dmesg_check(){ local n=$(dmesg_count) d
  d=$(( ${n:-0} - ${DMESG0:-0} ))
  echo "DMESG $1 amdgpu-incydenty: bazowo=$DMESG0 teraz=$n NOWE=$d" | tee -a $OUT
  [ "$d" -le 0 ]; }
MAINPID=$$
watchdog(){ while sleep 10; do t=$(jt); [ "$t" -ge "$JT_ABORT" ] && {
    echo "STRAZNIK: junction=$t C >= $JT_ABORT, PRZERYWAM CALY EKSPERYMENT" | tee -a $OUT
    touch "$ABORTF"
    kill_srv
    pkill -f "[s]oak.py" 2>/dev/null      # bash odklada TERM do konca dziecka na pierwszym planie
    echo "$CAP_OLD" > $CAP 2>/dev/null
    kill -TERM $MAINPID 2>/dev/null
    return 0; }; done; }
[ -s "$PPLOUT" ] || printf "wariant\tppl\tchunks\tsek\n" > $PPLOUT
[ -w "$CAP" ] || { echo "BLAD: $CAP nie do zapisu (chmod 666 ginie przy restarcie)."; exit 1; }
trap 'kill_srv; restore; rm -f "$ABORTF" "$ABORTF.seq"' EXIT
TAG="f16c-$WARIANT-$SPECV-aspm$ASPMP"
echo "$ASPMP" > $POL || { echo "BLAD: polityka ASPM odrzucona"; exit 1; }
[ "$(polstate)" = "$ASPMP" ] || { echo "BLAD: polityka to $(polstate) a nie $ASPMP"; exit 1; }
echo r > "$OD" || exit 1
echo manual > "$PL" || exit 1
echo "vo $MV" > "$OD" || { echo "vo odrzucony"; exit 1; }
[ "$WARIANT" = oszczednosc ] && { echo "s 1 2200" > "$OD" || { echo "cap taktu odrzucony"; exit 1; }; }
echo c > "$OD" || { echo "commit odrzucony"; exit 1; }
GV=$(grep -oE '\-?[0-9]+mV' "$OD" | tail -1 | tr -d 'mV')
[ "$GV" = "$MV" ] || { echo "ROZBIEZNOSC: vo=${GV}mV a nie $MV (obcinanie, faza 13)"; exit 1; }
echo "$((CAPW*1000000))" > "$CAP" || { echo "cap odrzucony"; exit 1; }
GC=$(( $(cat $CAP)/1000000 ))
[ "$GC" = "$CAPW" ] || { echo "ROZBIEZNOSC: cap=${GC}W a nie $CAPW"; exit 1; }
echo "=== $TAG === vo=${GV}mV cap=${GC}W perf=$(cat $PL) aspm=$(polstate) spec=$(spec $SPECV)" | tee -a $OUT
p=$(ppl "$TAG"); echo "PPL $TAG na zimno=$p ref=$PPL_REF" | tee -a $OUT
[ "$p" = "$PPL_REF" ] || { echo "STOP: bramka determinizmu padla na zimno (PPL=$p)." | tee -a $OUT; dmesg_check "$TAG"; exit 1; }
kill_srv; cool
SRV_LOG="logs/$TAG.log" ./srv.sh $BASE $(spec $SPECV) $REAS || { echo "SRVFAIL $TAG" | tee -a $OUT; exit 1; }
watchdog & WD=$!
echo "=== soak ${SOAK}s, straznik na junction >= $JT_ABORT C ==="
python3 soak.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 --reasoning medium \
  --secs "$SOAK" --out "${SOAKOUT}.jsonl" --tsv "${SOAKOUT}.tsv" 2>&1 | tail -n 20
echo "  junction po soaku=$(jt) C" | tee -a $OUT
kill -TERM $WD 2>/dev/null
kill_srv   # PRZED bramka: w bench-stock-303w.sh perplexity chodzilo przy zywym serwerze
p2=$(ppl "$TAG-po-soak"); echo "PPL $TAG po soaku=$p2 (przed: $p)" | tee -a $OUT
REFSEQ="results/reference-sequence-$TAG.json"
python3 - <<PY | tee -a $OUT
import json, os
# faza 17: powtarzalnosc mierzy sie MIEDZY sesjami, pozycja po pozycji.
# Serwer niesie stan miedzy zapytaniami (pamiec podreczna kontekstu), wiec
# przebieg i i przebieg 1 w tej samej sesji nie maja prawa dac tego samego
# wyjscia. Stara bramka porownywala je i dawala falszywy alarm.
o = [json.loads(l) for l in open("${SOAKOUT}.jsonl") if l.strip().startswith("{")][-1]
h = [r.get("sha1") for r in o["runs"]]
ref_path = "$REFSEQ"
print("SOAK skroty: %d przebiegow, %d unikalnych" % (len(h), len(set(h))))
if not os.path.exists(ref_path):
    json.dump(h, open(ref_path, "w"))
    print("SEKWENCJA: brak odniesienia, zapisano %d skrotow do %s" % (len(h), ref_path))
else:
    ref = json.load(open(ref_path))
    n = min(len(ref), len(h))
    bad = [i for i in range(n) if ref[i] != h[i]]
    if not n:
        print("SEKWENCJA: brak przebiegow do porownania")
    elif bad:
        print("SEKWENCJA ROZJAZD: %d/%d niezgodnych, pierwszy na pozycji %d (%s zamiast %s)"
              % (len(bad), n, bad[0] + 1, h[bad[0]], ref[bad[0]]))
        open("$ABORTF.seq", "w").close()
    else:
        print("SEKWENCJA ZGODNA: %d/%d wzgledem %s" % (n, n, ref_path))
PY
echo "  junction po=$(jt) C"
dmesg_check "$TAG" || { echo "F16C FAIL: nowe incydenty amdgpu w trakcie soaka" | tee -a $OUT; exit 1; }
[ -e "$ABORTF" ] && { echo "F16C FAIL: przerwane przez straznika temperatury" | tee -a $OUT; exit 1; }
[ -e "$ABORTF.seq" ] && { echo "F16C FAIL: rozjazd sekwencji wyjscia wzgledem odniesienia" | tee -a $OUT; exit 1; }
echo "F16C DONE" | tee -a $OUT
