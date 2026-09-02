# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen contexts f4-ctx-<len>.txt and f4-items.json from the phase-4 generator,
# results f5-<tag>.json. Comments and question wording are Polish, as elsewhere.
# Faza 5: rozdzielenie WYSZUKANIA od LICZENIA w zadaniach typu C.
# Ten sam material co faza 4, te same partycje, dwa pytania na pozycje:
#   N - "ile kluczy nalezy do partycji P" (dokladnie jak w fazie 4)
#   L - "wypisz wszystkie klucze partycji P"
# Prawda pobierana z samego pliku kontekstu, nie z metadanych generatora.
#   python3 ~/gate/f5-run.py <tag> [reps] [lengths]
import json,os,re,sys,time,hashlib
sys.path.insert(0,os.path.expanduser("~/gate"))
from kv_client import one

TAG=sys.argv[1]
REPS=int(sys.argv[2]) if len(sys.argv)>2 else 2
LENS=(sys.argv[3].split(",") if len(sys.argv)>3 else ["64k","120k"])
G=os.path.expanduser("~/gate")
meta=json.load(open(G+"/f4-items.json"))

KEY=r"[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}"
FACT=re.compile(r"klucz (%s) nalezy do partycji (\d+)\."%KEY)

# pozycje typu C z fazy 4 + numer partycji z tresci pytania
CITEMS=[]
for i,(typ,q,exp) in enumerate(meta["items"]):
    if typ!="C": continue
    p=int(re.search(r"partycji (\d+)\?",q).group(1))
    CITEMS.append({"i":i,"part":p,"qn":q,"exp":int(exp)})

def truth(L):
    t=open(G+"/f4-ctx-%s.txt"%L).read()
    d={}
    for k,p in FACT.findall(t): d.setdefault(int(p),set()).add(k)
    return d

# prawda musi byc identyczna na kazdej dlugosci - fakty sa te same, rozny tylko wypelniacz
base=None
for L in LENS:
    d=truth(L)
    cur={c["part"]:sorted(d.get(c["part"],())) for c in CITEMS}
    if base is None: base=cur
    elif cur!=base: sys.exit("RÓZNE zbiory prawdy miedzy dlugosciami - przerywam")
for c in CITEMS:
    got=len(base[c["part"]])
    if got!=c["exp"]: sys.exit("partycja %d: w kontekscie %d kluczy, generator mowi %d"%(c["part"],got,c["exp"]))
print("prawda zgodna z generatorem, %d pozycji, licznosci %s"%(len(CITEMS),[c["exp"] for c in CITEMS]),flush=True)

QL="Wypisz wszystkie klucze nalezace do partycji %d. Odpowiedz wylacznie kluczami oddzielonymi przecinkami, bez zadnego innego tekstu."
sha={L:hashlib.sha256(open(G+"/f4-ctx-%s.txt"%L,"rb").read()).hexdigest() for L in LENS}
res={"tag":TAG,"reps":REPS,"order":LENS,"ctx_sha256":sha,
     "truth":{str(k):v for k,v in base.items()},"runs":[]}
print("sha256:",json.dumps(sha,indent=1),flush=True)

for L in LENS:
    ctx=open(G+"/f4-ctx-%s.txt"%L).read()
    t0=time.time()
    warm=one(ctx+"\n\nPytanie: odpowiedz slowem OK.",True,mt=8,top=0,nothink=True)
    print(L,"prefill",warm["dt"],"s",warm["usage"],flush=True)
    for rep in range(REPS):
        for c in CITEMS:
            tset=set(base[c["part"]])
            # N pierwsze - dokladnie w warunkach fazy 4, nic go nie poprzedza
            rn=one(ctx+"\n\n"+c["qn"],True,mt=64,top=0,nothink=True)
            m=re.search(r"\b(\d{1,3})\b",rn["content"] or "")
            n_got=int(m.group(1)) if m else None
            # L
            rl=one(ctx+"\n\n"+QL%c["part"],True,mt=192,top=0,nothink=True)
            found=set(re.findall(KEY,(rl["content"] or "").upper()))
            hit=found&tset; extra=found-tset
            res["runs"].append({"len":L,"rep":rep,"i":c["i"],"part":c["part"],"n_true":c["exp"],
                "n_got":n_got,"n_ok":n_got==c["exp"],
                "l_found":sorted(found),"l_hit":len(hit),"l_extra":sorted(extra),
                "l_count":len(found),"l_ok":found==tset,
                "dt_n":rn["dt"],"dt_l":rl["dt"],"raw_l":(rl["content"] or "")[:300]})
            print("%s r%d p%02d n=%s/%d  lista: trafione %d/%d, zmyslone %d %s"%(
                L,rep,c["part"],n_got,c["exp"],len(hit),len(tset),len(extra),
                "OK" if found==tset else ""),flush=True)
    print(L,"gotowe w",round(time.time()-t0,1),"s",flush=True)
    json.dump(res,open(G+"/f5-%s.json"%TAG,"w"),ensure_ascii=False,indent=1)

def rows(L): return [r for r in res["runs"] if r["len"]==L]
print("\n%-6s  %-9s  %-9s  %-9s  %-9s"%("dl.","liczba OK","lista OK","recall","zmyslone"))
for L in LENS:
    s=rows(L); n=len(s)
    rec=sum(r["l_hit"] for r in s)/max(1,sum(r["n_true"] for r in s))
    print("%-6s  %-9s  %-9s  %-9s  %-9d"%(L,"%d/%d"%(sum(r["n_ok"] for r in s),n),
        "%d/%d"%(sum(r["l_ok"] for r in s),n),"%.3f"%rec,sum(len(r["l_extra"]) for r in s)))
print("\nkluczowe: ile razy lista byla kompletna, a liczba mimo to bledna")
for L in LENS:
    s=rows(L)
    a=sum(1 for r in s if r["l_hit"]==r["n_true"] and not r["n_ok"])
    b=sum(1 for r in s if r["l_hit"]<r["n_true"] and not r["n_ok"])
    print("  %-5s lista kompletna + zla liczba: %d   lista niekompletna + zla liczba: %d"%(L,a,b))
print("\nczy liczba zgadza sie z dlugoscia wlasnej listy")
for L in LENS:
    s=rows(L)
    print("  %-5s n_got == len(lista): %d/%d"%(L,sum(1 for r in s if r["n_got"]==r["l_count"]),len(s)))
