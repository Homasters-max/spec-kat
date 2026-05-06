---
id: pattern/context-kernel
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- search
- llm
- ssot
- domain/sdd
version: 4
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
---
# Context Kernel

L1-компонент: строит контекстный пакет для LLM по гибридной Push+Pull модели.

## How It Works

```text
Push (обязательный базовый контекст):
  - граф текущей задачи (QueryEngine.execute(explain_query(task_id)))
  - write_scope текущей задачи
  - текущий статус фазы + задачи из ReadModel
  - policy (behavioral rules из [[policy-projection]] через memory.read.policy())

Pull (по запросу LLM):
  - LLM вызывает resolve → QueryEngine расширяет контекст
  - LLM вызывает explain → ExecutionGuard фиксирует graph_fingerprint
  - RAG (L2): historical traces + extended read context
```

**Интерфейс:**

```python
class ContextKernel:
    def build_base(self, task_id: str, snapshot_loader: WikiSnapshotLoader) -> ContextPacket: ...
    def handle_pull(self, cmd: ResolveCommand) -> ContextSnapshot: ...
```

**AgentLoop контракт (строгий порядок, Q18):**

```text
Step 1: EventLog.read(event_pos)               → получить event_pos
Step 2: WikiSnapshotLoader.load_at(event_pos)  → получить wiki snapshot
Step 3: assert projection.event_pos == snapshot.event_pos  (I-SNAPSHOT-ALIGN-1)
Step 4: WikiSemanticExtractor.extract(node_id, snapshot) → SemanticContext
```

`ContextPacket` — это то что подаётся в `AgentHandle.step()` как system context. LLM не может запросить контекст вне разрешённых каналов (Pull строго через tool calls).

**Ограничения на Pull:**

- LLM может запросить только то что разрешает scope_policy
- Запросы логируются в TraceStore
- L2 RAG вызывается через CommandBus, не напрямую

## When To Use

Вызывается Session Orchestrator'ом при старте сессии (Push) и при каждом `resolve` tool call (Pull).

## Trade-offs

- Push гарантирует минимум контекста, но может содержать избыточное.
- Pull позволяет LLM уточнить, но каждый Pull = дополнительный round-trip через CommandBus.

## See Also
- [[wiki-snapshot-loader]]
- [[wiki-semantic-extractor]]

- [[graph-query-engine]]
- [[memory-layer]]
- [[policy-projection]]
- [[context-snapshot]]
- [[execution-guard]]
- [[input-port]]
- [[session-orchestrator]]

## Open Questions

- [ ] (P1) Q72: Ограничение токенов на ContextPacket? Кто enforces? Что если budget exceeded?
- [ ] (P1) Q73 PARTIAL: Алгоритм приоритизации данных в context при нехватке бюджета? push+pull есть, алгоритм не формализован.
- [ ] (P1) Q74: Когда context считается stale? Только при graph change или также при state change?
- [ ] (P1) Q76: Разрешено ли включать внешние источники (web, API) в context? Как они влияют на детерминизм?
- [ ] (P1) Q77: Может ли context одного TaskRun "протечь" в другой через shared projections?
- [ ] (P1) Q78: Как сравнить два context? Инструмент для debugging context changes между TaskRuns?

## Decisions

- [x] (P1) Q75: Context воспроизводим через paired snapshots (event_pos + wiki_snapshot_version = I-SNAPSHOT-ALIGN-1) → [[wiki-snapshot-loader]]
- [x] (P1) Q71: Context boundary — ContextPacket = seam между Stage 0 и Stage 1 → [[context-packet]]
