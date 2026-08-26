#!/usr/bin/env python3
"""Faza 16 krok 2: generator promptu z 12 zadaniami o weryfikowalnej odpowiedzi.

Zamiast szukac igiel w istniejacych promptach sadze wlasne, na roznych
glebokosciach, bo bramka jakosci musi porownywac warianty na tym samym
materiale, a klucz odpowiedzi musi byc jednoznaczny. Dane sa wpisane na sztywno
(zero losowosci), zeby prompt byl identyczny przy kazdym uruchomieniu.
"""
import json, sys

WPISY = [
    # id,      szafa,      urzadzenie,            godziny, technik,               czesc
    ("R-101", "szafa 12", "przelacznik rdzeniowy", 8341, "Marek Wilczynski",  "CZ-88213-X"),
    ("R-102", "szafa 04", "macierz dyskowa",       2917, "Halina Zubrzycka",  "CZ-40761-B"),
    ("R-103", "szafa 19", "zasilacz awaryjny",     6053, "Tomasz Grabiec",    "CZ-15590-D"),
    ("R-104", "szafa 07", "serwer obliczeniowy",   1284, "Iwona Skrzypczak",  "CZ-92308-K"),
    ("R-105", "szafa 23", "router brzegowy",       7726, "Bartosz Cholewa",   "CZ-63417-M"),
    ("R-106", "szafa 15", "kontroler pamieci",     3498, "Renata Poplawska",  "CZ-27845-T"),
    ("R-107", "szafa 02", "przelacznik dostepowy", 5162, "Krzysztof Nadolny", "CZ-71029-P"),
    ("R-108", "szafa 31", "brama VPN",             9405, "Aneta Bugajska",    "CZ-34952-R"),
    ("R-109", "szafa 26", "serwer kopii",          4873, "Damian Roztocki",   "CZ-58136-W"),
    ("R-110", "szafa 09", "analizator ruchu",      1509, "Sylwia Karpinska",  "CZ-80274-G"),
]
# wartosci 4-5 cyfrowe, bo 256 albo 412 wystepuje w kazdym zrodle C++ i psuloby ocene
TABELA = [("ALFA", 4127), ("BETA", 11873), ("GAMMA", 9034), ("DELTA", 2716), ("EPSILON", 7449)]

def blok_wpis(w):
    i, sz, dev, h, t, cz = w
    return (f"// ===== WPIS SERWISOWY {i} =====\n"
            f"// Lokalizacja: {sz}, urzadzenie: {dev}\n"
            f"// Licznik godzin pracy: {h}\n"
            f"// Technik odpowiedzialny: {t}\n"
            f"// Kod czesci zamiennej: {cz}\n"
            f"// ==============================\n")

def blok_tabela():
    s = "// ===== TABELA PRZEPUSTOWOSCI STANOWISK =====\n"
    for n, v in TABELA:
        s += f"// {n:<10}| {v} MB/s\n"
    return s + "// ===========================================\n"

