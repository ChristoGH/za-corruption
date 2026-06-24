import os, re, json, glob, yaml, math
from collections import defaultdict, Counter

ROOT="."
SEED=os.path.join(ROOT,"packages/ingestion/commission_ingestion/resolution/seed_entities.yaml")
CACHE=os.path.join(ROOT,"data/cache/extraction/claude-haiku-4-5/extract_v1")
PROC=os.path.join(ROOT,"data/processed/madlanga")

_NON=re.compile(r"[^A-Za-z0-9]+"); _WS=re.compile(r"\s+")
def norm(s): return _WS.sub(" ", _NON.sub(" ", (s or "").upper())).strip()

# resolver: normalised surface -> (id, name, type)
seed=yaml.safe_load(open(SEED))
RES={}
NAME={}
for e in seed["entities"]:
    eid=e["id"]; NAME[eid]=e["name"]; t=e.get("type","person")
    forms=[e["name"]]+e.get("aliases",[])
    for f in forms:
        RES[norm(f)]=(eid,t)
def resolve(surface):
    return RES.get(norm(surface))   # (id,type) or None

MAT="person:vusimuzi-matlala"

# chunk_id -> day
day={}
for fp in glob.glob(os.path.join(PROC,"*.jsonl")):
    for line in open(fp):
        if not line.strip(): continue
        r=json.loads(line)
        cid=r.get("chunk_id")
        if cid: day[cid]=r.get("day_no")

# per chunk: resolved entity ids (person/org); claims involving entities
chunk_ents=defaultdict(set)
ent_days=defaultdict(set)        # id -> set(days)
ent_chunks=Counter()             # id -> #chunks mentioned
mat_day_chunks=Counter()         # day -> #chunks mentioning matlala
claims_about_mat=Counter()       # speaker_id_or_label -> count of claims where matlala is subject
mat_claim_cosubjects=Counter()   # other entity in claims where matlala is subject/object
total_chunks=0

for fp in glob.glob(os.path.join(CACHE,"*.json")):
    d=json.loads(open(fp).read()); cid=d["chunk_id"]; dy=day.get(cid)
    ex=d["extraction"]; total_chunks+=1
    byref={}
    ids=set()
    for ent in ex.get("entities",[]):
        r=resolve(ent["name"])
        if r:
            byref[ent["ref"]]=r[0]
            if r[1] in ("person","org"):
                ids.add(r[0])
    chunk_ents[cid]=ids
    for i in ids:
        ent_chunks[i]+=1
        if dy is not None: ent_days[i].add(dy)
    if MAT in ids and dy is not None:
        mat_day_chunks[dy]+=1
    # claims involving matlala
    for cl in ex.get("claims",[]):
        subs={byref.get(r) for r in cl.get("subject_refs",[])}
        objs={byref.get(r) for r in cl.get("object_refs",[])}
        parties={x for x in (subs|objs) if x}
        if MAT in parties:
            sp=cl.get("speaker") or "(unknown)"
            spr=resolve(sp); claims_about_mat[ NAME.get(spr[0], sp) if spr else sp ]+=1
            for other in parties-{MAT}:
                mat_claim_cosubjects[other]+=1

N=total_chunks
fM=ent_chunks[MAT]
print(f"== corpus: {N} chunks · Matlala in {fM} chunks · {len(ent_days[MAT])} days ==\n")

# 1. TEMPORAL — top surge days
print("TOP DAYS BY MATLALA DENSITY (chunks mentioning him):")
for dyy,c in sorted(mat_day_chunks.items(), key=lambda x:-x[1])[:10]:
    print(f"  day {dyy:>3}: {c} chunks")
print()

# 2. DISTINCTIVE ASSOCIATES (lift), min co-occurrence 8
co=Counter()
for cid,ids in chunk_ents.items():
    if MAT in ids:
        for o in ids-{MAT}: co[o]+=1
print("DISTINCTIVE ASSOCIATES (lift = how specifically tied to Matlala vs overall frequency; min 8 shared chunks):")
rows=[]
for o,c in co.items():
    fO=ent_chunks[o]
    if c>=8 and fO>0:
        lift=(c*N)/(fM*fO)
        rows.append((lift,c,fO,o))
for lift,c,fO,o in sorted(rows,key=lambda x:-x[0])[:18]:
    print(f"  lift {lift:5.1f} | shared {c:>3} (of {fO:>4} total) | {NAME.get(o,o)}")
print()

print("RAW TOP CO-OCCURRENCE (for contrast — dominated by ever-present cast):")
for o,c in co.most_common(12):
    print(f"  {c:>3} shared | {NAME.get(o,o)}")
print()

# 3. ALLEGED NETWORK from claims (co-subject/object with Matlala)
print("ALLEGED-NETWORK — entities sharing a CLAIM with Matlala (subject/object together):")
for o,c in mat_claim_cosubjects.most_common(15):
    print(f"  {c:>3} claims | {NAME.get(o,o)}")
print()

# 4. WHO TESTIFIES ABOUT MATLALA
print("WHO MAKES CLAIMS ABOUT MATLALA (speaker → #claims):")
for sp,c in claims_about_mat.most_common(12):
    print(f"  {c:>3} | {sp}")
