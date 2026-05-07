from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

import yaml

from config import load_glossary
from models import ContextPacket, GlossaryHint, SearchResult
from search import SearchEngine


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            fm = yaml.safe_load(text[4:end]) or {}
            return fm, text[end + 5:]
    return {}, text


def _chunk_by_headers(content: str, max_chunk: int = 1500) -> list[str]:
    lines = content.splitlines(keepends=True)
    chunks: list[str] = []
    current: list[str] = []
    for line in lines:
        if re.match(r"^#{1,3} ", line) and current:
            chunk = "".join(current).strip()
            if chunk:
                chunks.append(chunk)
            current = [line]
        else:
            current.append(line)
    if current:
        chunk = "".join(current).strip()
        if chunk:
            chunks.append(chunk)
    if not chunks:
        chunks = [content[i : i + max_chunk] for i in range(0, len(content), max_chunk) if content[i : i + max_chunk].strip()]
    return chunks


def _extract_wikilinks(text: str) -> list[str]:
    return re.findall(r"\[\[([^\]]+)\]\]", text)


def _find_h1(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _glossary_hints(raw: str, glossary: list[dict]) -> list[GlossaryHint]:
    hints: list[GlossaryHint] = []
    raw_lower = raw.lower()
    for entry in glossary:
        term: str = entry.get("term", "")
        aliases: list[str] = entry.get("aliases", [])
        candidates = [term] + aliases
        if any(c.lower() in raw_lower for c in candidates if c):
            hints.append(
                GlossaryHint(
                    term=term,
                    page=entry.get("page", ""),
                    aliases=aliases,
                    type=entry.get("type", ""),
                )
            )
    return hints


def make_context_packet(source_path: Path, vault_root: Path) -> ContextPacket:
    raw_bytes = source_path.read_bytes()
    digest = _sha256(raw_bytes)
    raw_text = raw_bytes.decode("utf-8", errors="replace")

    _frontmatter, body = _parse_frontmatter(raw_text)
    chunks = _chunk_by_headers(body)
    glossary = load_glossary(vault_root)
    hints = _glossary_hints(raw_text, glossary)

    title = _find_h1(body) or source_path.stem
    wikilinks = _extract_wikilinks(body)
    query = " ".join([title] + wikilinks[:5])

    engine = SearchEngine(vault_root)
    try:
        related = engine.search(query, top_k=10)
    except Exception:
        related = []

    return ContextPacket(
        file=source_path,
        sha256=digest,
        raw_content=raw_text,
        content_chunks=chunks,
        glossary_hints=hints,
        related_pages=related,
    )


def _packet_to_dict(packet: ContextPacket) -> dict:
    return {
        "file": str(packet.file),
        "sha256": packet.sha256,
        "raw_content": packet.raw_content,
        "content_chunks": packet.content_chunks,
        "glossary_hints": [asdict(h) for h in packet.glossary_hints],
        "related_pages": [asdict(r) for r in packet.related_pages],
    }


def _dict_to_packet(data: dict) -> ContextPacket:
    return ContextPacket(
        file=Path(data["file"]),
        sha256=data["sha256"],
        raw_content=data["raw_content"],
        content_chunks=data["content_chunks"],
        glossary_hints=[GlossaryHint(**h) for h in data["glossary_hints"]],
        related_pages=[SearchResult(**r) for r in data["related_pages"]],
    )


def cache_context_packet(vault_root: Path, packet: ContextPacket) -> Path:
    cache_dir = vault_root / "runtime" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{packet.sha256}.json"
    path.write_text(json.dumps(_packet_to_dict(packet), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_context_packet(vault_root: Path, sha256: str) -> ContextPacket:
    path = vault_root / "runtime" / "cache" / f"{sha256}.json"
    return _dict_to_packet(json.loads(path.read_text(encoding="utf-8")))
