#!/bin/bash
# Faza 4b: mmproj BF16 vs Q8_0. CTK/CTV/UB/B/SPEC podstawiane po fazach 1-4.
set -u
CTK=${CTK:-q8_0}; CTV=${CTV:-q8_0}; UB=${UB:-1024}; BB=${BB:-4096}
SPEC=${SPEC:-"--spec-type draft-mtp --spec-draft-n-max 3"}
OUT=results/projector-q8-vs-bf16.jsonl
declare -A P=(
 [ggmlorg-BF16]=mmproj/mmproj-ggmlorg-BF16.gguf
 [ggmlorg-Q8_0]=mmproj/mmproj-ggmlorg-Q8_0.gguf
 [unsloth-BF16]=/home/user/llm/models/unsloth/Qwen3.8-27B-GGUF/mmproj-BF16.gguf
)
declare -A Q=(
 [pl-doc]="Odczytaj z tego dokumentu i podaj doslownie: numer protokolu, NIP wykonawcy, wartosc brutto, temperature punktu goracego, predkosc dekodowania oraz liczbe sztuk dyskow NVMe. Na koniec wskaz, czy w dokumencie jest jakas literowka - jesli tak, przepisz bledne slowo."
 [pl-tabela]="Odczytaj te tabele. Podaj: ile jest wierszy danych, ktory wariant ma najwyzszy decode i jaka wartosc, ktory ma najnizszy VRAM i jaka wartosc, ktory ma najwyzsza akceptacje i jaka wartosc, oraz ile wynosi decode dla q8_0/turbo4."
 [pl-wykres]="Opisz ten wykres. Podaj: ile jest slupkow, ktory jest najwyzszy i jaka ma wartosc, ktory najnizszy i jaka wartosc, jaki jest zakres i krok osi Y, oraz wartosci dla HIP MTP-3 i Vulkan 128K."
)
for tag in ggmlorg-BF16 ggmlorg-Q8_0 unsloth-BF16; do
  pgrep -f "llama-server.*8099" >/dev/null && { pkill -f "llama-server.*8099"; sleep 4; }
  SRV_LOG="logs/f4b-$tag.log" ./srv.sh -ngl 99 -c 65536 -fa on -ctk $CTK -ctv $CTV \
    -ctkd $CTK -ctvd $CTV -np 1 -ub $UB -b $BB $SPEC \
    --mmproj "${P[$tag]}" --image-min-tokens 1024 \
    --reasoning on --reasoning-effort medium --reasoning-budget 8192 \
    --reasoning-format deepseek --no-warmup || continue
  echo "VRAM_loaded_$tag=$(($(cat /sys/class/drm/card1/device/mem_info_vram_used)/1048576))MiB" | tee -a $OUT
  for img in pl-doc pl-tabela pl-wykres; do
    python3 run1.py --image images/$img.png --question "${Q[$img]}" \
      --max-tokens 2048 --tag "$tag/$img" --out $OUT >/dev/null 2>&1 \
      && echo "DONE $tag/$img" || echo "FAIL $tag/$img"
  done
  pkill -f "llama-server.*8099"; sleep 4
done
echo "FAZA4B DONE" | tee -a $OUT
