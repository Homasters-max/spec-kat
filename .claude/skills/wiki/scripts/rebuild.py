from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

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


def _build_graph(vault_root: Path) -> dict[str, dict[str, Any]]:
    """Single pass over all wiki files → full NodeData per page."""
    graph: dict[str, dict[str, Any]] = {}

    for page_type in _PAGE_TYPES:
        type_dir = vault_root / "wiki" / page_type
        if not type_dir.exists():
            continue
        for md_file in sorted(type_dir.glob("*.md")):
            page_id = md_file.stem
            text = md_file.read_text(encoding="utf-8")
            fm, body = _parse_frontmatter(text)

            graph[page_id] = {
                "type": page_type,
                "domain": fm.get("domain") or "?",
                "layer": fm.get("layer") or "?",
                "sdd_layer": fm.get("sdd_layer") or None,
                "sdd_domain": fm.get("sdd_domain") or None,
                "tags": fm.get("tags") or [],
                "updated": fm.get("updated") or "",
                "title": fm.get("title") or _extract_title(body) or page_id,
                "links": _extract_links(body),
            }

    return graph


def _write_graph_json(derived_dir: Path, graph: dict[str, dict]) -> None:
    (derived_dir / "graph.json").write_text(
        json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _write_index(derived_dir: Path, graph: dict[str, dict]) -> None:
    today = date.today().isoformat()
    pages = sorted(graph.items(), key=lambda kv: (_TYPE_ORDER.get(kv[1]["type"], 99), kv[0]))
    lines = [
        "# Wiki Index",
        "",
        f"_Updated: {today} · {len(pages)} pages_",
        "",
        *_table_header(["id", "type", "domain", "layer", "tags", "updated"]),
    ]
    for pid, p in pages:
        lines.append(
            f"| {pid} | {p['type']} | {p['domain']} | {p['layer']}"
            f" | {_tags_str(p['tags'])} | {p['updated']} |"
        )
    lines.append("")
    (derived_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_by_domain(views_dir: Path, graph: dict[str, dict]) -> None:
    today = date.today().isoformat()
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for pid, p in graph.items():
        groups[p["domain"]].append((pid, p))

    lines = ["# Pages by Domain", "", f"_Generated: {today}_"]
    for domain in sorted(groups):
        group = sorted(groups[domain], key=lambda kv: (_TYPE_ORDER.get(kv[1]["type"], 99), kv[0]))
        lines += ["", f"## {domain} ({len(group)})", ""]
        lines += _table_header(["id", "type", "layer", "tags", "updated"])
        for pid, p in group:
            lines.append(
                f"| {pid} | {p['type']} | {p['layer']}"
                f" | {_tags_str(p['tags'])} | {p['updated']} |"
            )
    lines.append("")
    (views_dir / "by-domain.md").write_text("\n".join(lines), encoding="utf-8")


def _write_by_layer(views_dir: Path, graph: dict[str, dict]) -> None:
    today = date.today().isoformat()
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for pid, p in graph.items():
        groups[p["layer"]].append((pid, p))

    lines = ["# Pages by Layer", "", f"_Generated: {today}_"]
    for layer in sorted(groups):
        group = sorted(groups[layer], key=lambda kv: (_TYPE_ORDER.get(kv[1]["type"], 99), kv[0]))
        lines += ["", f"## {layer} ({len(group)})", ""]
        lines += _table_header(["id", "type", "domain", "tags", "updated"])
        for pid, p in group:
            lines.append(
                f"| {pid} | {p['type']} | {p['domain']}"
                f" | {_tags_str(p['tags'])} | {p['updated']} |"
            )
    lines.append("")
    (views_dir / "by-layer.md").write_text("\n".join(lines), encoding="utf-8")


def _write_by_type(views_dir: Path, graph: dict[str, dict]) -> None:
    today = date.today().isoformat()
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for pid, p in graph.items():
        groups[p["type"]].append((pid, p))

    lines = ["# Pages by Type", "", f"_Generated: {today}_"]
    for page_type in _PAGE_TYPES:
        if page_type not in groups:
            continue
        group = sorted(groups[page_type], key=lambda kv: kv[0])
        lines += ["", f"## {page_type} ({len(group)})", ""]
        lines += _table_header(["id", "domain", "layer", "tags", "updated"])
        for pid, p in group:
            lines.append(
                f"| {pid} | {p['domain']} | {p['layer']}"
                f" | {_tags_str(p['tags'])} | {p['updated']} |"
            )
    lines.append("")
    (views_dir / "by-type.md").write_text("\n".join(lines), encoding="utf-8")


def _write_by_sdd_layer(views_dir: Path, graph: dict[str, dict]) -> None:
    today = date.today().isoformat()
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for pid, p in graph.items():
        sl = p["sdd_layer"]
        if sl:
            groups[sl].append((pid, p))

    lines = ["# Pages by SDD Layer", "", f"_Generated: {today}_"]
    for sdd_layer in sorted(groups):
        group = sorted(groups[sdd_layer], key=lambda kv: kv[0])
        lines += ["", f"## {sdd_layer} ({len(group)})", ""]
        lines += _table_header(["id", "type", "sdd_domain", "tags", "updated"])
        for pid, p in group:
            lines.append(
                f"| {pid} | {p['type']} | {p['sdd_domain'] or ''}"
                f" | {_tags_str(p['tags'])} | {p['updated']} |"
            )
    lines.append("")
    (views_dir / "by-sdd-layer.md").write_text("\n".join(lines), encoding="utf-8")


def _write_by_sdd_domain(views_dir: Path, graph: dict[str, dict]) -> None:
    today = date.today().isoformat()
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for pid, p in graph.items():
        sd = p["sdd_domain"]
        if sd:
            groups[sd].append((pid, p))

    lines = ["# Pages by SDD Domain", "", f"_Generated: {today}_"]
    for sdd_domain in sorted(groups):
        group = sorted(groups[sdd_domain], key=lambda kv: kv[0])
        # count by layer
        layer_counts: dict[str, int] = defaultdict(int)
        for _, p in group:
            sl = p["sdd_layer"] or "null"
            layer_counts[sl] += 1
        layer_summary = ", ".join(f"{k}: {v}" for k, v in sorted(layer_counts.items()))
        lines += ["", f"## {sdd_domain} ({layer_summary})", ""]
        lines += _table_header(["id", "type", "sdd_layer", "tags", "updated"])
        for pid, p in group:
            lines.append(
                f"| {pid} | {p['type']} | {p['sdd_layer'] or ''}"
                f" | {_tags_str(p['tags'])} | {p['updated']} |"
            )
    lines.append("")
    (views_dir / "by-sdd-domain.md").write_text("\n".join(lines), encoding="utf-8")


def rebuild_all(vault_root: Path) -> None:
    """Rebuild derived/index.md, derived/views/, and derived/graph.json."""
    graph = _build_graph(vault_root)

    derived_dir = vault_root / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)

    views_dir = derived_dir / "views"
    views_dir.mkdir(exist_ok=True)

    _write_graph_json(derived_dir, graph)
    _write_index(derived_dir, graph)
    _write_by_domain(views_dir, graph)
    _write_by_layer(views_dir, graph)
    _write_by_type(views_dir, graph)
    _write_by_sdd_layer(views_dir, graph)
    _write_by_sdd_domain(views_dir, graph)

    sdd_count = sum(1 for p in graph.values() if p["sdd_layer"])
    print(f"[OK] graph.json: {len(graph)} nodes")
    print(f"[OK] index.md: {len(graph)} pages")
    print(f"[OK] views/by-domain.md, by-layer.md, by-type.md")
    print(f"[OK] views/by-sdd-layer.md, by-sdd-domain.md ({sdd_count} annotated)")
