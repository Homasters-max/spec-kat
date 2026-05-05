---
id: pattern/context-packet
page_type: pattern
domain: wiki
layer: architecture
tags:
- seam
- pipeline
- ingestion
- automation
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS.md
---
# Context Packet

## Summary
Архитектурный шов между Stage 0 (CLI ingest) и Stage 1 (LLM extraction) в протоколе [[wiki-evolve]]. Сериализованный JSON-файл, содержащий всё необходимое для LLM: текст источника, glossary hints и релевантные страницы. Единственный конструктор — `ingest.py::make_context_packet` (I-WIKI-SEAM-1).

## How It Works

Структура (dataclass `ContextPacket`):

```python
@dataclass
class ContextPacket:
    file: Path                        # путь к raw-файлу
    sha256: str                       # хэш содержимого
    raw_content: str                  # полный текст
    content_chunks: list[str]         # разбивка по заголовкам
    glossary_hints: list[GlossaryHint]  # совпадения с glossary.yaml
    related_pages: list[SearchResult]   # топ-N релевантных страниц (BM25)
```

Кэшируется в `runtime/cache/<sha256>.json`. Имя файла = sha256 источника.

**Как создаётся** (`make_context_packet`):
1. Парсит YAML frontmatter
2. Извлекает H1-H3 заголовки
3. Разбивает на chunks по заголовкам
4. Извлекает wikilinks из текста
5. Делает glossary lookup из `glossary.yaml`
6. Делает BM25 search для `related_pages`

## When To Use
Читать ContextPacket нужно в начале Stage 1 — до написания `extraction.json`. Основной источник данных для LLM-анализа.

## Trade-offs
- Статичен после создания — не обновляется при изменении wiki
- `related_pages` пусты в начале (пустой wiki) — нормально для первых ingestion'ов

## See Also
- [[wiki-evolve]]
- [[extraction-result]]
- [[wiki-cli]]
