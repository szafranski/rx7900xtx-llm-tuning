# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen prompts f3-ctx-<len>.txt, results f3-*.json, images img/*.png. Prompt text
# and question wording are Polish, as in the rest of prompts/ here.
import json,sys,os,time,re
sys.path.insert(0,os.path.expanduser("~/gate"))
from kv_client import *
VAR=sys.argv[1]
LENS=["8k","32k","64k","120k"]
POS=[0.10,0.30,0.50,0.70,0.90]
WORDS=["ALFA","BETA","GAMMA","DELTA","EPSILON","ZETA","ETA","THETA"]  # 8 kluczy na komorke
def keys_for(L):
    ks=[]
    for pi,p in enumerate(POS):
        for wi,w in enumerate(WORDS):
            code="KOD-%d%d%02d-%s"%(pi+1,wi+1,(pi*8+wi)%100,w+str(pi+1))
            # rozsiane wokol pozycji p, w oknie +-2%
            rel=min(0.985,max(0.005,p+(wi-3.5)*0.005))
            ks.append((rel,code,pi,wi))
    return ks
res={"variant":VAR,"t_start":time.strftime("%H:%M:%S"),"cells":[]}
for L in LENS:
    base=open(os.path.expanduser("~/gate/f3-ctx-%s.txt")%L).read()
    paras=base.split("\n\n"); n=len(paras)
    ks=keys_for(L)
    for rel,code,pi,wi in ks:
        idx=max(0,min(n-1,int(rel*n)))
        paras[idx]=paras[idx]+" KLUCZ: %s."%code
    ctx="\n\n".join(paras)
    first=True
    for rel,code,pi,wi in ks:
        w=code.rsplit("-",1)[1]
        q="\n\nPytanie: w tekscie powyzej wystepuje dokladnie jeden klucz konczacy sie na %s. Podaj ten klucz w calosci i nic wiecej."%w
        r=one(ctx+q,True,mt=64,top=0,nothink=True)
        ans=(r["reasoning"]+" "+r["content"])
        ok=code in ans
        res["cells"].append({"len":L,"pos":POS[pi],"key":code,"ok":ok,"dt":r["dt"],
                             "ans":(r["content"] or r["reasoning"])[:120]})
        if first: print(L,"prefill+1",r["dt"],flush=True); first=False
    acc=sum(1 for c in res["cells"] if c["len"]==L and c["ok"])/float(len(ks))
    print("len",L,"acc",round(acc,3),flush=True)
res["t_end"]=time.strftime("%H:%M:%S")
json.dump(res,open(os.path.expanduser("~/gate/f3-3-%s.json")%VAR,"w"),ensure_ascii=False,indent=1)
print("WROTE3",VAR,flush=True)
