"""Content-addressed extraction cache — the primary cost-safety mechanism.

A result is keyed by ``(chunk_id, PROMPT_VERSION, model)``. The chunk_id is
already the sha256 of the chunk text, so the key is fully content-addressed:
re-running over unchanged inputs makes zero API calls, and bumping the prompt
version or switching model naturally invalidates without deleting anything.

Layout (all under data/cache/extraction/ by default, gitignored):
    <model>/<prompt_version>/<chunk_id>.json   — one cached extraction
    dead_letter.jsonl                          — malformed responses, for review
    spend.jsonl                                — per-call usage + cost audit log
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CACHE_DIR = Path("data/cache/extraction")


class ExtractionCache:
    def __init__(self, root: Path | str = DEFAULT_CACHE_DIR) -> None:
        self.root = Path(root)

    def _path(self, chunk_id: str, prompt_version: str, model: str) -> Path:
        return self.root / model / prompt_version / f"{chunk_id}.json"

    def get(self, chunk_id: str, prompt_version: str, model: str) -> dict | None:
        path = self._path(chunk_id, prompt_version, model)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, chunk_id: str, prompt_version: str, model: str, payload: dict) -> None:
        path = self._path(chunk_id, prompt_version, model)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def has(self, chunk_id: str, prompt_version: str, model: str) -> bool:
        return self._path(chunk_id, prompt_version, model).exists()

    def dead_letter(self, *, chunk_id: str, model: str, prompt_version: str,
                    error: str, raw_response: str) -> None:
        """A malformed response never crashes the run and is never silently
        dropped — it lands here for human review."""
        self.root.mkdir(parents=True, exist_ok=True)
        record = {
            "at": datetime.now(timezone.utc).isoformat(),
            "chunk_id": chunk_id,
            "model": model,
            "prompt_version": prompt_version,
            "error": error,
            "raw_response": raw_response,
        }
        with (self.root / "dead_letter.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def dead_letter_count(self) -> int:
        path = self.root / "dead_letter.jsonl"
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    def log_spend(self, record: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        record = {"at": datetime.now(timezone.utc).isoformat(), **record}
        with (self.root / "spend.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def total_spend_usd(self) -> float:
        path = self.root / "spend.jsonl"
        if not path.exists():
            return 0.0
        total = 0.0
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                total += json.loads(line).get("cost_usd", 0.0)
        return total
