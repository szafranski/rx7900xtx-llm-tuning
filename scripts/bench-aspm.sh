#!/bin/bash
# Faza 16 krok 3a: ile ASPM jest wart POD OBCIAZENIEM w nastawie docelowej F.
# Faza 10 krok 1 mierzyla ASPM na takcie fabrycznym (+0.96%). Pod capem 2200 MHz
# karta nie jest limitowana moca, wiec nie ma powodu zakladac tej samej liczby.
# Punkt "2200 MHz + -75 mV + ASPM default" nie byl nigdy zmierzony, a wlasnie
# jego mamy przyjac - to jest glowny powod tego testu, wycena ASPM jest wtorna.
# OD (napiecie, cap taktu, cap mocy) ustawiane RAZ i nietykane; miedzy blokami
# zmienia sie wylacznie polityka ASPM. Dwa przeloty w odwrotnej kolejnosci.
set -u
cd "$(dirname "$0")"
D=/sys/class/drm/card1/device
OD=$D/pp_od_clk_voltage
PL=$D/power_dpm_force_performance_level
H=$D/hwmon/hwmon1
CAP=$H/power1_cap
POL=/sys/module/pcie_aspm/parameters/policy
LNK=/sys/bus/pci/devices/0000:08:00.0/link
MV=${MV:--75}
SCLK=${SCLK:-2200}
CAPW=${CAPW:-272}
CHUNKS=${CHUNKS:-20}
PPL_REF=5.9335
OUT=results/aspm-under-load.jsonl
PPLOUT=results/aspm-perplexity.tsv
PPL=/home/user/llm/llama-cpp-turboquant-b10539-reasoning/build-vulkan-gfx1100/bin/llama-perplexity
MODEL=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf
CAP_OLD=$(cat $CAP)
SPEC="--spec-type draft-mtp,ngram-map-k --spec-draft-n-max 3 --spec-draft-p-min 0.60"
REAS="--reasoning on --reasoning-effort medium --reasoning-budget 8192 --reasoning-format deepseek"
BASE="-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 -np 1 -ub 1024 -b 4096 --no-warmup"
eval "$(grep '^Q=' f8.sh)"   # ten sam prompt co fazy 8, 9, 10
jt(){ echo $(($(cat $H/temp2_input)/1000)); }
kill_srv(){ pgrep -f "[l]lama-server.*8099" >/dev/null && { pkill -f "[l]lama-server.*8099"; sleep 5; }; return 0; }
cool(){ for i in $(seq 1 36); do [ "$(jt)" -le 55 ] && break; sleep 5; done; echo "  start junction=$(jt) C"; }
polstate(){ grep -oE "\[[a-z]+\]" $POL | tr -d "[]"; }
lnkstate(){ echo "l1_aspm=$(cat $LNK/l1_aspm 2>/dev/null) clkpm=$(cat $LNK/clkpm 2>/dev/null)"; }
restore(){ [ -w "$CAP" ] && echo "$CAP_OLD" > $CAP 2>/dev/null
  [ -w "$OD" ] && { echo r > "$OD" 2>/dev/null; echo auto > "$PL" 2>/dev/null; }
  [ -w "$POL" ] && echo default > $POL 2>/dev/null
  echo "PRZYWROCONO cap=$(( $(cat $CAP)/1000000 ))W perf=$(cat $PL) aspm=$(polstate)" | tee -a $OUT; }
ppl(){ local log="logs/f16d-ppl-$1.log" t0=$SECONDS
  $PPL -m $MODEL -f wikitext-2-raw/wiki.test.raw -c 4096 -fa on -ngl 99 -ub 1024 -b 4096 \
       -ctk q8_0 -ctv q8_0 --chunks $CHUNKS -t 6 > "$log" 2>&1
  local p=$(grep -oE "Final estimate: PPL = [0-9.]+" "$log" | grep -oE "[0-9.]+$"); [ -z "$p" ] && p="FAIL"
  printf "%s\t%s\t%s\t%s\n" "$1" "$p" "$CHUNKS" "$((SECONDS-t0))" >> $PPLOUT
  echo "$p"; }
dmesg_check(){ local n=$(dmesg 2>/dev/null | grep -icE "amdgpu.*(reset|timeout|fault|hang)")
  echo "DMESG $1 amdgpu-incydenty=$n" | tee -a $OUT; [ "${n:-0}" = "0" ]; }
set_aspm(){ local want=$1 before after
  before=$(lnkstate)
  echo "$want" > $POL || { echo "  zapis polityki odrzucony"; return 1; }
  [ "$(polstate)" = "$want" ] || { echo "  ROZBIEZNOSC: polityka to $(polstate), nie $want"; return 1; }
  sleep 2; after=$(lnkstate)
  echo "  polityka=$want link przed: $before  po: $after"
  [ "$before" = "$after" ] && echo "  UWAGA: stan linku sie nie zmienil"
  return 0; }
