from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

PageType = Literal["idea", "pattern", "tool"]
RewriteReason = Literal["small_page", "structural_change"]


@dataclass
class GlossaryHint:
    term: str
    page: str
    aliases: list[str]
    type: str


@dataclass
class SearchResult:
    page_id: str
    score: float


@dataclass
class ContextPacket:
    file: Path
    sha256: str
    raw_content: str
    content_chunks: list[str]
    glossary_hints: list[GlossaryHint]
    related_pages: list[SearchResult]


class ExtractedEntity(BaseModel):
    term: str
    type: Literal["idea", "pattern", "tool"]
    confidence: float
    in_glossary: bool


class Relation(BaseModel):
    from_term: str
    to_term: str
    type: str


class ConflictNote(BaseModel):
    page: str
    note: str


class GlossaryProposal(BaseModel):
    term: str
    suggested_page: str
    type: Literal["idea", "pattern", "tool"]
    reason: str


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    relations: list[Relation]
    conflicts: list[ConflictNote]
    glossary_proposals: list[GlossaryProposal]


@dataclass
class WikiDiff:
    page_id: str
    unified_diff: str
    base_sha256: str


@dataclass
class RewriteOp:
    page_id: str
    page_content: str
    reason: RewriteReason


@dataclass
class ApplyResult:
    success: bool
    conflict: bool
    applied_lines: int


@dataclass
class IngestLogEntry:
    sha256: str
    file: str
    ts: str
    packet_path: str


@dataclass
class QueryLogEntry:
    query_id: str
    query: str
    ts: str
    context_snapshot: dict = field(default_factory=dict)
