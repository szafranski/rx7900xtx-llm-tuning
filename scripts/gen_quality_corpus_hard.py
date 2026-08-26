#!/usr/bin/env python3
"""Faza 16 krok 2b: seria TRUDNA na tym samym promptcie.

Seria latwa dala 24/24 w kazdym wariancie, wiec nie mierzy niczego - sufit.
Te zadania wymagaja agregacji po wszystkich wpisach, dwoch skokow (cecha ->
wpis -> inna cecha) i sortowania, czyli dluzszych lancuchow, w ktorych bledna
akceptacja draftu ma gdzie sie objawic. Prompt sie NIE zmienia - inaczej nie
dalyby sie porownac z seria latwa.
"""
import json, sys, hashlib
from gen_quality_corpus import WPISY, TABELA

PROMPT_SHA = "094ae20dd258"  # prompts/Q16.txt z serii latwej

def main(prompt, out):
    got = hashlib.sha1(open(prompt, "rb").read()).hexdigest()[:12]
    assert got == PROMPT_SHA, f"prompt sie zmienil: {got} != {PROMPT_SHA}"
    H = {w[0]: w for w in WPISY}
    naj = max(WPISY, key=lambda w: w[3]); nij = min(WPISY, key=lambda w: w[3])
    pow5000 = [w[0] for w in WPISY if w[3] > 5000]
    trzy = [w[0] for w in sorted(WPISY, key=lambda w: w[3])[:3]]
    szafa23 = [w for w in WPISY if w[1] == "szafa 23"][0]
    tsum = sum(v for _, v in TABELA)
    tmax = max(TABELA, key=lambda x: x[1])[1]; tmin = min(TABELA, key=lambda x: x[1])[1]
    zad = [
        ("t01", "Zsumuj liczniki godzin pracy ze WSZYSTKICH wpisow serwisowych od R-101 do R-110. Podaj sam wynik.",
         [str(sum(w[3] for w in WPISY))]),
        ("t02", "Ktory wpis serwisowy ma najwyzszy licznik godzin pracy? Podaj jego numer i wartosc licznika.",
         [naj[0], str(naj[3])]),
        ("t03", "Ktory wpis serwisowy ma najnizszy licznik godzin pracy? Podaj jego numer i wartosc licznika.",
         [nij[0], str(nij[3])]),
        ("t04", "Wypisz numery wszystkich wpisow serwisowych, ktorych licznik godzin pracy przekracza 5000.",
         pow5000),
        ("t05", "Wypisz numery trzech wpisow serwisowych o najnizszych licznikach godzin pracy, od najnizszego.",
         trzy),
        ("t06", "Kto jest technikiem odpowiedzialnym za urzadzenie stojace w szafie 23? Podaj tez, jakie to urzadzenie.",
         ["Cholew", "router"]),
        ("t07", "Podaj kod czesci zamiennej dla tego wpisu serwisowego, ktory ma najwyzszy licznik godzin pracy.",
         [naj[5]]),
        ("t08", "W jakiej lokalizacji stoi urzadzenie z wpisu o najnizszym liczniku godzin pracy? Podaj tez nazwisko technika.",
         ["szaf", nij[1].split()[1], "Skrzypczak"]),
        ("t09", "Zsumuj wszystkie wartosci przepustowosci z tabeli przepustowosci stanowisk. Podaj sam wynik.",
         [str(tsum)]),
        ("t10", "Jaka jest roznica miedzy najwyzsza i najnizsza przepustowoscia w tabeli przepustowosci stanowisk?",
         [str(tmax - tmin)]),
    ]
    json.dump([{"id": i, "pytanie": q, "klucze": k} for i, q, k in zad],
              open(out, "w"), ensure_ascii=False, indent=1)
    print(f"{out}: {len(zad)} zadan trudnych, prompt bez zmian ({got})")

def demo():
    # klucze zadan agregujacych NIE moga wystepowac w promptcie doslownie,
    # inaczej model je przepisze zamiast policzyc
    import os
    txt = open("prompts/Q16.txt").read() if os.path.exists("prompts/Q16.txt") else None
    s = sum(w[3] for w in WPISY); assert s == 50768, s
    assert sum(v for _, v in TABELA) == 35199
    assert max(TABELA, key=lambda x: x[1])[1] - min(TABELA, key=lambda x: x[1])[1] == 9157
    assert [w[0] for w in sorted(WPISY, key=lambda w: w[3])[:3]] == ["R-104", "R-110", "R-102"]
    assert [w[0] for w in WPISY if w[3] > 5000] == ["R-101", "R-103", "R-105", "R-107", "R-108"]
    if txt:
        for k in (str(s), "35199", "9157"):
            assert k not in txt, f"wynik {k} jest w promptcie doslownie"
    print("demo ok")

if __name__ == "__main__":
    if "--demo" in sys.argv: demo()
    else: main(sys.argv[1], sys.argv[2])
