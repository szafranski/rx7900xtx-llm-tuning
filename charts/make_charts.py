#!/usr/bin/env python3
"""Generate the repository's charts as SVG from the files in data/.

Standard library only, so the charts can be regenerated and audited without
installing anything. Every bar carries its printed value, so the charts do not
depend on colour to be readable. Output is deterministic: running this twice on
unchanged data produces byte-identical files, which is what scripts/check.sh
verifies.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "charts"

W, H = 760, 380
PAD_L, PAD_R, PAD_T, PAD_B = 62, 24, 64, 92
PLOT_W, PLOT_H = W - PAD_L - PAD_R, H - PAD_T - PAD_B
# distinguishable in greyscale as well as colour
FILLS = ["#3b6ea5", "#8c4a6e", "#4a7c59", "#a1662f", "#5b5b7a", "#7a6a3a"]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def rows(name):
    p = DATA / name
    return [json.loads(l) for l in p.open(encoding="utf-8", errors="replace")
            if l.strip().startswith("{")]


def bar_chart(path, title, desc, y_label, bars, caption, fmt="{:.1f}"):
    """bars: list of (label, value, sublabel or None)."""
    top = max(v for _, v, _ in bars) * 1.18
    n = len(bars)
    slot = PLOT_W / n
    bw = min(slot * 0.62, 84)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'width="{W}" height="{H}" role="img" aria-labelledby="t d" '
         f'font-family="DejaVu Sans, Helvetica, Arial, sans-serif">',
         f'<title id="t">{esc(title)}</title><desc id="d">{esc(desc)}</desc>',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="{PAD_L}" y="26" font-size="15" font-weight="600" fill="#1a1a1a">{esc(title)}</text>',
         f'<text x="{PAD_L}" y="45" font-size="11.5" fill="#555555">{esc(y_label)}</text>']
    # y axis: four gridlines with printed values
    for i in range(5):
        v = top * i / 4
        y = PAD_T + PLOT_H - PLOT_H * i / 4
        s.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{PAD_L+PLOT_W}" y2="{y:.1f}" '
                 f'stroke="#e2e2e2" stroke-width="1"/>')
        s.append(f'<text x="{PAD_L-8}" y="{y+4:.1f}" font-size="10.5" fill="#666666" '
                 f'text-anchor="end">{v:.0f}</text>')
    s.append(f'<line x1="{PAD_L}" y1="{PAD_T+PLOT_H}" x2="{PAD_L+PLOT_W}" '
             f'y2="{PAD_T+PLOT_H}" stroke="#999999" stroke-width="1"/>')
    for i, (label, val, sub) in enumerate(bars):
        x = PAD_L + slot * i + (slot - bw) / 2
        h = PLOT_H * val / top
        y = PAD_T + PLOT_H - h
        s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                 f'fill="{FILLS[i % len(FILLS)]}"><title>{esc(label)}: {fmt.format(val)}</title></rect>')
        s.append(f'<text x="{x+bw/2:.1f}" y="{y-6:.1f}" font-size="11.5" font-weight="600" '
                 f'fill="#1a1a1a" text-anchor="middle">{esc(fmt.format(val))}</text>')
        s.append(f'<text x="{x+bw/2:.1f}" y="{PAD_T+PLOT_H+17:.1f}" font-size="11" '
                 f'fill="#333333" text-anchor="middle">{esc(label)}</text>')
        if sub:
            s.append(f'<text x="{x+bw/2:.1f}" y="{PAD_T+PLOT_H+32:.1f}" font-size="9.5" '
                     f'fill="#777777" text-anchor="middle" font-family="DejaVu Sans Mono, monospace">'
                     f'{esc(sub)}</text>')
    for j, line in enumerate(caption):
        s.append(f'<text x="{PAD_L}" y="{H-30+j*13}" font-size="10" fill="#666666">{esc(line)}</text>')
    s.append("</svg>")
    (OUT / path).write_text("\n".join(s) + "\n", encoding="utf-8")
    return path


def chart_speculation():
    r = {x["tag"]: x for x in rows("spec-vs-none.jsonl")}
    order = [("none", "none"), ("mtp", "draft-mtp"), ("chain", "draft-chain"),
             ("ngmod", "mtp+ngram-mod"), ("ngsimple", "mtp+ngram"), ("ngmapk", "mtp+ngram-map-k")]
    bars = [(lbl, r[k]["decode_tps"], None) for k, lbl in order if k in r]
    base = r["none"]["decode_tps"]
    return bar_chart(
        "speculation-decode.svg",
        "Decode throughput by speculative-decoding mode",
        "Bar chart of decode tokens per second for six speculation modes on a dense 27B model.",
        "tokens/s generated, higher is better",
        bars,
        [f"Source: data/spec-vs-none.jsonl. One run per mode, 19134-token prompt, 1200 tokens generated.",
         f"Best mode is {max(bars, key=lambda b: b[1])[1]/base:.2f}x the no-speculation baseline of {base:.1f} tok/s.",
         "Single run per mode: this ranks the modes, it does not establish run-to-run variance.",
         "See speculation-soak.svg for the same comparison with repeated runs."])


def chart_speculation_soak():
    bars = []
    for name, label in [("soak-efficient-nospec-runs.jsonl", "no speculation"),
                        ("soak-efficient-ngram-runs.jsonl", "mtp+ngram-map-k")]:
        runs = rows(name)[-1]["runs"]
        tps = [x["decode_tps"] for x in runs]
        bars.append((label, sum(tps) / len(tps),
                     f"n={len(tps)}, {min(tps):.1f}-{max(tps):.1f}"))
    return bar_chart(
        "speculation-soak.svg",
        "Speculative decoding during the 30-minute soak",
        "Bar chart comparing mean decode throughput with and without speculation over "
        "repeated requests in a sustained run.",
        "mean tokens/s over the soak, with sample count and observed range",
        bars,
        ["Source: data/soak-efficient-*-runs.jsonl. Same prompt, 1200 tokens per request,",
         "272 W / -75 mV / 2200 MHz, 128K context, q8_0 + turbo4 KV cache.",
         f"Ratio: {bars[1][1] / bars[0][1]:.2f}x. This is a dense 27B model, so every token",
         "reads all 17.5 GB of weights; speculation buys parallel commits, not a faster pass."])


def chart_output_stability():
    r = rows("aspm-under-load.jsonl")
    seen, bars = {}, []
    for x in r:
        tag = x["tag"]
        pos = tag.rsplit("/", 1)[1]
        setting = tag.split("-")[1] + " " + tag.rsplit("/", 1)[0].split("-")[-1]
        h = x["sha1"]
        seen.setdefault(h, len(seen) + 1)
        bars.append((f"{setting} {pos}", x["decode_tps"], f"#{seen[h]} {h[:6]}"))
    lo = min(b[1] for b in bars)
    hi = max(b[1] for b in bars)
    return bar_chart(
        "output-stability.svg",
        "Throughput moves, generated text does not",
        "Bar chart of decode throughput across twelve runs under three ASPM settings, "
        "annotated with the hash of the generated text; only two distinct hashes appear.",
        "tokens/s per run, with the hash of the text that run produced",
        bars,
        [f"Source: data/aspm-under-load.jsonl. 12 runs, 3 ASPM settings, 2 passes, 272 W / -75 mV / 2200 MHz.",
         f"Throughput spans {lo:.1f} to {hi:.1f} tok/s ({(hi/lo-1)*100:.1f}%), yet only {len(seen)} distinct output hashes occur,",
         "one per request position: every first request matches every other first request, and likewise the second."])


def chart_soak_power():
    out = []
    for name, label in [("soak-efficient-nospec-runs.jsonl", "no speculation"),
                        ("soak-efficient-ngram-runs.jsonl", "mtp+ngram-map-k")]:
        runs = rows(name)[-1]["runs"]
        tps = sum(x["decode_tps"] for x in runs) / len(runs)
        w = sum(x["decode"]["w_avg"] for x in runs) / len(runs)
        out.append((label, tps, w, len(runs)))
    bars = [(f"{lbl}", w / tps, f"{tps:.1f} tok/s, {w:.0f} W")
            for lbl, tps, w, _ in out]
    return bar_chart(
        "soak-energy.svg",
        "Energy per generated token during the 30-minute soak",
        "Bar chart comparing joules per generated token with and without speculative decoding.",
        "joules per generated token, lower is better",
        bars,
        [f"Source: data/soak-efficient-*-runs.jsonl. {out[0][3]} and {out[1][3]} requests, mean of per-request means.",
         "J/token = mean board power during decode divided by mean decode tokens/s.",
         "Board power only; it excludes CPU and the rest of the system.",
         "This metric is only comparable because both settings generate the same 1200 tokens per request."],
        fmt="{:.2f}")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for f in (chart_speculation(), chart_speculation_soak(),
              chart_output_stability(), chart_soak_power()):
        print("wrote charts/" + f)
