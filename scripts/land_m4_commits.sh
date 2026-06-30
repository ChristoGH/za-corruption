#!/usr/bin/env bash
# One-off: land the uncommitted M4 work onto a milestone branch as atomic,
# hook-gated commits. Run on your Mac (the agent sandbox cannot, its mount
# blocks file deletion that git needs). Re-runnable: each group commits only
# if it has staged changes.
#
#   bash scripts/land_m4_commits.sh
#
# It never pushes and never merges. Pushing stays with you at the review gate.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# Clear the stale lock from the earlier interrupted git op (harmless if absent).
rm -f .git/index.lock

BRANCH="feat/m4-claim-layer"
git switch -c "$BRANCH" 2>/dev/null || git switch "$BRANCH"
echo "On branch: $(git branch --show-current)"

commit_group () {
  local msg="$1"; shift
  git add -- "$@"
  if git diff --cached --quiet; then
    echo "  skip (nothing staged): $msg"
  else
    git commit -m "$msg"
  fi
}

# 1. The behaviour change and its test, together, so the tree stays green.
commit_group "feat(m4): keep speaker-unresolved claims with raw STATED_BY (ADR 0007)" \
  packages/ingestion/commission_ingestion/graph/neo4j_store.py \
  packages/ingestion/commission_ingestion/cli/build_graph.py \
  packages/ingestion/tests/test_graph.py \
  docs/decisions/0007-raw-speaker-fallback.md

# 2. Canonical seed data.
commit_group "chore(m4): expand canonical seed entities" \
  packages/ingestion/commission_ingestion/resolution/seed_entities.yaml

# 3. The other decision record.
commit_group "docs(m4): record post-canary follow-up decisions (ADR 0006)" \
  docs/decisions/0006-post-canary-followups.md

# 4. Process discipline: hooks, backup targets, ignores, project contract.
commit_group "chore(m4): commit and voice discipline hooks, backup targets, ignores" \
  scripts/hooks/commit-msg scripts/hooks/pre-commit scripts/hooks/pre-push scripts/hooks/post-commit \
  Makefile .gitignore CLAUDE.md \
  .cursor/rules/commit-discipline.mdc .cursor/rules/voice.mdc

# 5. Public method, re-entry point, forward plans, video-ingest research.
commit_group "docs(m4): method, re-entry point, and forward plans" \
  METHOD.md NEXT.md \
  plans/evidentiary-completeness-track.md plans/live-cosmograph-from-neo4j.md \
  plans/post-extraction-roadmap.md plans/staying-current-pipeline.md \
  docs/madlanga_full_day_video_transcription_technology.md

# 6. Analysis, cosmograph build, and post-run utility scripts.
commit_group "chore(m4): analysis, cosmograph, and post-build scripts" \
  scripts/association_analysis.py scripts/surge_analysis.py \
  scripts/build_cosmograph_data.py scripts/build_cosmograph_html.py \
  scripts/postrun_sweep.py scripts/recover_batch.py \
  scripts/suggest_aliases.py scripts/sync_to_vault.py

# 7. Series A post drafts and visuals (mp4s excluded by .gitignore).
commit_group "docs(m4): Series A post drafts and visuals" \
  linkedin/

echo
echo "Done. Review with:  git log --oneline -8"
echo "Anything left dirty:"
git status --short
echo
echo "When you are satisfied, push the branch yourself:  ALLOW_PUSH=1 git push -u origin $BRANCH"
