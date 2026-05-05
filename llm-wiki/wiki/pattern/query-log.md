---
id: pattern/query-log
page_type: pattern
domain: wiki
layer: implementation
tags:
- knowledge-base
- read-only
- pipeline
- ingestion
- domain/wiki
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS1.md
---
# Query Log

## Summary
Append-only журнал запросов к вики (`query_log.jsonl`). Хранит `query_id`, текст запроса, timestamp и опциональный `context_snapshot`. Используется для накопления вопросов, ответы на которые содержат ценные знания, достойные оформления в wiki-страницы.

## How It Works
1. После wiki-query сессии LLM сигнализирует `promote_suggestion`, если запрос содержит полезные знания.
2. Пользователь запускает: `QID=$(wiki log-query --query "<вопрос>")` — добавляет запись в `query_log.jsonl`, возвращает `query_id`.
3. Опционально: `wiki log-query --query "<вопрос>" --snapshot /path/ctx.json` — прикрепляет контекст к записи.
4. `wiki promote <query_id>` создаёт [[context-packet]] из сохранённого `context_snapshot` для последующего wiki-evolve.
5. Если `context_snapshot` пустой (нет `--snapshot`), `wiki promote` завершается с ошибкой `"context_snapshot is empty"`.

## When To Use
- После wiki-query, когда ответ содержит знания, которые стоит сохранить как wiki-страницу.
- Перед вызовом `wiki promote`: всегда сначала `wiki log-query`, чтобы получить `query_id`.
- `promote_suggestion` в выводе LLM — это сигнал, не готовый `query_id`. `query_id` создаёт только `wiki log-query`.

## Trade-offs
- Без `--snapshot` promote невозможен — нужен контекст для создания ContextPacket.
- `query_id` — 12-символьный hex UUID, не переносим между vault-ами.
- `wiki log` показывает оба типа (ingest + query) с фильтрацией по `--n`.

## See Also
- [[wiki-query]]
- [[wiki-cli]]
- [[ingest-log]]
- [[context-packet]]
- [[wiki-evolve]]
