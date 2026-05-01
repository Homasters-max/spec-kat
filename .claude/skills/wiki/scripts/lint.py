from __future__ import annotations

import difflib
import re
from pathlib import Path

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_PAGE_TYPES = ("idea", "pattern", "tool")


def _all_pages(vault_root: Path) -> dict[str, str]:
    """Return {page_id: content} for all wiki pages."""
    pages: dict[str, str] = {}
    for page_type in _PAGE_TYPES:
        d = vault_root / "wiki" / page_type
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            pages[f.stem] = f.read_text(encoding="utf-8")
    return pages


def _build_incoming(pages: dict[str, str]) -> dict[str, set[str]]:
    """Return {page_id: set of page_ids that link to it}."""
    incoming: dict[str, set[str]] = {pid: set() for pid in pages}
    for src_id, content in pages.items():
        for link in _WIKILINK_RE.findall(content):
            if link in incoming:
                incoming[link].add(src_id)
    return incoming


def find_orphans(vault_root: Path) -> list[str]:
    """Pages with no incoming wikilinks."""
    pages = _all_pages(vault_root)
    if not pages:
        return []
    incoming = _build_incoming(pages)
    return sorted(pid for pid, sources in incoming.items() if not sources)


def find_broken_links(vault_root: Path) -> list[tuple[str, str]]:
    """(src_page_id, broken_target) for [[links]] pointing to non-existent pages."""
    pages = _all_pages(vault_root)
    broken: list[tuple[str, str]] = []
    for src_id, content in pages.items():
        for link in _WIKILINK_RE.findall(content):
            if link not in pages:
                broken.append((src_id, link))
    return sorted(broken)


def find_duplicates(vault_root: Path) -> list[tuple[str, str]]:
    """Pairs of pages with SequenceMatcher ratio > 0.85."""
    pages = _all_pages(vault_root)
    ids = sorted(pages)
    duplicates: list[tuple[str, str]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ratio = difflib.SequenceMatcher(None, pages[a], pages[b]).ratio()
            if ratio > 0.85:
                duplicates.append((a, b))
    return duplicates


def run_lint(vault_root: Path) -> dict:
    """Aggregate all lint checks."""
    orphans = find_orphans(vault_root)
    broken = find_broken_links(vault_root)
    duplicates = find_duplicates(vault_root)
    return {
        "orphans": orphans,
        "broken_links": [{"src": s, "target": t} for s, t in broken],
        "duplicates": [{"a": a, "b": b} for a, b in duplicates],
    }
