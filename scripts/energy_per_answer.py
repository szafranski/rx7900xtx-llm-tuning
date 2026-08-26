#!/usr/bin/env python3
"""Faza 12: energia i czas na ODPOWIEDZ (nie na token).

Rozne od pw.py: nie ucina generacji (max-tokens duze), liczy calke mocy po calym
requescie, wykrywa ucieta odpowiedz po finish_reason i zapisuje liczbe znakow
odpowiedzi koncowej osobno od znakow rozumowania.
Sprzet TYLKO do czytania - zaden zapis do sysfs.
"""
import argparse, hashlib, json, threading, time, urllib.request

H = "/sys/class/drm/card1/device/hwmon/hwmon1"
D = "/sys/class/drm/card1/device"
JMAX = 105.0


def rd(p):
    try:
        return int(open(p).read())
    except Exception:
        return 0


class Sampler(threading.Thread):
    def __init__(self, hz=4.0):
        super().__init__(daemon=True)
        self.hz, self.stop, self.rows, self.overtemp = hz, False, [], None

    def run(self):
        while not self.stop:
            j = rd(f"{H}/temp2_input") / 1000.0
            self.rows.append((time.time(), rd(f"{H}/power1_average"), int(j * 1000),
                              rd(f"{D}/gpu_busy_percent"), rd(f"{H}/in0_input"),
                              rd(f"{H}/freq1_input"), rd(f"{H}/fan1_input")))
            if j >= JMAX and self.overtemp is None:
                self.overtemp = j
                self.stop = True
                return
            time.sleep(1.0 / self.hz)


def win(rows, t0, t1, idle_w):
    """Energia w oknie [t0,t1]. Calka trapezami po realnych znacznikach czasu."""
    s = [r for r in rows if t0 <= r[0] <= t1]
    if len(s) < 2:
        return None
    j = 0.0
    for a, b in zip(s, s[1:]):
        j += (a[1] / 1e6 + b[1] / 1e6) / 2.0 * (b[0] - a[0])
    span = s[-1][0] - s[0][0]
    n = len(s)
    return {"n": n, "span_s": round(span, 2), "j": round(j, 1),
            "j_net": round(max(0.0, j - idle_w * span), 1),
            "w_avg": round(j / span, 1) if span else 0.0,
            "w_max": round(max(r[1] for r in s) / 1e6, 1),
            "junction_max": round(max(r[2] for r in s) / 1000.0, 1),
            "busy_avg": round(sum(r[3] for r in s) / n, 1),
            "mv_avg": round(sum(r[4] for r in s) / n, 1),
            "sclk_avg": round(sum(r[5] for r in s) / n / 1e6, 0),
            "fan_max": max(r[6] for r in s)}


def ask(prompt_file, question, max_tokens, effort):
    txt = open(prompt_file).read() if prompt_file else ""
    content = (txt + "\n\n" + question) if txt else question
    body = {"messages": [{"role": "user", "content": content}], "temperature": 0,
            "top_k": 1, "seed": 1234, "max_tokens": max_tokens, "stream": False}
    if effort:
        body["reasoning_effort"] = effort
    req = urllib.request.Request("http://127.0.0.1:8099/v1/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=3600))


def idle(sec=6.0):
    sm = Sampler(); sm.start(); time.sleep(sec); sm.stop = True; sm.join(2)
    s = sm.rows
    return round(sum(r[1] for r in s) / len(s) / 1e6, 1) if s else 0.0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt"); ap.add_argument("--question", required=True)
    ap.add_argument("--max-tokens", type=int, default=12000)
    ap.add_argument("--effort"); ap.add_argument("--tag", default="")
    ap.add_argument("--idle-w", type=float, default=18.0)
    ap.add_argument("--out")
    a = ap.parse_args()

    sm = Sampler(); sm.start()
    t0 = time.time()
    r = ask(a.prompt, a.question, a.max_tokens, a.effort)
    t1 = time.time()
    sm.stop = True; sm.join(2)

    tm = r.get("timings", {})
    ch = r["choices"][0]
    msg = ch["message"]
    dn = tm.get("predicted_n") or 0
    pn = tm.get("prompt_n") or 0
    dtps = round(tm.get("predicted_per_second") or 0, 2)
    ptps = round(tm.get("prompt_per_second") or 0, 2)
    d_s = dn / dtps if dtps else 0.0
    p_s = pn / ptps if ptps else 0.0
    body_txt = msg.get("content") or ""
    reas = msg.get("reasoning_content") or ""

    o = {"tag": a.tag, "wall_s": round(t1 - t0, 2),
         "finish_reason": ch.get("finish_reason"),
         "truncated": bool(dn >= a.max_tokens),
         "prompt_n": pn, "predicted_n": dn,
         "prefill_tps": ptps, "decode_tps": dtps,
         "prefill_s": round(p_s, 2), "decode_s": round(d_s, 2),
         "reasoning_chars": len(reas), "answer_chars": len(body_txt),
         "draft_n": tm.get("draft_n"), "draft_n_accepted": tm.get("draft_n_accepted"),
         "sha1": hashlib.sha1(body_txt.encode()).hexdigest()[:12],
         "overtemp_c": sm.overtemp, "idle_w_ref": a.idle_w,
         "total": win(sm.rows, t0, t1, a.idle_w),
         "decode": win(sm.rows, t1 - d_s, t1, a.idle_w),
         "prefill": win(sm.rows, t1 - d_s - p_s, t1 - d_s, a.idle_w)}
    if o["draft_n"]:
        o["accept_pct"] = round(100 * o["draft_n_accepted"] / o["draft_n"], 2)
    tot = o["total"]
    if tot:
        # to jest sedno fazy 12: energia i czas na JEDNA ODPOWIEDZ
        o["j_per_answer"] = tot["j"]
        o["j_per_answer_net"] = tot["j_net"]
        o["s_per_answer"] = o["wall_s"]
        if o["answer_chars"]:
            o["j_per_1k_znakow_odpowiedzi"] = round(tot["j"] / o["answer_chars"] * 1000, 1)
    if a.out:
        open(a.out, "a").write(json.dumps(o, ensure_ascii=False) + "\n")
    print(json.dumps(o, ensure_ascii=False))
