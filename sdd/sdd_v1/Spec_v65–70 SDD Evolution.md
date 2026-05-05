Ключевая мысль:
Твоя система изначально: SDD = controlled development system
После Phase 65–70: SDD = controlled + self-improving system

Вот главный invariant, который стоит явно добавить:
I-SDD-CORE-1:
Spec, Task model и EventLog MUST оставаться
единственным источником истины.
Sandbox, Agents, Learning — вспомогательные слои,
НЕ влияющие на семантику исполнения.

# Spec_v65–70 — SDD Evolution: Sandbox Execution, Multi-Agent Orchestration, Audit-Driven Learning

Status: Draft (post Phase 64)
Baseline: Spec_v64_AgentAuditSystem.md

Goal:
Эволюция SDD из deterministic execution system → adaptive, self-improving system
без потери:
- determinism
- event sourcing
- invariants (SENAR)

Ключевая идея:
L1 (execution) усиливается sandbox isolation
L2 (evaluation) → становится driver для L3 (evolution)
L3 → управляемая адаптация агентов и протоколов

---

# Phase 65 — Sandbox Execution (Isolated L1)

## Goal
Изолировать выполнение задач (как Sandcastle), сохранив EventLog как SSOT.

## Architecture

ExecutionContext:

```text
Task → Worktree(branch=T-NNN)
     → Container (optional)
     → Execution
     → Commit (artifact)
     → Merge (fast-forward)
     → Cleanup
````

## BC-SANDBOX

src/sdd/sandbox/
manager.py        # lifecycle worktree/container
worktree.py       # git worktree create/remove
container.py      # docker wrapper (optional)
executor.py       # run commands inside sandbox
snapshot.py       # capture FS snapshot (deterministic)

## Invariants

I-SANDBOX-1:
Каждый Task MUST выполняться в отдельном worktree

I-SANDBOX-2:
Sandbox MUST быть уничтожен после completion (no residue)

I-SANDBOX-3:
Все изменения MUST фиксироваться через git commit

I-SANDBOX-4:
Execution MUST быть reproducible given same repo state + spec

## Integration

BC-EXECUTION → BC-SANDBOX (optional layer)
EventLog остаётся primary, git = artifact log

---

# Phase 66 — Deterministic Replay + Snapshotting

## Goal

Сделать execution воспроизводимым на уровне FS + команд.

## Architecture

```text
EventLog + Repo Snapshot → Replay → Same Output
```

## Components

snapshot_id:

* git commit hash
* * optional FS diff

ExecutionRecord:

* commands[]
* env vars
* sandbox config

## Invariants

I-REPLAY-1:
Replay(State₀, Events) → Stateₙ (identical)

I-REPLAY-2:
Все команды MUST быть логированы с args + env

I-REPLAY-3:
External calls MUST быть либо запрещены, либо зафиксированы

---

# Phase 67 — Multi-Agent Orchestration (L1.5)

## Goal

Добавить orchestrator для нескольких агентов (planner/executor/reviewer)

## Model

```text
Task
 ├─ PlannerAgent
 ├─ ExecutorAgent
 └─ ReviewerAgent
```

## BC-ORCHESTRATOR

src/sdd/orchestrator/
pipeline.py       # agent pipeline
roles.py          # planner/executor/reviewer
scheduler.py      # sequential/parallel execution
context.py        # context passing between agents

## Execution Flow

```text
Planner → Plan
Executor → Implement
Reviewer → Validate
→ merge decision
```

## Invariants

I-AGENT-1:
Каждый агент MUST работать в sandbox

I-AGENT-2:
Агенты MUST коммуницировать только через structured context

I-AGENT-3:
Решение о merge MUST проходить через Guard

---

# Phase 68 — Protocol Formalization (Ground Truth Expansion)

## Goal

Сделать implement.md → machine-readable protocol

## Model

ProtocolStep:

```python
ProtocolStep:
  id: str
  command_pattern: str
  rule_refs: list[str]
  required: bool
