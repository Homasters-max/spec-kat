
# **DocGraph Orchestration (SDD)**

## 0. Goal

Ввести **DocGraph Orchestration** — механизм, позволяющий:

* описывать план разработки как **граф документов (Wiki)**
* компилировать этот граф в **EventLog (SSOT)**
* управлять исполнением через **детерминированный Execution Graph**

DocGraph = **Intent DSL**, НЕ runtime.

---

## 1. Scope

Включает:

* Wiki-документы (Obsidian)
* DocGraph parsing / validation
* PlanManager compilation pipeline
* ContextKernel graph expansion

Не включает:

* UI/UX Obsidian
* LLM prompting детали
* конкретные storage реализации

---

## 2. Core Model

### 2.1 Dual Graph Model

```text
Intent Graph (Wiki)        — editable, may be inconsistent
Execution Graph (EventLog) — SSOT, deterministic
```

---

### 2.2 SSOT Rule

```text
EventLog = single source of truth
Wiki     = derived / cached intent
```

---

## 3. Entity Model (Fractal)

Все сущности имеют единый lifecycle:

```text
Draft → Approved → InProgress → Done
```

### Типы узлов:

```text
Domain  (D-*) — верхний уровень
Phase   (P-*) — orchestration unit
Task    (T-*) — execution unit
```

---

## 4. DocGraph DSL (Wiki Format)

## 4.1 Manifest (обязательный)

```yaml
---
id: T-Login-Endpoint
type: task
status: OPEN

depends:
  - T-JWT-Generation

part_of: P-Auth-Core

affects:
  - T-Security-Middleware
---
```

---

## 4.2 Free Text

Используется только для:

* LLM контекста
* документации

НЕ участвует в execution.

---

## 4.3 Link Semantics

```text
depends → execution dependency (DAG)
part_of → hierarchy (tree)
affects → traceability (non-execution)
```

---

## 5. Graph Types

### 5.1 Dependency Graph

```text
edges: depends
type: DAG
used for execution ordering
```

---

### 5.2 Structure Graph

```text
edges: part_of
type: tree
used for scope + context
```

---

### 5.3 Trace Graph

```text
edges: affects
type: free graph
used for context enrichment only
```

---

## 6. Compilation Pipeline

```text
Wiki
 ↓
DocGraphParser
 ↓
DocGraphValidator
 ↓
PlanManager
 ↓
EventLog
 ↓
Projections (Execution Graph)
```

---

## 6.1 DocGraphParser

Input:

* Markdown files

Output:

* AST (nodes + edges)

Rules:

* ONLY frontmatter parsed for execution
* ignore free text

---

## 6.2 DocGraphValidator

Checks:

```text
1. DAG validity (depends)
2. Tree validity (part_of)
3. Node existence
4. Type correctness
5. Scope consistency
```

Failure → abort sync

---

## 6.3 PlanManager (Compiler)

Transforms:

```text
DocGraph AST → Commands → EventLog
```

Emits:

```text
TaskSpawned
TaskBlocked
DependencyRegistered
```

---

## 7. Execution Model

Execution driven ONLY by EventLog:

```text
TaskReady:
  all dependencies DONE

TaskBlocked:
  at least one dependency not DONE
```

---

## 8. Sync Model

### 8.1 sync-wiki

```text
Wiki → EventLog
```

* parse
* validate
* emit commands

---

### 8.2 render-wiki

```text
EventLog → Wiki
```

* update status
* reflect actual state

---

## 9. Consistency Model

```text
Write:
  strong (WriteKernel transaction)

Read:
  deterministic snapshot at AgentLoop start

Staleness:
  ≤ 1 loop iteration
```

---

## 10. ContextKernel Integration

### 10.1 Context Expansion

Order:

```text
1. Task node
2. depends (DONE only)
3. parent phase
4. domain
5. affects (optional)
```

---

### 10.2 Limits

```text
max_depth = 2
max_nodes = N
priority: depends > part_of > affects
```

---

## 11. Scope Model

```text
Phase defines max scope
Task defines restricted scope
```

Rule:

```text
task_scope ⊆ phase_scope
```

---

## 12. Invariants

### 12.1 SSOT

```text
I-GRAPH-SSOT-1:
EventLog is single source of truth

I-GRAPH-SSOT-2:
DocGraph MUST NOT drive execution directly
```

---

### 12.2 DSL

```text
I-GRAPH-DSL-1:
DocGraph is declarative DSL

I-GRAPH-MANIFEST-1:
Execution graph MUST be derived ONLY from frontmatter
```

---

### 12.3 Graph Integrity

```text
I-GRAPH-ACYCLIC-1:
depends MUST form DAG

I-GRAPH-TREE-1:
part_of MUST form tree

I-GRAPH-TRACE-1:
affects MUST NOT affect execution
```

---

### 12.4 Consistency

```text
I-GRAPH-DRIFT-1:
Wiki is stale after EventLog mutation

I-CONSISTENCY-1:
Cross-domain reads are cycle-bounded
```

---

### 12.5 Context

```text
I-GRAPH-CTX-1:
Graph traversal MUST be bounded
```

---

### 12.6 Scope

```text
I-GRAPH-SCOPE-1:
Task inherits max scope from phase

I-GRAPH-SCOPE-2:
Task scope MUST be narrower than phase scope
```

---

## 13. Anti-Patterns

```text
❌ Parsing dependencies from free text
❌ Using affects for execution
❌ Allowing cyclic depends
❌ Direct execution from Wiki
❌ Unbounded graph traversal
❌ Task scope = phase scope blindly
```

---

## 14. Domain Placement

```text
Blueprint:
  - DocGraphParser
  - DocGraphValidator
  - PlanManager

Core:
  - EventLog
  - WriteKernel

Engine:
  - AgentLoop
  - ContextKernel

Intelligence:
  - analysis (read-only)
```

---

## 15. Interfaces (Minimal)

### Parser

```python
parse(files) -> DocGraphAST
```

---

### Validator

```python
validate(ast) -> OK | Error
```

---

### PlanManager

```python
compile(ast) -> Commands[]
```

---

### ContextKernel

```python
build_context(task_id) -> Context
```

---

## 16. Trade-offs

```text
+ Human-readable planning
+ Deterministic execution
+ Strong context for LLM

- Requires strict DSL discipline
- Potential graph size explosion
- Sync/render overhead
```

---

## 17. Final Model

```text
Markdown (DSL)
   ↓
DocGraph
   ↓
Compiler (PlanManager)
   ↓
EventLog (SSOT)
   ↓
Execution Graph
   ↓
AgentLoop
   ↓
ContextKernel (bounded traversal)
```

---

## 18. Definition of Done

DocGraph Orchestration считается реализованным если:

```text
✓ sync-wiki компилирует DSL → EventLog
✓ render-wiki синхронизирует статусы
✓ DAG валидируется
✓ ContextKernel использует граф
✓ Execution НЕ зависит от Wiki напрямую
✓ Все инварианты enforceable
```

---

