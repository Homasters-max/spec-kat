"""transcript/parser.py — ConversationParser для Claude Code JSONL транскриптов.

Инварианты:
    I-TRANSCRIPT-2: читать с start_offset, не с начала файла
    I-TRANSCRIPT-3: read-only; не модифицировать Claude Code файлы
    I-TRACE-REF-1: find_tool_result — точная связка по tool_use_id; fuzzy match по тексту запрещён
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ToolPair:
    """Связанная пара tool_use + tool_result из транскрипта."""
    tool_use_id: str
    tool_name: str
    tool_input: dict
    tool_output: str
    timestamp: str
    assistant_uuid: str
    user_uuid: str


@dataclass
class TranscriptSession:
    """Результат парсинга одной SDD-сессии из транскрипта."""
    session_id: str
    transcript_path: str
    tool_pairs: list[ToolPair] = field(default_factory=list)
    assistant_texts: list[str] = field(default_factory=list)


def _parse_iso_timestamp(ts_str: str) -> float:
    """ISO 8601 → UNIX timestamp float."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()


def _extract_tool_result_output(block: dict) -> str:
    """Извлечь текстовый вывод из блока tool_result."""
    result_content = block.get("content", [])
    if isinstance(result_content, str):
        return result_content
    if isinstance(result_content, list):
        return "\n".join(
            c.get("text", "")
            for c in result_content
            if isinstance(c, dict) and c.get("type") == "text"
        )
    return ""


def parse_session(
    transcript_path: str,
    start_offset: int = 0,
) -> TranscriptSession:
    """Читает JSONL с start_offset, возвращает TranscriptSession.

    I-TRANSCRIPT-2: всегда читать с start_offset (не с начала файла).
    I-TRANSCRIPT-3: read-only.
    """
    path = Path(transcript_path)
    session_id = path.stem

    # Back up 8 KiB so the assistant tool_use block that precedes the first
    # tool_result of this session (written just before record-session captured
    # the offset) is included in the parse window.
    safe_offset = max(0, start_offset - 8192)
    with path.open("rb") as f:
        f.seek(safe_offset)
        raw = f.read().decode("utf-8", errors="replace")

    # tool_use_id → pending tool_use metadata (до получения tool_result)
    pending: dict[str, dict] = {}
    tool_pairs: list[ToolPair] = []
    assistant_texts: list[str] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        record_type = record.get("type", "")
        message = record.get("message") or {}
        content_blocks = message.get("content") or []
        if isinstance(content_blocks, str):
            content_blocks = []

        if record_type == "assistant":
            assistant_uuid = record.get("uuid", "")
            timestamp = record.get("timestamp", "")
            for block in content_blocks:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "tool_use":
                    pending[block["id"]] = {
                        "tool_name": block.get("name", ""),
                        "tool_input": block.get("input") or {},
                        "timestamp": timestamp,
                        "assistant_uuid": assistant_uuid,
                    }
                elif btype == "text":
                    text = block.get("text", "").strip()
                    if text:
                        assistant_texts.append(text)

        elif record_type == "user":
            user_uuid = record.get("uuid", "")
            for block in content_blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue
                tool_use_id = block.get("tool_use_id", "")
                if not tool_use_id or tool_use_id not in pending:
                    continue
                info = pending.pop(tool_use_id)
                tool_pairs.append(
                    ToolPair(
                        tool_use_id=tool_use_id,
                        tool_name=info["tool_name"],
                        tool_input=info["tool_input"],
                        tool_output=_extract_tool_result_output(block),
                        timestamp=info["timestamp"],
                        assistant_uuid=info["assistant_uuid"],
                        user_uuid=user_uuid,
                    )
                )

    return TranscriptSession(
        session_id=session_id,
        transcript_path=str(transcript_path),
        tool_pairs=tool_pairs,
        assistant_texts=assistant_texts,
    )


def find_tool_result(
    session: TranscriptSession,
    tool_use_id: str | None = None,
    ts: float | None = None,
) -> ToolPair | None:
    """Ищет ToolPair детерминированно.

    Приоритет 1: точная связка по tool_use_id (I-TRACE-REF-1).
    Fallback: ближайший по timestamp (abs < 2.0) если tool_use_id=None.
    Fuzzy match по тексту команды запрещён.
    """
    if tool_use_id is not None:
        for pair in session.tool_pairs:
            if pair.tool_use_id == tool_use_id:
                return pair
        return None

    if ts is not None:
        best: ToolPair | None = None
        best_delta = float("inf")
        for pair in session.tool_pairs:
            try:
                pair_ts = _parse_iso_timestamp(pair.timestamp)
                delta = abs(pair_ts - ts)
                if delta < 2.0 and delta < best_delta:
                    best_delta = delta
                    best = pair
            except (ValueError, KeyError):
                continue
        return best

    return None


def project_dir_from_cwd(cwd: str) -> Path:
    """'/root/project' → ~/.claude/projects/-root-project/

    Конвертирует абсолютный путь в ключ проекта Claude Code:
    все '/' заменяются на '-' (включая ведущий).
    """
    project_key = cwd.replace("/", "-")
    return Path.home() / ".claude" / "projects" / project_key


def latest_transcript(project_dir: Path) -> Path | None:
    """Возвращает самый свежий .jsonl файл в project_dir по mtime."""
    candidates = list(project_dir.glob("*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
