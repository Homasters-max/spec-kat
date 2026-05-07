from __future__ import annotations

import json
import os
from pathlib import Path

from rank_bm25 import BM25Okapi

from models import SearchResult


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


class SearchEngine:
    def __init__(self, vault_root: Path) -> None:
        self.vault_root = vault_root
        self._bm25: BM25Okapi | None = None
        self._page_ids: list[str] = []
        self._index_built: bool = False

    def _cache_path(self) -> Path:
        return self.vault_root / "runtime" / "cache" / "bm25_corpus.json"

    def _wiki_files(self) -> list[Path]:
        wiki_dir = self.vault_root / "wiki"
        if not wiki_dir.exists():
            return []
        return sorted(wiki_dir.rglob("*.md"))

    def _current_mtimes(self) -> dict[str, float]:
        return {str(p): p.stat().st_mtime for p in self._wiki_files()}

    def build_index(self) -> None:
        cache = self._cache_path()
        current_mtimes = self._current_mtimes()

        if cache.exists():
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if cached.get("mtimes") == current_mtimes:
                self._page_ids = cached["page_ids"]
                corpus_tokens = cached["corpus_tokens"]
                self._bm25 = BM25Okapi(corpus_tokens)
                return

        files = self._wiki_files()
        self._page_ids = [p.stem for p in files]
        corpus_tokens: list[list[str]] = []
        for f in files:
            text = f.read_text(encoding="utf-8")
            corpus_tokens.append(_tokenize(text))

        self._bm25 = BM25Okapi(corpus_tokens) if corpus_tokens else None
        self._index_built = True

        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps({"mtimes": current_mtimes, "page_ids": self._page_ids, "corpus_tokens": corpus_tokens}),
            encoding="utf-8",
        )

    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        if not self._index_built:
            self.build_index()

        if not self._page_ids or self._bm25 is None:
            return []

        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(
            zip(self._page_ids, scores),
            key=lambda x: x[1],
            reverse=True,
        )
        # BM25 can return negative scores for small corpora (term in all docs → negative IDF)
        # Return all top_k hits; caller can filter by score if needed
        return [
            SearchResult(page_id=pid, score=float(score))
            for pid, score in ranked[:top_k]
            if score != 0.0
        ]
