#!/usr/bin/env python3
"""Faza 15 krok 3b: gdzie dokladnie rozjezdzaja sie wyjscia dwoch wariantow.

Sam rozny sha1 nie rozstrzyga, co sie stalo. Sa dwie mozliwosci i roznia sie
wnioskiem:
 a) blad akceptacji - wariant przyjmuje tokeny, ktorych model docelowy by nie
    wybral, wtedy rozjazd jest wczesny i tresc dalej idzie w swoja strone,
 b) inny ksztalt wsadu weryfikacji -> inne zaokraglenia zmiennoprzecinkowe ->
    inny argmax na remisie, wtedy rozjazdy sa pojedyncze, pozne i wygladaja jak
    wymiana slowa na rownowazne.
Bez tego rozroznienia nie wolno powiedziec ani "zepsute", ani "bezpieczne".
"""
import difflib, json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
na, nb = sys.argv[1], sys.argv[2]
for i, (x, y) in enumerate(zip(a, b), 1):
    if x == y:
        print(f"tura {i}: identyczne ({len(x)} znakow)")
        continue
    pref = 0
    while pref < min(len(x), len(y)) and x[pref] == y[pref]:
        pref += 1
    print(f"tura {i}: rozjazd na znaku {pref} z {len(x)}/{len(y)} "
          f"({100*pref/max(len(x),len(y)):.1f}% wspolnego prefiksu)")
    print(f"  {na}: ...{x[max(0,pref-60):pref+80]!r}")
    print(f"  {nb}: ...{y[max(0,pref-60):pref+80]!r}")
    sm = difflib.SequenceMatcher(None, x.split(), y.split())
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    print(f"  blokow roznicy w slowach: {len(ops)}, podobienstwo {sm.ratio():.4f}")
    for tag, i1, i2, j1, j2 in ops[:5]:
        print(f"    {tag}: {' '.join(x.split()[i1:i2])[:70]!r} -> {' '.join(y.split()[j1:j2])[:70]!r}")
