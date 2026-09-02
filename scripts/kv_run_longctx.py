# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen contexts f4-ctx-<len>.txt and f4-items.json, results f4-<tag>.json.
# Comments and question wording are Polish, as in the rest of prompts/ here.
# Faza 4: seria trudna. Uruchamiac na jednym wariancie KV naraz.
#   python3 ~/gate/f4-run.py <tag> [reps] [lengths]
# Kazda dlugosc: jeden prefill prefiksu, potem pytania na wspolnym cache'u.
# reps>1 daje podloge: niezgodnosc odpowiedzi tego samego wariantu na tym samym pytaniu.
import json,os,re,sys,time
sys.path.insert(0,os.path.expanduser("~/gate"))
from kv_client import one

TAG=sys.argv[1]
REPS=int(sys.argv[2]) if len(sys.argv)>2 else 2
LENS=(sys.argv[3].split(",") if len(sys.argv)>3 else ["8k","32k","64k","120k"])
G=os.path.expanduser("~/gate")
meta=json.load(open(G+"/f4-items.json"))
ITEMS=meta["items"]

PAT={"A":r"\b(\d{2})\b","B":r"(WEZEL-\d{3})","C":r"\b(\d{1,3})\b"}
def grade(typ,txt,exp):
    m=re.search(PAT[typ],(txt or "").upper().replace("Ę","E").replace("Ł","L"))
    got=m.group(1) if m else None
    return got,(got==exp.upper())

import hashlib
sha={L:hashlib.sha256(open(G+"/f4-ctx-%s.txt"%L,"rb").read()).hexdigest() for L in LENS}
res={"tag":TAG,"reps":REPS,"order":LENS,"ctx_sha256":sha,
     "meta":{k:v for k,v in meta.items() if k!="items"},"runs":[]}
print("sha256 kontekstow:",json.dumps(sha,indent=1),flush=True)
for L in LENS:
    ctx=open(G+"/f4-ctx-%s.txt"%L).read()
    t0=time.time()
    warm=one(ctx+"\n\nPytanie: odpowiedz slowem OK.",True,mt=8,top=0,nothink=True)
    print(L,"prefill",warm["dt"],"s",warm["usage"],flush=True)
    for rep in range(REPS):
        for i,(typ,q,exp) in enumerate(ITEMS):
            r=one(ctx+"\n\n"+q,True,mt=64,top=0,nothink=True)
            got,ok=grade(typ,r["content"],exp)
            res["runs"].append({"len":L,"rep":rep,"i":i,"typ":typ,"exp":exp,"got":got,
                                "ok":ok,"dt":r["dt"],"raw":r["content"][:120],
                                "cached":(r["usage"] or {}).get("prompt_tokens_details",{}).get("cached_tokens")})
            print("%s r%d #%02d %s exp=%s got=%s %s"%(L,rep,i,typ,exp,got,"OK" if ok else "ZLE"),flush=True)
    print(L,"gotowe w",round(time.time()-t0,1),"s",flush=True)
    json.dump(res,open(G+"/f4-%s.json"%TAG,"w"),ensure_ascii=False,indent=1)

# podsumowanie: trafnosc na dlugosc/typ i niezgodnosc miedzy powtorzeniami
def acc(f):
    s=[r for r in res["runs"] if f(r)]
    return "%d/%d"%(sum(1 for r in s if r["ok"]),len(s)) if s else "-"
print("\ntrafnosc")
print("dlugosc  "+"  ".join("%-8s"%t for t in "ABC")+"  razem")
for L in LENS:
    print("%-8s "%L+"  ".join("%-8s"%acc(lambda r,L=L,t=t: r["len"]==L and r["typ"]==t) for t in "ABC")+"  "+acc(lambda r,L=L: r["len"]==L))
if REPS>1:
    dis=0; tot=0
    for L in LENS:
        for i in range(len(ITEMS)):
            g=[r["got"] for r in res["runs"] if r["len"]==L and r["i"]==i]
            if len(g)>1:
                tot+=1; dis+= (len(set(g))>1)
    print("\nniezgodnosc miedzy powtorzeniami: %d/%d pozycji"%(dis,tot))
