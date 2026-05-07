---
id: pattern/ingest-log
page_type: pattern
domain: wiki
layer: implementation
tags:
- ingestion
- write-path
- ssot
- automation
- pipeline
- domain/wiki
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS1.md
---
# Ingest Log

## Summary
Append-only журнал обработанных raw-файлов (`ingest_log.jsonl`). Хранит SHA256, путь файла, timestamp и путь к [[context-packet]]. Используется [[wiki-cli]] для определения pending-файлов: файл считается необработанным, пока его SHA256 не появится в `ingest_log.jsonl`.

## How It Works
1. `wiki ingest <file>` вычисляет SHA256 raw-файла и создаёт [[context-packet]].
2. LLM проходит Stage 1 → Stage 2, создаются черновики в `runtime/tmp/`.
3. После `wiki apply-drafts`, `wiki rebuild`, `wiki lint` и `git commit` — финальный шаг: `wiki mark-ingested <sha256> --file <path>`.
4. `mark-ingested` проверяет, не записан ли SHA256 уже, и добавляет запись в `ingest_log.jsonl`.
5. `wiki ingest --pending` фильтрует raw-файлы через `git.py::pending_raw_files` = uncommitted raw/ WHERE sha256 NOT IN ingest_log.

## When To Use
- Всегда как последний шаг wiki-evolve pipeline (I-WIKI-INGEST-1).
- Для диагностики: `wiki log --n 10` показывает последние записи с типом `ingest`.
- Для проверки: повторный вызов `mark-ingested` с тем же SHA256 → `[SKIP]`, идемпотентен.

## Trade-offs
- Запись выполняется только явным вызовом `mark-ingested` — автоматически не добавляется.
- Если `mark-ingested` не вызван, файл повторно появится в `wiki ingest --pending` в следующей сессии.
- `--file` обязателен согласно I-WIKI-INGEST-1: без него команда завершается с exit 1.

## See Also
- [[wiki-cli]]
- [[wiki-evolve]]
- [[context-packet]]
- [[query-log]]
