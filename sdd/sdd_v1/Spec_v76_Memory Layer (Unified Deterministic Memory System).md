# Spec_v76 — Phase 76: Memory Layer (Unified Deterministic Memory System)

Status: Draft  
Baseline: Spec_v64 (Audit), v71 (Meta-Harness), v72 (Scenario), v74 (M9), v75 (Safety)

---

## 0. Goal

Создать **единый Memory Layer (BC-MEMORY)**, который:

- объединяет:
  - EventLog / trace (episodic memory)
  - Graph / SpatialIndex (semantic memory)
  - Harness/session memory (short-term)
- даёт **унифицированный, детерминированный API чтения/записи**
- остаётся строго совместим с:
  - event-sourcing (SSOT = EventLog)
  - Guard / Sandbox / Permissions
  - replay / determinism

---

## 1. Core Model

```text
Memory Layer =
  Episodic Memory   (EventLog, trace, Scenario, M1–M9)
  Semantic Memory   (Graph, SpatialIndex, Specs, Code)
  Working Memory    (ContextEngine / Harness session)
  Derived Memory    (projections, aggregates, patterns)
````

---

## 2. Memory Types

### 2.1 Episodic (SSOT)

```text
Source:
  - EventLog
  - trace.jsonl
  - Scenario runs
  - audit metrics (M1–M9)

Properties:
  - append-only
  - immutable
  - replayable
```

---

### 2.2 Semantic (Project Memory)

```text
Source:
  - SpatialIndex / Graph
  - Specs / Code / Docs

Properties:
  - versioned
  - structured (graph)
  - queryable
```

---

### 2.3 Working (Session Memory)

```text
Source:
  - ContextEngine
  - Harness trajectory

Properties:
  - ephemeral
  - bounded (token budget)
  - deterministic snapshot per step
```

---

### 2.4 Derived Memory

```text
Source:
  - projections from EventLog
  - aggregations (TaskMemory, AgentMemory)

Examples:
  - failure patterns
  - task summaries
  - agent performance history
```

---

## 3. Memory Scopes

```text
ProjectMemory  → весь проект (semantic + aggregated episodic)
TaskMemory     → конкретная задача (trace + summary + M1–M9)
AgentMemory    → поведение агента (cross-task)
UserMemory     → user-level preferences (optional)
SessionMemory  → текущий run (working)
```

---

## 4. Architecture / BCs

```text
src/sdd/memory/
  api.py            # unified interface
  episodic.py       # EventLog adapters
  semantic.py       # Graph/SpatialIndex adapters
  working.py        # ContextEngine integration
  derived.py        # projections & aggregates
  ingest.py         # compaction ingestion
  query.py          # unified query engine
```

---

## 5. Unified API

### Read

```python
class MemoryAPI:
    def read(self,
             scope: str,
             query: MemoryQuery) -> MemoryResult: ...
```

### Write (indirect)

```python
def ingest(events: list[Event]) -> None
# ONLY via EventLog or compaction pipeline
```

---

## 6. Query Model

```python
@dataclass(frozen=True)
class MemoryQuery:
    type: str            # episodic | semantic | derived
    scope: str           # task | project | agent | user
    filters: dict
    limit: int
    order: str           # time | relevance
```

---

## 7. Determinism Rules

I-MEM-SSOT-1  
→ EventLog MUST be the only source of truth for episodic memory

I-MEM-NO-MUTATION-1  
→ memory records immutable (no overwrite)

I-MEM-REPLAY-1  
→ Memory.read MUST return identical results under replay

I-MEM-SNAPSHOT-1  
→ working memory snapshot fixed per step

---

## 8. Ingestion Pipeline

### Bulk ingestion (compaction)

```text
trace → summary → ingest →
  → TaskMemory
  → AgentMemory
  → pattern extraction
```

### On-the-fly

```text
during execution:
  → events appended
  → no direct writes to memory
```

---

## 9. Integration with Harness

```text
Harness:
  - controls working memory
  - triggers compaction
  - calls Memory.read for context assembly
```

I-MEM-HARNESS-1  
→ ONLY harness may access Memory API

---

## 10. Integration with ContextEngine

```text
Context = f(
  Memory.read(episodic),
  Memory.read(semantic),
  Memory.read(derived)
)
```

I-MEM-CONTEXT-1  
→ context MUST be built only via Memory API

---

## 11. Permissions & Safety

I-MEM-SCOPE-1  
→ Memory.read MUST enforce allowed scope

I-MEM-NO-LEAK-1  
→ cross-task access запрещён без разрешения

I-MEM-GUARD-1  
→ all memory queries validated by Guard

---

## 12. Event-Driven Model

```text
EventLog → projections → Memory views
```

I-MEM-PROJECTION-1  
→ all derived memory MUST be projection of events

---

## 13. Anti-Patterns (forbidden)

```text
❌ direct DB writes
❌ mutable memory state
❌ bypassing EventLog
❌ ad-hoc vector stores outside system
```

---

## 14. DoD

-  MemoryAPI реализован
    
-  Episodic = EventLog only
    
-  Semantic = Graph only
    
-  Derived = projections only
    
-  ContextEngine использует MemoryAPI
    
-  Replay даёт идентичные результаты
    
-  Guard проверяет все запросы
    
-  Нет прямых write-path кроме EventLog
    

---

## 15. Summary

```text
Memory Layer в SDD:

НЕ отдельная БД,
а унифицированный слой над:

- EventLog (episodic)
- Graph (semantic)
- Harness (working)

Принципы:
- memory = event stream + projections
- read-only через API
- deterministic & replayable

Результат:
агенты получают единый способ "помнить",
а система остаётся строгой, проверяемой и расширяемой
```