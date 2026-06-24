#!/usr/bin/env python3
"""Alias candidate-suggester — a HUMAN-GATED proposal generator.

Scans extracted entity surfaces that the canonical store does NOT resolve, and
proposes (never applies) two kinds of seed edits:

  1. attach_to_existing — a new alias for an existing canonical person, when the
     unresolved surface shares that person's surname and exactly one canonical
     entity owns it.
  2. new_entity         — a cluster of unresolved surfaces (persons by surname,
     orgs by leading significant token) that has no canonical home yet.

Safety, mirroring resolution/canonical.py:
  * Nothing is written to seed_entities.yaml. Output is a review file.
  * Every bare-surname-only form is flagged "do-not-anchor".
  * Surnames already ambiguous in the seed, or owned by >1 canonical, are flagged.
  * The human approves a merge by copying an approved block into the seed and
    re-running resolution — resolution stays a pure function of (extractions, seed).

Usage:
    python scripts/suggest_aliases.py [--min-count 2] [--out reports/]
"""
from __future__ import annotations
import argparse, json, glob, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/ingestion"))
from commission_ingestion.resolution.canonical import (  # noqa: E402
    load_store, normalise, strip_titles, _TYPE_GROUP,
)

ORG_STOP = {"THE", "OF", "AND", "SERVICES", "SERVICE", "COMMISSION", "DEPARTMENT",
            "COMPANY", "LIMITED", "PTY", "PROTECTION", "UNIT"}


def day_index(processed_dir: Path) -> dict[str, str]:
    idx = {}
    for f in glob.glob(str(processed_dir / "*.jsonl")):
        if not re.search(r"day0*\d+_", f):
            continue
        for line in open(f):
            d = json.loads(line)
            idx[d["chunk_id"]] = str(d["day_no"])
    return idx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-dir", default="data/cache/extraction/claude-haiku-4-5/extract_v1")
    ap.add_argument("--processed-dir", default="data/processed/madlanga")
    ap.add_argument("--min-count", type=int, default=2)
    ap.add_argument("--out", default="reports")
    args = ap.parse_args()

    store = load_store()
    prov = day_index(Path(args.processed_dir))

    sur2ids: dict[tuple, set] = defaultdict(set)
    for e in store.entities:
        grp = _TYPE_GROUP[e.entity_type]
        for form in e.surface_forms():
            for tok in strip_titles(form).split():
                sur2ids[(grp, tok)].add(e.entity_id)

    unres: dict[tuple, dict] = defaultdict(lambda: {"n": 0, "days": set()})
    for cf in glob.glob(str(Path(args.cache_dir) / "*.json")):
        j = json.load(open(cf))
        day = prov.get(j["chunk_id"], "?")
        for ent in j["extraction"]["entities"]:
            etype = ent.get("type", "person")
            if etype not in ("person", "org", "acronym"):
                continue
            if store.lookup(ent["name"], etype) is not None:
                continue
            key = (ent["name"].strip(), "org" if etype == "acronym" else etype)
            unres[key]["n"] += 1
            unres[key]["days"].add(day)

    attach: dict[str, list] = defaultdict(list)
    new_person: dict[str, list] = defaultdict(list)
    org_clusters: dict[str, list] = defaultdict(list)

    for (surface, typ), meta in unres.items():
        if meta["n"] < args.min_count:
            continue
        days = sorted(meta["days"])
        if typ == "person":
            form = normalise(surface); toks = strip_titles(form).split()
            if not toks:
                continue
            surname = toks[-1]
            flags = []
            if len(toks) == 1:
                flags.append("do-not-anchor: bare-surname-only")
            if (("person", surname) in store.ambiguous_surnames):
                flags.append("ambiguous-surname-in-seed")
            owners = sur2ids.get(("person", surname), set())
            if len(owners) == 1:
                attach[next(iter(owners))].append([surface, meta["n"], days, flags])
            elif len(owners) > 1:
                flags.append(f"surname owned by {len(owners)} canonicals")
                attach["AMBIGUOUS:" + surname].append([surface, meta["n"], days, flags])
            else:
                new_person[surname].append([surface, meta["n"], days, flags])
        else:
            f = normalise(surface)
            toks = [t for t in f.split() if t not in ORG_STOP and len(t) > 2]
            anchor = toks[0] if toks else f
            org_clusters[anchor].append([surface, meta["n"], days])

    tot = lambda rows: sum(r[1] for r in rows)
    proposals = {
        "attach_to_existing": {
            (store.by_id[eid].name if eid in store.by_id else eid): sorted(rows, key=lambda r: -r[1])
            for eid, rows in sorted(attach.items(), key=lambda kv: -tot(kv[1]))
        },
        "new_person_entities": {
            sn: sorted(rows, key=lambda r: -r[1])
            for sn, rows in sorted(new_person.items(), key=lambda kv: -tot(kv[1]))
        },
        "new_org_entities": {
            anc: sorted(rows, key=lambda r: -r[1])
            for anc, rows in sorted(org_clusters.items(), key=lambda kv: -tot(kv[1]))
        },
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "alias_candidates.json").write_text(json.dumps(proposals, indent=1, default=list))

    lines = ["# Alias candidates — REVIEW (human-gated, nothing applied)\n",
             "Generated by `scripts/suggest_aliases.py`. Copy approved blocks into "
             "`resolution/seed_entities.yaml` and re-run resolution. Verify identity before "
             "merging; never merge on a bare surname.\n"]
    lines.append("## 1. Proposed new aliases for existing canonical persons\n")
    for name, rows in proposals["attach_to_existing"].items():
        if name.startswith("AMBIGUOUS:"):
            continue
        lines.append(f"\n**{name}**\n")
        for surface, n, days, flags in rows:
            fl = f"  _({'; '.join(flags)})_" if flags else ""
            lines.append(f"- `{surface}` ×{n}, days {days}{fl}")
    lines.append("\n## 2. New ORG entities to seed (high-value gaps)\n")
    for anc, rows in list(proposals["new_org_entities"].items())[:12]:
        forms = ", ".join(f"`{r[0]}`×{r[1]}" for r in rows[:5])
        lines.append(f"- **{anc.title()}** (total ×{tot(rows)}): {forms}")
    lines.append("\n## 3. New PERSON entities to seed\n")
    for sn, rows in list(proposals["new_person_entities"].items())[:12]:
        forms = ", ".join(f"`{r[0]}`×{r[1]}" for r in rows[:4])
        flagged = any(f for r in rows for f in r[3])
        lines.append(f"- **{sn.title()}** (×{tot(rows)}){' ⚠' if flagged else ''}: {forms}")
    (out / "alias_candidates_review.md").write_text("\n".join(lines))

    print(f"unresolved surfaces (>= {args.min_count}): {sum(1 for _,m in unres.items() if m['n']>=args.min_count)}")
    print(f"attach-to-existing targets: {sum(1 for k in attach if not k.startswith('AMBIGUOUS'))}")
    print(f"new org clusters: {len(org_clusters)} | new person surnames: {len(new_person)}")
    print(f"wrote {out/'alias_candidates_review.md'} and {out/'alias_candidates.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
