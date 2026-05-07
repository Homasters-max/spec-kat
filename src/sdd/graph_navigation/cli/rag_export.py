"""CLI handler: sdd rag-export [--rebuild] — BC-36-4.

I-RAG-EXPORT-NOT-IN-QUERY-1: MUST NOT be imported from query handlers (resolve/explain/trace/invariant).
I-RAG-EXPORT-TASK-MODE-1: excluded from task mode (key starts with 'rag' → excluded per I-TASK-MODE-1).
I-RUNTIME-ORCHESTRATOR-1: no domain logic beyond pipeline calls and arg parsing.
I-PHASE-ISOLATION-1: no direct imports from sdd.graph.cache or sdd.graph.builder.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from sdd.graph.service import GraphService
from sdd.graph_navigation.cli.formatting import emit_error
from sdd.graph_navigation.rag.lightrag_exporter import LightRAGExporter
from sdd.graph_navigation.rag.registry import LightRAGRegistry
from sdd.spatial.index import IndexBuilder

if TYPE_CHECKING:
    from sdd.context_kernel.rag_types import LightRAGClient

logger = logging.getLogger(__name__)


def run(*, rebuild: bool = False, project_root: str = ".") -> int:
    """Execute sdd rag-export pipeline. Returns exit code (0 = success, 1 = error)."""
    try:
        index = IndexBuilder(project_root).build()
    except Exception as exc:
        emit_error("GRAPH_NOT_BUILT", str(exc))
        return 1

    try:
        graph = GraphService().get_or_build(index, force_rebuild=rebuild)
    except Exception as exc:
        emit_error("GRAPH_NOT_BUILT", str(exc))
        return 1

    fingerprint = graph.source_snapshot_hash
    registry = LightRAGRegistry()

    if not rebuild and registry.has_kg(fingerprint):
        logger.info("KG up-to-date for fingerprint %s — skipping export.", fingerprint[:8])
        print(f"rag-export: KG up-to-date for fingerprint {fingerprint[:8]}..., skipping.")
        return 0

    if rebuild:
        kg_path = registry.get_path(fingerprint)
        if kg_path.exists():
            shutil.rmtree(kg_path)

    try:
        rag_client = _make_lightrag_client(registry.get_path(fingerprint))
    except ImportError as exc:
        emit_error("INTERNAL_ERROR", f"lightrag not installed: {exc}. Run: pip install lightrag")
        return 1

    from sdd.context_kernel.documents import DocProvider
    docs = DocProvider(index).get_chunks(list(graph.nodes.keys()))

    LightRAGExporter().export(graph, docs, rag_client, registry, fingerprint)
    print(f"rag-export: KG exported for fingerprint {fingerprint[:8]}...")
    return 0


def _make_lightrag_client(working_dir: Path) -> "LightRAGClient":
    """Create LightRAGClient backed by lightrag-hku (optional dependency).

    Uses fake embedding (zero vectors, 384-dim) so no API key is required.
    Raises ImportError if lightrag-hku is not installed.
    """
    import asyncio  # noqa: PLC0415

    try:
        import numpy as np  # type: ignore[import-not-found]  # noqa: PLC0415
        from lightrag import LightRAG  # type: ignore[import-not-found]  # noqa: PLC0415
        from lightrag.utils import EmbeddingFunc  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(f"lightrag-hku not installed: {exc}") from exc

    working_dir.mkdir(parents=True, exist_ok=True)

    async def _fake_embed(texts: list[str], **_: object) -> "np.ndarray":  # type: ignore[type-arg]
        return np.zeros((len(texts), 384))

    async def _fake_llm(prompt: str, **_: object) -> str:
        return ""

    embed_func = EmbeddingFunc(embedding_dim=384, max_token_size=512, func=_fake_embed)
    rag = LightRAG(
        working_dir=str(working_dir),
        embedding_func=embed_func,
        llm_model_func=_fake_llm,
    )
    asyncio.run(rag.initialize_storages())
    return rag  # type: ignore[return-value]
