from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import yaml

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_PAGE_TYPES = ("idea", "pattern", "tool")
_TYPE_ORDER = {t: i for i, t in enumerate(_PAGE_TYPES)}


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm_text = text[3:end].strip()
            body = text[end + 4:].lstrip("\n")
            return yaml.safe_load(fm_text) or {}, body
    return {}, text


# C1: parse YAML frontmatter from a page file
def _read_page_meta(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return yaml.safe_load(text[3:end].strip()) or {}
    return {}


def _extract_title(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _extract_links(body: str) -> list[str]:
    return _WIKILINK_RE.findall(body)


def _tags_str(tags: list[str]) -> str:
    return ", ".join(tags) if tags else ""


def _table_header(cols: list[str]) -> list[str]:
    sep = "|".join("---" for _ in cols)
    return [f"| {' | '.join(cols)} |", f"|{sep}|"]


def _build_pages(vault_root: Path) -> tuple[list[dict], dict[str, list[str]]]:
    pages: list[dict] = []
    graph: dict[str, list[str]] = {}

    for page_type in _PAGE_TYPES:
        type_dir = vault_root / "wiki" / page_type
        if not type_dir.exists():
            continue
        for md_file in sorted(type_dir.glob("*.md")):
            page_id = md_file.stem
            text = md_file.read_text(encoding="utf-8")
            fm, body = _parse_frontmatter(text)

            pages.append({
                "id": page_id,
                "type": page_type,
                "domain": fm.get("domain") or "?",
                "layer": fm.get("layer") or "?",
                "tags": fm.get("tags") or [],
                "updated": fm.get("updated") or "",
                "title": fm.get("title") or _extract_title(body) or page_id,
            })
            graph[page_id] = _extract_links(body)

    # C2: sort by type order then id
    pages.sort(key=lambda p: (_TYPE_ORDER.get(p["type"], 99), p["id"]))
    return pages, graph


def _write_index(derived_dir: Path, pages: list[dict]) -> None:
    today = date.today().isoformat()
    lines = [
        "# Wiki Index",
        "",
        f"_Updated: {today} · {len(pages)} pages_",
        "",
        *_table_header(["id", "type", "domain", "layer", "tags", "updated"]),
    ]
    for p in pages:
        lines.append(
            f"| {p['id']} | {p['type']} | {p['domain']} | {p['layer']}"
            f" | {_tags_str(p['tags'])} | {p['updated']} |"
        )
    lines.append("")
    (derived_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_by_domain(views_dir: Path, pages: list[dict]) -> None:
    today = date.today().isoformat()
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in pages:
        groups[p["domain"]].append(p)

    lines = ["# Pages by Domain", "", f"_Generated: {today}_"]
    for domain in sorted(groups):
        group = groups[domain]
        lines += ["", f"## {domain} ({len(group)})", ""]
        lines += _table_header(["id", "type", "layer", "tags", "updated"])
        for p in group:
            lines.append(
                f"| {p['id']} | {p['type']} | {p['layer']}"
                f" | {_tags_str(p['tags'])} | {p['updated']} |"
            )
    lines.append("")
    (views_dir / "by-domain.md").write_text("\n".join(lines), encoding="utf-8")


def _write_by_layer(views_dir: Path, pages: list[dict]) -> None:
    today = date.today().isoformat()
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in pages:
        groups[p["layer"]].append(p)

    lines = ["# Pages by Layer", "", f"_Generated: {today}_"]
    for layer in sorted(groups):
        group = groups[layer]
        lines += ["", f"## {layer} ({len(group)})", ""]
        lines += _table_header(["id", "type", "domain", "tags", "updated"])
        for p in group:
            lines.append(
                f"| {p['id']} | {p['type']} | {p['domain']}"
                f" | {_tags_str(p['tags'])} | {p['updated']} |"
            )
    lines.append("")
    (views_dir / "by-layer.md").write_text("\n".join(lines), encoding="utf-8")


def _write_by_type(views_dir: Path, pages: list[dict]) -> None:
    today = date.today().isoformat()
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in pages:
        groups[p["type"]].append(p)

    lines = ["# Pages by Type", "", f"_Generated: {today}_"]
    for page_type in _PAGE_TYPES:
        if page_type not in groups:
            continue
        group = groups[page_type]
        lines += ["", f"## {page_type} ({len(group)})", ""]
        lines += _table_header(["id", "domain", "layer", "tags", "updated"])
        for p in group:
            lines.append(
                f"| {p['id']} | {p['domain']} | {p['layer']}"
                f" | {_tags_str(p['tags'])} | {p['updated']} |"
            )
    lines.append("")
    (views_dir / "by-type.md").write_text("\n".join(lines), encoding="utf-8")


def rebuild_all(vault_root: Path) -> None:
    """Rebuild derived/index.md, derived/views/, and derived/graph.json."""
    pages, graph = _build_pages(vault_root)

    derived_dir = vault_root / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)

    # C2: updated index.md with domain/layer/tags/updated columns
    _write_index(derived_dir, pages)

    # C3: create derived/views/ if not exists
    views_dir = derived_dir / "views"
    views_dir.mkdir(exist_ok=True)

    # C4: by-domain.md
    _write_by_domain(views_dir, pages)

    # C5: by-layer.md
    _write_by_layer(views_dir, pages)

    # C6: by-type.md
    _write_by_type(views_dir, pages)

    # graph.json (unchanged)
    (derived_dir / "graph.json").write_text(
        json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"[OK] index.md: {len(pages)} pages")
    print(f"[OK] views/by-domain.md, by-layer.md, by-type.md")
    print(f"[OK] graph.json: {len(graph)} nodes")
