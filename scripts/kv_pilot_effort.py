# Committed as run, from the measurement host. Working directory is ~/gate there.
# Two decisive checks before spending hours on an effort-level comparison:
# what the level actually does to the prompt, and what changing it costs the
# prompt cache. Comments are Polish, as elsewhere.
# Faza 7, pilot. Dwa pytania rozstrzygajace, zanim wydamy godziny:
#  A) czy reasoning_effort per zapytanie faktycznie zmienia wyrenderowany prompt
#     (a nie jest cicho ignorowany) - sprawdzam przez /apply-template, bez 120k;
#  B) czy zmiana poziomu unieważnia prefiks 120k, czy --cache-reuse 256 to
#     przesuwa. Szablon wstawia instrukcje na POCZATKU bloku systemowego, wiec
#     low i medium roznia sie pierwszymi ~30 tokenami promptu 120k.
#     Jesli cached_tokens spada do zera przy zmianie poziomu, ramion NIE wolno
#     przeplatac - kazde zapytanie placiloby pelny prefill.
import json,os,sys,time,urllib.request,urllib.error
G=os.path.expanduser("~/gate")
U="http://127.0.0.1:8098"

def post(path,obj,timeout=1800):
    r=urllib.request.Request(U+path,data=json.dumps(obj).encode(),
                             headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(r,timeout=timeout))

def body(prompt,mt,eff,seed=None):
    b={"messages":[{"role":"user","content":prompt}],"max_tokens":mt,"cache_prompt":True,
       "temperature":0.6,"top_p":0.95,"top_k":20,"min_p":0.05}
    if seed is not None: b["seed"]=seed
    if eff is not None: b["chat_template_kwargs"]={"reasoning_effort":eff}
    return b

out={"A":{},"B":[]}

# --- A: wyrenderowany prompt, krotka wiadomosc ---
print("=== A: /apply-template ===",flush=True)
for eff in [None,"low","medium","xhigh"]:
    try:
        r=post("/apply-template",body("czesc",8,eff))
        p=r.get("prompt","")
        out["A"][str(eff)]={"len":len(p),"head":p[:260]}
        print("effort=%-7s len=%5d head=%r"%(eff,len(p),p[:170]),flush=True)
    except urllib.error.HTTPError as e:
        print("effort=%-7s HTTP %s (endpoint niedostepny?)"%(eff,e.code),flush=True)
        out["A"][str(eff)]={"err":e.code}
    except Exception as e:
        print("effort=%-7s blad %s"%(eff,e),flush=True); out["A"][str(eff)]={"err":str(e)}

# --- B: czy zmiana poziomu zbija cache na 120k ---
ctx=open(G+"/f4-ctx-120k.txt").read()
meta=json.load(open(G+"/f4-items.json"))
C=[(i,t,q,e) for i,(t,q,e) in enumerate(meta["items"]) if t=="C"][0]
i,typ,q,exp=C
print("\n=== B: prefiks 120k, pozycja #%02d typ C ==="%i,flush=True)
print("kolejnosc: medium, low, medium, low - ta sama tresc pytania",flush=True)
for k,eff in enumerate(["medium","low","medium","low"]):
    t0=time.time(); r=post("/v1/chat/completions",body(ctx+"\n\n"+q,8320,eff,seed=7)); dt=time.time()-t0
    ch=r["choices"][0]; m=ch["message"]; u=r.get("usage") or {}
    tm=r.get("timings") or {}
    rec={"k":k,"eff":eff,"dt":round(dt,2),
         "prompt_tok":u.get("prompt_tokens"),
         "cached":(u.get("prompt_tokens_details") or {}).get("cached_tokens"),
         "compl_tok":u.get("completion_tokens"),
         "reas_chars":len(m.get("reasoning_content") or ""),
         "content":(m.get("content") or "")[:40],
         "finish":ch.get("finish_reason"),
         "prompt_ms":tm.get("prompt_ms"),"predicted_ms":tm.get("predicted_ms"),
         "prompt_n":tm.get("prompt_n"),"predicted_n":tm.get("predicted_n"),
         "draft_n":tm.get("draft_n"),"draft_n_accepted":tm.get("draft_n_accepted")}
    out["B"].append(rec)
    print("%d) %-6s %6.1f s | prefill %s tok / %s ms | cached %s | gen %s tok / %s ms | rozum %d zn | %r %s"%(
        k,eff,rec["dt"],rec["prompt_n"],
        None if rec["prompt_ms"] is None else round(rec["prompt_ms"]),
        rec["cached"],rec["predicted_n"],
        None if rec["predicted_ms"] is None else round(rec["predicted_ms"]),
        rec["reas_chars"],rec["content"],rec["finish"]),flush=True)
    json.dump(out,open(G+"/f7-pilot.json","w"),ensure_ascii=False,indent=1)

print("\noczekiwane exp=%s"%exp,flush=True)
b=out["B"]
if len(b)>=2 and b[0]["prompt_n"] is not None:
    print("WNIOSEK: prefill przy zmianie poziomu = %s tok (pierwszy byl %s). %s"%(
        b[1]["prompt_n"],b[0]["prompt_n"],
        "cache-reuse to przesuwa -> mozna przeplatac" if (b[1]["prompt_n"] or 0) < 2000
        else "prefiks uniewazniony -> ramiona BLOKOWO, nie przeplatane"),flush=True)
