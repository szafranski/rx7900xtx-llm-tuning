# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen prompts f3-ctx-<len>.txt, results f3-*.json, images img/*.png. Prompt text
# and question wording are Polish, as in the rest of prompts/ here.
import json,sys,os,time
sys.path.insert(0,os.path.expanduser("~/gate"))
from kv_client import *
VAR=sys.argv[1]; L=sys.argv[2] if len(sys.argv)>2 else "64k"
ctx=open(os.path.expanduser("~/gate/f3-ctx-%s.txt")%L).read()
out=[]
for i in range(4):
    r=one(ctx+QCTRL,False)
    out.append(r); print(i,r["tok"],r["logprob"],r["dt"],flush=True)
json.dump({"variant":VAR,"len":L,"runs":out},open(os.path.expanduser("~/gate/f3-noise-%s-%s.json")%(VAR,L),"w"),ensure_ascii=False,indent=1)
print("WROTEN",VAR,flush=True)
