---
id: pattern/doc-graph-parser
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- validation
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/Wiki Skill DocGraph Integration Plan.md
---
# DocGraphParser

Первый компонент `sync-wiki` pipeline: читает wiki-файлы с `type: task|phase`, парсирует frontmatter DSL и возвращает типизированные узлы для валидации и компиляции в EventLog.

## How It Works

```text
wiki-files (type: task|phase) → DocGraphParser → list[DocGraphNode]
                                                ↓
                                   + current_projection: EventLogProjection
                                                ↓
                                         DocGraphInput
```

**Что делает:**
- Сканирует wiki-файлы с `type: task` или `type: phase` в frontmatter
- Игнорирует файлы с `type: domain` (не компилируются в EventLog — I-DOCGRAPH-DOMAIN-1)
- Парсирует frontmatter DSL → валидированные `DocGraphNode`
- Читает текущую `EventLogProjection` (для diff-вычисления в PlanManager)

**Output:**

```python
@dataclass
class DocGraphInput:
    nodes: list[DocGraphNode]
    current_projection: EventLogProjection
```

**Валидация обязательных полей:** `id`, `name`, `type`, `depends`, `part_of`. Отсутствие → reject с ошибкой.

## When To Use

Вызывается только из `sync-wiki` pipeline. Не вызывается напрямую; входная точка — команда `sdd sync-wiki`.

## Trade-offs

- Парсинг только `task|phase` (не `domain`) — преднамеренное разделение: domain-узлы обрабатывает `WikiSemanticExtractor` через prose, не структуру.
- Строгая валидация обязательных полей fail-fast предотвращает частичную компиляцию.

## See Also

- [[doc-graph-validator]]
- [[plan-manager]]
- [[doc-graph-node]]
- [[sync-wiki]]
