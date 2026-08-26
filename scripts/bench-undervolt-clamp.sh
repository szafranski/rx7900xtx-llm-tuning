#!/bin/bash
# Faza 11C: domkniecie pytania z 11A. Czy offset napiecia ponizej -75 mV realnie
# schodzi nizej pod capem taktu, czy sterownik go obcina? Kanal pomiarowy:
# hwmon/in0_input (realny VDDGFX w mV) - ten sam, ktorego uzywa pw.py jako mv_avg.
# Obciazenie: llama-perplexity, bo i tak jest bramka jakosci. Bez pw.py, bo tok/s
# w 11A juz zmierzone i plaskie - tu interesuje nas wylacznie napiecie.
# Uzycie: ./bench-undervolt-clamp.sh 2200:-75 2200:-200 3045:-75
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
POL=/sys/module/pcie_aspm/parameters/policy
OUT=results/undervolt-clamp-vddgfx.tsv
PPL=/home/user/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-perplexity
MODEL=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
CHUNKS=${CHUNKS:-12}
PPL_REF=5.9335
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
cool(){ for i in $(seq 1 36); do [ "$(jt)" -le 55 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }
polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
set_all(){ local mhz=$1 mv=$2
  [ "$mhz" -ge 500 ] && [ "$mhz" -le 3045 ] || { echo "ODMOWA: $mhz poza 500-3045"; return 1; }
  [ "$mv" -le 0 ] && [ "$mv" -ge -250 ] || { echo "ODMOWA: $mv poza 0..-250"; return 1; }
  echo r > "$OD" || return 1
  echo manual > "$PL" || return 1
  echo "vo $mv" > "$OD" || return 1
  echo "s 1 $mhz" > "$OD" || return 1
  echo c > "$OD" || return 1
  local gv=$(grep -oE '\-?[0-9]+mV' "$OD" | tail -1 | tr -d 'mV')
  local gs=$(sed -n '/OD_SCLK/,/OD_MCLK/p' "$OD" | grep -oE '^1: [0-9]+' | grep -oE '[0-9]+$')
  [ "$gv" = "$mv" ] && [ "$gs" = "$mhz" ] || { echo "  ROZBIEZNOSC: odczyt vo=${gv} sclk=${gs}"; return 1; }
  echo "  ustawione vo=${gv}mV sclk_max=${gs}MHz aspm=$(polstate)"
}
restore(){ [ -w "$OD" ] && { echo r > "$OD" 2>/dev/null; echo auto > "$PL" 2>/dev/null; }
  [ -w "$POL" ] && echo default > $POL 2>/dev/null
  echo "PRZYWROCONO perf=$(cat $PL) vo=$(grep -oE '\-?[0-9]+mV' $OD | tail -1) aspm=$(polstate)"; }
# probkuje in0_input co 1 s dopoki plik-znacznik istnieje
sampler(){ local f=$1
  while [ -e "$f" ]; do
    echo "$(cat $H/in0_input) $(cat $H/freq1_input) $(cat $H/power1_average) $(jt)" >> "$f.raw"
    sleep 1
  done
}
[ -s "$OUT" ] || printf "wariant\tsclk_cap\tvo_mV\tvddgfx_avg_mV\tvddgfx_max_mV\tsclk_avg_MHz\tmoc_avg_W\tjt_max_C\tprobki\tppl\n" > $OUT
trap 'restore' EXIT
echo performance > $POL || { echo "BLAD: ASPM odrzucony"; exit 1; }
for spec in "$@"; do
  mhz=${spec%%:*}; mv=${spec##*:}
  tag="f11c-sclk${mhz}-uv${mv}"
  echo "=== $tag ==="
  set_all "$mhz" "$mv" || { echo "$tag SETFAIL"; continue; }
  cool
  MARK=/tmp/f11c.$$
  : > "$MARK"; : > "$MARK.raw"
  sampler "$MARK" & SP=$!
  log="logs/f11c-$tag.log"
  $PPL -m $MODEL -f wikitext-2-raw/wiki.test.raw -c 4096 -fa on -ngl 99 -ub 1024 -b 4096 \
       -ctk q8_0 -ctv q8_0 --chunks $CHUNKS -t 6 > "$log" 2>&1
  rm -f "$MARK"; wait $SP 2>/dev/null
  p=$(grep -oE "Final estimate: PPL = [0-9.]+" "$log" | grep -oE "[0-9.]+$"); [ -z "$p" ] && p="FAIL"
  # pierwsze 15 probek to rozbieg (wczytywanie modelu), odrzucam
  read vavg vmax savg wavg jtmax n <<<"$(awk 'NR>15 && $1>0 {v+=$1; if($1>vm)vm=$1; s+=$2; w+=$3; if($4>j)j=$4; n++}
    END{ if(n>0) printf "%.1f %d %.0f %.1f %d %d", v/n, vm, s/n/1000000, w/n/1000000, j, n; else print "0 0 0 0 0 0" }' "$MARK.raw")"
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$tag" "$mhz" "$mv" "$vavg" "$vmax" "$savg" "$wavg" "$jtmax" "$n" "$p" >> $OUT
  echo "  VDDGFX avg=${vavg}mV max=${vmax}mV sclk_avg=${savg}MHz moc=${wavg}W jt_max=${jtmax}C probki=$n ppl=$p"
  [ "$p" = "$PPL_REF" ] || echo "  UWAGA: ppl=$p a nie $PPL_REF"
  rm -f "$MARK.raw"
done
echo "F11C DONE"
column -t $OUT
