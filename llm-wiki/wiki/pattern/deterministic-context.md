---
id: pattern/deterministic-context
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- ssot
- write-path
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/SDD Architectural Hardening — CQRS EventLog Guard Idempotency.md
---
# Deterministic Context

`build_context` — чистая функция от Snapshot. Детерминизм гарантирует: одинаковый snapshot → одинаковый `ContextPacket`; тест без моков времени и сети.

## How It Works

```python
def build_context(task_id: str, snapshot: State) -> ContextPacket:
    """
    Pure function.
    snapshot = reduce(EventLog[0:N]) — несёт version для OCC.
    MUST NOT call datetime.now(), random.*, network, DB.
    """
```

Snapshot передаётся снаружи — от [[write-kernel]] или SessionOrchestrator:

```python
snapshot = reduce(event_store.load(up_to=N))
packet   = build_context(task_id, snapshot)
```

**Optional memoization** с инвалидацией по `snapshot.version`:

```python
_cache: dict[int, ContextPacket] = {}

def build_context(task_id: str, snapshot: State) -> ContextPacket:
    if snapshot.version in _cache:
        return _cache[snapshot.version]
    result = _compute(task_id, snapshot)
    _cache[snapshot.version] = result
    return result
```

**Отлаживаемость:**

```python
# Воспроизвести контекст на момент события N:
replay_context(task_id, N) = build_context(task_id, reduce(EventLog[0:N]))
```

**Инварианты:**

```text
I-CTX-DET-1: identical snapshot → identical ContextPacket
             build_context(task_id, s_a) == build_context(task_id, s_b) если s_a == s_b
I-CTX-DET-2: build_context MUST NOT call datetime.now(), random.*, network, DB
```

## When To Use

Вызывается [[write-kernel]] или SessionOrchestrator перед передачей контекста в LLM-агент. Также используется в [[replay-based-testing]] для воспроизводимости тестовых сценариев.

## Trade-offs

- Чистота функции = тестируемость без времени и сети
- Memoization по version — O(1) для повторных вызовов с тем же snapshot
- Snapshot может содержать весь EventLog в памяти — tradeoff при больших логах

## See Also

- [[write-kernel]]
- [[cqrs-boundary]]
- [[replay-based-testing]]
- [[event-sourcing]]
