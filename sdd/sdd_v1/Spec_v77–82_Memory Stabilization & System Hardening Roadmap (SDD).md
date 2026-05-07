Spec_v77–82 — Memory Stabilization & System Hardening Roadmap (SDD)

Goal:
Сделать Memory Layer (Spec_v76) не просто хранилищем, а:
- управляемым (governance),
- проверяемым (contracts/tests),
- воспроизводимым (DiagnosticFS),
- безопасным (safety),
- интегрированным в Meta-Harness (self-improvement loop).

Это слой стабилизации всей системы, а не новая функциональность.

---

## Phase 77 — Memory Governance & Retention

BC-MEM-GOV

Задача: контроль объёма, времени жизни и удалений.

Core:

- Retention policies:
  - TaskMemory: TTL (short)
  - AgentMemory: medium TTL
  - ProjectMemory: long / ∞
- Storage tiers:
  - HOT: JSONL / in-memory
  - WARM: DuckDB / Parquet
  - COLD: archive (compressed)

- Deletion:
  - soft-delete через EventLog (tombstone)
  - исключение из всех Derived projections

- Quotas:
  - per project / agent / user
  - trigger → compaction / summarization / archive

Invariants:

- I-MEM-GOV-1: Memory = append-only + derived projections (no overwrite)
- I-MEM-DELETE-1: delete request MUST propagate to all projections
- I-MEM-AUDIT-1: любой Memory.read объясним (source events)

---

## Phase 78 — Memory Query Contracts & Testing

BC-MEM-CONTRACT

Задача: сделать память детерминированным API с тестами.

Core:

- Typed queries:
  - EpisodicQuery(task_id, time_range)
  - SemanticQuery(nodes, relations)
  - DerivedQuery(type, filters)

- Strict schemas:
  - MemoryResult v1/v2 (versioned)

- Retrieval test suite:
  - (query → expected events/ids)

Invariants:

- I-MEM-CONTRACT-1: каждый query type имеет фиксированную схему
- I-MEM-REGRESSION-1: изменения Memory запрещены без прохождения retrieval tests
- I-MEM-VERSION-1: backward compatibility через versioned results

---

## Phase 79 — DiagnosticFS (Filesystem View of Memory)

BC-DIAG-FS

Задача: сделать память доступной как файловую систему (для Meta-Harness и debugging).

Core:

- Virtual FS (read-only projection):
  /tasks/T-NNN/trace.jsonl
  /tasks/T-NNN/summary.json
  /harnesses/run_id/candidate_id/*
  /agents/<agent_id>/stats.json

- CLI:
  - mh list
  - mh show-trace
  - mh diff

Invariants:

- I-FS-CONSIST-1: FS = pure projection(EventLog + Memory)
- I-FS-READONLY-1: никаких write операций
- I-FS-STABLE-1: структура стабильна по версиям
- I-FS-GUARD-1: Guard/permissions применяются

---

## Phase 80 — Memory-Aware Context Engine

BC-CTX-MEM

Задача: контролируемая сборка контекста из памяти.

Core:

- Context = f(Memory.read(...)) с paging:
  - Memory = disk
  - Context window = RAM

- Post-filtering:
  - relevance scoring
  - deduplication
  - anti-noise

- Profiles:
  - latency-optimized
  - recall-optimized
  - balanced

- Structured output:
  - system fragments
  - history snippets
  - tool inputs

Invariants:

- I-CTX-MEM-1: Context формируется только через Memory API
- I-CTX-POSTFILTER-1: raw MemoryResult не попадает напрямую в prompt
- I-CTX-DETERMINISM-1: одинаковый input → одинаковый context

---

## Phase 81 — Memory Safety & Governance

BC-MEM-SAFE

Задача: защита памяти как attack surface.

Core:

- Access control:
  - scope-based (project/user/agent/task)

- Redaction:
  - field-level masking
  - sensitive data filtering

- Injection protection:
  - sanitize retrieved content
  - block instructions leaking into system prompt

- Audit:
  - log every Memory.read

Invariants:

- I-MEM-MULTI-1: cross-tenant mixing запрещено
- I-MEM-SANITIZE-1: retrieved memory не может менять system behavior напрямую
- I-MEM-AUDIT-LOG-1: каждый read логируется
- I-MEM-LEAK-1: Derived не может утекать вне scope

---

## Phase 82 — Meta-Memory & Self-Evaluation

BC-MEM-META

Задача: сделать память измеримой и оптимизируемой.

Core:

- Metrics:
  - M-MEM-COVERAGE (сколько релевантных событий найдено)
  - M-MEM-LATENCY
  - M-MEM-COST
  - M-MEM-RECALL-QUALITY

- Diagnostics:
  - missing memory detection
  - stale memory detection

- Meta-Harness hooks:
  - read-only доступ к Memory + DiagnosticFS
  - оптимизация retrieval стратегии

- Explainability:
  - "почему это попало в контекст"
  - trace → memory → context mapping

Invariants:

- I-MEM-META-1: memory metrics считаются детерминированно
- I-MEM-EXPLAIN-1: любой context explainable через Memory
- I-MEM-HARNESS-1: Meta-Harness имеет только read-only доступ

---

## System-Level Guarantees (итог)

После Phase 77–82:

1. Memory НЕ ломает SDD:
   - read-only через API
   - EventLog остаётся SSOT

2. Memory управляем:
   - retention + quotas + deletion

3. Memory проверяем:
   - retrieval tests + contracts

4. Memory воспроизводим:
   - DiagnosticFS + replay

5. Memory безопасен:
   - guard + sanitize + audit

6. Memory участвует в self-improvement:
   - Meta-Harness использует его как источник truth

---

## Ключевая идея

Memory = не база данных  
Memory = детерминированная проекция EventLog + Graph  
Memory API = единственная точка доступа  
Context = строго контролируемая выборка Memory  
Meta-Harness = оптимизатор над этим слоем  

→ это делает SDD системой с управляемой памятью, а не «логами + RAG».