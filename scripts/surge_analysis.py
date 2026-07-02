import os,re,json,glob,yaml
from collections import Counter
ROOT="."
SEED=os.path.join(ROOT,"packages/ingestion/commission_ingestion/resolution/seed_entities.yaml")
CACHE=os.path.join(ROOT,"data/cache/extraction/claude-haiku-4-5/extract_v1")
PROC=os.path.join(ROOT,"data/processed/madlanga")
_NON=re.compile(r"[^A-Za-z0-9]+");_WS=re.compile(r"\s+")
def norm(s): return _WS.sub(" ",_NON.sub(" ",(s or "").upper())).strip()
seed=yaml.safe_load(open(SEED)); RES={}
for e in seed["entities"]:
    for f in [e["name"]]+e.get("aliases",[]): RES[norm(f)]=e["id"]
def rid(s): return RES.get(norm(s))
MAT="person:vusimuzi-matlala"
day={}; total_day=Counter()
for fp in glob.glob(os.path.join(PROC,"*.jsonl")):
    for line in open(fp):
        if not line.strip(): continue
        r=json.loads(line); cid=r.get("chunk_id")
        if cid:
            day[cid]=r.get("day_no")
            if r.get("day_no") is not None: total_day[r["day_no"]]+=1
mat_day=Counter()
for fp in glob.glob(os.path.join(CACHE,"*.json")):
    ex=json.loads(open(fp).read())["extraction"]
    ids={rid(en["name"]) for en in ex.get("entities",[])}
    if MAT in ids:
        d=day.get(json.loads(open(fp).read())["chunk_id"])
        if d is not None: mat_day[d]+=1
days=sorted(total_day)
out=[{"day":d,"mat":mat_day.get(d,0),"total":total_day[d]} for d in days]
json.dump(out, open("/tmp/surge_data.json","w"))
print("days:",len(days),"| Matlala total chunks:",sum(mat_day.values()))
print("top surge days (chunks naming Matlala):")
for d,c in mat_day.most_common(8):
    print(f"  day {d:>3}: {c:>3} of {total_day[d]:>3} passages")
