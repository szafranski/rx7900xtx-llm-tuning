# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen context f4-ctx-120k.txt and f4-items.json from the phase-4 generator,
# results f8-<tag>.json. Comments and question wording are Polish, as elsewhere.
# Faza 8 (test D): co robi model, gdy budzet rozumowania konczy sie w polowie mysli.
#   python3 ~/gate/f8-run.py <tag>
#
# Dlaczego to pytanie ma sens: we wszystkich poprzednich fazach budzet 8192 nie
# byl nigdy wykorzystany - max zaobserwowane 3532 tokeny = 43%. Trybu awarii
# wiec nigdy nie widzielismy, a llama.cpp ma na niego osobny mechanizm:
# --reasoning-budget-message wstrzykuje tekst PRZED tagiem konca mysli, czyli
# serwer domyka blok rozumowania sam. To nie musi byc ucieta odpowiedz - moze
# byc odpowiedz udzielona przedwczesnie. Test rozstrzyga, ktore z dwoch.
#
# Material i pozycje IDENTYCZNE jak w fazie 6/7 (f4-items.json, ctx 120k), zeby
# porownanie bylo sparowane: te same pytania przy budzecie 8192 daly 32/32 (B) i
# 32/32 (C) na poziomie medium.
#
# max_tokens 1024 przy budzecie 512: margines musi byc DUZY, inaczej nie da sie
# odroznic "budzet sie skonczyl" od "skonczyl sie max_tokens". Jesli finish
# bedzie 'length', to znaczy ze zabraklo max_tokens i pomiar jest nieważny.
import json,os,re,sys,time,hashlib,urllib.request
G=os.path.expanduser("~/gate")
U="http://127.0.0.1:8098"
TAG=sys.argv[1]
L="120k"
MT=1024

def post(path,obj,timeout=1800):
    r=urllib.request.Request(U+path,data=json.dumps(obj).encode(),
                             headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(r,timeout=timeout))

def ask(msgs,mt,seed=None):
    b={"messages":msgs,"max_tokens":mt,"cache_prompt":True,
       "temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.05}
    if seed is not None: b["seed"]=seed
    t0=time.time(); r=post("/v1/chat/completions",b); dt=time.time()-t0
    ch=r["choices"][0]; m=ch["message"]; u=r.get("usage") or {}; tm=r.get("timings") or {}
    reas=m.get("reasoning_content") or ""
    return {"dt":round(dt,2),"content":(m.get("content") or ""),
            "reas":reas,"reas_chars":len(reas),
            "finish":ch.get("finish_reason"),
            "compl_tok":u.get("completion_tokens"),
            "cached":(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
            "prompt_n":tm.get("prompt_n"),"prompt_ms":tm.get("prompt_ms"),
            "predicted_n":tm.get("predicted_n"),"predicted_ms":tm.get("predicted_ms")}

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
res={"tag":TAG,"len":L,"ctx_sha256":sha,"budget":512,"max_tokens":MT,"effort":"medium",
     "n_items":len(ITEMS),"sampling":{"temp":0.6,"top_p":0.95,"top_k":20,"min_p":0.05},
     "porownanie":"te same pozycje i ziarna przy budzecie 8192: f6-m1.json (32/32 B, 32/32 C)",
     "runs":[]}
print("budzet 512, max_tokens %d, pozycji %d, sha %s"%(MT,len(ITEMS),sha[:16]),flush=True)

t0=time.time()
w=ask([{"role":"user","content":ctx+"\n\nPytanie: odpowiedz slowem OK."}],8)
print("prefill: %.1f s, prompt_n=%s, cached=%s\n"%(w["dt"],w["prompt_n"],w["cached"]),flush=True)
res["warm"]={k:v for k,v in w.items() if k!="reas"}

for i,typ,q,e in ITEMS:
    r=ask([{"role":"user","content":ctx+"\n\n"+q}],MT,seed=i)   # ziarno jak rep0 w f6
    got,ok,bare=grade(typ,r["content"],e)
    puste=not (r["content"] or "").strip()
    res["runs"].append({"i":i,"typ":typ,"exp":e,"got":got,"ok":ok,"bare":bare,
                        "pusta_odpowiedz":puste,
                        **{k:v for k,v in r.items() if k!="reas"},
                        "reas_ogon":r["reas"][-200:],"content":r["content"][:300]})
    print("#%02d %s exp=%s got=%s %s finish=%s gen=%s tok reas=%d zn.%s"%(
        i,typ,e,got,"OK" if ok else "ZLE",r["finish"],r["predicted_n"],r["reas_chars"],
        " PUSTA-ODPOWIEDZ" if puste else ""),flush=True)
    json.dump(res,open(G+"/f8-%s.json"%TAG,"w"),ensure_ascii=False,indent=1)

# Czy po wyczerpaniu budzetu rozmowa daje sie kontynuowac: dokladamy odpowiedz
# modelu i drugie pytanie. Prefiks zostaje ten sam, wiec to tanie.
i0,t0typ,q0,e0=ITEMS[-1]
prev=res["runs"][-1]
i1,t1typ,q1,e1=ITEMS[0]
f=ask([{"role":"user","content":ctx+"\n\n"+q0},
       {"role":"assistant","content":prev["content"]},
       {"role":"user","content":q1}],MT,seed=777)
got,ok,bare=grade(t1typ,f["content"],e1)
res["druga_tura"]={"pytanie_i":i1,"typ":t1typ,"exp":e1,"got":got,"ok":ok,
                   **{k:v for k,v in f.items() if k!="reas"},
                   "reas_ogon":f["reas"][-200:],"content":f["content"][:300]}
print("\ndruga tura po wyczerpaniu budzetu: finish=%s got=%s %s, gen=%s tok, reas=%d zn."%(
    f["finish"],got,"OK" if ok else "ZLE",f["predicted_n"],f["reas_chars"]),flush=True)
json.dump(res,open(G+"/f8-%s.json"%TAG,"w"),ensure_ascii=False,indent=1)

def sel(typ): return [r for r in res["runs"] if r["typ"]==typ]
print("\n%-4s %-10s %-12s %-12s %s"%("typ","poprawne","pustych","finish=length","mediana reas zn."))
for typ in ("B","C"):
    s=sel(typ)
    med=sorted(r["reas_chars"] for r in s); m=med[len(med)//2] if med else 0
    print("%-5s %-10s %-12s %-12s %d"%(typ,
        "%d/%d"%(sum(1 for r in s if r["ok"]),len(s)),
        "%d/%d"%(sum(1 for r in s if r["pusta_odpowiedz"]),len(s)),
        "%d/%d"%(sum(1 for r in s if r["finish"]=="length"),len(s)),m))
print("\nogony rozumowania (czy blok domknieto sam, czy urwano w polowie zdania):")
for r in res["runs"][:4]+res["runs"][-4:]:
    print("  #%02d %s ...%r"%(r["i"],r["typ"],r["reas_ogon"][-90:]))
print("\nlacznie %.1f min"%((time.time()-t0)/60))
