# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen context f4-ctx-120k.txt and f4-items.json from the phase-4 generator,
# results f6-<tag>.json. Comments and question wording are Polish, as elsewhere.
# Faza 6: czy rozumowanie zmienia trafnosc na 120k, w ustawieniach produkcyjnych.
#   python3 ~/gate/f6-run.py <tag> [reps] [len]
# Dwa ramiona na tym samym materiale: rozumowanie ON i OFF, wszystko inne rowne.
# Bez ramienia OFF nie da sie przypisac roznicy rozumowaniu, bo probkujemy
# produkcyjnie (temp 0.6), a nie greedy jak w fazach 4-5.
# Kolejnosc ramion w parze jest naprzemienna miedzy powtorzeniami - w fazie 5
# pozycja w parze okazala sie miec wplyw, wiec nie moze byc stala.
# Pilot mierzy dlugosc rozumowania PO prefillu i z niej wylicza czas calosci.
import json,os,re,sys,time,hashlib,urllib.request
G=os.path.expanduser("~/gate")
U="http://127.0.0.1:8098"

TAG=sys.argv[1]
REPS=int(sys.argv[2]) if len(sys.argv)>2 else 4
L=sys.argv[3] if len(sys.argv)>3 else "120k"
PILOT_MT=1536          # limit pilota; jesli pilot go dobija, rozumowanie jest dlugie
FLOOR_MT=512
CEIL_MT=8320           # budzet rozumowania 8192 + miejsce na odpowiedz

def post(path,obj,timeout=1800):
    r=urllib.request.Request(U+path,data=json.dumps(obj).encode(),
                             headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(r,timeout=timeout))

