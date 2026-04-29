"""DocumentChunk, ContentMapper, DefaultContentMapper, DocProvider — filesystem I/O layer (BC-36-3)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from sdd.spatial.index import SpatialIndex
from sdd.spatial.nodes import SpatialNode


@dataclass
class DocumentChunk:
    node_id:    str
    content:    str
    kind:       str        # "code" | "invariant" | "task" | "doc"
    char_count: int
    meta:       dict[str, object]
    references: list[str]  # node_ids in content, filtered to valid graph nodes (I-DOC-REFS-1)


class ContentMapper(Protocol):
    def extract_chunk(self, node: SpatialNode, content: str) -> str:
        """FILE + line_start/line_end → slice; FILE without bounds → whole file; non-FILE → ""."""
        ...


class DefaultContentMapper:
    """Canonical ContentMapper. Uses line_start/line_end from node meta (I-DOC-CHUNK-BOUNDARY-1)."""

    def extract_chunk(self, node: SpatialNode, content: str) -> str:
        if node.kind != "FILE":
            return ""
        ls = node.meta.get("line_start")
        le = node.meta.get("line_end")
        if ls is not None and le is not None:
            lines = content.splitlines()
            return "\n".join(lines[ls - 1:le])
        return content


# Matches full node_id forms that may appear in source content (e.g. COMMAND:complete, FILE:src/...).
_NODE_ID_RE = re.compile(r"\b[A-Z][A-Z0-9_]*:[A-Za-z0-9._/:-]+")

_KIND_MAP: dict[str, str] = {
    "FILE":      "code",
    "INVARIANT": "invariant",
    "TASK":      "task",
}


def _extract_references(content: str, valid_node_ids: frozenset[str]) -> list[str]:
    """Find node_ids referenced in content; drop broken refs (I-DOC-REFS-1)."""
    seen: set[str] = set()
    result: list[str] = []
    for m in _NODE_ID_RE.finditer(content):
        candidate = m.group(0).rstrip(".,;:)")
        if candidate in valid_node_ids and candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


class DocProvider:
    """Single filesystem I/O point in Context Kernel (I-DOC-FS-IO-1).

    Resolves file paths from SpatialIndex; reads actual content from filesystem.
    Non-FILE nodes produce empty DocumentChunk (I-DOC-NON-FILE-1).
    References are filtered to valid SpatialIndex node_ids (I-DOC-REFS-1).
    """

    def __init__(
        self,
        index: SpatialIndex,
        mapper: ContentMapper = DefaultContentMapper(),
    ) -> None:
        self._index = index
        self._mapper = mapper
        self._valid_ids: frozenset[str] = frozenset(index.nodes.keys())

    def get_chunks(self, node_ids: list[str]) -> list[DocumentChunk]:
        """Fetch DocumentChunk for each node_id; unknown node_ids are silently skipped."""
        chunks: list[DocumentChunk] = []
        for nid in node_ids:
            node = self._index.nodes.get(nid)
            if node is None:
                continue
            raw = self._read_raw(node)
            content = self._mapper.extract_chunk(node, raw)
            refs = _extract_references(content, self._valid_ids) if content else []
            chunks.append(DocumentChunk(
                node_id=nid,
                content=content,
                kind=_KIND_MAP.get(node.kind, "doc"),
                char_count=len(content),
                meta=dict(node.meta),
                references=refs,
            ))
        return chunks

    def _read_raw(self, node: SpatialNode) -> str:
        """Read raw content via SpatialIndex cache; fall back to filesystem for loaded indexes."""
        try:
            return self._index.read_content(node)
        except KeyError:
            # SpatialIndex loaded from disk has an empty _content_map — read from filesystem.
            if node.kind == "FILE" and node.path:
                try:
                    with open(node.path) as f:
                        return f.read()
                except OSError:
                    return ""
            return ""
