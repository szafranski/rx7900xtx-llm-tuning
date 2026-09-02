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
    "soak-efficient-ngram.log":        ("30 min soak, console log from the superseded gate", "272 W, -75 mV, 2200 MHz, ngram-map-k", "soak-and-output-gate.sh"),
    "soak-efficient-ngram-runs.jsonl":  ("30 min soak, per-request records and output hashes", "272 W, -75 mV, 2200 MHz, ngram-map-k", "soak-and-output-gate.sh"),
    "soak-efficient-nospec.log":       ("30 min soak, console log from the superseded gate", "272 W, -75 mV, 2200 MHz, no speculation", "soak-and-output-gate.sh"),
    "soak-efficient-nospec-runs.jsonl": ("30 min soak, per-request records and output hashes", "272 W, -75 mV, 2200 MHz, no speculation", "soak-and-output-gate.sh"),
    "reference-sequence-ngram.json":    ("Reference output-hash sequence the gate compares against", "272 W, -75 mV, 2200 MHz, ngram-map-k", "soak-and-output-gate.sh"),
    "reference-sequence-nospec.json":   ("Reference output-hash sequence the gate compares against", "272 W, -75 mV, 2200 MHz, no speculation", "soak-and-output-gate.sh"),
    "perplexity-chunks.txt":       ("Per-chunk perplexity, wikitext-2 test split", "factory", "bench-idle.sh"),
    "quality-keys.json":           ("Answer keys for the keyed retrieval tasks", "n/a", "gen_quality_corpus.py"),
    "quality-keys-hard.json":      ("Answer keys for the harder keyed tasks", "n/a", "gen_quality_corpus_hard.py"),
    "power-cap-sweep.jsonl":       ("Power cap 303 / 288 / 272 W under decode load", "0 mV, unrestricted clock", "bench-power-cap.sh"),
    "clock-cap-sweep.jsonl":       ("Max SCLK 3045 down to 1800 MHz", "272 W, 0 mV", "bench-clock-cap.sh"),
    "undervolt-sweep.jsonl":       ("Voltage offset 0 to -125 mV", "272 W, unrestricted clock", "bench-undervolt-capped.sh"),
    "undervolt-sweep-capped.jsonl":("Voltage offset -100 to -200 mV, showing the clamp", "272 W, 2200 MHz", "bench-undervolt-capped.sh"),
    "undervolt-clamp-vddgfx.tsv":  ("Applied VDDGFX at -75 vs -200 mV, with and without the clock cap", "272 W", "bench-undervolt-clamp.sh"),
    "stock-303w.jsonl":            ("Loaded reference run at factory settings", "303 W, 0 mV, unrestricted clock", "bench-stock-303w.sh"),
    "stock-303w-soak.jsonl":       ("Soak at factory settings", "303 W, 0 mV, unrestricted clock", "bench-stock-303w.sh"),
    "aspm-sweep-early.jsonl":      ("First ASPM sweep, before the profile was fixed", "varied", "bench-aspm-early.sh"),
    "profile-combinations.jsonl":  ("Cap, clock and offset combinations", "varied", "bench-profile-combinations.sh"),
    "profile-final.jsonl":         ("Confirmation run of the chosen profile", "272 W, -75 mV, 2200 MHz", "bench-profile-final.sh"),
    "projector-q8-vs-bf16.jsonl":  ("Three image tasks against Q8_0 and BF16 projectors", "272 W, -75 mV, 2200 MHz", "bench-projector.sh"),
    "context-32k.jsonl":           ("Parameter sweep at 32K context: p-min, ubatch, reasoning, MMVQ", "272 W, -75 mV", "bench-context-32k.sh"),
    "context-128k-cache-types.jsonl": ("KV cache types at 128K on a 92K prompt", "272 W, -75 mV, 2200 MHz", "bench-context-65k.sh"),
    "reasoning-energy-per-answer.jsonl": ("Energy to answer one question at reasoning off / medium", "272 W, -75 mV", "bench-reasoning-energy.sh"),
    "reasoning-energy-hard.jsonl": ("The same on a question that generates far more", "272 W, -75 mV", "bench-reasoning-energy-hard.sh"),
    "multiturn-contents.jsonl":    ("Per-turn output of the multi-turn session", "272 W, -75 mV, 2200 MHz", "bench-multiturn.sh"),
    "energy-early.jsonl":          ("Early energy measurements, before the profile was fixed", "varied", "bench-energy-early.sh"),
    "energy-early-soak.jsonl":     ("Early soak, before the profile was fixed", "varied", "bench-energy-early.sh"),
    "kv-startup-128k.log":         ("Startup and prefill timing lines behind the memory figures, both cache types", "272 W, -75 mV, 2200 MHz", "srv-kv-128k.sh"),
    "kv-longctx-q8.json":          ("Three-task long-context set at 8K-120K, q8_0 V cache, two passes", "272 W, -75 mV, 2200 MHz", "kv_run_longctx.py"),
    "kv-longctx-turbo4.json":      ("Three-task long-context set at 8K-120K, turbo4 V cache, two passes", "272 W, -75 mV, 2200 MHz", "kv_run_longctx.py"),
    "kv-longctx-items.json":       ("Questions and answer keys for the long-context set", "n/a", "kv_gen_longctx.py"),
    "kv-nexttoken-q8.json":        ("Next-token distributions at 8K-120K, q8_0 V cache, ctx 131072", "272 W, -75 mV, 2200 MHz", "kv_run_nexttoken.py"),
    "kv-nexttoken-turbo4.json":    ("Next-token distributions at 8K-120K, turbo4 V cache, ctx 131072", "272 W, -75 mV, 2200 MHz", "kv_run_nexttoken.py"),
    "kv-repeat-q8-64k.json":       ("Four recomputes of one 64K prompt, q8_0 V cache", "272 W, -75 mV, 2200 MHz", "kv_run_repeat.py"),
    "kv-repeat-turbo4-64k.json":   ("Four recomputes of one 64K prompt, turbo4 V cache", "272 W, -75 mV, 2200 MHz", "kv_run_repeat.py"),
    "kv-needles-turbo4.json":      ("160-cell needle matrix, turbo4 V cache, ceiling result", "272 W, -75 mV, 2200 MHz", "kv_run_needles.py"),
    "kv-vision-q8.json":           ("Three image tasks, q8_0 V cache, ctx 131072", "272 W, -75 mV, 2200 MHz", "kv_run_vision.py"),
    "kv-vision-turbo4.json":       ("Three image tasks, turbo4 V cache, ctx 131072", "272 W, -75 mV, 2200 MHz", "kv_run_vision.py"),
    "spec-mtp-early.jsonl":        ("First MTP measurements", "303 W, 0 mV", "bench-context-32k.sh"),
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