def ask(prompt,mt,think,seed=None):
    # probkowanie produkcyjne; seed rozny per powtorzenie, zeby probki byly niezalezne
    b={"messages":[{"role":"user","content":prompt}],"max_tokens":mt,"cache_prompt":True,
       "temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.05}
    if seed is not None: b["seed"]=seed
    if not think: b["chat_template_kwargs"]={"enable_thinking":False}
    t0=time.time(); r=post("/v1/chat/completions",b); dt=time.time()-t0
    ch=r["choices"][0]; m=ch["message"]; u=r.get("usage") or {}
    return {"dt":round(dt,2),"content":(m.get("content") or ""),
            "reas_chars":len(m.get("reasoning_content") or ""),
            "finish":ch.get("finish_reason"),
            "compl_tok":u.get("completion_tokens"),
            "cached":(u.get("prompt_tokens_details") or {}).get("cached_tokens")}

meta=json.load(open(G+"/f4-items.json"))
ITEMS=[(i,t,q,e) for i,(t,q,e) in enumerate(meta["items"]) if t in ("B","C")]
PAT={"B":r"(WEZEL-\d{3})","C":r"\b(\d{1,3})\b"}
def grade(typ,txt,exp):
    # tylko po content; rozumowanie NIE jest punktowane.
    # Z rozumowaniem ON model moze odpowiedziec zdaniem, a nie gola wartoscia, i
    # wtedy pierwszy regex trafia w zla liczbe ("partycja 77 ma 5 kluczy" -> 77).
    # Nie zgaduje ktora liczba jest wlasciwa: oznaczam odpowiedzi NIE-gole i
    # licze je osobno, do recznego przejrzenia.
    t=(txt or "").upper().strip()
    m=re.search(PAT[typ],t)
    got=m.group(1) if m else None
    bare=bool(got) and re.fullmatch(r"[^A-Z0-9]*"+re.escape(got)+r"[^A-Z0-9]*",t) is not None
    return got,(got==exp.upper()),bare

ctx=open(G+"/f4-ctx-%s.txt"%L).read()
sha=hashlib.sha256(ctx.encode()).hexdigest()
res={"tag":TAG,"reps":REPS,"len":L,"ctx_sha256":sha,"n_items":len(ITEMS),
     "sampling":{"temp":0.6,"top_p":0.95,"top_k":20,"min_p":0.05},
     "server":"f6-srv.sh, ustawienia produkcyjne, cache-reuse 256","pilot":[],"runs":[]}
print("dlugosc %s, sha256 %s, pozycji %d, powtorzen %d"%(L,sha[:16],len(ITEMS),REPS),flush=True)

t0=time.time()
warm=ask(ctx+"\n\nPytanie: odpowiedz slowem OK.",8,False)
print("prefill %.1f s, cached %s"%(warm["dt"],warm["cached"]),flush=True)

# --- pilot: trzy pozycje typu C z rozumowaniem, po to zeby ustawic max_tokens ---
for i,typ,q,e in [it for it in ITEMS if it[1]=="C"][:3]:
    r=ask(ctx+"\n\n"+q,PILOT_MT,True)
    r["i"]=i; r["typ"]=typ; res["pilot"].append(r)
    print("pilot #%02d %s: %.1f s, tokenow %s, rozumowania %d znakow, finish=%s, content=%r"%(
        i,typ,r["dt"],r["compl_tok"],r["reas_chars"],r["finish"],r["content"][:60]),flush=True)
ct=[p["compl_tok"] or 0 for p in res["pilot"]]
dts=[p["dt"] for p in res["pilot"]]
ucieta=sum(1 for p in res["pilot"] if p["finish"]=="length")
MT=max(FLOOR_MT,min(CEIL_MT,int(max(ct)*1.6)+128))
if ucieta: MT=CEIL_MT   # pilot dobil limit, wiec nie zgaduj - daj pelny budzet
n_on=len(ITEMS)*REPS
proj=(sum(dts)/len(dts))*n_on   # przy ucietym pilocie to DOLNE ograniczenie
res["pilot_summary"]={"compl_tok":ct,"dt":dts,"ucietych":ucieta,"max_tokens":MT}
print("\nPILOT: tokenow %s, czasy %s, ucietych %d -> max_tokens=%d"%(ct,dts,ucieta,MT),flush=True)
print("PROJEKCJA%s: ramie ON ok. %.0f min (%d zapytan), ramie OFF ok. %.0f min, "
      "razem ok. %.0f min\n"%(" (DOLNE ograniczenie, pilot dobil limit)" if ucieta else "",
      proj/60,n_on,n_on*8/60,proj/60+n_on*8/60),flush=True)
if os.environ.get("F6_STOP_AFTER_PILOT"):
    json.dump(res,open(G+"/f6-%s.json"%TAG,"w"),ensure_ascii=False,indent=1)
    sys.exit("F6_STOP_AFTER_PILOT ustawione - koncze po pilocie")

# --- macierz: oba ramiona, kolejnosc ramion naprzemienna miedzy powtorzeniami ---
for rep in range(REPS):
    arms=["off","on"] if rep%2==0 else ["on","off"]
    for i,typ,q,e in ITEMS:
        for arm in arms:
            think=(arm=="on")
            r=ask(ctx+"\n\n"+q,MT if think else 64,think,seed=1000*rep+i)
            got,ok,bare=grade(typ,r["content"],e)
            trunc=(r["finish"]=="length") or not (r["content"] or "").strip()
            res["runs"].append({"len":L,"rep":rep,"i":i,"typ":typ,"arm":arm,"arm_pos":arms.index(arm),
                                "exp":e,"got":got,"ok":ok,"bare":bare,"trunc":trunc,**r,
                                "content":r["content"][:200]})
            print("r%d #%02d %s %-3s exp=%s got=%s %s%s (%.1f s, %s tok, reas %d zn.)"%(
                rep,i,typ,arm,e,got,"OK" if ok else "ZLE",
                " UCIETA" if trunc else "",r["dt"],r["compl_tok"],r["reas_chars"]),flush=True)
        json.dump(res,open(G+"/f6-%s.json"%TAG,"w"),ensure_ascii=False,indent=1)
    print("-- powtorzenie %d gotowe, %.1f min od startu"%(rep,(time.time()-t0)/60),flush=True)

# --- podsumowanie: operacyjne (uciecie = blad) i warunkowe (tylko zakonczone) ---
def sel(**kw): return [r for r in res["runs"] if all(r[k]==v for k,v in kw.items())]
print("\n%-4s %-4s  %-14s  %-16s  %s"%("ramie","typ","operacyjnie","warunkowo","ucietych"))
for arm in ("off","on"):
    for typ in ("B","C"):
        s=sel(arm=arm,typ=typ); done=[r for r in s if not r["trunc"]]
        print("%-5s %-4s  %-14s  %-16s  %d/%d"%(arm,typ,
            "%d/%d"%(sum(1 for r in s if r["ok"] and not r["trunc"]),len(s)),
            "%d/%d"%(sum(1 for r in done if r["ok"]),len(done)) if done else "-",
            sum(1 for r in s if r["trunc"]),len(s)))
for arm in ("off","on"):
    s=sel(arm=arm); nb=[r for r in s if not r["bare"] and not r["trunc"]]
    print("%s: odpowiedzi NIE-golych (do recznego przejrzenia): %d/%d"%(arm,len(nb),len(s)))
    for r in nb[:8]: print("    #%02d %s got=%s content=%r"%(r["i"],r["typ"],r["got"],r["content"][:120]))
for arm in ("off","on"):
    s=sel(arm=arm)
    tk=[r["compl_tok"] or 0 for r in s]; d=[r["dt"] for r in s]
    print("%s: sredni czas %.1f s, srednio %.0f tokenow wyjscia, lacznie %.1f min"%(
        arm,sum(d)/len(d),sum(tk)/len(tk),sum(d)/60))
# rozrzut miedzy powtorzeniami - przy probkowaniu podloga nie jest zerowa
for arm in ("off","on"):
    dis=tot=0
    for i,typ,q,e in ITEMS:
        g={r["got"] for r in sel(arm=arm,i=i)}
        tot+=1; dis+=len(g)>1
    print("%s: pozycji z niejednakowa odpowiedzia miedzy powtorzeniami: %d/%d"%(arm,dis,tot))
