"""LightRAGRegistry — pure filesystem registry for fingerprint-bound KG storage.

I-RAG-REGISTRY-PURE-1: No imports from GraphService, ContextEngine, or LightRAGClient.
I-RAG-EXPORT-FRESHNESS-1: Storage bound to graph_fingerprint.
"""
from __future__ import annotations

from pathlib import Path

from sdd.infra.paths import get_sdd_root


class LightRAGRegistry:
    """Pure filesystem registry: graph_fingerprint → KG path.

    Storage: <sdd_root>/runtime/lightrag_cache/<graph_fingerprint>/
    """

    def has_kg(self, fingerprint: str) -> bool:
        """True if KG directory for fingerprint exists on disk."""
        return self.get_path(fingerprint).exists()

    def get_path(self, fingerprint: str) -> Path:
        """Return path for fingerprint regardless of KG existence."""
        return get_sdd_root() / "runtime" / "lightrag_cache" / fingerprint