def main(src, out_prompt, out_klucze):
    txt = open(src).read()
    bloki = [blok_wpis(w) for w in WPISY] + [blok_tabela()]
    # glebokosci rozlozone od 5% do 95%, zeby zmierzyc tez odczyt ze srodka kontekstu
    gl = [5, 13, 21, 29, 37, 45, 53, 61, 69, 77, 90]
    assert len(gl) == len(bloki)
    # wstawiamy od konca, zeby wczesniejsze wstawki nie przesuwaly pozniejszych pozycji
    for d, b in sorted(zip(gl, bloki), reverse=True):
        p = len(txt) * d // 100
        nl = txt.find("\n", p)
        p = nl + 1 if nl != -1 else p
        txt = txt[:p] + "\n" + b + "\n" + txt[p:]
    open(out_prompt, "w").write(txt)

    W = {w[0]: w for w in WPISY}
    naj = max(TABELA, key=lambda x: x[1]); nij = min(TABELA, key=lambda x: x[1])
    zad = [
        ("z01", f"Jaki jest kod czesci zamiennej we wpisie serwisowym {W['R-101'][0]}?", [W["R-101"][5]]),
        # nazwiska i nazwy urzadzen oceniane rdzeniem, bo polski odmienia: "Haliny Zubrzyckiej"
        ("z02", "Kto jest technikiem odpowiedzialnym we wpisie serwisowym R-102?", ["Zubrzyck"]),
        ("z03", "Ile godzin pracy pokazuje licznik we wpisie serwisowym R-103?", [str(W["R-103"][3])]),
        # rdzen "szaf" plus numer, bo model odmienia: "w szafie 07"
        ("z04", "W jakiej lokalizacji stoi urzadzenie z wpisu serwisowego R-104?",
         ["szaf", W["R-104"][1].split()[1]]),
        ("z05", "Jaki jest kod czesci zamiennej we wpisie serwisowym R-105?", [W["R-105"][5]]),
        ("z06", "Kto jest technikiem odpowiedzialnym we wpisie serwisowym R-106?", ["Poplawsk"]),
        ("z07", "Ile godzin pracy pokazuje licznik we wpisie serwisowym R-107?", [str(W["R-107"][3])]),
        ("z08", "Jakie urzadzenie opisuje wpis serwisowy R-108?", ["bram", "VPN"]),
        ("z09", "Zsumuj liczniki godzin pracy z wpisow serwisowych R-103 i R-107. Podaj wynik.",
         [str(W["R-103"][3] + W["R-107"][3])]),
        ("z10", "Odejmij licznik godzin pracy z wpisu R-110 od licznika z wpisu R-109. Podaj wynik.",
         [str(W["R-109"][3] - W["R-110"][3])]),
        ("z11", "W tabeli przepustowosci stanowisk: ktore stanowisko ma najwyzsza przepustowosc i jaka wartosc?",
         [naj[0], str(naj[1])]),
        ("z12", "W tabeli przepustowosci stanowisk: ktore stanowisko ma najnizsza przepustowosc i jaka wartosc?",
         [nij[0], str(nij[1])]),
    ]
    json.dump([{"id": i, "pytanie": q, "klucze": k} for i, q, k in zad],
              open(out_klucze, "w"), ensure_ascii=False, indent=1)
    print(f"prompt {out_prompt}: {len(txt)} znakow, {len(bloki)} blokow, {len(zad)} zadan")

def demo():
    # samosprawdzenie: kazdy klucz musi wystepowac w promptcie dokladnie tam,
    # gdzie go zasadzilem, a wyniki arytmetyczne NIE moga wystepowac doslownie
    # (inaczej model by je przepisal, a nie policzyl)
    import tempfile, os
    d = tempfile.mkdtemp()
    src = os.path.join(d, "src.txt"); open(src, "w").write("linia\n" * 20000)
    p = os.path.join(d, "q.txt"); k = os.path.join(d, "k.json")
    main(src, p, k)
    txt = open(p).read(); zad = json.load(open(k))
    assert len(zad) == 12
    for z in zad:
        for key in z["klucze"]:
            if z["id"] in ("z09", "z10"):
                assert key not in txt, f"{z['id']}: wynik {key} jest w promptcie doslownie"
            elif len(key) >= 8:
                # dlugie klucze (kody czesci, nazwiska) musza byc jednoznaczne
                assert txt.count(key) == 1, f"{z['id']}: klucz {key} wystepuje {txt.count(key)} razy"
            else:
                assert key in txt, f"{z['id']}: klucz {key} nieobecny"
    # bloki musza byc w rosnacej kolejnosci glebokosci
    poz = [txt.find(f"WPIS SERWISOWY R-1{n:02d}") for n in range(1, 11)]
    assert poz == sorted(poz) and poz[0] > 0, poz
    assert 0.03 < poz[0] / len(txt) < 0.08, poz[0] / len(txt)
    print("demo ok")

if __name__ == "__main__":
    if "--demo" in sys.argv: demo()
    else: main(sys.argv[1], sys.argv[2], sys.argv[3])
