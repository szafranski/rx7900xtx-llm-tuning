#!/usr/bin/env python3
"""Faza 15 krok 2: sesja wieloturowa z powracajacym kontekstem.

Cala seria mierzyla dotad jeden strzal: dlugi prompt, swieza odpowiedz. To
przypadek, w ktorym n-gram jest bezuzyteczny, i to zmierzylismy w fazie 2.
Praca agentowa i kodowa ma inny ksztalt: ten sam plik wraca do kontekstu tura
po turze.

Transkrypt jest STALY. Gdyby kazdy wariant dopisywal do historii swoja
odpowiedz, rozmowy rozjechalyby sie po dwoch, trzech turach i warianty
przestalyby wykonywac ten sam test. Wiec: tryb "record" tworzy transkrypt raz,
tryb "replay" podaje kazdemu wariantowi identyczny prefiks z pliku, mierzy ture
k i WYRZUCA wygenerowana odpowiedz.

Metryka glowna: czas scienny calej sesji i czas per tura, plus TTFT. Nie tok/s -
lekcja z fazy 12 (metryka na token klamie, gdy nastawa zmienia liczbe tokenow).
Energia z obu kanalow, per sesja, nie per token; nie jest bramka, bo nie mamy
licznika przy gniazdku.

Konsekwencja stalego transkryptu, powiedziana wprost: cache serwera po turze k-1
trzyma wygenerowana odpowiedz, a tura k zada odpowiedzi z pliku, wiec wspolny
prefiks konczy sie na pytaniu k-1 i kazda tura doprefillowuje a[k-1] + u[k].
To jest identyczne dla wszystkich wariantow, wiec sie skraca w porownaniu, ale
nie jest to doslowny przebieg realnej sesji.
"""
import argparse, hashlib, json, sys, time, urllib.request
import pw14

URL = "http://127.0.0.1:8099/v1/chat/completions"

def ask(messages, max_tokens, reasoning, stream):
    """Zwraca (content, ttft_s, wall_s, timings). TTFT wymaga strumienia."""
    body = {"messages": messages, "temperature": 0, "top_k": 1, "seed": 1234,
            "max_tokens": max_tokens, "stream": stream}
    if reasoning:
        body["reasoning_effort"] = reasoning
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    if not stream:
        r = json.load(urllib.request.urlopen(req, timeout=3600))
        m = r["choices"][0]["message"]
        return (m.get("content") or "", None, time.time() - t0,
                dict(r.get("timings", {}), rea_chars=len(m.get("reasoning_content") or "")))
    out, rea, ttft, tm = [], [], None, {}
    with urllib.request.urlopen(req, timeout=3600) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                ch = json.loads(payload)
            except ValueError:
                continue
            if ch.get("timings"):
                tm = ch["timings"]
            for c in ch.get("choices") or []:
                d = c.get("delta") or {}
                if d.get("reasoning_content"):
                    rea.append(d["reasoning_content"])
                piece = d.get("content")
                if piece:
                    if ttft is None:
                        ttft = time.time() - t0
                    out.append(piece)
    return "".join(out), ttft, time.time() - t0, dict(tm, rea_chars=len("".join(rea)))

