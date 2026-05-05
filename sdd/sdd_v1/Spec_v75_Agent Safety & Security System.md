# Spec_v75 — Phase 75: Agent Safety & Security System

Status: Draft
Baseline: Spec_v64 (Audit), v71 (Meta-Harness), v72 (Scenario), v74 (M9)

---

## 0. Goal

Ввести **жёсткую, формализованную систему безопасности (Safety & Security Layer)**,
которая:

- предотвращает неконтролируемые действия агентов
- гарантирует изоляцию выполнения
- обеспечивает проверяемость (auditability)
- НЕ ломает детерминизм и event-sourcing

Система покрывает 9 архитектурных слоёв:
while-loop, context, tools, sub-agents, built-ins, persistence, prompt assembly, hooks, permissions.

---

## 1. Architecture Overview

```text
Agent Runtime =
  WhileLoop
    → ContextManager
    → PromptAssembler
    → Tool/Skill Layer
    → SubAgent Orchestrator
    → Lifecycle Hooks
    → Sandbox Execution
    → Trace/EventLog
    → Guard Layer (Safety)
````

Safety встроен как **Guard Layer + Invariants + Isolation**.

---

## 2. Threat Model

### Threat Classes

```text
T1: Scope violation        (доступ к запрещённым файлам)
T2: Prompt injection       (манипуляция system prompt / context)
T3: Tool abuse             (вызов опасных команд)
T4: State corruption       (некорректные события)
T5: Non-determinism        (рандом, внешние API)
T6: Privilege escalation   (обход ролей/ограничений)
T7: Data exfiltration      (утечка данных)
T8: Infinite loop / stall  (зависание агента)
T9: Cross-session leakage  (пересечение сессий)
```

---

## 3. Safety Domains

## 3.1 While Loop Control

```text
I-LOOP-BOUND-1
→ max_iterations MUST be bounded (configurable)

I-LOOP-EXIT-1
→ loop MUST terminate on:
   - task complete
   - guard violation
   - timeout

I-LOOP-DETERMINISTIC-1
→ iteration sequence MUST be reproducible (same seed/state)
```

---

## 3.2 Context Management

```text
I-CONTEXT-SCOPE-1
→ context MUST include ONLY:
   - task inputs
   - allowed files
   - spec references

I-CONTEXT-IMMUTABLE-1
→ context snapshot immutable per step

I-CONTEXT-NO-LEAK-1
→ cross-task data access запрещён

I-CONTEXT-BUDGET-1
→ token/slot budget MUST be enforced
```

---

## 3.3 Skills & Tools

```text
I-TOOL-WHITELIST-1
→ только разрешённые tools доступны

I-TOOL-DETERMINISTIC-1
→ tools MUST be deterministic OR wrapped

I-TOOL-AUDIT-1
→ каждый tool call MUST иметь trace event

I-TOOL-SANDBOX-1
→ все tool calls выполняются в sandbox
```

---

## 3.4 Sub-Agents

```text
I-AGENT-ISOLATION-1
→ каждый sub-agent имеет:
   - отдельный context
   - отдельный trace

I-AGENT-ROLE-1
→ роли (planner/executor/reviewer) фиксированы

I-AGENT-NO-ESCALATION-1
→ sub-agent НЕ может менять свои permissions
```

---

## 3.5 Built-in Skills

```text
I-BUILTIN-SAFE-1
→ built-in skills MUST be pure or sandboxed

I-BUILTIN-NO-SIDEFX-1
→ запрещены внешние side-effects
```

---

## 3.6 Session Persistence

```text
I-SESSION-ISOLATED-1
→ session_id MUST isolate state

I-SESSION-ENV-1
→ task_id/session_id через env vars (не файлы)

I-SESSION-APPEND-ONLY-1
→ все логи append-only

I-SESSION-REPLAY-1
→ полное воспроизведение из EventLog
```

---

## 3.7 System Prompt Assembly

```text
I-PROMPT-STATIC-1
→ system prompt MUST быть фиксированным шаблоном

I-PROMPT-INJECTION-1
→ user input НЕ может менять system prompt

I-PROMPT-TRACE-1
→ финальный prompt MUST быть логирован

I-PROMPT-DETERMINISTIC-1
→ prompt assembly MUST быть детерминирован
```

---

## 3.8 Lifecycle Hooks

```text
I-HOOK-ORDER-1
→ Pre → Execute → Post фиксированный порядок

I-HOOK-NO-MUTATION-1
→ hooks НЕ могут менять state напрямую

I-HOOK-AUDIT-1
→ каждый hook event MUST логироваться

I-HOOK-SAFE-1
→ hooks выполняются в sandbox
```

---

## 3.9 Permissions & Safety

### Permission Model

```text
Permission = {
  allowed_files: set[str]
  allowed_tools: set[str]
  allowed_commands: set[str]
}
```

### Invariants

```text
I-PERM-STRICT-1
→ default = deny-all

I-PERM-CHECK-1
→ каждый FILE_READ/WRITE проверяется

I-PERM-COMMAND-1
→ каждый COMMAND проверяется

I-PERM-NO-BYPASS-1
→ обход guard невозможен

I-PERM-AUDIT-1
→ violations MUST фиксироваться
```

---

## 4. Guard Layer

```text
Guard = deterministic function:
  (State, Command, Context) → ALLOW | DENY
```

### Guard Types

```text
ScopeGuard       → файлы
CommandGuard     → команды
NormGuard        → правила SDD
GraphGuard       → навигация
SafetyGuard      → общий контроль
```

---

## 5. Sandbox Model

```text
Sandbox:
  - isolated FS root
  - no network
  - fixed env vars
  - fixed seed
```

### Invariants

```text
I-SANDBOX-ISO-1
→ нет доступа вне root

I-SANDBOX-NET-1
→ network disabled

I-SANDBOX-SEED-1
→ random seed фиксирован

I-SANDBOX-CLEAN-1
→ state reset между run
```

---

## 6. Event & Audit Security

```text
I-EVENT-IMMUTABLE-1
→ EventLog append-only

I-EVENT-ORDER-1
→ события строго упорядочены

I-AUDIT-COMPLETE-1
→ все действия агента MUST логироваться

I-AUDIT-TRACE-1
→ trace.jsonl = полный execution log
```

---

## 7. Failure Handling

```text
On violation:
  → DENY execution
  → log violation
  → terminate or continue (policy)

On critical violation:
  → abort task
```

---

## 8. Anti-Abuse Guarantees

```text
G1: агент не может читать вне scope
G2: агент не может писать вне sandbox
G3: агент не может менять spec/state
G4: агент не может скрыть действия
G5: агент не может эскалировать права
G6: агент не может вызвать недетерминизм
```

---

## 9. DoD

-  Все tool/command calls проходят Guard
    
-  Sandbox изолирует FS + env
    
-  Prompt assembly детерминирован
    
-  EventLog полный и воспроизводимый
    
-  Permissions enforced (deny-by-default)
    
-  Sub-agents изолированы
    
-  Hooks безопасны и логируются
    
-  Replay == original execution
    
-  Все 9 threat classes покрыты
    

---

## 10. Summary

```text
Safety в SDD = не “фильтр”, а системное свойство:

- Guard → контроль действий
- Sandbox → изоляция
- Invariants → формальная безопасность
- EventLog → проверяемость

Результат:
агент = полностью контролируемый, воспроизводимый и безопасный исполнитель
```