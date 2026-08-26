#!/usr/bin/env python3
"""Faza 16 krok 2: ocena odpowiedzi po TRESCI wobec klucza.

Skrot sha1 nie mierzy poprawnosci (faza 15, krok 3), wiec bramka jakosci musi
patrzec, czy odpowiedz zawiera wlasciwa wartosc. Normalizacja jest nietrywialna
(polskie znaki, przecinek kontra kropka kontra spacja w tysiacach), dlatego ma
samosprawdzenie na assertach.
"""
import json, re, sys, unicodedata
from collections import defaultdict

def norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ł", "l").replace("Ł", "L")  # l z kreska nie rozklada sie
    s = s.casefold()
    # separator tysiecy miedzy cyframi: spacja, przecinek, kropka, apostrof
    s = re.sub(r"(?<=\d)[  ,.'](?=\d\d\d(?!\d))", "", s)
    return re.sub(r"\s+", " ", s)

def hit(odp, klucz):
    o, k = norm(odp), norm(klucz)
    if k.replace(" ", "").isdigit():
        return re.search(r"(?<!\d)" + re.escape(k) + r"(?!\d)", o) is not None
    return k in o

def main(klucze, wyniki):
    zad = {z["id"]: z for z in json.load(open(klucze))}
    per = defaultdict(lambda: defaultdict(dict))
    for ln in open(wyniki):
        ln = ln.strip()
        if not ln.startswith("{"): continue
        r = json.loads(ln)
        tag = r.get("tag", "")
        m = re.match(r"^(.+)/([zt]\d\d)$", tag)  # z = seria latwa, t = trudna
        if not m: continue
        wariant, zid = m.group(1), m.group(2)
        wariant_bez_przebiegu = re.sub(r"^p\d-", "", wariant).split("/")[0]
        tresc = r.get("content", "")
        if not tresc.strip():
            # pusta tresc to artefakt pomiaru (rozumowanie zjadlo budzet), nie zla
            # odpowiedz - liczona osobno, inaczej wyglada jak utrata jakosci
            per[wariant_bez_przebiegu][zid][wariant] = None
        else:
            per[wariant_bez_przebiegu][zid][wariant] = all(hit(tresc, k) for k in zad[zid]["klucze"])
    print(f"{'wariant':<26} {'trafienia':>10}  {'z':>4}   nietrafione")
    for w in sorted(per):
        traf = tot = 0; zle = []; puste = 0
        for zid in sorted(per[w]):
            for run, ok in per[w][zid].items():
                tot += 1
                if ok is None: puste += 1; zle.append(f"{zid}(PUSTE)")
                elif ok: traf += 1
                else: zle.append(f"{zid}({run.split('/')[0]})")
        pu = f" [{puste} pustych]" if puste else ""
        print(f"{w:<26} {traf:>10} {tot:>5}   {' '.join(zle) if zle else '-'}{pu}")

def demo():
    assert hit("Wynik to 11 873 MB/s", "11873")
    assert hit("Wynik to 11,873", "11873")
    assert hit("Wynik to 11.873", "11873")
    assert hit("Wynik: 11873.", "11873")
    assert not hit("Wynik to 111873", "11873")
    assert not hit("Wynik to 118730", "11873")
    assert not hit("Wynik to 1187", "11873")
    assert hit("Technik: Marek Wilczyński", "Marek Wilczynski")
    assert hit("technik to marek  wilczynski, szafa 12", "Marek Wilczynski")
    assert hit("Hałina Żubrzycka", "Halina Zubrzycka")  # tylko znaki diakrytyczne
    assert not hit("Halina Zubrowska", "Halina Zubrzycka")  # inne nazwisko to blad
    assert hit("Kod: CZ-88213-X", "CZ-88213-X")
    assert not hit("Kod: CZ-88213-Y", "CZ-88213-X")
    # lokalizacja jest oceniana rdzeniem plus numerem, bo model odmienia rzeczownik
    assert all(hit("urzadzenie stoi w szafie 07", k) for k in ["szaf", "07"])
    assert all(hit("Lokalizacja: szafa 07", k) for k in ["szaf", "07"])
    assert not all(hit("Lokalizacja: szafa 12", k) for k in ["szaf", "07"])
    print("demo ok")

if __name__ == "__main__":
    if "--demo" in sys.argv: demo()
    else: main(sys.argv[1], sys.argv[2])
