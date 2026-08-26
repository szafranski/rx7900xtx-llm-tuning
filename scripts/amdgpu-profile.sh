#!/bin/bash
set -Eeuo pipefail

mode=${1:-}
pci=${2:-0000:08:00.0}
cap_w=${3:-272000000}
offset=${4:--75}
sclk=${5:-2200}
dev=/sys/bus/pci/devices/$pci
od=$dev/pp_od_clk_voltage
perf=$dev/power_dpm_force_performance_level

[ -w "$od" ] && [ -w "$perf" ] || { echo "AMDGPU OverDrive niedostepny dla $pci"; exit 1; }

cap=
for h in "$dev"/hwmon/hwmon*; do
    [ -r "$h/name" ] && [ "$(<"$h/name")" = amdgpu ] && [ -w "$h/power1_cap" ] && { cap=$h/power1_cap; break; }
done
[ -n "$cap" ] || { echo "Nie znaleziono power1_cap dla $pci"; exit 1; }

if [ "$mode" = reset ]; then
    echo r > "$od"
    cat "${cap}_default" > "$cap"
    echo auto > "$perf"
    echo "Przywrocono ustawienia AMDGPU dla $pci"
    exit
fi
[ "$mode" = apply ] || { echo "Uzycie: $0 apply|reset [PCI [CAP_UW [OFFSET_MV [MAX_SCLK_MHZ]]]]"; exit 2; }
[[ $cap_w =~ ^[0-9]+$ && $offset =~ ^-[0-9]+$ && $sclk =~ ^[0-9]+$ ]] || { echo "Nieprawidlowe argumenty profilu"; exit 2; }

cap_min=$(<"${cap}_min")
cap_max=$(<"${cap}_max")
read -r off_min off_max < <(awk '/^VDDGFX_OFFSET:/ {gsub(/mv/, ""); print $2, $3; exit}' "$od")
read -r sclk_min sclk_max < <(awk '/^SCLK:/ {gsub(/Mhz/, ""); print $2, $3; exit}' "$od")
(( cap_w >= cap_min && cap_w <= cap_max )) || { echo "Power cap $cap_w poza zakresem $cap_min-$cap_max"; exit 1; }
(( offset >= off_min && offset <= off_max )) || { echo "Offset $offset poza zakresem $off_min-$off_max mV"; exit 1; }
(( sclk >= sclk_min && sclk <= sclk_max )) || { echo "SCLK $sclk poza zakresem $sclk_min-$sclk_max MHz"; exit 1; }

old_cap=$(<"$cap")
old_perf=$(<"$perf")
armed=1
rollback() {
    [ "${armed:-0}" = 1 ] || return
    set +e
    echo r > "$od"
    echo "$old_cap" > "$cap"
    echo "$old_perf" > "$perf"
    echo "BLAD: profil odrzucony, przywrocono stan poprzedni" >&2
}
trap rollback ERR

echo r > "$od"
echo manual > "$perf"
echo "vo $offset" > "$od"
echo "s 1 $sclk" > "$od"
echo c > "$od"
echo "$cap_w" > "$cap"

got_offset=$(awk '/^OD_VDDGFX_OFFSET:/ {getline; gsub(/mV/, ""); print; exit}' "$od")
got_sclk=$(awk '/^OD_SCLK:/ {seen=1; next} seen && $1 == "1:" {gsub(/Mhz/, "", $2); print $2; exit}' "$od")
got_cap=$(<"$cap")
got_perf=$(<"$perf")
[ "$got_offset" = "$offset" ] && [ "$got_sclk" = "$sclk" ] && [ "$got_cap" = "$cap_w" ] && [ "$got_perf" = manual ]

armed=0
trap - ERR
echo "AMDGPU $pci: cap=$((got_cap / 1000000))W offset=${got_offset}mV max_sclk=${got_sclk}MHz perf=$got_perf"
