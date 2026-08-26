#!/usr/bin/env python3
"""Profil termiczny sustained: N zapytan pod jednym, nieprzerwanym samplerem.
Pokazuje narastanie temperatury i ewentualny throttling, ktorego krotkie
przebiegi z fazy 2-5 nie mogly zobaczyc."""
import argparse, json, time
import run1
from pw import Sampler, win

ap = argparse.ArgumentParser()
ap.add_argument("--prompt"); ap.add_argument("--question", required=True)
ap.add_argument("--max-tokens", type=int, default=1200)
ap.add_argument("--reasoning"); ap.add_argument("--secs", type=int, default=600)
ap.add_argument("--out"); ap.add_argument("--tsv")
a = ap.parse_args()

sm = Sampler(); sm.start()
t0 = time.time(); runs = []; i = 0
while time.time() - t0 < a.secs and sm.overtemp is None:
    i += 1
    ta = time.time()
    r = run1.run(a.prompt, a.question, a.max_tokens, a.reasoning, None, f"soak{i}")
    tb = time.time()
    dn, dtps = r.get("predicted_n") or 0, r.get("decode_tps") or 0
    d_s = dn / dtps if dtps else 0.0
    w = win(sm.rows, tb - d_s, tb)
    # faza 16: skrot na przebieg, zeby soak byl tez bramka powtarzalnosci na
    # goracej karcie, a nie tylko profilem termicznym
    runs.append({"i": i, "sha1": r.get("sha1"), "sha1_reasoning": r.get("sha1_reasoning"),
                 "t_rel": round(ta - t0, 1), "decode_tps": dtps,
                 "predicted_n": dn, "decode": w,
                 "j_per_tok": round(w["w_avg"] * d_s / dn, 3) if w and dn else None})
    print(json.dumps(runs[-1], ensure_ascii=False), flush=True)
sm.stop = True; sm.join(2)

rows = sm.rows
first = win(rows, t0, t0 + 60)
last = win(rows, rows[-1][0] - 60, rows[-1][0]) if rows else None
o = {"tag": "soak", "secs": round(time.time() - t0, 1), "n_runs": i,
     "overtemp_c": sm.overtemp, "samples": len(rows),
     "first_60s": first, "last_60s": last, "whole": win(rows, t0, time.time()),
     "tps_first": runs[0]["decode_tps"] if runs else None,
     "tps_last": runs[-1]["decode_tps"] if runs else None,
     "runs": runs}
if a.tsv:
    with open(a.tsv, "w") as f:
        f.write("t_rel\tw\tedge\tjunction\tmem\tfan\tbusy\tmv\tsclk_hz\n")
        for r in rows:
            f.write("%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%d\t%d\t%d\n" % (
                r[0] - t0, r[1] / 1e6, r[2] / 1000.0, r[3] / 1000.0, r[4] / 1000.0,
                r[5], r[6], r[7], r[8]))
if a.out:
    open(a.out, "a").write(json.dumps(o, ensure_ascii=False) + "\n")
print(json.dumps({k: v for k, v in o.items() if k != "runs"}, ensure_ascii=False, indent=1))
