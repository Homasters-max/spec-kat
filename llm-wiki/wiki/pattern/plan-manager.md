---
id: pattern/plan-manager
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- validation
- write-path
- automation
- domain/sdd
version: 2
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SDD_Bounded_Contexts_Plan.md
- raw/Wiki Skill DocGraph Integration Plan.md
---
# PlanManager

**[proposed]** L2-компонент Blueprint-домена: строит и валидирует детерминированный граф исполнения фазы. Единственный потребитель `DocGraphInput` из `sync-wiki` pipeline.

## How It Works

**Входной шов — DocGraphInput (Q17):**

```python
@dataclass
class DocGraphInput:
    nodes: list[DocGraphNode]
    current_projection: EventLogProjection
```

PlanManager принимает `DocGraphInput` от [[doc-graph-validator]] и вычисляет diff относительно `current_projection`. Нет прямого чтения wiki-файлов (I-PM-INPUT-1). `Plan_vN.md` и `TaskSet_vN.md` заменены `DocGraphInput` как входной формат.

**Dependency DAG:** задачи — это DAG, не список. Зависимости enforced при построении. Циклические зависимости → reject.

**Scope Isolation:** вычисляет `write_scope` для каждой задачи → `TaskScopeProjection` (используется [[sandbox-manager]] для изоляции).

**Conflict Detection:** запрещает параллельные задачи с пересекающимися `write_scope`.

```text
DocGraphInput → PlanManager
  ├─ diff vs current_projection
  ├─ validate mutation matrix
  ├─ compute write_scope per task
  ├─ detect write_scope conflicts (parallel tasks)
  ├─ emit PlanCreated | delta events
  ├─ emit GraphVersionRecorded {version: hash(event_pos)}
  └─ update TaskScopeProjection
```

**GraphVersion (I-PM-GRAPHVER-1):** каждый успешный sync записывает `GraphVersionRecorded { version: hash(event_pos) }`. Используется для fingerprint в [[graph-query-engine]].

**Матрица допустимых мутаций (Q2):**

| Операция                    | Разрешено?                        |
|-----------------------------|-----------------------------------|
| Добавить узел               | Да                                |
| Переименовать (`name`)      | Да                                |
| Изменить `depends`          | Только до `TaskSpawned`           |
| Удалить узел                | Запрещено после `TaskSpawned`     |
| Изменить `part_of`          | Требует DAG проверки              |
| Изменить `scope`            | Только до `TaskStarted`           |

`TaskScopeProjection` читается Engine через `memory.blueprint.read.task_scope(task_id)`.

## When To Use

При создании/обновлении плана фазы через `sdd sync-wiki`. Единственный путь к `PlanCreated` event и `TaskScopeProjection`.

## Trade-offs

- DAG-структура сложнее simple list, но предотвращает undefined execution order.
- DocGraphInput как входной шов изолирует PlanManager от деталей wiki-формата.

## See Also

- [[sdd-bounded-contexts]] — Blueprint domain, L2
- [[doc-graph-parser]] — поставляет DocGraphInput
- [[doc-graph-validator]] — валидирует перед PlanManager
- [[sync-wiki]] — pipeline-оркестратор
- [[phase-orchestrator]] — читает TaskScopeProjection
- [[sandbox-manager]] — потребитель TaskScopeProjection
- [[memory-layer]] — `memory.blueprint.read.task_scope(task_id)`
