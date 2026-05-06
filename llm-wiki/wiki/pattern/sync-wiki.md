---
id: pattern/sync-wiki
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- write-path
- automation
- git
- domain/sdd
version: 2
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/Wiki Skill DocGraph Integration Plan.md
---
# sync-wiki

Команда компиляции DocGraph-узлов из Wiki в EventLog. **Human gate**: явная операция, не авто-триггер (Q11). Обязательна перед `activate-phase`.

## How It Works

```text
sdd sync-wiki
  └─ DocGraphParser         # читает wiki/*.md (type: task|phase)
       └─ DocGraphValidator # проверяет DAG инварианты
            └─ PlanManager  # вычисляет diff vs текущей EventLogProjection
                 └─ WriteKernel  # emits events атомарно
```

**Атомарность (`I-GRAPH-SYNC-ATOMIC-1`):** либо все команды emitted, либо ни одной. Нет частичного применения.

**Сериализация (`I-SYNC-SERIAL-1`):** нельзя параллельно запускать `sync-wiki` для одного graph.

**Идемпотентность:** PlanManager читает текущую `EventLogProjection` → emits только для diff. Повторный sync без изменений = no-op.

> **Дизайн-решение (Q8):** `idempotent=True` не используется — ключ идемпотентности по `node_id` потребовал бы расширения модели данных.

**Events, записываемые в EventLog:**
- `SyncWikiExecuted { phase_id, event_pos, wiki_files_hash }` (Q19) — читается PhaseOrchestrator для freshness check
- `GraphVersionRecorded` (Q17, I-PM-GRAPHVER-1) — версионирует граф

## When To Use

1. После создания/изменения структурных полей DocGraph-узлов (`depends`, `part_of`, `scope`)
2. Перед `activate-phase` — обязателен (I-SYNC-FRESHNESS-1)
3. PhaseOrchestrator блокирует `activate-phase` при нарушении freshness (Q19)

**LLM напоминает, но не запускает.** `sync-wiki` — исключительно human gate.

## Trade-offs

- Явный human gate даёт полный контроль над моментом компиляции, но требует дисциплины (не забыть запустить перед activate-phase).
- Атомарность защищает от частичного применения, но означает что крупные изменения = один большой атомарный коммит.
- **Отклонённые альтернативы (Q11):** auto-on-session-start — рискует применить незавершённые правки Wiki; file watcher — ломает атомарность компиляции (нет контроля момента).

## See Also

- [[doc-graph-parser]]
- [[doc-graph-validator]]
- [[plan-manager]]
- [[render-wiki]]
- [[phase-orchestrator]]
- [[docgraph-dual-ssot]]
