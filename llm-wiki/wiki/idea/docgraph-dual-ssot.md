---
id: idea/docgraph-dual-ssot
page_type: idea
domain: sdd
layer: architecture
tags:
- ssot
- pipeline
- enforcement
- automation
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/Wiki Skill DocGraph Integration Plan.md
---
# DocGraph Dual SSOT

Ключевой архитектурный принцип DocGraph (Q1, Q6, Q20): разные источники истины для структуры и семантики, переключающиеся в момент `sync-wiki`.

## Summary

В DocGraph нет единого SSOT — есть два источника с чётким разделением ответственности и временным переключением авторитета:

**До `sync-wiki`:**
```
Wiki = SSOT для структуры (единственный источник намерения)
```

**После `sync-wiki`:**
```
EventLog = SSOT для структуры (status, deps, blocked_by)
Wiki     = SSOT для семантики (prose: Summary, Criteria, Notes)
```

**Правило конфликтов (post-sync):** EventLog ALWAYS wins для структурных данных.

## Enforcement Points

Три точки принуждения (Q20):

**1. QueryEngine — разделение адаптеров:**
```
EventExtractor    → структура (status, deps)       из EventLog
WikiSemanticExtractor → семантика (prose, intent)  из WikiSnapshot
```
Источники не пересекаются (I-QE-ADAPTER-1/2).

**2. PlanManager — только typed input:**
- Входной шов: `DocGraphInput` (из wiki до sync)
- После компиляции: только `EventLogProjection`
- Нет прямого чтения wiki-файлов (I-PM-INPUT-1)

**3. ContextKernel — aligned snapshots:**
```
projection.event_pos == snapshot.event_pos  (I-SNAPSHOT-ALIGN-1)
```

## Declared Invariants

- `I-GRAPH-SSOT-2`: Wiki = semantic SSOT; EventLog = structural SSOT (post-sync)
- `I-NO-DUAL-GRAPH-1`: нельзя строить граф одновременно из Wiki и EventLog
- `I-RUNTIME-NO-WIKI-1`: runtime компоненты читают wiki только через WikiSnapshotLoader

## When To Use

Этот принцип применяется везде, где компонент работает с DocGraph-данными. При неясности: "откуда брать статус задачи?" — ответ EventLog (post-sync). "Откуда брать описание задачи?" — ответ Wiki.

## Trade-offs

- Двойной SSOT требует чёткого понимания "когда переключился авторитет" — документировано через `sync-wiki` как явный gate.
- Aligned snapshots (I-SNAPSHOT-ALIGN-1) добавляют строгость, но предотвращают context skew между структурой и семантикой.

## See Also

- [[sync-wiki]]
- [[render-wiki]]
- [[graph-query-engine]]
- [[plan-manager]]
- [[context-kernel]]
