---
id: pattern/trace-projection
page_type: pattern
domain: sdd
layer: architecture
tags:
- ssot
- write-path
- pipeline
- automation
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/sdd-v2-architecture-deepening.md
---
# Trace Projection

## Summary

TraceProjection — это частичная PostgreSQL-проекция в [[projection-registry]], заменяющая [[trace-store]] (JSONL-файл). Хранит историю шагов агента (graph calls, explains, file writes) по `task_id`. Обновляется атомарно вместе с EventLog append — в той же транзакции. Consumers — [[execution-guard]] (fingerprint check) и [[scope-guard]] (scope verification) — получают O(1) typed queries вместо O(N) full scan.

## How It Works

**Частичная проекция:** не все события из EventLog попадают в TraceProjection. ProjectionRegistry фильтрует по флагу `CommandSpec.affects_trace = true`. Только события от `resolve`, `explain`, `write` (любой Edit/Write tool call) подаются в проекцию. События `activate-phase`, `bootstrap-policy`, `record-session`, `switch-phase` — игнорируются.

**TraceWriter** регистрируется как listener на [[command-bus]] — hook срабатывает автоматически на `file_write`, `graph_call`, `explain`. Write path для вызывающего кода не меняется.

**TraceReader** предоставляет typed queries по `task_id`:

```text
TraceReader.get_fingerprint(task_id) -> GraphFingerprint
TraceReader.get_writes(task_id)      -> list[FileWrite]
TraceReader.get_steps(task_id)       -> list[TraceEntry]
```

**Запись TraceEntry** содержит: `ts`, `task_id`, `kind` (`"graph_call"` | `"explain"` | `"file_write"` | `"command"`), `payload` dict.

**Atomic update:** ProjectionRegistry обновляет TraceProjection в той же PostgreSQL-транзакции что и EventLog append — гарантия consistency без дополнительного coordination.

## When To Use

Везде где нужна история шагов агента в рамках TaskRun. Два основных потребителя:
- [[execution-guard]]: проверяет `has_graph` / `has_explain` / `graph_fingerprint` через [[graph-session-projection]], которая строится поверх TraceProjection
- [[scope-guard]]: проверяет что все file writes входят в `write_scope` задачи

## Trade-offs

**Плюсы:** O(1) queries (PostgreSQL index по `task_id`); atomicity с EventLog; `replay-based-testing` работает автоматически — тот же механизм что у других проекций; `execution_log.jsonl` удаляется как runtime-артефакт.

**Минусы:** зависимость от PostgreSQL (нет лёгкого fallback на файл); частичная проекция требует дисциплины при добавлении новых команд — нужно явно задать `affects_trace`.

**Инвариант фильтрации:** `CommandSpec.affects_trace` задаётся при регистрации команды в [[command-bus]]. Отсутствие флага = `false` (default). Новая команда, которая должна попадать в Trace, обязана явно объявить `affects_trace = true`.

**Routing vs семантика:** `CommandSpec.affects_trace` — семантическая аннотация для Guards и AuditEngine. Она НЕ используется для маршрутизации в [[projection-registry]]. Routing определяется исключительно `subscribed_commands`, объявленными при регистрации TraceProjection.

## See Also

- [[trace-store]] — заменяемый компонент (JSONL реализация)
- [[projection-registry]] — инфраструктура атомарных проекций
- [[execution-guard]] — основной потребитель
- [[scope-guard]] — второй потребитель
- [[graph-session-projection]] — смежная проекция, строящаяся на тех же событиях
