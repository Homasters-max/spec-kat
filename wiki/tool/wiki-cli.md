---
id: tool/wiki-cli
page_type: tool
domain: wiki
layer: implementation
tags:
- cli
- pipeline
- knowledge-base
- python
- automation
version: 4
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS.md
---
# Wiki CLI

## Summary
Консольный инструмент (`wiki`) для управления персональной базой знаний на основе markdown. Реализует три протокола: [[wiki-evolve]], [[wiki-query]], [[wiki-curate]]. Построен на принципе [[automation-over-llm]]: детерминированный код делает механическую работу, LLM — только смысловую.

## Архитектура модулей

| Модуль | Назначение |
|--------|-----------|
| `models.py` | Контракты данных: `ContextPacket`, `ExtractionResult`, `WikiDiff`, `RewriteOp` |
| `config.py` | Загрузка `wiki_config.yaml`, чтение/запись glossary |
| `state.py` | Append-only логи: `ingest_log.jsonl`, `query_log.jsonl` |
| `git.py` | Обнаружение pending raw-файлов через git status |
| `repo.py` | CRUD страниц wiki: `create_page`, `apply_diff`, `rewrite_page` |
| `search.py` | BM25-индекс по всем страницам `wiki/**/*.md` |
| `ingest.py` | Stage 0: создание [[context-packet]] из raw-файла |
| `apply.py` | Stage 2: применение LLM-черновиков к wiki |
| `rebuild.py` | Генерация `derived/index.md`, `derived/graph.json` |
| `lint.py` | Проверка: orphans, broken links, duplicates, frontmatter |

## Установка

```bash
WIKI_SRC=/root/project/.claude/skills/wiki
python3 -m venv $WIKI_SRC/venv
$WIKI_SRC/venv/bin/pip install -e $WIKI_SRC/scripts/ -q
ln -sf $WIKI_SRC/venv/bin/wiki /usr/local/bin/wiki
```

## Ключевые инварианты

- `repo.py` не имеет метода `save_page()` — только `create_page`, `apply_diff`, `rewrite_page`
- `ingest.py::make_context_packet` — единственный конструктор `ContextPacket`
- `apply_drafts` останавливается на первом конфликте (не откатывает применённые)
- `wiki mark-ingested` — финальный шаг pipeline: записывает SHA256 в [[ingest-log]] (I-WIKI-INGEST-1)
- `wiki log-query` — записывает вопрос в [[query-log]], возвращает `query_id` для `wiki promote`
- `wiki evolve` — запускает wiki-evolve pipeline из CLI (без ручного запуска skill)
- `wiki register`, `wiki vaults`, `wiki use` — управление [[multi-vault]] реестром
- `wiki status` — показывает состояние pipeline: pending файлы, черновики, записи логов
- `wiki save-proposals` — сохраняет `glossary_proposals` из extraction.json в `.wiki/config/glossary_pending.yaml`; skip если term уже есть (I-WIKI-SEQ-1)
- `wiki delete <page_id> [--confirm]` — dry-run или удаление страницы: чистит входящие wikilinks, glossary entry, вызывает rebuild (I-WIKI-DELETE-1)
- `git.py::pending_raw_files` = uncommitted raw/ WHERE sha256 NOT IN ingest_log

## See Also
- [[wiki-evolve]]
- [[wiki-query]]
- [[wiki-curate]]
- [[context-packet]]
- [[extraction-result]]
- [[automation-over-llm]]
- [[git-as-ssot]]
- [[ingest-log]]
- [[query-log]]
- [[wiki-frontmatter]]
- [[page-meta]]
- [[multi-vault]]
