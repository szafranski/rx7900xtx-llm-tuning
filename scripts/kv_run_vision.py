# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen prompts f3-ctx-<len>.txt, results f3-*.json, images img/*.png. Prompt text
# and question wording are Polish, as in the rest of prompts/ here.
import json,sys,os,time,base64,hashlib,urllib.request
sys.path.insert(0,os.path.expanduser("~/gate"))
from kv_client import post
VAR=sys.argv[1]
CASES=[("t1.png","Odczytaj dokladnie kod widoczny na obrazie. Podaj sam kod.","KOD-7731-OMEGA"),
       ("t2.png","Na wykresie slupkowym podaj wartosc slupka oznaczonego MAR. Podaj sama liczbe.","47"),
       ("t3.png","Ile czerwonych kol jest na obrazie? Podaj sama liczbe.","13")]
res={"variant":VAR,"t_start":time.strftime("%H:%M:%S"),"cases":[]}
for fn,q,key in CASES:
    raw=open(os.path.expanduser("~/gate/img/"+fn),"rb").read()
    url="data:image/png;base64,"+base64.b64encode(raw).decode()
    b={"messages":[{"role":"user","content":[{"type":"text","text":q},
        {"type":"image_url","image_url":{"url":url}}]}],
       "temperature":0,"top_k":1,"top_p":1,"seed":42,"max_tokens":512,"cache_prompt":False}
    t0=time.time(); r=post("/v1/chat/completions",b); dt=time.time()-t0
    m=r["choices"][0]["message"]
    cont=m.get("content") or ""; reas=m.get("reasoning_content") or ""
    ok=key.lower() in (cont+" "+reas).lower()
    res["cases"].append({"img":fn,"key":key,"ok":ok,"dt":round(dt,2),
        "sha1":hashlib.sha1((reas+"\n@@\n"+cont).encode()).hexdigest()[:12],
        "content":cont[:200],"md5img":hashlib.md5(raw).hexdigest()[:8]})
    print(fn,key,"OK" if ok else "BLAD",round(dt,1),repr(cont[:80]),flush=True)
res["t_end"]=time.strftime("%H:%M:%S")
json.dump(res,open(os.path.expanduser("~/gate/f3-4-%s.json")%VAR,"w"),ensure_ascii=False,indent=1)
print("WROTE4",VAR,flush=True)
