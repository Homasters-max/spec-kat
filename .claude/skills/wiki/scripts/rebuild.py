from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_PAGE_TYPES = ("idea", "pattern", "tool")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm_text = text[3:end].strip()
            body = text[end + 4:].lstrip("\n")
            return yaml.safe_load(fm_text) or {}, body
    return {}, text


def _extract_title(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _extract_links(body: str) -> list[str]:
    return _WIKILINK_RE.findall(body)


def rebuild_all(vault_root: Path) -> None:
    """Rebuild derived/index.md and derived/graph.json from wiki pages."""
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

            title = fm.get("title") or _extract_title(body) or page_id
            tags: list[str] = fm.get("tags") or []
            links = _extract_links(body)

            pages.append({"id": page_id, "type": page_type, "title": title, "tags": tags})
            graph[page_id] = links

    derived_dir = vault_root / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)

    # index.md — markdown table
    lines = [
        "# Wiki Index",
        "",
        "| id | type | title | tags |",
        "|---|---|---|---|",
    ]
    for p in pages:
        tags_str = ", ".join(p["tags"]) if p["tags"] else ""
        lines.append(f"| {p['id']} | {p['type']} | {p['title']} | {tags_str} |")
    lines.append("")
    (derived_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")

    # graph.json
    (derived_dir / "graph.json").write_text(
        json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"[OK] index.md: {len(pages)} pages")
    print(f"[OK] graph.json: {len(graph)} nodes")
