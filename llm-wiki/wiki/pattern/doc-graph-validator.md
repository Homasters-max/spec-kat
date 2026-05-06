---
id: pattern/doc-graph-validator
page_type: pattern
domain: sdd
layer: architecture
tags:
- validation
- pipeline
- automation
- enforcement
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/Wiki Skill DocGraph Integration Plan.md
---
# DocGraphValidator

Второй компонент `sync-wiki` pipeline: принимает `list[DocGraphNode]` от [[doc-graph-parser]] и применяет структурные инварианты DAG перед передачей в [[plan-manager]].

## How It Works

```text
DocGraphInput → DocGraphValidator → validated DocGraphInput
                      ↓ (на ошибке)
                 sync-wiki прерывается, EventLog не изменяется
```

**Enforced проверки v1 (Q15, I-INVARIANT-META-1):**

| Инвариант              | Что проверяет                                              |
|------------------------|------------------------------------------------------------|
| `I-GRAPH-ACYCLIC-1`    | DAG validation: нет циклов в `depends` + `part_of`        |
| `I-GRAPH-SYNC-1`       | Reject destructive diffs (удаление узла после spawn)      |
| `I-GRAPH-DEP-IMMUT-1`  | `depends` frozen после `TaskSpawned`: изменение → reject  |

**Матрица допустимых изменений (Q2):**

| Операция                      | Разрешено?                           |
|-------------------------------|--------------------------------------|
| Добавить новый узел            | Да                                   |
| Переименовать узел (`name`)    | Да (только `name`, не `id`)          |
| Изменить `depends`             | Только до `TaskSpawned`              |
| Удалить узел                   | Запрещено после `TaskSpawned`        |
| Изменить `part_of`             | Требует DAG проверки (нет циклов)    |
| Изменить `scope`               | Только до `TaskStarted`              |

## When To Use

Вызывается только из `sync-wiki` pipeline, между `DocGraphParser` и `PlanManager`. Не bypass-ится: атомарность `I-GRAPH-SYNC-ATOMIC-1` означает что при ошибке валидации весь sync отменяется.

## Trade-offs

- Fail-fast на любой инвариант: нет частичного применения, нет rollback после частичной записи.
- Enforced-only инварианты v1 (из Q15) — расширяемы без изменения core pipeline.

## See Also

- [[doc-graph-parser]]
- [[plan-manager]]
- [[sync-wiki]]
- [[write-kernel]]