run_at(){ local tag=$1
  kill_srv; cool
  SRV_LOG="logs/f16d-$tag.log" ./srv.sh $BASE $SPEC $REAS || { echo "SRVFAIL $tag" | tee -a $OUT; return 1; }
  for rep in 1 2; do
    python3 pw.py --prompt prompts/P20K.txt --question "$Q" --max-tokens 1200 \
      --reasoning medium --tag "$tag/r$rep" --idle-w 12.7 --out $OUT >/dev/null 2>&1 \
      && echo "  ok $tag/r$rep" || echo "  FAIL $tag/r$rep"
  done
  kill_srv
  echo "  junction po przelocie=$(jt) C  $(lnkstate)"; }
[ -s "$PPLOUT" ] || printf "wariant\tppl\tchunks\tsek\n" > $PPLOUT
[ -w "$CAP" ] || { echo "BLAD: $CAP nie do zapisu (chmod 666 ginie przy restarcie)."; exit 1; }
[ -w "$OD" ] || { echo "BLAD: $OD nie do zapisu."; exit 1; }
[ -w "$POL" ] || { echo "BLAD: $POL nie do zapisu."; exit 1; }
LOADMAX=${LOADMAX:-0.40}
BUSYMAX=${BUSYMAX:-3.0}   # procent zajetosci CPU, prog wlasciwy
load1(){ cut -d" " -f1 /proc/loadavg; }
# Zajetosc CPU z /proc/stat, nie loadavg. Srednia obciazenia liczy tez zadania w
# stanie nieprzerywalnym (zapisy btrfs po buildzie) i procesy niced, wiec potrafi
# stac na 1.4 przy procesorze bezczynnym w 92 procentach - i odwrotnie, krotki
# skok obciazenia w ogole nia nie rusza. Moc pakietu zalezy od zajetosci, nie od
# dlugosci kolejki, wiec progujemy na zajetosci.
busy(){ python3 -c '
import time
def rd():
    v = list(map(int, open("/proc/stat").readline().split()[1:]))
    return sum(v), v[3] + v[4]          # total, idle+iowait
a = rd(); time.sleep(4); b = rd()
tot = b[0] - a[0]
print("%.1f" % (100.0 * (tot - (b[1] - a[1])) / tot if tot else 0.0))
'; }
loadok(){ awk -v m="$BUSYMAX" -v b="$(busy)" 'BEGIN{exit !(b<=m)}'; }
for i in $(seq 1 180); do loadok && break
  [ $((i % 6)) = 1 ] && echo "czekam na wyciszenie maszyny: cpu=$(busy)% > $BUSYMAX%, load1=$(load1)"
  sleep 10; done
loadok || { echo "PRZERWANE: cpu=$(busy)% > $BUSYMAX% (load1=$(load1))"; exit 1; }
echo "na starcie: cpu=$(busy)% load1=$(load1) (prog $BUSYMAX%)"
trap 'kill_srv; restore' EXIT
# --- nastawa docelowa, raz, z weryfikacja odczytem wstecznym ---
echo r > "$OD" || exit 1
echo manual > "$PL" || exit 1
echo "vo $MV" > "$OD" || { echo "vo odrzucony"; exit 1; }
echo "s 1 $SCLK" > "$OD" || { echo "cap taktu odrzucony"; exit 1; }
echo c > "$OD" || { echo "commit odrzucony"; exit 1; }
GV=$(grep -oE '\-?[0-9]+mV' "$OD" | tail -1 | tr -d 'mV')
[ "$GV" = "$MV" ] || { echo "ROZBIEZNOSC: vo=${GV}mV a nie $MV"; exit 1; }
echo "$((CAPW*1000000))" > "$CAP" || { echo "cap mocy odrzucony"; exit 1; }
GC=$(( $(cat $CAP)/1000000 ))
[ "$GC" = "$CAPW" ] || { echo "ROZBIEZNOSC: cap=${GC}W a nie $CAPW"; exit 1; }
echo "=== FAZA 16d === vo=${GV}mV sclk=$SCLK cap=${GC}W perf=$(cat $PL) spec=ngram-map-k" | tee -a $OUT
# bramka determinizmu raz, na nastawie OD (ASPM jej nie zmienia - faza 10 krok 1)
p=$(ppl "f16d-zimno"); echo "PPL na zimno=$p ref=$PPL_REF" | tee -a $OUT
[ "$p" = "$PPL_REF" ] || { echo "STOP: bramka determinizmu padla (PPL=$p)." | tee -a $OUT; exit 1; }
for pass in 1 2; do
  if [ "$pass" = 1 ]; then V="default performance powersave"; else V="powersave performance default"; fi
  for v in $V; do
    echo "=== ASPM $v (przelot $pass) ==="
    set_aspm "$v" || { echo "ASPM $v SETFAIL" | tee -a $OUT; continue; }
    run_at "aspm-$v-p$pass"
    dmesg_check "aspm-$v-p$pass" || echo "UWAGA: incydenty amdgpu przy ASPM $v" | tee -a $OUT
  done
done
echo "F16D DONE" | tee -a $OUT
