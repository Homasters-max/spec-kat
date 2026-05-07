---
id: pattern/test-catalog-projection
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- validation
- ssot
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/replay-based-testing-architecture.md
---
# TestCatalogProjection

L1-Projection: индекс тестов, сгруппированных по `affected_commands` и `affected_projections`. Хранится в [[projection-registry]] с подпиской через command names. Центральный компонент [[trace-aligned-test-partitioning]] (TATP).

## How It Works

```python
@dataclass
class TestCatalogEntry:
    test_id: str                      # "G-T-034" | "S-abc123"
    test_type: TestType               # GOLDEN | SCENARIO | ADVERSARIAL
    affected_projections: list[str]
    affected_commands: list[str]      # автовывод при golden-approve (I-REPLAY-13)
    scope: dict                       # {"phase_id": 3}

class TestCatalogProjection:
    subscribed_commands = {
        "golden-approve",   # → GoldenFixtureApproved
        "complete-task",    # → ScenarioGenerated (только при COMPLETE)
        "update-policy",    # → PolicyUpdated
        "activate-phase",   # → PhaseInitialized
    }

    def handle(self, event: Event) -> None:
        if event.type == "GoldenFixtureApproved":
            self._index_golden(event)
        elif event.type == "ScenarioGenerated":
            self._index_scenario(event)
        ...

    def filter(
        self,
        commands: list[str] | None = None,
        projections: list[str] | None = None,
        phase_id: int | None = None,
    ) -> list[TestCatalogEntry]: ...
```

**Автовывод `affected_commands` при `golden-approve` (AD-8):**

```python
event_types = {e.type for e in fixture.task_events}
affected_commands = REGISTRY.inverse_lookup(event_types)          # event_type → command
affected_projections = ProjectionRegistry.projections_for(affected_commands)
```

Нулевой ручной труд — не рассинхронизируется с кодом.

## `sdd test --diff` — TATP алгоритм (AD-6)

```bash
sdd test --diff HEAD~1
```

1. `git diff --name-only HEAD~1` → изменённые файлы
2. CommandSpec changes → `changed_commands` (приоритет)
3. `handler_registry.yaml` lookup → дополнительные `changed_commands`
4. `ProjectionRegistry.subscribed_commands` → `changed_projections`
5. `TestCatalog.filter(commands=changed_commands)` → N релевантных тестов
6. [[replay-engine]] запускает только их

```yaml
# handler_registry.yaml
src/sdd/handlers/write.py: write
src/sdd/handlers/resolve.py: resolve
src/sdd/guards/execution_guard.py: [write, resolve, explain]
```

## Три bounded context домена

| Домен | affected_projections | Sandbox | Скорость |
|-------|---------------------|---------|----------|
| L0 Core | `["StateProjection"]` | in-memory | миллисекунды |
| L1 Execution | `["TraceProjection", "GraphSessionProjection"]` | temp PostgreSQL | секунды |
| L2 Governance | `["PolicyProjection"]` | full SandboxManager | минуты |

## When To Use

`sdd test --diff HEAD~1` — developer flow перед коммитом. Tier 3 фильтрация через TestCatalog встроена в [[audit-engine]].calculate_M9() (I-REPLAY-9).

## Trade-offs

- Projection обновляется атомарно с EventLog — eventual consistency не применима (I-REPLAY-9)
- `handler_registry.yaml` — ручная синхронизация с файловой структурой handlers

## See Also

- [[projection-registry]]
- [[replay-based-testing]]
- [[replay-engine]]
- [[golden-fixture]]
- [[audit-engine]]
- [[memory-layer]]
