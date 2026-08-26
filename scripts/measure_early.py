#!/usr/bin/env python3
"""Baseline spec-none + Faza 2b (reasoning medium, PL) + Faza 3 (ubatch x MTP).
Parametry: NMAX (zwyciezca fazy 2), PMIN (opcjonalny), UB, BB."""
import json, os, subprocess, sys, time
sys.path.insert(0, ".")
import run1

OUT = "results/30-faza2b-3.jsonl"
NMAX = os.environ.get("NMAX", "3")
PMIN = os.environ.get("PMIN", "")
UB, BB = os.environ.get("UB", "1024"), os.environ.get("BB", "4096")
ENV = {"RADV_PERFTEST": "nogttspill"}

Q_EN = ("List 40 distinct function, class or struct names that appear in this code. "
        "Output one per line as: NAME - one short sentence describing what it does. "
        "Do not stop early, produce all 40 lines.")
Q_PL = ("Wymien 40 roznych nazw funkcji, klas lub struktur wystepujacych w tym kodzie. "
        "Kazda w osobnej linii w formacie: NAZWA - jedno krotkie zdanie po polsku "
        "opisujace, co robi. Nie przerywaj wczesniej, podaj wszystkie 40 linii.")
Q_PL_NEEDLE = ("Odpowiedz po polsku. Najpierw podaj doslownie kod dostepu do wezla "
               "obliczeniowego oraz osobe odpowiedzialna, ktore wystepuja w tym tekscie. "
               "Potem opisz w piecu zdaniach, czego dotyczy ten kod.")

MTP = ["--spec-type", "draft-mtp", "--spec-draft-n-max", NMAX]
if PMIN:
    MTP += ["--spec-draft-p-min", PMIN]

def base(ub, bb, reasoning_off=True):
    a = (f"-ngl 99 -c 65536 -fa on -ctk q8_0 -ctv q8_0 -ctkd q8_0 -ctvd q8_0 "
         f"-np 1 -ub {ub} -b {bb} --no-warmup").split()
    if reasoning_off:
        a += ["--reasoning", "off"]
    else:
        a += ["--reasoning", "on", "--reasoning-effort", "medium",
              "--reasoning-budget", "8192", "--reasoning-format", "deepseek"]
    return a

def stop():
    subprocess.run(["pkill", "-f", "llama-server.*8099"], capture_output=True)
    time.sleep(4)

def go(tag, srv_args, question, maxtok, prompt="prompts/P20K.txt"):
    stop()
    e = dict(os.environ); e.update(ENV)
    e["SRV_LOG"] = "logs/f3-" + tag.replace("/", "_") + ".log"
    r = subprocess.run(["./srv.sh"] + srv_args, env=e, capture_output=True, text=True)
    if "SERVER UP" not in r.stdout:
        print("SRVFAIL " + tag + ": " + (r.stdout + r.stderr)[-400:], flush=True); return None
    try:
        res = run1.run(prompt, question, maxtok, None, None, tag)
    except Exception as ex:
        print("RUNFAIL " + tag + ": " + repr(ex), flush=True); stop(); return None
    res["srv_args"] = " ".join(srv_args)
    open(OUT, "a").write(json.dumps(res, ensure_ascii=False) + "\n")
    print("DONE {}: dec={} pf={} acc={} n={} think={} vram={} gtt={} jc={} sha={}".format(
        tag, res["decode_tps"], res["prefill_tps"], res.get("accept_pct"),
        res["predicted_n"], res["reasoning_chars"], res["vram_mib"], res["gtt_mib"],
        res["junction_c"], res["sha1"]), flush=True)
    stop()
    return res

# --- baseline bez spekulacji, wzorcowe sha
go("ref_specnone", base(UB, BB) + ["--spec-type", "none"], Q_EN, 1024)

# --- doprecyzowanie p-min + rozrzut miedzy przebiegami
for tag, pm in (("pmin0.65", "0.65"), ("pmin0.70", "0.70"),
                ("pmin0.60_rep2", "0.60"), ("pmin0.60_rep3", "0.60")):
    go("pm_" + tag,
       base(UB, BB) + ["--spec-type", "draft-mtp", "--spec-draft-n-max", NMAX,
                       "--spec-draft-p-min", pm],
       Q_EN, 1024)

# --- Faza 2b: reasoning
go("r_off_en", base(UB, BB) + MTP, Q_EN, 1024)
go("r_medium_en", base(UB, BB, False) + MTP, Q_EN, 4096)
go("r_medium_pl", base(UB, BB, False) + MTP, Q_PL, 4096)
go("r_medium_pl_needle", base(UB, BB, False) + MTP, Q_PL_NEEDLE, 4096)

# --- Faza 3: ubatch x MTP (reasoning off, izolacja zmiennej)
for ub, bb in (("288", "2048"), ("512", "2048"), ("2048", "8192")):
    go("f3_ub" + ub, base(ub, bb) + MTP, Q_EN, 1024)

print("FAZA2B-3 DONE", flush=True)
