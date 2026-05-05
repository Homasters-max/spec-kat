---
id: tool/trace-store
page_type: tool
domain: sdd
layer: architecture
tags: [pipeline, read-only, automation, write-path, domain/sdd]
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
- raw/sdd-v2-architecture-deepening.md
---
# TraceStore

Хранилище записей исполнения SDD task session. Определяет два интерфейса — `TraceWriter` и `TraceReader` — которые остаются стабильным контрактом для consumers. Оригинальная реализация: `execution_log.jsonl` (JSONL, full scan). Актуальная реализация в sdd_v2: [[trace-projection]] (PostgreSQL, атомарная проекция через [[projection-registry]]).

## How It Works

**Интерфейсы (стабильны):**

```python
@dataclass
class TraceEntry:
    ts     : timestamp
    task_id: str
    kind   : str     # "graph_call" | "explain" | "file_write" | "command"
    payload: dict

class TraceWriter(Protocol):
    def append(self, entry: TraceEntry) -> None: ...

class TraceReader(Protocol):
    def get_fingerprint(self, task_id: str) -> GraphFingerprint: ...
    def get_writes(self, task_id: str) -> list[FileWrite]: ...
    def get_steps(self, task_id: str) -> list[TraceEntry]: ...
```

**Запись `file_write` entries** происходит автоматически — hook на Claude Code Edit/Write tools вызывает `TraceWriter.append()`. Агент не декларирует file writes вручную.

**Частичная запись:** не каждое событие попадает в Trace. В sdd_v2 [[projection-registry]] фильтрует по `CommandSpec.affects_trace = true` — только `resolve`, `explain`, `write`. Команды `activate-phase`, `record-session`, `switch-phase` в Trace не попадают.

**Потребители:**

- [[execution-guard]] — fingerprint check через `get_fingerprint(task_id)`
- [[scope-guard]] — scope verification через `get_writes(task_id)`

## When To Use

Через интерфейсы `TraceWriter` / `TraceReader` — автоматически в течение всей task session. Прямого обращения к реализации нет: consumers получают reader через dependency injection.

## Trade-offs

**JSONL (оригинал):** нет индексации → полный scan при каждом `query()`; рядом с PostgreSQL EventLog это архитектурный анахронизм; нет atomicity с EventLog append.

**TraceProjection (sdd_v2):** O(1) queries по `task_id`; атомарное обновление в той же транзакции что EventLog append; replay-based-testing автоматически; `execution_log.jsonl` удаляется как runtime-артефакт.

## See Also

- [[trace-projection]] — актуальная реализация в sdd_v2 (PostgreSQL, ProjectionRegistry)
- [[execution-guard]] — основной consumer
- [[scope-guard]] — второй consumer
- [[sdd-meta-harness]] — архитектурный обзор
