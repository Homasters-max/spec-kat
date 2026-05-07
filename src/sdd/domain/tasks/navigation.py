"""TaskNavigationSpec — навигационные метаданные задачи. Spec_v55 §2 BC-55-P3."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResolveKeyword:
    keyword: str
    expected_kinds: tuple[str, ...]  # ("COMMAND", "INVARIANT", ...)


@dataclass(frozen=True)
class TaskNavigationSpec:
    """Навигационные метаданные задачи. Версионированная эволюция:
      v55: resolve_keywords + write_scope (keyword-search era)
      v56: anchor_nodes + allowed_traversal + write_scope (node-id era)
    """
    write_scope: tuple[str, ...]

    resolve_keywords: tuple[ResolveKeyword, ...] = ()
    anchor_nodes: tuple[str, ...] = ()
    allowed_traversal: tuple[str, ...] = ()

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> "TaskNavigationSpec":
        """Parse from TaskSet markdown section dict."""
        write_scope_raw = raw.get("write_scope", "")
        write_scope: tuple[str, ...] = (
            tuple(s.strip() for s in write_scope_raw.split(",") if s.strip())
            if isinstance(write_scope_raw, str)
            else tuple(write_scope_raw)
        )

        resolve_keywords: list[ResolveKeyword] = []
        for entry in raw.get("resolve_keywords", []):
            if isinstance(entry, dict):
                resolve_keywords.append(ResolveKeyword(
                    keyword=entry["keyword"],
                    expected_kinds=tuple(entry.get("expected_kinds", [])),
                ))
            elif isinstance(entry, str):
                resolve_keywords.append(ResolveKeyword(keyword=entry, expected_kinds=()))

        anchor_nodes_raw = raw.get("anchor_nodes", "")
        anchor_nodes: tuple[str, ...] = (
            tuple(s.strip() for s in anchor_nodes_raw.split(",") if s.strip())
            if isinstance(anchor_nodes_raw, str)
            else tuple(anchor_nodes_raw)
        )

        allowed_traversal_raw = raw.get("allowed_traversal", "")
        allowed_traversal: tuple[str, ...] = (
            tuple(s.strip() for s in allowed_traversal_raw.split(",") if s.strip())
            if isinstance(allowed_traversal_raw, str)
            else tuple(allowed_traversal_raw)
        )

        return cls(
            write_scope=write_scope,
            resolve_keywords=tuple(resolve_keywords),
            anchor_nodes=anchor_nodes,
            allowed_traversal=allowed_traversal,
        )

    def is_anchor_mode(self) -> bool:
        """True = v56+ (anchor_nodes present). False = v55 (resolve_keywords era)."""
        return bool(self.anchor_nodes)
