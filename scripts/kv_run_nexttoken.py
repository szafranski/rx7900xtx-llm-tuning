# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen prompts f3-ctx-<len>.txt, results f3-*.json, images img/*.png. Prompt text
# and question wording are Polish, as in the rest of prompts/ here.
import json,sys,os,time
sys.path.insert(0,os.path.expanduser("~/gate"))
from kv_client import *
VAR=sys.argv[1]
res={"variant":VAR,"t_start":time.strftime("%H:%M:%S")}
LENS=[("8k",8000),("32k",32000),("64k",64000),("120k",120000)]
REPS={"8k":2,"32k":1,"64k":1,"120k":1}
ctxs={}
for name,tgt in LENS:
    f=os.path.expanduser("~/gate/f3-ctx-%s.txt")%name
    if os.path.exists(f):
        t=open(f).read()
    else:
        t,_,_=build_n(tgt); open(f,"w").write(t)
    ctxs[name]=t
    res.setdefault("ctx_info",{})[name]={"chars":len(t)}
    print("ctx",name,len(t),flush=True)
res["test0"]=[one(ctxs["8k"]+QCTRL,True) for _ in range(3)]
print("test0 done",flush=True)
t1={}
for name,_ in LENS:
    t1[name]=[one(ctxs[name]+QCTRL,False) for _ in range(REPS[name])]
    print("test1",name,"done",t1[name][0].get("tok"),t1[name][0].get("logprob"),flush=True)
res["test1"]=t1
P=ctxs["64k"]+QCTRL
half=ctxs["64k"][:len(ctxs["64k"])//2]
a=one(P,False)
_=one(half+QCTRL,True,mt=1,top=0)
b=one(P,True)
res["test2"]={"recompute":a,"reuse":b}
print("test2 done",flush=True)
res["t_end"]=time.strftime("%H:%M:%S")
json.dump(res,open(os.path.expanduser("~/gate/f3-012-%s.json")%VAR,"w"),ensure_ascii=False,indent=1)
print("WROTE",VAR,flush=True)
