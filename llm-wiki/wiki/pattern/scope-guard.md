---
id: pattern/scope-guard
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- write-path
- validation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Meta Harness Core.md
---
# Scope Guard

L1 guard в SDD: верифицирует, что агент писал только в файлы, объявленные в `write_scope` задачи. Источник данных — [[trace-store]] (автоматический hook на Edit/Write tools).

## How It Works

```python
def check(trace: TraceReader, task: Task) -> Result:
    file_writes = [e.payload["path"] for e in trace.query({"kind": "file_write"})]
    violations = [f for f in file_writes if f not in task.write_scope]
    if violations:
        return DENY(f"OUT_OF_SCOPE: {violations}")
    return OK
```

**Task write_scope:**

```yaml
Task:
  write_scope:
    - "src/sdd/*.py"
    - "tests/unit/*.py"
```

**Правила:**

```text
file ∈ write_scope → разрешено
file ∉ write_scope → DENY (даже если есть graph path)
новый файл ∈ write_scope → разрешено без graph path
новый файл ∉ write_scope → DENY
```

`write_scope` = human-approved declaration. Graph path для файлов из scope **не требуется**.

Вызывается как часть write-команды (шаг 6 в execution flow), после `event_store.append`.

## When To Use

Автоматически при каждой write-команде (`sdd complete T-NNN`) в SDD task session.

## Trade-offs

- Зависит от корректной работы hook на Edit/Write tools — если hook не сработал, violation не будет обнаружена.
- `write_scope` задаётся человеком в TaskSet — требует точного указания всех файлов.

## See Also

- [[trace-store]]
- [[execution-guard]]
- [[sdd-meta-harness]]
