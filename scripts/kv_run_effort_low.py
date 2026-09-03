# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen context f4-ctx-120k.txt and f4-items.json from the phase-4 generator,
# results f7-<tag>.json. Comments and question wording are Polish, as elsewhere.
# Faza 7: ramie reasoning_effort=low na starej bramce 120k.
#   python3 ~/gate/f7-run.py <tag> [reps]
# Rola: TANI TEST REGRESJI wobec ramienia "on" (=medium) z fazy 6, nie dowod
# rownowaznosci. Medium ma tam 64/64, czyli sufit bramki - low moze tylko
# zremisowac albo przegrac, a remis nie znaczy "rownie dobre", tylko "ta bramka
# nie rozroznia".
#
# Dlaczego JEDNO ramie i blokowo, a nie przeplatanie:
# pilot f7 pokazal, ze szablon wstawia instrukcje poziomu na POCZATKU bloku
# systemowego, wiec prompt 120k dla low rozni sie od medium od tokenu zero.
# --cache-reuse 256 tego nie przesuwa: przy zmianie poziomu cached=0 i pelny
# prefill 119993 tok / 392 s. Przeplecione ramiona = 6.5 min prefillu na KAZDE
# zapytanie. Blokowo placimy prefill raz.
#
# Kolejnosc pozycji i ziarna (1000*rep+i) sa IDENTYCZNE jak w fazie 6, zeby
# porownanie bylo sparowane. Mapa ngram-map-k przezywa miedzy zapytaniami
# (common_ngram_map_begin nie czysci keys/key_map), wiec kolejnosc nie jest
# neutralna i nie wolno jej zmienic.
#
# Czas mierzymy Z ROZBICIEM. Zegar sciany jest zdominowany przez prefill i
# pokazalby "low nie zmienia nic" (436 s vs 400 s w pilocie), gdy generacja
# rozni sie 9x. Liczy sie predicted_ms/predicted_n.
import json,os,re,sys,time,hashlib,urllib.request
G=os.path.expanduser("~/gate")
U="http://127.0.0.1:8098"
TAG=sys.argv[1]
REPS=int(sys.argv[2]) if len(sys.argv)>2 else 4
L="120k"
EFF="low"
MT=8320                # tak jak w fazie 6: budzet 8192 + miejsce na odpowiedz
                       # budzet zostaje IDENTYCZNY jak w medium - bezpiecznik,
                       # nie druga zmienna eksperymentalna (max byl 3532)

def post(path,obj,timeout=1800):
    r=urllib.request.Request(U+path,data=json.dumps(obj).encode(),
                             headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(r,timeout=timeout))

