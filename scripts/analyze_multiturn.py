#!/usr/bin/env python3
"""Analiza fazy 15 krok 2. Metryka glowna: czas scienny calej sesji.
Regula wygranej ustalona z gory: >= 5% wobec wariantu mtp."""
import json, statistics as st, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.startswith("{")]
rep = [r for r in rows if r["mode"] == "replay"]
def var(tag): return tag.split("-", 1)[1].split("/")[0]
vs = sorted({var(r["tag"]) for r in rep}, key=lambda v: (v != "mtp", v))
base = None
print(f"{'wariant':10s} {'n':>2s} {'sesja s':>9s} {'zakres':>17s} {'TTFT sr':>8s} {'tok':>6s} {'GPU Wh':>7s} {'CPU Wh':>7s} {'delta':>8s}  sha")
for v in vs:
    s = [r for r in rep if var(r["tag"]) == v]
    t = [r["session_s"] for r in s]
    m = st.mean(t)
    if v == "mtp": base = m
    d = f"{100*(base/m-1):+.2f}%" if base else ""
    print(f"{v:10s} {len(t):2d} {m:9.1f} {min(t):8.1f}-{max(t):.1f} "
          f"{st.mean(r['ttft_avg_s'] for r in s):8.2f} {st.mean(r['tok_out'] for r in s):6.0f} "
          f"{st.mean(r.get('gpu_wh') or 0 for r in s):7.3f} {st.mean(r.get('cpu_wh') or 0 for r in s):7.3f} "
          f"{d:>8s}  {sorted({r['sha1_session'] for r in s})}")
print("\nprzyspieszenie dodatnie = szybciej od mtp. Regula: >= 5% i grupy nienachodzace.")
print("\nper tura (srednia z probek, czas sekundy):")
nt = max(len(r["per_turn"]) for r in rep)
print("tura  " + "".join(f"{v:>10s}" for v in vs))
for k in range(nt):
    line = f"{k+1:4d}  "
    for v in vs:
        s = [r for r in rep if var(r["tag"]) == v]
        line += f"{st.mean(r['per_turn'][k]['wall_s'] for r in s):10.1f}"
    print(line)
print("\nakceptacja draftu, tura 10 (diagnostyka):")
for v in vs:
    s = [r for r in rep if var(r["tag"]) == v]
    a = [100*(r['per_turn'][-1]['draft_n_accepted'] or 0)/(r['per_turn'][-1]['draft_n'] or 1) for r in s]
    dn = [r['per_turn'][-1]['draft_n'] or 0 for r in s]
    print(f"  {v:10s} drafty={st.mean(dn):7.0f} akceptacja={st.mean(a):5.2f}%")
