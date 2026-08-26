#!/usr/bin/env python3
"""Energia na token. Owija run1.run() samplerem sysfs (moc, temp, napiecie, takt).

Okna prefill/decode wyznaczane od konca przebiegu: decode jest ostatnie, wiec
wyrownanie do t1 jest dokladne bez znacznikow czasu po stronie serwera.
Twardy strop bezpieczenstwa: junction >= JMAX przerywa sampler i oznacza wynik.
"""
import argparse, json, sys, threading, time
import run1

H = "/sys/class/drm/card1/device/hwmon/hwmon1"
D = "/sys/class/drm/card1/device"
JMAX = 105.0  # emergency karty to 115 C

def rd(p):
    try:
        return int(open(p).read())
    except Exception:
        return 0
def cpu_jiffies():
    v = list(map(int, open("/proc/stat").readline().split()[1:]))
    return sum(v), sum(v) - v[3] - (v[4] if len(v) > 4 else 0)   # (total, busy) bez idle i iowait

class Sampler(threading.Thread):
    def __init__(self, hz=4.0):
        super().__init__(daemon=True)
        self.hz, self.stop, self.rows, self.overtemp = hz, False, [], None
        self.prev = cpu_jiffies()   # R3: obciazenie CPU mierzone ciagle, nie tylko na starcie
    def run(self):
        while not self.stop:
            j = rd(f"{H}/temp2_input") / 1000.0
            cur = cpu_jiffies()
            dt, db = cur[0] - self.prev[0], cur[1] - self.prev[1]
            self.prev = cur
            cpu = round(100.0 * db / dt, 2) if dt > 0 else 0.0
            self.rows.append((time.time(), rd(f"{H}/power1_average"),
                              rd(f"{H}/temp1_input"), int(j * 1000), rd(f"{H}/temp3_input"),
                              rd(f"{H}/fan1_input"), rd(f"{D}/gpu_busy_percent"),
                              rd(f"{H}/in0_input"), rd(f"{H}/freq1_input"), cpu))
            if j >= JMAX and self.overtemp is None:
                self.overtemp = j
                self.stop = True
                return
            time.sleep(1.0 / self.hz)

def win(rows, t0, t1):
    s = [r for r in rows if t0 <= r[0] <= t1]
    if not s:
        return None
    p = [r[1] / 1e6 for r in s]
    n = len(s)
    return {"n": n, "w_avg": round(sum(p) / n, 1), "w_max": round(max(p), 1),
            "junction_avg": round(sum(r[3] for r in s) / n / 1000.0, 1),
            "junction_max": round(max(r[3] for r in s) / 1000.0, 1),
            "edge_max": round(max(r[2] for r in s) / 1000.0, 1),
            "mem_max": round(max(r[4] for r in s) / 1000.0, 1),
            "fan_max": max(r[5] for r in s),
            "busy_avg": round(sum(r[6] for r in s) / n, 1),
            "mv_avg": round(sum(r[7] for r in s) / n, 1),
            "sclk_avg": round(sum(r[8] for r in s) / n / 1e6, 0),
            "cpu_busy_avg": round(sum(r[9] for r in s) / n, 2),
            "cpu_busy_max": round(max(r[9] for r in s), 2)}

def idle(sec=4.0, hz=4.0):
    sm = Sampler(hz); sm.start(); time.sleep(sec); sm.stop = True; sm.join(2)
    return win(sm.rows, 0, time.time()) or {}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt"); ap.add_argument("--question", required=True)
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--reasoning"); ap.add_argument("--tag", default="")
    ap.add_argument("--out"); ap.add_argument("--idle-w", type=float, default=14.0)
    ap.add_argument("--cpu-busy-max", type=float, default=3.0,
                    help="prog obcego obciazenia CPU; probka dostaje flage brudna, nie jest kasowana")
    a = ap.parse_args()

    sm = Sampler(); sm.start()
    t0 = time.time()
    res = run1.run(a.prompt, a.question, a.max_tokens, a.reasoning, None, a.tag)
    t1 = time.time()
    sm.stop = True; sm.join(2)

    pn, ptps = res.get("prompt_n") or 0, res.get("prefill_tps") or 0
    dn, dtps = res.get("predicted_n") or 0, res.get("decode_tps") or 0
    d_s = dn / dtps if dtps else 0.0
    p_s = pn / ptps if ptps else 0.0
    dec = win(sm.rows, t1 - d_s, t1)
    pre = win(sm.rows, t1 - d_s - p_s, t1 - d_s)
    tot = win(sm.rows, t0, t1)

    o = {"tag": a.tag, "decode_tps": dtps, "prefill_tps": ptps,
         "predicted_n": dn, "prompt_n": pn,
         "decode_s": round(d_s, 2), "prefill_s": round(p_s, 2),
         "accept_pct": res.get("accept_pct"), "vram_mib": res.get("vram_mib"),
         "reasoning_chars": res.get("reasoning_chars"), "sha1": res.get("sha1"),
         "overtemp_c": sm.overtemp, "idle_w_ref": a.idle_w,
         "cpu_busy_max_pct": a.cpu_busy_max,
         "decode": dec, "prefill": pre, "total": tot}
    if dec and dn:
        o["j_per_tok"] = round(dec["w_avg"] * d_s / dn, 3)
        o["j_per_tok_net"] = round(max(0.0, dec["w_avg"] - a.idle_w) * d_s / dn, 3)
        o["tok_per_wh"] = round(dn / (dec["w_avg"] * d_s / 3600.0), 1) if dec["w_avg"] else None
    o["brudna"] = bool(tot and tot["cpu_busy_max"] > a.cpu_busy_max)
    if o["brudna"]:
        print("UWAGA: obce obciazenie CPU w oknie pomiaru: max=%.2f%% > %.2f%%"
              % (tot["cpu_busy_max"], a.cpu_busy_max), file=sys.stderr)
    if a.out:
        open(a.out, "a").write(json.dumps(o, ensure_ascii=False) + "\n")
    print(json.dumps(o, ensure_ascii=False))