def ask(prompt,mt,seed=None):
    b={"messages":[{"role":"user","content":prompt}],"max_tokens":mt,"cache_prompt":True,
       "temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.05,
       "chat_template_kwargs":{"reasoning_effort":EFF}}
    if seed is not None: b["seed"]=seed
    t0=time.time(); r=post("/v1/chat/completions",b); dt=time.time()-t0
    ch=r["choices"][0]; m=ch["message"]; u=r.get("usage") or {}; tm=r.get("timings") or {}
    return {"dt":round(dt,2),"content":(m.get("content") or ""),
            "reas_chars":len(m.get("reasoning_content") or ""),
            "finish":ch.get("finish_reason"),
            "compl_tok":u.get("completion_tokens"),
            "cached":(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
            "prompt_n":tm.get("prompt_n"),"prompt_ms":tm.get("prompt_ms"),
            "predicted_n":tm.get("predicted_n"),"predicted_ms":tm.get("predicted_ms"),
            "draft_n":tm.get("draft_n"),"draft_acc":tm.get("draft_n_accepted")}

meta=json.load(open(G+"/f4-items.json"))
ITEMS=[(i,t,q,e) for i,(t,q,e) in enumerate(meta["items"]) if t in ("B","C")]
PAT={"B":r"(WEZEL-\d{3})","C":r"\b(\d{1,3})\b"}
def grade(typ,txt,exp):
    t=(txt or "").upper().strip()
    m=re.search(PAT[typ],t)
    got=m.group(1) if m else None
    bare=bool(got) and re.fullmatch(r"[^A-Z0-9]*"+re.escape(got)+r"[^A-Z0-9]*",t) is not None
    return got,(got==exp.upper()),bare

ctx=open(G+"/f4-ctx-%s.txt"%L).read()
sha=hashlib.sha256(ctx.encode()).hexdigest()
res={"tag":TAG,"reps":REPS,"len":L,"effort":EFF,"ctx_sha256":sha,"n_items":len(ITEMS),
     "max_tokens":MT,"sampling":{"temp":0.6,"top_p":0.95,"top_k":20,"min_p":0.05},
     "server":"f6-srv.sh (--reasoning-effort medium), poziom nadpisany per zapytanie na low",
     "porownanie":"ramie 'on' z f6-m1.json (= medium), te same pozycje, ziarna i kolejnosc",
     "runs":[]}
print("dlugosc %s, sha256 %s, pozycji %d, powtorzen %d, effort=%s"%(
    L,sha[:16],len(ITEMS),REPS,EFF),flush=True)

t0=time.time()
w=ask(ctx+"\n\nPytanie: odpowiedz slowem OK.",8)
print("prefill ramienia: %.1f s, prompt_n=%s, cached=%s\n"%(w["dt"],w["prompt_n"],w["cached"]),flush=True)
res["warm"]=w

for rep in range(REPS):
    for i,typ,q,e in ITEMS:
        r=ask(ctx+"\n\n"+q,MT,seed=1000*rep+i)
        got,ok,bare=grade(typ,r["content"],e)
        trunc=(r["finish"]=="length") or not (r["content"] or "").strip()
        res["runs"].append({"len":L,"rep":rep,"i":i,"typ":typ,"arm":"low","exp":e,
                            "got":got,"ok":ok,"bare":bare,"trunc":trunc,**r,
                            "content":r["content"][:200]})
        print("r%d #%02d %s exp=%s got=%s %s%s (gen %s tok / %.1f s, reas %d zn., cached %s)"%(
            rep,i,typ,e,got,"OK" if ok else "ZLE"," UCIETA" if trunc else "",
            r["predicted_n"],(r["predicted_ms"] or 0)/1000.0,r["reas_chars"],r["cached"]),flush=True)
        json.dump(res,open(G+"/f7-%s.json"%TAG,"w"),ensure_ascii=False,indent=1)
    print("-- powtorzenie %d gotowe, %.1f min od startu"%(rep,(time.time()-t0)/60),flush=True)

def sel(**kw): return [r for r in res["runs"] if all(r[k]==v for k,v in kw.items())]
def med(v): 
    v=sorted(v); n=len(v); return None if not n else (v[n//2] if n%2 else (v[n//2-1]+v[n//2])/2)
print("\n%-4s  %-14s  %-16s  %s"%("typ","operacyjnie","warunkowo","ucietych"))
for typ in ("B","C"):
    s=sel(typ=typ); done=[r for r in s if not r["trunc"]]
    print("%-5s %-14s  %-16s  %d/%d"%(typ,
        "%d/%d"%(sum(1 for r in s if r["ok"] and not r["trunc"]),len(s)),
        "%d/%d"%(sum(1 for r in done if r["ok"]),len(done)) if done else "-",
        sum(1 for r in s if r["trunc"]),len(s)))
nb=[r for r in res["runs"] if not r["bare"] and not r["trunc"]]
print("odpowiedzi NIE-golych (do recznego przejrzenia): %d/%d"%(nb.__len__(),len(res["runs"])))
for r in nb[:8]: print("    #%02d %s got=%s content=%r"%(r["i"],r["typ"],r["got"],r["content"][:120]))
for typ in ("B","C"):
    s=sel(typ=typ)
    print("%s: mediana generacji %.1f s / %s tok; mediana zegara %.1f s; rozumowanie mediana %d zn., max %d zn."%(
        typ,med([(r["predicted_ms"] or 0)/1000.0 for r in s]),med([r["predicted_n"] or 0 for r in s]),
        med([r["dt"] for r in s]),med([r["reas_chars"] for r in s]),max(r["reas_chars"] for r in s)))
dis=tot=0
for i,typ,q,e in ITEMS:
    g={r["got"] for r in sel(i=i)}; tot+=1; dis+=len(g)>1
print("pozycji z niejednakowa odpowiedzia miedzy powtorzeniami: %d/%d"%(dis,tot))
print("prefill placony powtornie (cached==0) w %d zapytaniach na %d"%(
    sum(1 for r in res["runs"] if (r["cached"] or 0)==0),len(res["runs"])))
print("\nlacznie %.1f min"%((time.time()-t0)/60))
