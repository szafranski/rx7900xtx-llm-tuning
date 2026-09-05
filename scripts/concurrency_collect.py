#!/usr/bin/env python3
"""Skleja wyniki z bench-concurrency.sh w dwa pliki dla data/.

Czyta results/resp-*.json i results/wall-*.txt (blok "timings" prosto od
serwera, bez telemetrii GPU, bo ten test jej nie zbieral) oraz logs/monitor-p*.log
z sampleera 1 Hz. Pisze do data/.

Nazwa etykiety niesie caly opis przebiegu: "p<sloty>-<rola>[-warm]" albo
"p<sloty>-q<n>". Stad biora sie kolumny arm/parallel/role.
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STAMP = sys.argv[1] if len(sys.argv) > 1 else "20260905"

# Sampler chodzi dalej przez chwile po ostatniej odpowiedzi, a przy recznym
# uruchamianiu potrafi zostac na dluzej. Zamiast wpisywac granice recznie:
# bierzemy od pierwszej do ostatniej probki z requests_processing > 0 i
# dokladamy PAD sekund z obu stron.
PAD = 30
FIELDS = ("prompt_tokens_total", "tokens_predicted_total", "requests_processing",
          "requests_deferred", "n_busy_slots_per_decode")
SAMPLE = re.compile(r"^(\d\d:\d\d:\d\d) vram=(\d+)MiB ?(.*)$")


def secs(t):
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


def arm_of(label):
    m = re.match(r"^p(\d+)-(.+)$", label)
    if not m:
        raise SystemExit(f"etykieta nie do rozlozenia: {label}")
    par, rest = int(m.group(1)), m.group(2)
    if rest == "solo":
        return f"p{par}/1req", par, "solo"
    if rest.startswith("q"):
        return f"p{par}/4req", par, rest
    if rest.endswith("-warm"):
        return f"p{par}/2req-warm", par, rest[:-len("-warm")]
    return f"p{par}/3req", par, rest


def requests():
    recs = []
    for p in sorted((ROOT / "results").glob("resp-p*.json")):
        label = p.stem[len("resp-"):]
        t = json.loads(p.read_text())["timings"]
        wall = float((ROOT / "results" / f"wall-{label}.txt").read_text().split("=")[1])
        arm, par, role = arm_of(label)
        recs.append({
            "tag": label, "arm": arm, "parallel": par, "role": role,
            "prompt_total_n": t["cache_n"] + t["prompt_n"],
            "cache_n": t["cache_n"], "prompt_new_n": t["prompt_n"],
            "prompt_ms": round(t["prompt_ms"], 1),
            "prompt_per_second": round(t["prompt_per_second"], 1),
            "predicted_n": t["predicted_n"], "predicted_ms": round(t["predicted_ms"], 1),
            "decode_tps": round(t["predicted_per_second"], 2),
            "draft_n": t["draft_n"], "draft_n_accepted": t["draft_n_accepted"],
            "accept_pct": round(100 * t["draft_n_accepted"] / t["draft_n"], 1),
            "wall_s": round(wall, 2),
        })
    return recs


def monitor():
    out = []
    for p in sorted((ROOT / "logs").glob("monitor-p*.log")):
        session = "parallel-" + p.stem.split("-p")[-1]
        rows = []
        for line in p.read_text(errors="replace").splitlines():
            m = SAMPLE.match(line.strip())
            if not m:
                continue
            kv = dict(x.split("=", 1) for x in m.group(3).split() if "=" in x)
            r = {"session": session, "t": m.group(1), "vram_mib": int(m.group(2))}
            # Pusty blok licznikow to /metrics, ktore nie odpowiedzialo w 2 s.
            for f in FIELDS:
                v = kv.get("llamacpp:" + f)
                r[f] = float(v) if v is not None else None
            rows.append(r)
        busy = [secs(r["t"]) for r in rows if (r["requests_processing"] or 0) > 0]
        if not busy:
            continue
        lo, hi = min(busy) - PAD, max(busy) + PAD
        out += [r for r in rows if lo <= secs(r["t"]) <= hi]
    return out


def write(name, rows):
    path = DATA / name
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print(f"{path}: {len(rows)}")


def main():
    write(f"concurrency-{STAMP}.jsonl", requests())
    write(f"concurrency-{STAMP}-monitor.jsonl", monitor())


if __name__ == "__main__":
    main()
