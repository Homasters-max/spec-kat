---
id: pattern/wiki-docgraph
page_type: pattern
domain: wiki
layer: architecture
tags:
- pipeline
- write-path
- llm
- automation
- domain/wiki
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SKILL.md
---
# Wiki DocGraph

## Summary
Протокол создания и редактирования [[doc-graph-node]] execution-узлов в wiki. Отличается от knowledge pages (`page_type: idea|pattern|tool`) схемой frontmatter и жизненным циклом — структурные поля owned EventLog'ом, prose редактируется вручную (I-DOCGRAPH-FM-1).

## How It Works

**Таблица типов узлов:**

| `type` | Префикс ID | Компилируется в EventLog? | Роль |
|--------|------------|---------------------------|------|
| `domain` | `d-` | Нет | Semantic cluster |
| `phase` | `p-` | Да | Execution boundary |
| `task` | `t-` | Да | Atomic work item |

**Поля-владельцы (критично):**

| Поле | Владелец | LLM может редактировать? |
|------|----------|--------------------------|
| `id` | Human | Никогда (immutable slug) |
| `status` | EventLog | Никогда (`render-wiki` пишет) |
| `blocked_by` | EventLog | Никогда (`render-wiki` пишет) |
| `depends` | Human | Только до TaskSpawned |
| `scope` | Human | Только до TaskStarted |
| `name`, `affects` | Human | Да |

**Режим A — создание execution-узла (task / phase):**

```yaml
---
id: t-<slug>
name: "Title"
type: task
status: OPEN         # ⛔ EventLog-owned
blocked_by: []       # ⛔ EventLog-owned
depends: []
part_of: p-<id>
affects: []
scope: []
---
```

После создания → напомнить: `sdd sync-wiki` обязателен перед `activate-phase` (I-SYNC-FRESHNESS-1).

**Режим B — создание domain-узла (semantic-only):**

```yaml
---
id: d-<slug>
name: "Domain Name"
type: domain
# ЗАПРЕЩЕНЫ: status, blocked_by, depends, scope (I-DOCGRAPH-DOMAIN-2)
---
```

Domain-узлы `sync-wiki` пропускает. После создания — `sync-wiki` не нужен.

**Режим C — редактирование prose существующего узла:**

```bash
wiki show <node-id>
# если меняется только prose → runtime/tmp/<node-id>.diff.md (только prose секции)
# если меняются структурные поля → предупредить: запрещено после TaskSpawned
wiki apply-drafts
```

## When To Use
- Создание новой задачи или фазы в DocGraph
- Редактирование Summary / Acceptance Criteria существующего узла
- Создание domain-узла для семантической группировки

## Trade-offs
- `status` и `blocked_by` НЕЛЬЗЯ редактировать вручную — `render-wiki` перезапишет (I-DOCGRAPH-OWNED-1)
- `depends` frozen после TaskSpawned — структурные изменения невозможны после старта (I-GRAPH-DEP-IMMUT-1)
- Prose и структура живут в разных SSOT: prose → wiki files; структура → EventLog ([[docgraph-dual-ssot]])
- [[wiki-semantic-extractor]] читает prose из WikiSnapshot, не напрямую из файлов (I-DOCGRAPH-PROSE-1)

## See Also
- [[doc-graph-node]]
- [[sync-wiki]]
- [[docgraph-dual-ssot]]
- [[wiki-semantic-extractor]]
