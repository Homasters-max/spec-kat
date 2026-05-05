---
id: tool/trace-store
page_type: tool
domain: sdd
layer: architecture
tags:
- pipeline
- read-only
- automation
- write-path
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# TraceStore

Хранилище записей исполнения SDD task session. Два интерфейса (`TraceWriter` + `TraceReader`), одна реализация. Файл: `execution_log.jsonl`.

## How It Works

```python
@dataclass
class TraceEntry:
    ts: timestamp
    kind: str     # "graph_call" | "explain" | "file_write" | "command"
    payload: dict # snapshot_id, file_path, command_type и т.д.

class TraceWriter(Protocol):
    def append(self, entry: TraceEntry) -> None: ...

class TraceReader(Protocol):
    def query(self, filters: dict) -> list[TraceEntry]: ...

class TraceStore(TraceWriter, TraceReader):
    ...
```

**Запись `file_write` entries:**

- Claude Code Edit/Write tools → автоматический hook → `TraceStore.append(TraceEntry(kind="file_write", ...))`
- Агент **не декларирует** file writes вручную — hook делает это автоматически.

**Потребители:**

- [[execution-guard]] — читает trace для fingerprint check.
- [[scope-guard]] — читает `file_write` записи для scope verification.

## When To Use

Автоматически пишется в течение всей task session. Читается guards при каждой команде.

## Trade-offs

- JSONL формат — нет индексации, полный scan при `query()`.
- Зависит от корректной конфигурации hook на Edit/Write tools.

## See Also

- [[execution-guard]]
- [[scope-guard]]
- [[sdd-meta-harness]]
