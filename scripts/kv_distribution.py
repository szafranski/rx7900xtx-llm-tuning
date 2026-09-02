#!/usr/bin/env python3
"""Next-token distribution comparison for the two KV cache types.

Reads data/kv-nexttoken-*.json and data/kv-repeat-*-64k.json and prints every
number quoted in docs/context-and-quality.md for the 128K cache-type section.

The metric is a truncated total variation distance: half the L1 distance over
the union of the two reported top-20 lists, with a token absent from one list
counted as probability zero. It is not the full-vocabulary TVD, because the
server only reports 20 entries. The captured mass printed alongside bounds the
error: with both lists holding at least 0.99995 of the distribution, the true
TVD cannot differ from this figure by more than the omitted mass.
"""
import itertools, json, math, pathlib, sys

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
LENS = ["8k", "32k", "64k", "120k"]


def probs(top):
    return {t: math.exp(lp) for t, lp in top}


def tvd(a, b):
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b))


def mass(a):
    return sum(a.values())


def first(x):
    return x[0] if isinstance(x, list) else x


def main():
    d = {v: json.loads((DATA / ("kv-nexttoken-%s.json" % v)).read_text()) for v in ("q8", "turbo4")}

    print("cross-variant, one full recompute each, greedy")
    print("%-6s %-10s %-10s %-10s %-9s %-9s %s" % ("len", "trunc TVD", "mass q8", "mass t4", "p1 q8", "p1 t4", "top-1"))
    for l in LENS:
        A, B = first(d["q8"]["test1"][l]), first(d["turbo4"]["test1"][l])
        a, b = probs(A["top"]), probs(B["top"])
        print("%-6s %-10.6f %-10.6f %-10.6f %-9.5f %-9.5f %r"
              % (l, tvd(a, b), mass(a), mass(b), math.exp(A["logprob"]), math.exp(B["logprob"]), A["tok"]))

    print("\nwithin-variant, four recomputes of the same 64k prompt, same metric")
    print("%-8s %-6s %-10s %-10s %-10s %s" % ("variant", "pairs", "min", "median", "max", "logprob range"))
    for v in ("q8", "turbo4"):
        runs = json.loads((DATA / ("kv-repeat-%s-64k.json" % v)).read_text())["runs"]
        ps = [probs(r["top"]) for r in runs]
        lps = [r["logprob"] for r in runs]
        pr = sorted(tvd(x, y) for x, y in itertools.combinations(ps, 2))
        print("%-8s %-6d %-10.6f %-10.6f %-10.6f %.6f"
              % (v, len(pr), pr[0], pr[len(pr) // 2], pr[-1], max(lps) - min(lps)))

    print("\nprompt-cache reuse vs full recompute, 64k, same metric")
    for v in ("q8", "turbo4"):
        t = d[v]["test2"]
        print("%-8s %.6f" % (v, tvd(probs(first(t["recompute"])["top"]), probs(first(t["reuse"])["top"]))))

    print("\nrepeat of the same 8k prompt on a warm prompt cache, same variant")
    for v in ("q8", "turbo4"):
        r = d[v]["test1"]["8k"]
        if isinstance(r, list) and len(r) > 1:
            print("%-8s %.8f" % (v, tvd(probs(r[0]["top"]), probs(r[1]["top"]))))

    print("\nneedle matrix and vision")
    n = json.loads((DATA / "kv-needles-turbo4.json").read_text())
    ok = sum(1 for c in n["cells"] if c["ok"])
    print("turbo4 needles %d/%d" % (ok, len(n["cells"])))
    for v in ("q8", "turbo4"):
        c = json.loads((DATA / ("kv-vision-%s.json" % v)).read_text())["cases"]
        print("%-8s vision %d/%d, sha1 %s" % (v, sum(1 for x in c if x["ok"]), len(c), [x["sha1"] for x in c]))


if __name__ == "__main__":
    sys.exit(main())