```

PROTOCOL_STEPS_MAP:

* mapping step_id → patterns

## Step Evaluation

```text
step_status ∈ {OK, VIOLATION, MISSING, EXTRA}
```

## Invariants

I-PROTOCOL-1:
Все шаги MUST быть описаны в PROTOCOL_STEPS_MAP

I-PROTOCOL-2:
Каждое действие агента MUST быть сопоставимо шагу

I-PROTOCOL-3:
Несопоставимые действия → EXTRA

---

# Phase 69 — Audit → Learning Bridge (L2 → L3)

## Goal

Использовать audit (M1–M8) как вход для улучшения системы

## Inputs

* summary.json
* audit_report.md
* AgentScore
* DataQuality

## BC-LEARNING

src/sdd/learning/
analyzer.py       # агрегирует метрики
pattern_miner.py  # ищет повторяющиеся ошибки
suggester.py      # генерирует улучшения
trust_region.py   # ограничивает изменения

## Output

LearningProposal:

```python
{
  "type": "protocol_fix | norm_update | prompt_update",
  "target": "...",
  "change": "...",
  "confidence": float
}
```

## Invariants

I-LEARN-1:
Learning MUST быть read-only к Spec

I-LEARN-2:
Все предложения MUST быть проверяемы (trace-backed)

I-LEARN-3:
No direct mutation — только proposals

---

# Phase 70 — Controlled Evolution (L3)

## Goal

Безопасное изменение системы на основе LearningProposal

## Pipeline

```text
Proposal
 → Simulation
 → Statistical Validation
 → Guard Approval
 → Apply
```

## BC-EVOLUTION

src/sdd/evolution/
proposer.py
simulator.py
validator.py
applier.py

## Validation

* A/B tasks replay
* metric improvement (M1–M8)
* no regression

## Invariants

I-EVO-1:
Изменения MUST проходить simulation

I-EVO-2:
Изменения MUST улучшать метрики или быть нейтральными

I-EVO-3:
Guard + HumanGate REQUIRED для apply

I-EVO-4:
Все изменения MUST быть reversible

---

# Cross-Phase Concepts

## 1. Event Sourcing remains core

```text
Command → Event → Projection
```

Sandbox / Agents / Learning НЕ нарушают это

---

## 2. Separation of Concerns

| Layer | Responsibility               |
| ----- | ---------------------------- |
| L1    | Execution (sandbox, agents)  |
| L2    | Evaluation (audit)           |
| L3    | Evolution (learning + apply) |
| G     | Guard (invariants, safety)   |

---

## 3. Determinism Boundary

Deterministic:

* metrics
* replay
* event processing

Non-deterministic:

* LLM synthesis (isolated)

---

## 4. Data Model Expansion

Task → TaskRun:

```python
TaskRun:
  task_id
  sandbox_id
  snapshot_id
  agent_roles[]
  metrics
```

---

## 5. Key Metrics (final)

M1 — protocol_adherence
M2 — scope_discipline
M3 — test_efficiency
M4 — implementation_focus
M5 — time_distribution
M6 — behavioral_quality
M7 — task_completion
M8 — step_correctness_ratio

---

## 6. Critical Design Decisions

1. Git ≠ EventLog
2. Sandbox = infra isolation, not logic safety
3. Audit = deterministic, LLM only synthesis
4. Learning = proposal-based, not auto-mutation
5. Evolution = gated, simulated, reversible

---

## Final System View

```text
            ┌──────────────┐
            │   Spec (L0)  │
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │ Execution L1 │  ← Sandbox + Agents
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │ Evaluation L2│  ← Audit (M1–M8)
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │ Evolution L3 │  ← Learning + Apply
            └──────┬───────┘
                   │
            ┌──────▼───────┐
            │   Guard (G)  │
            └──────────────┘
```

---

# Итог

SDD v65–70 превращает систему:

```text
SDD v64:
deterministic executor + audit

→

