from __future__ import annotations

import difflib
import re
from pathlib import Path

import yaml

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_PAGE_TYPES = ("idea", "pattern", "tool")


def _strip_code_blocks(text: str) -> str:
    return _CODE_BLOCK_RE.sub("", text)


def _parse_frontmatter(text: str) -> dict | None:
    """Return frontmatter dict, or None if no valid frontmatter."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return yaml.safe_load(text[3:end].strip()) or {}
    return None


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
        for link in _WIKILINK_RE.findall(_strip_code_blocks(content)):
            if link in incoming:
                incoming[link].add(src_id)
    return incoming


def find_orphans(vault_root: Path, pages: dict[str, str] | None = None) -> list[str]:
    """Pages with no incoming wikilinks."""
    if pages is None:
        pages = _all_pages(vault_root)
    if not pages:
        return []
    incoming = _build_incoming(pages)
    return sorted(pid for pid, sources in incoming.items() if not sources)


def find_broken_links(vault_root: Path, pages: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """(src_page_id, broken_target) for [[links]] pointing to non-existent pages."""
    if pages is None:
        pages = _all_pages(vault_root)
    broken: list[tuple[str, str]] = []
    for src_id, content in pages.items():
        for link in _WIKILINK_RE.findall(_strip_code_blocks(content)):
            if link not in pages:
                broken.append((src_id, link))
    return sorted(broken)


def find_duplicates(vault_root: Path, pages: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Pairs of pages with SequenceMatcher ratio > 0.85."""
    if pages is None:
        pages = _all_pages(vault_root)
    ids = sorted(pages)
    duplicates: list[tuple[str, str]] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            sm = difflib.SequenceMatcher(None, pages[a], pages[b])
            if sm.real_quick_ratio() > 0.85 and sm.quick_ratio() > 0.85 and sm.ratio() > 0.85:
                duplicates.append((a, b))
    return duplicates


def check_frontmatter(
    vault_root: Path,
    domains: list[str] | None = None,
    layers: list[str] | None = None,
    pages: dict[str, str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Check frontmatter for all wiki pages.

    Returns (warnings, errors) — each item: {page_id, message}.
    D1: no frontmatter → WARNING
    D2: invalid domain → ERROR (only if domains list provided)
    D3: invalid layer → ERROR (only if layers list provided)
    D4: empty tags → WARNING
    """
    if pages is None:
        pages = _all_pages(vault_root)

    warnings: list[dict] = []
    errors: list[dict] = []

    for page_id, text in sorted(pages.items()):
        fm = _parse_frontmatter(text)

        # D1
        if fm is None:
            warnings.append({"page_id": page_id, "message": "no frontmatter"})
            continue

        # D2
        if domains is not None:
            domain = fm.get("domain") or ""
            if domain not in domains:
                errors.append({
                    "page_id": page_id,
                    "message": f"invalid domain: {domain!r} (allowed: {domains})",
                })

        # D3
        if layers is not None:
            layer = fm.get("layer") or ""
            if layer not in layers:
                errors.append({
                    "page_id": page_id,
                    "message": f"invalid layer: {layer!r} (allowed: {layers})",
                })

        # D4
        tags = fm.get("tags")
        if tags is not None and tags == []:
            warnings.append({"page_id": page_id, "message": "empty tags"})

    return warnings, errors


def check_hub_domains(
    vault_root: Path,
    domains: list[str],
    pages: dict[str, str] | None = None,
) -> list[dict]:
    """For each domain with ≥3 pages that has no page tagged role/hub → WARNING."""
    if not domains:
        return []
    if pages is None:
        pages = _all_pages(vault_root)
    domain_count: dict[str, int] = {d: 0 for d in domains}
    domain_has_hub: dict[str, bool] = {d: False for d in domains}
    for content in pages.values():
        fm = _parse_frontmatter(content)
        if fm is None:
            continue
        page_domain = fm.get("domain", "")
        if page_domain not in domain_count:
            continue
        domain_count[page_domain] += 1
        tags = fm.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        if "role/hub" in tags:
            domain_has_hub[page_domain] = True
    return [
        {
            "page_id": d,
            "message": f"No hub page for domain '{d}'. Add tag 'role/hub' to the overview page.",
        }
        for d in domains
        if domain_count[d] >= 3 and not domain_has_hub[d]
    ]


def check_sdd_annotations(
    vault_root: Path,
    sdd_components: list[str],
    pages: dict[str, str] | None = None,
) -> list[dict]:
    """WARNING if a page from sdd_components list is missing sdd_layer or sdd_domain in frontmatter."""
    if not sdd_components:
        return []
    if pages is None:
        pages = _all_pages(vault_root)

    warnings: list[dict] = []
    for page_id in sdd_components:
        if page_id not in pages:
            warnings.append({"page_id": page_id, "message": "sdd_component page not found in wiki"})
            continue
        fm = _parse_frontmatter(pages[page_id])
        if fm is None:
            warnings.append({"page_id": page_id, "message": "sdd_component has no frontmatter"})
            continue
        missing = [f for f in ("sdd_layer", "sdd_domain") if not fm.get(f)]
        if missing:
            warnings.append({
                "page_id": page_id,
                "message": f"sdd_component missing fields: {missing}",
            })
    return warnings


def run_lint(
    vault_root: Path,
    domains: list[str] | None = None,
    layers: list[str] | None = None,
    skip_duplicates: bool = False,
    sdd_components: list[str] | None = None,
) -> dict:
    """Aggregate all lint checks. Pages loaded once and shared across all checks."""
    pages = _all_pages(vault_root)
    orphans = find_orphans(vault_root, pages=pages)
    broken = find_broken_links(vault_root, pages=pages)
    duplicates = find_duplicates(vault_root, pages=pages) if not skip_duplicates else []
    warnings, errors = check_frontmatter(vault_root, domains=domains, layers=layers, pages=pages)
    hub_warnings = check_hub_domains(vault_root, domains or [], pages=pages)
    sdd_warnings = check_sdd_annotations(vault_root, sdd_components or [], pages=pages)
    warnings = warnings + hub_warnings + sdd_warnings
    return {
        "orphans": orphans,
        "broken_links": [{"src": s, "target": t} for s, t in broken],
        "duplicates": [{"a": a, "b": b} for a, b in duplicates],
        "warnings": warnings,
        "errors": errors,
    }
