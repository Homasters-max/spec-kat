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
- domain/wiki
version: 3
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/TASKS.md
---
# Wiki Evolve

## Summary
Основной write-path протокол [[wiki-cli]]. Обрабатывает raw-файл через трёхстадийный pipeline: ingest → extraction → apply. Детерминированные стадии (Stage 0, post-action) выполняет CLI, смысловую стадию (Stage 1, Stage 2) — LLM. Реализует [[diff-first-updates]].

## How It Works

**Step 0 (опционально):**

```bash
wiki status      # проверить stale-черновики в runtime/tmp/
wiki clean-tmp   # очистить если остались с предыдущей сессии (I-WIKI-CLEAN-1)
```

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
wiki validate-extraction                     # exit non-zero → STOP
wiki save-proposals                          # только если proposals > 0 (I-WIKI-SEQ-1)
```

**Stage 2 (LLM):**
- Читает `ExtractionResult`, проверяет существование страниц batch-командой:

```bash
wiki exists <id1> <id2> ...   # быстрее N последовательных wiki show
```

- Для каждой entity выбирает операцию: `create` / `diff` / `rewrite`
- `create` — страница не существует → пишет `runtime/tmp/<id>.create.md`
- `rewrite` — страница существует, структурное изменение или размер ≤ 1000 chars → пишет `runtime/tmp/<id>.rewrite.md`
- `diff` — страница существует, небольшое дополнение, размер > 1000 chars → workflow через `wiki gen-diff`:

```bash
wiki show <page_id>                                           # читаем текущий контент
# LLM пишет runtime/tmp/<page_id>.new.md с полным новым контентом
wiki gen-diff <page_id> --new-content runtime/tmp/<page_id>.new.md
# → создаёт runtime/tmp/<page_id>.diff.md, удаляет .new.md
```

```bash
wiki apply-drafts   # conflict → STOP
```

**Post-action:**

```bash
wiki finalize --file <raw/path.md>   # rebuild → lint → mark-ingested → git commit
wiki sync-glossary                   # пользователь вручную
```

## When To Use
Когда нужно добавить новые знания в wiki из markdown/txt файла в `raw/`.

## Trade-offs
- LLM-стадии не автоматизированы — требуют участия Claude в сессии
- Конфликт при `apply-drafts` требует ручного разрешения (I-WIKI-CONFLICT-1)
- После `apply-drafts` `runtime/tmp/` очищается — черновики не сохраняются
- `wiki finalize` не коммитит при отсутствии staged/unstaged изменений (идемпотентен)

## See Also
- [[wiki-cli]]
- [[context-packet]]
- [[extraction-result]]
- [[diff-first-updates]]
- [[wiki-query]]
- [[wiki-curate]]
- [[wiki-session-isolation]] — изоляция tmp/ между wiki-evolve и wiki-curate сессиями
