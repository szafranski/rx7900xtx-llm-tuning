#!/bin/bash
# Faza 7: energia na token i profil termiczny. Sprzet TYLKO do czytania:
# zaden zapis do power1_cap, pp_od_clk_voltage ani power_dpm_force_performance_level.
set -u
OUT=results/energy-early.jsonl
SOAK=results/energy-early-soak.jsonl
TSV=results/71-faza7-soak.tsv
SPEC="--spec-type draft-mtp --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctkd q8_0 -np 1 --no-warmup"
Q="Napisz po polsku szczegolowa, rzeczowa notatke techniczna o tym, jak dziala pamiec podreczna procesora: poziomy L1/L2/L3, polityki zapisu, spojnosc miedzy rdzeniami, wplyw lokalnosci odwolan na wydajnosc. Rozwin kazdy watek."

kill_srv(){ pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 5; }; return 0; }
jt(){ echo $(($(cat /sys/class/drm/card1/device/hwmon/hwmon1/temp2_input)/1000)); }

cool(){ # czekaj na wystudzenie do <=50 C, max 180 s, zeby kazda konfiguracja startowala z tego samego punktu
  for i in $(seq 1 36); do [ "$(jt)" -le 50 ] && break; sleep 5; done
  echo "  start junction=$(jt) C"
}

cfg(){ # $1 tag  $2 reasoning(""|medium)  $3... args serwera
  local tag=$1 reas=$2; shift 2
  kill_srv; cool
  SRV_LOG="logs/f7-$tag.log" ./srv.sh $BASE "$@" \
    || { echo "SRVFAIL $tag" | tee -a $OUT; return 0; }
  local ra=""; [ -n "$reas" ] && ra="--reasoning $reas"
  for rep in 1 2; do
    python3 pw.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
      $ra --tag "$tag/r$rep" --idle-w "$IDLE_W" --out $OUT >/dev/null 2>&1 \
      && echo "  ok $tag/r$rep" || echo "  FAIL $tag/r$rep"
  done
  kill_srv
}

kill_srv
echo "=== P1 idle ==="
IDLE_W=$(python3 -c 'import pw,json; d=pw.idle(6.0); print(d["w_avg"])')
echo "idle_w=$IDLE_W" | tee -a $OUT
python3 -c 'import pw,json; print(json.dumps({"tag":"idle","idle":pw.idle(6.0)}))' | tee -a $OUT

echo "=== P2 energia na token (cap 303 W, ctx 65536) ==="
cfg nomtp       ""       -ctk q8_0 -ctv q8_0   -ctvd q8_0   -ub 1024 -b 4096
cfg mtp         ""       -ctk q8_0 -ctv q8_0   -ctvd q8_0   -ub 1024 -b 4096 $SPEC
cfg mtp-turbo4  ""       -ctk q8_0 -ctv turbo4 -ctvd turbo4 -ub 1024 -b 4096 $SPEC
cfg mtp-ub288   ""       -ctk q8_0 -ctv q8_0   -ctvd q8_0   -ub 288  -b 2048 $SPEC
cfg mtp-reas    medium   -ctk q8_0 -ctv q8_0   -ctvd q8_0   -ub 1024 -b 4096 $SPEC $REAS

echo "=== P3 profil termiczny sustained 10 min (tryb docelowy) ==="
kill_srv; cool
SRV_LOG="logs/f7-soak.log" ./srv.sh $BASE -ctk q8_0 -ctv q8_0 -ctvd q8_0 \
  -ub 1024 -b 4096 $SPEC $REAS \
  && python3 soak.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
       --reasoning medium --secs 600 --out $SOAK --tsv $TSV
kill_srv
echo "FAZA7 DONE" | tee -a $OUT