def sess(turns, transcript, mode, max_tokens, reasoning):
    """Jedna sesja. W trybie record buduje transkrypt, w replay go odtwarza."""
    msgs, rows, rec = [], [], []
    for k, u in enumerate(turns):
        msgs.append({"role": "user", "content": u})
        content, ttft, wall, tm = ask(msgs, max_tokens, reasoning, mode == "replay")
        rows.append({"turn": k + 1, "wall_s": round(wall, 2),
                     "ttft_s": round(ttft, 2) if ttft else None,
                     "prompt_n": tm.get("prompt_n"), "predicted_n": tm.get("predicted_n"),
                     "prefill_tps": round(tm.get("prompt_per_second") or 0, 2),
                     "decode_tps": round(tm.get("predicted_per_second") or 0, 2),
                     "draft_n": tm.get("draft_n"), "draft_n_accepted": tm.get("draft_n_accepted"),
                     "out_chars": len(content), "rea_chars": tm.get("rea_chars"),
                     "_content": content,
                     "sha1": hashlib.sha1(content.encode()).hexdigest()[:12]})
        if mode == "record":
            if not content.strip():
                raise SystemExit(
                    f"tura {k+1}: pusta tresc, {tm.get('rea_chars')} znakow rozumowania, "
                    f"{tm.get('predicted_n')} tokenow. Caly budzet zjadlo rozumowanie - "
                    f"podnies --max-tokens, inaczej transkrypt bedzie bezwartosciowy.")
            rec.append(content)
            msgs.append({"role": "assistant", "content": content})
        else:
            # wygenerowana odpowiedz idzie do kosza, do historii wchodzi ta z pliku
            msgs.append({"role": "assistant", "content": transcript[k]})
    return rows, rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--mode", choices=["record", "replay"], required=True)
    ap.add_argument("--max-tokens", type=int, default=900)
    ap.add_argument("--reasoning", default="medium")
    ap.add_argument("--tag", default=""); ap.add_argument("--out")
    ap.add_argument("--save-content", help="zapisz tresci tur do pliku json, do porownania wyjsc miedzy wariantami")
    a = ap.parse_args()

    turns = json.load(open(a.turns))
    tr = json.load(open(a.transcript)) if a.mode == "replay" else None
    if tr is not None and len(tr) != len(turns):
        sys.exit(f"transkrypt ma {len(tr)} odpowiedzi na {len(turns)} tur")

    sm = pw14.Sampler(); sm.start()
    t0 = time.time()
    rows, rec = sess(turns, tr, a.mode, a.max_tokens, a.reasoning)
    t1 = time.time()
    sm.stop = True; sm.join(2)

    if a.mode == "record":
        json.dump(rec, open(a.transcript, "w"), ensure_ascii=False, indent=1)
        print(f"zapisano transkrypt: {a.transcript}, {len(rec)} odpowiedzi")

    w = pw14.win(sm.rows, t0, t1) or {}
    o = {"tag": a.tag, "mode": a.mode, "turns": len(turns),
         "session_s": round(t1 - t0, 2),
         "ttft_avg_s": round(sum(r["ttft_s"] or 0 for r in rows) / len(rows), 2),
         "ttft_max_s": max((r["ttft_s"] or 0) for r in rows),
         "tok_out": sum(r["predicted_n"] or 0 for r in rows),
         "sha1_session": hashlib.sha1("|".join(r["sha1"] for r in rows).encode()).hexdigest()[:12],
         "overtemp_c": sm.overtemp, "session": w, "per_turn": rows}
    if w.get("w_avg"):
        o["gpu_wh"] = round(w["w_avg"] * (t1 - t0) / 3600.0, 3)
    if w.get("cpu_pkg_w"):
        o["cpu_wh"] = round(w["cpu_pkg_w"] * (t1 - t0) / 3600.0, 3)
    if a.save_content:
        json.dump([r["_content"] for r in rows], open(a.save_content, "w"),
                  ensure_ascii=False, indent=1)
    for r in rows:
        r.pop("_content", None)   # tresc nie idzie do pliku wynikow, tylko skrot
    if a.out:
        open(a.out, "a").write(json.dumps(o, ensure_ascii=False) + "\n")
    d = dict(o); d.pop("per_turn")
    print(json.dumps(d, ensure_ascii=False))

def demo():
    # jedyne nietrywialne miejsce bez serwera: skladanie historii i wyrzucanie generacji
    seen = []
    def fake(msgs, *_):
        seen.append([m["content"] for m in msgs])
        return "GEN%d" % len(seen), 0.1, 1.0, {"predicted_n": 1, "prompt_n": 2}
    global ask
    real, ask = ask, fake
    try:
        rows, rec = sess(["u1", "u2", "u3"], ["A1", "A2", "A3"], "replay", 10, None)
        assert seen[1] == ["u1", "A1", "u2"], seen[1]          # do historii idzie plik
        assert seen[2] == ["u1", "A1", "u2", "A2", "u3"], seen[2]
        assert rec == [] and len(rows) == 3
        seen.clear()
        rows, rec = sess(["u1", "u2"], None, "record", 10, None)
        assert seen[1] == ["u1", "GEN1", "u2"], seen[1]        # tu wlasna generacja
        assert rec == ["GEN1", "GEN2"]
        # pusta odpowiedz musi zatrzymac nagrywanie, nie trafic do transkryptu
        seen.clear()
        ask = lambda *a: ("   ", 0.1, 1.0, {"rea_chars": 900, "predicted_n": 900})
        try:
            sess(["u1"], None, "record", 10, None)
        except SystemExit as e:
            assert "pusta tresc" in str(e), e
        else:
            raise AssertionError("pusta tresc przeszla przez nagrywanie")
    finally:
        ask = real
    print("demo ok")

if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo(); sys.exit(0)
    main()
