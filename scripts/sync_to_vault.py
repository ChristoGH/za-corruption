#!/usr/bin/env python
"""Sync curated project docs from this repo into the Obsidian knowledge vault.

"Permanent attachment" = a repeatable export, not a one-off copy. Run this whenever
the plans/reports change and the vault stays in step. Each exported file lands in
`<vault>/30-Resources/Commission-Intelligence/` with Obsidian frontmatter prepended
(so Dataview sees it) and a backlink to the [[Commission Intelligence]] hub note, so
the graph view connects everything.

The hand-written hub note (`10-Projects/Commission Intelligence.md`) is NEVER touched.

    uv run python scripts/sync_to_vault.py                 # sync (default vault path)
    uv run python scripts/sync_to_vault.py --dry-run       # show what would change
    uv run python scripts/sync_to_vault.py --vault ~/path  # override vault location

Wire it to run automatically (optional): add to a git post-commit hook, or a cron/
launchd job. See the repo README section "Vault sync".
"""
from __future__ import annotations

import argparse
import os
import shutil
from datetime import date
from pathlib import Path

# Curated set of repo docs to surface in the vault. Edit freely.
MANIFEST = [
    "plans/post-extraction-roadmap.md",
    "plans/evidentiary-completeness-track.md",
    "reports/canary_signoff_triage.md",
    "reports/sectionC_bucket1_review.md",
    "reports/postrun_sweep.md",
    "reports/evidence_brief_matlala_hinge.md",
    "docs/ontology.md",
    "docs/decisions/0006-post-canary-followups.md",
]

HUB = "Commission Intelligence"          # the 10-Projects hub note title
DEST_SUBDIR = "30-Resources/Commission-Intelligence"
DEFAULT_VAULT = os.environ.get("KNOWLEDGE_VAULT", "~/github_repos/knowledge-vault")


def has_frontmatter(text: str) -> bool:
    return text.lstrip().startswith("---")


def obsidian_wrap(repo_rel: str, body: str) -> str:
    """Prepend Obsidian frontmatter + a backlink, unless the file already has frontmatter."""
    today = date.today().isoformat()
    fm = (
        "---\n"
        "type: note\n"
        f"project: {HUB}\n"
        f"source: za-corruption/{repo_rel}\n"
        f"synced: {today}\n"
        "tags: [commission, investigative, synced]\n"
        "---\n\n"
        f"> Synced from `za-corruption/{repo_rel}` · part of [[{HUB}]] · do not edit here (edit in the repo).\n\n"
    )
    if has_frontmatter(body):
        # File already carries its own frontmatter; just add the provenance banner after it.
        end = body.index("---", body.index("---") + 3) + 3
        banner = f"\n\n> Synced from `za-corruption/{repo_rel}` · part of [[{HUB}]] · do not edit here.\n"
        return body[:end] + banner + body[end:]
    return fm + body


def main() -> None:
    ap = argparse.ArgumentParser(description="Sync repo docs into the Obsidian vault")
    ap.add_argument("--vault", default=DEFAULT_VAULT, help="Vault root (or set $KNOWLEDGE_VAULT)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    vault = Path(args.vault).expanduser()
    if not vault.is_dir():
        raise SystemExit(f"vault not found: {vault} (set --vault or $KNOWLEDGE_VAULT)")
    dest = vault / DEST_SUBDIR
    if not (vault / "10-Projects" / f"{HUB}.md").exists():
        print(f"WARNING: hub note '10-Projects/{HUB}.md' not found in vault — create it first.")

    synced = skipped = missing = 0
    for rel in MANIFEST:
        src = repo / rel
        if not src.exists():
            print(f"  missing (skip): {rel}")
            missing += 1
            continue
        out = dest / Path(rel).name
        new = obsidian_wrap(rel, src.read_text(encoding="utf-8"))
        if out.exists() and out.read_text(encoding="utf-8") == new:
            skipped += 1
            continue
        if args.dry_run:
            print(f"  would write: {DEST_SUBDIR}/{out.name}")
        else:
            dest.mkdir(parents=True, exist_ok=True)
            out.write_text(new, encoding="utf-8")
            print(f"  wrote: {DEST_SUBDIR}/{out.name}")
        synced += 1

    verb = "would sync" if args.dry_run else "synced"
    print(f"\n{verb} {synced} · unchanged {skipped} · missing {missing}  →  {dest}")
    if not args.dry_run and synced:
        print(f"Open Obsidian → [[{HUB}]] to see them linked.")


if __name__ == "__main__":
    main()
