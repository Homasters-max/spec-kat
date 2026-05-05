---
id: pattern/wiki-evolve
page_type: pattern
domain: wiki
layer: architecture
tags:
- pipeline
- ingestion
- write-path
- llm
- automation
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS.md
---
# Wiki Evolve

## Summary
Основной write-path протокол [[wiki-cli]]. Обрабатывает raw-файл через трёхстадийный pipeline: ingest → extraction → apply. Детерминированные стадии (Stage 0, post-action) выполняет CLI, смысловую стадию (Stage 1, Stage 2) — LLM. Реализует [[diff-first-updates]].

## How It Works

**Stage 0 (CLI):**

```bash
wiki ingest --pending --take 1   # из очереди (стандартный путь)
wiki ingest raw/file.md          # конкретный файл
```

Создаёт [[context-packet]] в `runtime/cache/<sha256>.json`.

**Stage 1 (LLM):**
- Читает `ContextPacket`: `content_chunks`, `glossary_hints`, `related_pages`
- Пишет `runtime/tmp/extraction.json` в формате [[extraction-result]]

```bash
wiki validate-extraction   # exit non-zero → STOP
```

**Stage 2 (LLM):**
- Читает `ExtractionResult`, проверяет существование страниц
- Для каждой entity выбирает операцию: `create` / `diff` / `rewrite`
- Пишет черновики в `runtime/tmp/<page_id>.[create|diff|rewrite].md`

```bash
wiki apply-drafts   # conflict → STOP
```

**Post-action (строгий порядок):**

```bash
wiki rebuild
wiki lint                                    # exit 0 обязателен
git commit <raw_file> <wiki/**>
wiki mark-ingested <sha256> --file <path>    # --file обязателен
wiki save-proposals                          # только если proposals > 0
wiki sync-glossary                           # пользователь вручную
```

## When To Use
Когда нужно добавить новые знания в wiki из markdown/txt файла в `raw/`.

## Trade-offs
- LLM-стадии не автоматизированы — требуют участия Claude в сессии
- Конфликт при `apply-drafts` требует ручного разрешения
- После `apply-drafts` `runtime/tmp/` очищается — черновики не сохраняются

## See Also
- [[wiki-cli]]
- [[context-packet]]
- [[extraction-result]]
- [[diff-first-updates]]
- [[wiki-query]]
- [[wiki-curate]]
