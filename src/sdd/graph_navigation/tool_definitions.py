"""Tool definitions for agent integration — BC-36-7 §7.2.

I-TOOL-DEF-1: Tool definitions MUST match CLI contract exactly.
Changing CLI signature = breaking change → requires bump of tool schema version.
"""
from __future__ import annotations

from typing import Any

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "sdd_resolve",
        "description": (
            "Поиск узлов графа по свободному тексту. Возвращает ranked list кандидатов "
            "(SearchCandidate) без выбора. При одном кандидате ContextEngine автоматически "
            "применяет RESOLVE_EXACT (I-SEARCH-AUTO-EXACT-1)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Свободный текст или NAMESPACE:ID"},
                "rebuild": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    },
    {
        "name": "sdd_explain",
        "description": (
            "Объяснить как работает узел графа: его out-связи (emits, guards, implements, "
            "tested_by). Для EVENT/TERM автоматически применяется TRACE fallback."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "Точный node_id, например COMMAND:complete",
                },
                "rebuild": {"type": "boolean", "default": False},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "sdd_trace",
        "description": (
            "Проследить обратные связи узла: кто на него ссылается (reverse BFS, max hop=2). "
            "Лучший выбор для EVENT и TERM узлов."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "Точный node_id, например EVENT:TaskImplementedEvent",
                },
                "rebuild": {"type": "boolean", "default": False},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "sdd_invariant",
        "description": (
            "Навигация по инварианту: узел INVARIANT + verified_by + introduced_in связи."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invariant_id": {
                    "type": "string",
                    "description": "Идентификатор инварианта, например I-GRAPH-DET-1",
                },
                "rebuild": {"type": "boolean", "default": False},
            },
            "required": ["invariant_id"],
        },
    },
]
