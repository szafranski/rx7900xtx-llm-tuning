# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen prompts f3-ctx-<len>.txt, results f3-*.json, images img/*.png. Prompt text
# and question wording are Polish, as in the rest of prompts/ here.
import json,urllib.request,sys,os,hashlib,time
U="http://127.0.0.1:8098"
def post(path,obj,timeout=1200):
    r=urllib.request.Request(U+path,data=json.dumps(obj).encode(),headers={"Content-Type":"application/json"})
    return json.load(urllib.request.urlopen(r,timeout=timeout))
def ntok(t):
    return len(post("/tokenize",{"content":t})["tokens"])
FILL=("Poziomy pamieci podrecznej procesora roznia sie opoznieniem i pojemnoscia, "
 "a polityka zapisu decyduje o tym, kiedy dane wracaja do pamieci glownej. "
 "Spojnosc miedzy rdzeniami utrzymuje protokol unieważniania linii. ")
def para(i):
    return "Akapit %d. %s%s"%(i,FILL,("Lokalnosc odwolan czasowa i przestrzenna wplywa na trafienia." if i%3==0 else "Prefetcher zgaduje kolejne adresy na podstawie kroku dostepu."))
def build(target,needles=()):
    # needles: list of (rel_pos_float, key_string)
    paras=[para(i) for i in range(1,4000)]
    # wstaw igly na pozycjach wzglednych
    for rel,key in needles:
        idx=max(1,min(len(paras)-1,int(rel*len(paras))))
        paras[idx]=paras[idx]+" KLUCZ: %s."%key
    txt="\n\n".join(paras)
    # binarne obcinanie po akapitach do docelowej liczby tokenow
    lo,hi=1,len(paras)
    while lo<hi:
        mid=(lo+hi+1)//2
        if ntok("\n\n".join(paras[:mid]))<=target: lo=mid
        else: hi=mid-1
    return "\n\n".join(paras[:lo])
def build_n(target,needles=()):
    # najpierw ustal ile akapitow miesci sie w target, potem wstaw igly wzgledem TEJ liczby
    paras=[para(i) for i in range(1,4000)]
    lo,hi=1,len(paras)
    while lo<hi:
        mid=(lo+hi+1)//2
        if ntok("\n\n".join(paras[:mid]))<=target: lo=mid
        else: hi=mid-1
    sel=paras[:lo]
    for rel,key in needles:
        idx=max(0,min(lo-1,int(rel*lo)))
        sel[idx]=sel[idx]+" KLUCZ: %s."%key
    t="\n\n".join(sel)
    return t,lo,ntok(t)
QCTRL="\n\nPytanie: podsumuj jednym zdaniem, czym rozni sie polityka write-back od write-through."
def one(prompt,cache,mt=1,top=20):
    b={"messages":[{"role":"user","content":prompt}],"temperature":0,"top_k":1,"top_p":1,
       "seed":42,"max_tokens":mt,"cache_prompt":cache}
    if top: b["logprobs"]=True; b["top_logprobs"]=top
    t0=time.time(); r=post("/v1/chat/completions",b); dt=time.time()-t0
    ch=r["choices"][0]
    lp=ch.get("logprobs") or {}
    cont=(ch["message"].get("content") or "")
    reas=(ch["message"].get("reasoning_content") or "")
    out={"dt":round(dt,2),"usage":r.get("usage"),
         "sha1":hashlib.sha1((reas+"\n@@\n"+cont).encode()).hexdigest()[:12],
         "content":cont[:400],"reasoning":reas[:400]}
    cl=lp.get("content") or []
    if cl:
        c0=cl[0]
        out["tok"]=c0.get("token"); out["logprob"]=c0.get("logprob")
        out["top"]=[(x.get("token"),x.get("logprob")) for x in (c0.get("top_logprobs") or [])]
    return out
