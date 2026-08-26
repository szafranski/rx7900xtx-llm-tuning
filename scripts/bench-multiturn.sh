#!/bin/bash
# Faza 15 krok 2: sesja wieloturowa z powracajacym kontekstem.
# Jedyna zmienna: --spec-type. Reszta flag identyczna.
# Transkrypt nagrywany RAZ konfiguracja kontrolna i potem tylko odtwarzany,
# zeby warianty liczyly dokladnie te same wejscia (patrz naglowek measure.py).
# Serwer restartowany dla KAZDEGO powtorzenia, nie tylko dla wariantu: po
# przejsciu 10 tur cache trzyma cala rozmowe, wiec tura 1 kolejnego powtorzenia
# trafilaby w cache w calosci i przestala byc pomiarem.
# Kolejnosc wariantow odwrocona w przebiegu 2.
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
OUT=results/multiturn-session.jsonl
TR=results/multiturn-transcript.json
MAXTOK=2600  # 900 nie wystarczalo: rozumowanie medium zjadalo caly budzet i tresc byla pusta
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
SPECBASE="--spec-draft-n-max 3 --spec-draft-p-min 0.60"
VARIANTS="${VARIANTS:-mtp ngmod ngsimple ngmapk}"
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 24); do [ "$(jt)" -le 55 ] && break; sleep 5; done; }
spec(){
  case "$1" in
    mtp)      echo "--spec-type draft-mtp $SPECBASE" ;;
    ngmod)    echo "--spec-type draft-mtp,ngram-mod $SPECBASE" ;;
    ngsimple) echo "--spec-type draft-mtp,ngram-simple $SPECBASE" ;;
    ngmapk)   echo "--spec-type draft-mtp,ngram-map-k $SPECBASE" ;;
    chain)    echo "--spec-type draft-mtp --spec-chain 1 $SPECBASE" ;;
    *)        echo "" ;;
  esac
}
trap 'kill_srv' EXIT
kill_srv
echo r > "$OD" 2>/dev/null; echo auto > "$PL"; echo 303000000 > "$H/power1_cap"
echo "STAN cap=$(cat $H/power1_cap) perf=$(cat $PL) vo=$(grep -oE '\-?[0-9]+mV' $OD | tail -1)" | tee -a $OUT

if [ ! -s "$TR" ]; then
  echo "=== nagrywanie transkryptu (kontrola) ==="
  cool
  SRV_LOG="logs/f15b-record.log" ./srv.sh $BASE $(spec mtp) $REAS || { echo "SRVFAIL record" | tee -a $OUT; exit 1; }
  python3 measure.py --turns turns.json --transcript "$TR" --mode record \
    --max-tokens $MAXTOK --reasoning medium --tag record --out $OUT || { echo "RECFAIL" | tee -a $OUT; exit 1; }
  kill_srv
fi
python3 -c "import json;t=json.load(open('$TR'));print('transkrypt:',len(t),'odpowiedzi,',sum(len(x) for x in t),'znakow')" | tee -a $OUT

for pass in 1 2; do
  if [ "$pass" = 1 ]; then V="$VARIANTS"; else V=$(echo $VARIANTS | tr ' ' '\n' | tac | tr '\n' ' '); fi
  for v in $V; do
    for rep in 1 2; do
      tag="p${pass}-$v/r$rep"
      echo "=== $tag ==="
      cool
      SRV_LOG="logs/f15b-p${pass}-$v-r$rep.log" ./srv.sh $BASE $(spec $v) $REAS \
        || { echo "SRVFAIL $tag" | tee -a $OUT; continue; }
      python3 measure.py --turns turns.json --transcript "$TR" --mode replay \
        --max-tokens $MAXTOK --reasoning medium --tag "$tag" --out $OUT >/dev/null 2>&1 \
        && echo "  ok $tag" || echo "  FAIL $tag"
      kill_srv
    done
    n=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
    echo "DMESG p${pass}-$v amdgpu-incydenty=$n" | tee -a $OUT
  done
done
echo "F15B DONE" | tee -a $OUT
