# Committed as run, from the measurement host. Working directory is ~/gate there:
# frozen contexts f4-ctx-<len>.txt and f4-items.json, results f4-<tag>.json.
# Comments and question wording are Polish, as in the rest of prompts/ here.
# Faza 4: generator serii trudnej. Buduje ten SAM zestaw faktow i pytan dla kazdej
# dlugosci kontekstu; zmienia sie tylko ilosc wypelniacza. Zapisuje na dysk, zeby
# oba warianty KV dostaly bajtowo identyczne wejscie.
import json,os,random,sys
sys.path.insert(0,os.path.expanduser("~/gate"))
from kv_client import ntok,para

SEED=20260902
N_PER_TYPE=8
LEN={"8k":8000,"32k":32000,"64k":64000,"120k":120000}
AL="ABCDEFGHJKMNPQRSTUVWXYZ23456789"
R=random.Random(SEED)

def key(used):
    while True:
        k="".join(R.choice(AL) for _ in range(4))+"-"+"".join(R.choice(AL) for _ in range(4))
        if k not in used:
            used.add(k); return k

def near(k,used):
    # klucz roznacy sie jednym znakiem - lamie dopasowanie leksykalne
    for _ in range(200):
        i=R.choice([j for j in range(9) if j!=4])
        c=R.choice(AL)
        if c==k[i]: continue
        n=k[:i]+c+k[i+1:]
        if n not in used:
            used.add(n); return n
    return key(used)

def gen():
    used=set(); parts=list(range(10,100)); R.shuffle(parts); pi=0
    def part():
        nonlocal pi
        p=parts[pi]; pi+=1; return p
    facts=[]   # (rel_pos, tekst)
    items=[]   # (typ, pytanie, odpowiedz)
    def put(rel,txt): facts.append([rel,txt])

    # A: pojedyncze wyszukanie w tlumie bliskich kluczy
    for _ in range(N_PER_TYPE):
        k=key(used); p=part()
        put(R.uniform(0.03,0.97),"Rejestr: klucz %s nalezy do partycji %d."%(k,p))
        for _ in range(3):
            put(R.uniform(0.03,0.97),"Rejestr: klucz %s nalezy do partycji %d."%(near(k,used),part()))
        items.append(["A","Do ktorej partycji nalezy klucz %s? Odpowiedz wylacznie dwucyfrowa liczba, bez zadnego innego tekstu."%k,str(p)])

    # B: dwa skoki, fakty daleko od siebie
    for _ in range(N_PER_TYPE):
        k=key(used); p=part(); node=R.randint(100,999)
        put(R.uniform(0.02,0.30),"Rejestr: klucz %s nalezy do partycji %d."%(k,p))
        put(R.uniform(0.70,0.98),"Mapa: partycja %d jest obslugiwana przez WEZEL-%03d."%(p,node))
        for _ in range(3):
            np_=part()
            put(R.uniform(0.02,0.98),"Rejestr: klucz %s nalezy do partycji %d."%(near(k,used),np_))
            put(R.uniform(0.02,0.98),"Mapa: partycja %d jest obslugiwana przez WEZEL-%03d."%(np_,R.randint(100,999)))
        items.append(["B","Ktory wezel obsluguje klucz %s? Odpowiedz wylacznie w formacie WEZEL-NNN, bez zadnego innego tekstu."%k,"WEZEL-%03d"%node])

    # C: przeliczenie rozsypanych wpisow tej samej partycji
    for _ in range(N_PER_TYPE):
        p=part(); n=R.randint(3,7)
        for _ in range(n):
            put(R.uniform(0.02,0.98),"Rejestr: klucz %s nalezy do partycji %d."%(key(used),p))
        items.append(["C","Ile kluczy nalezy do partycji %d? Odpowiedz wylacznie liczba, bez zadnego innego tekstu."%p,str(n)])

    R.shuffle(facts)
    return facts,items

def build(facts,target):
    def txt(n):
        ps=[para(i) for i in range(1,n+1)]
        for rel,t in facts:
            j=max(0,min(n-1,int(rel*n)))
            ps[j]=ps[j]+" "+t
        return "\n\n".join(ps)
    lo,hi=1,3000
    while lo<hi:
        mid=(lo+hi+1)//2
        if ntok(txt(mid))<=target: lo=mid
        else: hi=mid-1
    t=txt(lo)
    return t,lo,ntok(t)

if __name__=="__main__":
    facts,items=gen()
    out={"seed":SEED,"n_per_type":N_PER_TYPE,"n_facts":len(facts),"items":items,"ctx":{}}
    for name,tgt in LEN.items():
        t,np_,nt=build(facts,tgt)
        p=os.path.expanduser("~/gate/f4-ctx-%s.txt"%name)
        open(p,"w").write(t)
        out["ctx"][name]={"paras":np_,"tokens":nt,"chars":len(t)}
        print(name,"akapitow",np_,"tokenow",nt)
    json.dump(out,open(os.path.expanduser("~/gate/f4-items.json"),"w"),ensure_ascii=False,indent=1)
    print("faktow",len(facts),"pytan",len(items))
