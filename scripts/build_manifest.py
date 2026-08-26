#!/usr/bin/env python3
"""Regenerate data/manifest.csv: one row per committed measurement file.

Experiment metadata lives in EXPERIMENTS below; sizes, record counts and
SHA-256 are computed from the files themselves so the manifest cannot drift.
"""
import csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# file -> (experiment, configuration under test, producing script)
EXPERIMENTS = {
    "spec-vs-none.jsonl":          ("Speculative decoding variants, 20K prompt", "303 W, 0 mV, auto clock", "bench-speculation.sh"),
    "spec-variants-paired.jsonl":  ("Same variants run twice, hashes compared position by position", "303 W, 0 mV, auto clock", "bench-spec-variants.sh"),
    "single-shot.jsonl":           ("Single-request decode, n-gram on and off", "272 W, -75 mV, 2200 MHz", "bench-speculation.sh"),
    "multiturn-session.jsonl":     ("Ten-turn session, replayed transcript", "272 W, -75 mV, 2200 MHz", "bench-multiturn.sh"),
    "context-128k.jsonl":          ("Decode and VRAM at 128K context, with and without projector", "272 W, -75 mV, 2200 MHz", "bench-context.sh"),
    "quality-keyed.jsonl":         ("22 keyed retrieval tasks over a 50K corpus", "272 W, -75 mV, 2200 MHz", "bench-quality.sh"),
    "quality-keyed-hard.jsonl":    ("Harder keyed variant of the same corpus", "272 W, -75 mV, 2200 MHz", "bench-quality.sh"),
    "aspm-under-load.jsonl":       ("ASPM default/performance/powersave under decode load", "272 W, -75 mV, 2200 MHz", "bench-aspm.sh"),
    "aspm-idle.jsonl":             ("ASPM at idle, GPU rail", "272 W, -75 mV, 2200 MHz", "bench-aspm-idle.sh"),
    "aspm-cpu-package.jsonl":      ("ASPM effect on CPU package power", "272 W, -75 mV, 2200 MHz", "bench-aspm-cpu.sh"),
    "aspm-perplexity.tsv":         ("Perplexity before and after the ASPM sweep", "272 W, -75 mV, 2200 MHz", "bench-aspm.sh"),
    "idle-power.jsonl":            ("Idle GPU power baseline", "factory and capped", "bench-idle.sh"),
    "idle-with-projector.jsonl":   ("Idle power with the vision projector loaded", "272 W, -75 mV, 2200 MHz", "bench-idle-projector.sh"),
    "display-refresh-idle.jsonl":  ("Idle power at 144 Hz vs 120 Hz", "272 W, -75 mV, 2200 MHz", "bench-display-refresh.sh"),
    "vision.jsonl":                ("Vision prompts, Q8_0 vs BF16 projector", "272 W, -75 mV, 2200 MHz", "bench-speculation.sh"),
    "soak-efficient-ngram.jsonl":       ("30 min soak, summary record", "272 W, -75 mV, 2200 MHz, ngram-map-k", "soak-and-output-gate.sh"),
    "soak-efficient-ngram-runs.jsonl":  ("30 min soak, per-request records and output hashes", "272 W, -75 mV, 2200 MHz, ngram-map-k", "soak-and-output-gate.sh"),
    "soak-efficient-nospec.jsonl":      ("30 min soak, summary record", "272 W, -75 mV, 2200 MHz, no speculation", "soak-and-output-gate.sh"),
    "soak-efficient-nospec-runs.jsonl": ("30 min soak, per-request records and output hashes", "272 W, -75 mV, 2200 MHz, no speculation", "soak-and-output-gate.sh"),
    "reference-sequence-ngram.json":    ("Reference output-hash sequence the gate compares against", "272 W, -75 mV, 2200 MHz, ngram-map-k", "soak-and-output-gate.sh"),
    "reference-sequence-nospec.json":   ("Reference output-hash sequence the gate compares against", "272 W, -75 mV, 2200 MHz, no speculation", "soak-and-output-gate.sh"),
    "perplexity-chunks.txt":       ("Per-chunk perplexity, wikitext-2 test split", "factory", "bench-idle.sh"),
    "quality-keys.json":           ("Answer keys for the keyed retrieval tasks", "n/a", "gen_quality_corpus.py"),
    "quality-keys-hard.json":      ("Answer keys for the harder keyed tasks", "n/a", "gen_quality_corpus_hard.py"),
}

def records(p):
    if p.suffix == ".jsonl":
        return sum(1 for l in p.open(encoding="utf-8", errors="replace")
                   if l.strip().startswith("{"))
    if p.suffix == ".json":
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
            return len(o) if isinstance(o, (list, dict)) else 1
        except json.JSONDecodeError:
            return ""
    return sum(1 for _ in p.open(encoding="utf-8", errors="replace"))

def main():
    rows, missing = [], []
    for p in sorted(DATA.iterdir()):
        if p.name in ("manifest.csv", "README.md", "LICENSE") or not p.is_file():
            continue
        meta = EXPERIMENTS.get(p.name)
        if meta is None:
            missing.append(p.name)
            continue
        rows.append({
            "file": p.name, "experiment": meta[0], "configuration": meta[1],
            "script": meta[2], "records": records(p), "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        })
    if missing:
        print("ERROR: no manifest entry for: " + ", ".join(missing), file=sys.stderr)
        return 1
    out = DATA / "manifest.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{out}: {len(rows)} rows")
    return 0

if __name__ == "__main__":
    sys.exit(main())
