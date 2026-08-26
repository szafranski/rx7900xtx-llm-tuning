#!/usr/bin/env python3
"""Test sparowany na chunkach dla fazy 4. Wejscie: ../data/perplexity-chunks.txt
(wyciag z logow llama-perplexity: bloki '@@@ nazwa' i linie 'k wartosc').
Odzyskuje wklad kazdego chunku z narastajacej PPL i porownuje warianty parami.
Uruchomienie: python3 paired_test.py
"""
import math, os, statistics as st

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data/perplexity-chunks.txt")

def load(path):
    series, cur = {}, None
    for line in open(path):
        line = line.strip()
        if line.startswith("@@@"):
            cur = line[4:]; series[cur] = {}
        elif line and cur:
            k, v = line.split(); series[cur][int(k)] = float(v)
    return series

def per_chunk_nll(s):
    """nll_k = k*ln(P_k) - (k-1)*ln(P_{k-1}); P_k to PPL narastajaca po k chunkach"""
    return {k: k * math.log(s[k]) - ((k - 1) * math.log(s[k - 1]) if k > 1 else 0.0)
            for k in sorted(s)}

def paired(N, a, b, label):
    ks = sorted(set(N[a]) & set(N[b]))
    d = [N[b][k] - N[a][k] for k in ks]
    m, se = st.mean(d), st.stdev(d) / math.sqrt(len(d))
    pct = (math.exp(st.mean([N[b][k] for k in ks])) /
           math.exp(st.mean([N[a][k] for k in ks])) - 1) * 100
    print(f"{label:24s} n={len(d):3d} dNLL={m:+.6f} +/-{se:.6f} t={m/se:+6.2f} "
          f"dPPL={pct:+.4f}% gorszych={sum(1 for x in d if x > 0)}/{len(d)}")

def demo():
    """Kontrola: wariant porownany sam ze soba musi dac dokladnie zero."""
    N = {"x": {1: 1.0, 2: 2.0, 3: 3.0}}
    ks = sorted(N["x"])
    d = [N["x"][k] - N["x"][k] for k in ks]
    assert all(x == 0.0 for x in d)
    # kontrola odzyskiwania: stala PPL p na kazdym kroku => kazdy chunk ma nll=ln(p)
    p = 6.5
    got = per_chunk_nll({k: p for k in range(1, 6)})
    assert all(abs(v - math.log(p)) < 1e-12 for v in got.values()), got
    print("demo ok")

if __name__ == "__main__":
    demo()
    N = {k: per_chunk_nll(v) for k, v in load(SRC).items()}
    for lang in ("EN", "PL"):
        print(f"--- {lang} ---")
        for var in ("q8-q8", "q8-turbo4", "q8-turbo3"):
            paired(N, f"f4-f16-f16-{lang}-c80", f"f4-{var}-{lang}-c80", f"f16 -> {var} {lang}")
