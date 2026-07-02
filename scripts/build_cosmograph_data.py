import os,re,json,glob,yaml
from collections import Counter
ROOT="."
SEED=os.path.join(ROOT,"packages/ingestion/commission_ingestion/resolution/seed_entities.yaml")
CACHE=os.path.join(ROOT,"data/cache/extraction/claude-haiku-4-5/extract_v1")
_NON=re.compile(r"[^A-Za-z0-9]+");_WS=re.compile(r"\s+")
def norm(s): return _WS.sub(" ",_NON.sub(" ",(s or "").upper())).strip()
seed=yaml.safe_load(open(SEED)); RES={}; ROLE={}; NAME={}; TYPE={}
for e in seed["entities"]:
    eid=e["id"];NAME[eid]=e["name"];TYPE[eid]=e.get("type","person");note=(e.get("note") or "").lower()
    role="bench" if ("chairperson" in note or "bench" in note or "commissioner (present" in note) \
        else "counsel" if ("evidence leader" in note or "counsel" in note) else "witness"
    ROLE[eid]=role
    for f in [e["name"]]+e.get("aliases",[]): RES[norm(f)]=eid
def rid(s): return RES.get(norm(s))
MAT="person:vusimuzi-matlala"; ROLE[MAT]="subject"
for c in ("org:medicare-24","org:cat-vip"): ROLE[c]="company"
for c in ("org:saps","org:ipid","org:pktt","org:crime-intelligence","org:dpci","org:npa","org:empd"):
    if c in ROLE: ROLE[c]="org"
if "person:senzo-mchunu" in ROLE: ROLE["person:senzo-mchunu"]="political"

# modality of a predicate -> stance bucket
def modality(p):
    p=(p or "").lower()
    if any(k in p for k in("denied","denies","disputed","rejected","vehemently")): return "deny"
    if any(k in p for k in("asked","whether","questioned","put to","do you","did you","you say","correct?")): return "question"
    if any(k in p for k in("stated","testified","said","confirmed","alleged","claimed","maintained","described","indicated","accepted","conceded","agreed")): return "assert"
    return "other"

ment=Counter(); co_mat=Counter(); chunk_ents=[]; cand={}; stance=Counter()  # (node, bucket)->n
STRONG=re.compile(r"\b(deni|paid|pay|fund|own|met|meet|arrang|instruct|bribe|appoint|award|sign|interdict|kill|threat|influenc|corrupt|recruit|assist|transfer)",re.I)
for fp in glob.glob(os.path.join(CACHE,"*.json")):
    ex=json.loads(open(fp).read())["extraction"]
    byref={en["ref"]:rid(en["name"]) for en in ex.get("entities",[])}
    ids={v for v in byref.values() if v and TYPE.get(v) in ("person","org")}
    if ids:
        chunk_ents.append(ids)
        for i in ids: ment[i]+=1
        if MAT in ids:
            for o in ids-{MAT}: co_mat[o]+=1
    for cl in ex.get("claims",[]):
        parties={byref.get(r) for r in cl.get("subject_refs",[])}|{byref.get(r) for r in cl.get("object_refs",[])}
        if MAT in parties:
            sp=cl.get("speaker","");pred=cl.get("predicate","");q=cl.get("quote","");m=modality(pred)
            sc=(2 if STRONG.search(pred) else 0)+min(len(pred),140)/140
            for o in parties-{MAT,None}:
                cand.setdefault(o,[]).append((sc,sp,pred,q)); stance[(o,m)]+=1

top=[o for o,_ in co_mat.most_common(40) if ment[o]>=20]
keep=[MAT]+top[:19]
for c in ("org:medicare-24","org:cat-vip"):
    if c not in keep and c in ment: keep.append(c)
keepset=set(keep)
pair=Counter()
for ids in chunk_ents:
    k=[i for i in ids if i in keepset]
    for a in range(len(k)):
        for b in range(a+1,len(k)): x,y=sorted((k[a],k[b])); pair[(x,y)]+=1

CUR={MAT:"Businessman ('Cat' Matlala). Named across 62 of 106 hearing days — the #1 non-procedural figure in the entire commission.",
 "org:medicare-24":"Matlala-linked company. Surfaces on 32 hearing days.",
 "org:cat-vip":"Matlala-linked security company. Surfaces on 26 hearing days."}
def best_claim(o):
    c=cand.get(o)
    if not c: return None
    s,sp,pred,q=sorted(c,key=lambda x:-x[0])[0]
    return {"speaker":sp,"predicate":pred[:200],"quote":q[:220]}
def node_stance(o):
    a,d,qn=stance[(o,"assert")],stance[(o,"deny")],stance[(o,"question")]
    tot=a+d+qn+stance[(o,"other")]
    if ROLE.get(o)=="company": label="ownership"
    elif d>=5: label="contested"
    elif qn>a: label="questioned"
    else: label="asserted"
    return label,{"assert":a,"deny":d,"question":qn}

nodes=[]
for i in keep:
    st,sc=node_stance(i)
    n={"id":i,"name":NAME.get(i,i),"role":ROLE.get(i,"witness"),"ment":ment[i],"w":co_mat.get(i,0),
       "type":"org" if TYPE.get(i)=="org" else "person","stance":st,"sc":sc}
    if i in CUR: n["note"]=CUR[i]
    bc=best_claim(i)
    if bc and i!=MAT: n["claim"]=bc
    nodes.append(n)
links=[{"s":a,"t":b,"w":w} for (a,b),w in pair.items() if w>=10]
json.dump({"nodes":nodes,"links":links,"MAT":MAT},open("/tmp/cosmo_data.json","w"))
print(json.dumps({"nodes":len(nodes),"denied":[n["name"] for n in nodes if n["stance"]=="denied"],
 "questioned":[n["name"] for n in nodes if n["stance"]=="questioned"]}))