SDD v70:
self-improving, sandboxed, multi-agent system
с сохранением:
- SSOT (EventLog)
- invariants
- reproducibility
```

---
---

# Spec_v65 — §5 Invariants (Hard Boundaries for SDD Evolution)

Goal:
Зафиксировать архитектурные границы так, чтобы их нарушение было невозможно
(или приводило к fail-fast). Эти инварианты обязательны для Phase 65–70
(Sandbox, Multi-Agent, Audit→Learning, Evolution).

---

## 5.1 Core Principle

I-SDD-CORE-1:
Единственный способ изменить состояние системы:
Command → Handler → Event → EventLog → Projection.
Любая прямая запись в состояние (DB, файлы, spec, projections) = ERROR.

I-SDD-BOUNDARY-1:
Ни один слой (L1/L2/L3) не может:
- изменить состояние системы
- минуя Command→Event pipeline
- или без прохождения Guard

---

## 5.2 Spec Layer (L0)

I-SPEC-IMMUTABLE-1:
`speсs/` — immutable. LLM/runtime НЕ могут изменять.

I-SPEC-IMMUTABLE-2:
Изменение Spec возможно только:
Human → PR → review → merge.

---

## 5.3 Execution Layer (L1 — sandbox, agents)

I-EXEC-INPUT-1:
Execution может читать только:
- Spec
- Task
- State (projection)

I-EXEC-OUTPUT-1:
Execution может писать только:
- Commands (→ EventLog)
- artifacts (fs/git)

I-EXEC-NO-BYPASS-1:
Прямая запись в EventStore запрещена (только через handlers).

I-SANDBOX-1:
Каждый Task выполняется в isolated sandbox (worktree/container).

I-SANDBOX-2:
Sandbox уничтожается после выполнения (no residue).

I-SANDBOX-3:
Sandbox — infra слой, НЕ влияет на бизнес-логику.

---

## 5.4 Evaluation Layer (L2 — audit)

I-AUDIT-READONLY-1:
Audit строго read-only:
- НЕ пишет в EventStore
- НЕ меняет src/
- НЕ меняет Spec/Task

I-AUDIT-SOURCE-1:
Метрики считаются ТОЛЬКО из:
- trace.jsonl
- summary.json

I-AUDIT-NO-LLM-GROUND-1:
LLM output НЕ используется как ground truth.

---

## 5.5 Learning Layer (L3 — analyzer)

I-LEARN-PROPOSAL-1:
Learning генерирует только Proposal (data).

I-LEARN-NO-ACT-1:
Learning НЕ может:
- менять Spec
- менять код
- выполнять команды

I-LEARN-TRACE-1:
Все предложения MUST быть обоснованы trace/metrics.

---

## 5.6 Evolution (Apply)

I-EVO-GATED-1:
Любое изменение проходит:
Proposal → Simulation → Validation → Guard → HumanGate → Apply.

I-EVO-METRIC-1:
Изменение допустимо только если:
- улучшает метрики (M1–M8)
- или нейтрально (no regression)

I-EVO-REVERSIBLE-1:
Каждое изменение MUST иметь rollback.

---

## 5.7 Guard Layer (G — SENAR)

I-GUARD-FINAL-1:
Любое действие проходит через Guard.

I-GUARD-BLOCK-1:
Нарушение invariant → execution STOP (fail-fast).

---

## 5.8 Dependency Constraints (critical)

I-DEP-1:
L2 (audit) НЕ зависит от LLM output.

I-DEP-2:
L3 (learning) НЕ пишет в L1/L0.

I-DEP-3:
Sandbox НЕ влияет на семантику выполнения.

I-DEP-4:
Git НЕ является источником истины (только artifact).

---

## 5.9 Event Access

I-CMD-ONLY-1:
EventStore доступен только через Command handlers.

Любой прямой доступ:
event_store.append(...) вне handler → ERROR.

---

## 5.10 Scope Enforcement

I-SCOPE-HARD-1:
Любой доступ к файлам вне allowed_paths → FAIL.

I-SCOPE-HARD-2:
Scope НЕ может расширяться во время выполнения.

I-SCOPE-HARD-3:
`src/**`, `tests/**` доступны только если явно указаны в inputs.

---

## 5.11 Determinism

I-REPLAY-1:
Replay(State₀, Events) → Stateₙ (идентичен).

I-REPLAY-2:
Все команды, env, inputs MUST быть логированы.

I-REPLAY-3:
Внешние вызовы запрещены или зафиксированы.

---

## 5.12 Failure Semantics

I-FAIL-FAST-1:
Любое нарушение invariant → немедленный STOP.

I-FAIL-NO-SILENT-1:
Silent errors запрещены.

---

## 5.13 Design Rule (meta)

I-DESIGN-RULE-1:
Любой новый компонент обязан удовлетворять:

1. Не создаёт новый источник истины
2. Не обходит Command→Event pipeline
3. Не нарушает layer boundaries
4. Детерминируем (или явно изолирован)
5. Проверяем через trace + invariants

---

## 5.14 Practical Rule

I-POWERLESS-1:
LLM / Agents / Learning:
- могут читать
- могут исполнять
- могут предлагать
НО не могут принимать финальные решения.

---

# Итог

Эти инварианты гарантируют:

- Spec остаётся immutable
- EventLog остаётся SSOT
- Execution остаётся детерминированным
- Audit остаётся объективным
- Learning остаётся безопасным
- Evolution остаётся контролируемым

Нарушение любого invariant = архитектурная ошибка.
