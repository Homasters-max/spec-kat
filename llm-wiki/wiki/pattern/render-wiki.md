---
id: pattern/render-wiki
page_type: pattern
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
# render-wiki

Обратная проекция EventLog → Wiki. Автоматически запускается после каждого commit в EventLog. Обновляет только EventLog-owned поля в DocGraph-узлах, не трогая человеческий контент.

## How It Works

**Триггер:** auto после каждого commit в EventLog (как projection rebuild, Q7).

**Atomic directory versioning (Q13, I-WIKI-ATOMIC-1):**

```text
EventLog commit
  └─ render-wiki
       ├─ writes: /wiki/tmp_vN/
       ├─ fsync
       ├─ rename → /wiki/vN/
       └─ update pointer (current_version)
```

**Что пишет (EventLog-owned):**
- `status` — текущий статус задачи/фазы из EventLog
- `blocked_by` — derived: список блокирующих незавершённых зависимостей

**Что НЕ трогает (Human-owned):**
- `id`, `name`, `type`, `depends`, `part_of`, `affects`, `scope`
- весь prose (Summary, Acceptance Criteria, Notes)

Нарушение — `I-WIKI-OWNERSHIP-1`.

**Modes:**
- `eager` (default): после каждого commit
- `batched`: каждые N events (для снижения I/O при bulk operations)

**GC (`I-WIKI-GC-1`):** хранить последние N snapshots (default=10), старые удалять.

**domain-узлы:** render-wiki никогда их не трогает (нет EventLog-owned полей).

## When To Use

Не вызывается вручную. Автоматическая часть EventLog pipeline. Результат читается через [[wiki-snapshot-loader]].

## Trade-offs

- Атомарный rename (`tmp_vN → vN`) гарантирует что читатели никогда не видят неполный snapshot.
- `eager` mode создаёт snapshot на каждый commit — дополнительная нагрузка на диск при высокой частоте событий.

## See Also

- [[wiki-snapshot-loader]]
- [[sync-wiki]]
- [[doc-graph-node]]
- [[docgraph-dual-ssot]]
