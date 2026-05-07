---
id: idea/doc-graph-node
page_type: idea
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- write-path
- ssot
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/Wiki Skill DocGraph Integration Plan.md
---
# DocGraph Node

Базовая единица DocGraph — узел исполнения или семантического кластера в SDD. Каждый wiki-файл с полем `type: domain|phase|task` является DocGraph-узлом.

## Summary

DocGraph-узлы имеют два принципиально разных жизненных цикла:

- **Wiki lifecycle** (до `sync-wiki`): Wiki = единственный источник структуры; узлы Draft/Approved
- **SDD lifecycle** (после `sync-wiki`): EventLog = источник структуры; Wiki = источник семантики (prose)

## Node Types

| `type`   | Префикс ID | Компилируется в EventLog? | Имеет `status`? | Роль                   |
|----------|------------|---------------------------|-----------------|------------------------|
| `domain` | `d-`       | Нет                       | Нет             | Semantic cluster       |
| `phase`  | `p-`       | Да                        | Да              | Execution boundary     |
| `task`   | `t-`       | Да                        | Да              | Atomic work item       |

Иерархия: `domain → phase → task` (через поле `part_of`).

## Frontmatter Schema

Точная схема для `type: task|phase`:

```yaml
id: t-<slug>         # immutable slug (node_id); kebab-case
name: "Title"        # mutable display name
type: task           # task | phase
status: OPEN         # EventLog-owned — render-wiki пишет, LLM никогда не трогает
blocked_by: []       # EventLog-owned — render-wiki пишет автоматически
depends: []          # DAG edges; FROZEN после TaskSpawned
part_of: p-<id>      # родительский узел
affects: []          # traceability hints (P5, lowest priority)
scope: []            # empty = наследует от phase; FROZEN после TaskStarted
```

Для `type: domain` — только `id`, `name`, `type` (поля `status`, `blocked_by`, `depends`, `scope` ЗАПРЕЩЕНЫ — I-DOCGRAPH-DOMAIN-2).

## Field Ownership

| Поле         | Владелец  | Пишет              | LLM может редактировать?     |
|--------------|-----------|--------------------|------------------------------|
| `id`         | Human     | Human (один раз)   | Никогда                      |
| `name`       | Human     | Human              | Да (переименование)          |
| `type`       | Human     | Human (один раз)   | Никогда                      |
| `status`     | EventLog  | render-wiki        | Никогда                      |
| `blocked_by` | EventLog  | render-wiki        | Никогда                      |
| `depends`    | Human     | Human (до spawn)   | Только до TaskSpawned        |
| `part_of`    | Human     | Human              | Требует DAG проверки         |
| `affects`    | Human     | Human              | Да                           |
| `scope`      | Human     | Human (до start)   | Только до TaskStarted        |

Нарушение ownership → `I-DOCGRAPH-OWNED-1`.

## When To Use

Создавать DocGraph-узлы при проектировании нового плана фазы. `type: domain` — семантический кластер без компиляции в EventLog. `type: phase|task` — исполняемые узлы, требуют `sdd sync-wiki` после создания.

## Trade-offs

- Immutable `id` (slug) даёт стабильные ссылки из EventLog и между узлами, но требует продуманного именования при создании.
- EventLog-owned поля (`status`, `blocked_by`) автоматически актуальны, но создают зависимость от `render-wiki` для отображения состояния.

## See Also

- [[sync-wiki]]
- [[render-wiki]]
- [[doc-graph-parser]]
- [[docgraph-dual-ssot]]
