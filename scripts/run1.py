#!/usr/bin/env python3
"""Jeden przebieg: wysyla prompt do dzialajacego llama-server:8099 i zbiera metryki."""
import hashlib, json, os, re, subprocess, sys, time, urllib.request

def gpu(f): return int(open(f"/sys/class/drm/card1/device/{f}").read())
def hotspot():
    o = subprocess.run(["sensors"], capture_output=True, text=True).stdout
    m = re.search(r"junction:\s+\+([\d.]+)", o)
    return float(m.group(1)) if m else 0.0

def run(prompt_file, question, max_tokens=512, reasoning=None, images=None, tag=""):
    txt = open(prompt_file).read() if prompt_file else ""
    content = (txt + "\n\n" + question) if txt else question
    if images:
        parts = [{"type": "text", "text": content}]
        for im in images:
            import base64
            b = base64.b64encode(open(im, "rb").read()).decode()
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:image/png;base64,{b}"}})
        msg = {"role": "user", "content": parts}
    else:
        msg = {"role": "user", "content": content}
    body = {"messages": [msg], "temperature": 0, "top_k": 1, "seed": 1234,
            "max_tokens": max_tokens, "stream": False}
    if reasoning is not None:
        body["reasoning_effort"] = reasoning
    v0, g0 = gpu("mem_info_vram_used"), gpu("mem_info_gtt_used")
    req = urllib.request.Request("http://127.0.0.1:8099/v1/chat/completions",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=3600))
    wall = time.time() - t0
    v1, g1 = gpu("mem_info_vram_used"), gpu("mem_info_gtt_used")
    tm = r.get("timings", {})
    ch = r["choices"][0]["message"]
    out = {
        "tag": tag, "wall_s": round(wall, 2),
        "prompt_n": tm.get("prompt_n"), "prefill_tps": round(tm.get("prompt_per_second") or 0, 2),
        "predicted_n": tm.get("predicted_n"), "decode_tps": round(tm.get("predicted_per_second") or 0, 2),
        "draft_n": tm.get("draft_n"), "draft_n_accepted": tm.get("draft_n_accepted"),
        "vram_mib": round(v1 / 1048576, 1), "vram_delta_mib": round((v1 - v0) / 1048576, 1),
        "gtt_mib": round(g1 / 1048576, 1), "gtt_delta_mib": round((g1 - g0) / 1048576, 1),
        "junction_c": hotspot(),
        "reasoning_chars": len(ch.get("reasoning_content") or ""),
        "content": ch.get("content") or "",
        "reasoning_content": ch.get("reasoning_content") or "",
        "sha1": hashlib.sha1((ch.get("content") or "").encode()).hexdigest()[:12],
        "sha1_reasoning": hashlib.sha1((ch.get("reasoning_content") or "").encode()).hexdigest()[:12],
    }
    if out["draft_n"]:
        out["accept_pct"] = round(100 * out["draft_n_accepted"] / out["draft_n"], 2)
    return out

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt"); ap.add_argument("--question", required=True)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--reasoning"); ap.add_argument("--image", action="append")
    ap.add_argument("--tag", default=""); ap.add_argument("--out")
    a = ap.parse_args()
    res = run(a.prompt, a.question, a.max_tokens, a.reasoning, a.image, a.tag)
    line = json.dumps(res, ensure_ascii=False)
    if a.out: open(a.out, "a").write(line + "\n")
    d = dict(res); d["content"] = d["content"][:400]
    print(json.dumps(d, ensure_ascii=False, indent=1))
