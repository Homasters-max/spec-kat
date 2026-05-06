---
id: pattern/session-orchestrator
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- automation
- enforcement
- write-path
- domain/sdd
version: 4
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/SDD System Architecture - Component Inventory and Boundaries.md
- raw/orchestrator-agentloop-plan.md
---
# Session Orchestrator

L1-компонент: chains stateless sessions, проверяет human gates в EventLog перед стартом каждой сессии, делегирует выполнение [[agent-loop]].

## How It Works

Нет постоянно живущего loop (GL-9). Session Orchestrator = оркестратор между сессиями:

```text
[Human starts session]
    ↓
Orchestrator.start():
  1. check EventLog: human gate cleared?
     → если нет → emit HumanGateReached, stop
  2. determine session type (IMPLEMENT / VALIDATE / ...)
  3. load current state via ReadModel
  4. initialize ContextKernel
  5. create SandboxManager.create(task_id)
  6. AgentHandle.start(model, config)
  7. AgentLoop.run(phase_id, agent_handle) → LoopOutcome
     ↓
Orchestrator.complete():
  ветвление по LoopOutcome (см. ниже)
```

**LoopOutcome ветвление:**

| LoopOutcome | Действие |
|-------------|----------|
| `COMPLETE` | `SandboxManager.commit()`; `AuditEngine.calculate()`; `ScenarioGen.build()`; emit `SessionCompleted`; suggest next session |
| `GATE` | `SandboxManager.freeze(ttl=policy.gate_freeze_ttl_hours)`; human уведомляется; новый [[agent-loop]] при возобновлении работает в том же Sandbox (unfreeze); по истечении TTL → discard + ErrorEvent |
| `CORE_ABORT` | `SandboxManager.discard()` немедленно; сессия закрывается без AuditEngine; ErrorEvent уже в EventLog |
| `PROTOCOL_ABORT` | AuditEngine запускается (M1-M8, M9=0 принудительно); результат для MetaOptimization; `SandboxManager.discard()`; сессия закрывается |

**Human gate check:** Orchestrator читает EventLog через ReadModel и ищет `HumanGateCleared` events. Если gate не очищен → `HumanGateReached` event + stop. Никакого active polling нет — human инициирует следующую сессию вручную.

## When To Use

Является точкой входа для каждой новой сессии. Управляет lifecycle всех L1-компонентов в рамках одного TaskRun.

## Trade-offs

- Нет persistent loop → нет overhead от долгоживущего процесса, но нет и автоматического продолжения.
- Human должен явно инициировать каждую сессию — intentional design, не ограничение.
- GATE freeze vs discard: freeze сохраняет контекст для возобновления; TTL предотвращает бесконечно висящие Sandbox.

## Open Questions

- [ ] (P1) Q66: Какие шаги ОБЯЗАТЕЛЬНЫ в pipeline фазы? Могут ли фазы иметь разные pipeline-конфигурации?
- [ ] (P1) Q67: Могут ли шаги выполняться параллельно? Как координировать конкурентные writes к одному файлу?
- [ ] (P1) Q68: Как перейти с незакрытой фазы на следующую? PhaseAbandoned event? Влияние на projections?
- [ ] (P1) Q69: Можно ли открыть закрытую задачу/фазу? Как это влияет на монотонность EventLog и I-PHASE-LIFECYCLE-2?
- [ ] (P1) Q70: Статусы спеки/плана: DRAFT→REVIEW→APPROVED→OBSOLETE. Кто переводит? Что происходит при OBSOLETE с зависимыми задачами?
- [ ] (P3) Q222: Где исчерпывающий список всех точек human approval? Spec approve, plan approve, phase complete, policy update — что ещё?
- [ ] (P3) Q223: Что происходит если human не реагирует N часов? Auto-expire? Freeze state?
- [ ] (P3) Q224: Как человек узнаёт что его ожидают? Telegram, email, CLI poll?
- [ ] (P3) Q225: Человек может дать feedback через время после завершения задачи? Как применяется к уже выполненному?
- [ ] (P3) Q226: Человек одобряет план частично — "делай пункты 1–3, пункт 4 переработай". Механика?
- [ ] (P3) Q227: Может ли human делегировать gate approval другому human или автоматической проверке?

- [ ] (P2) Q186: Фазы строго последовательны (I-PHASE-SEQ-1), но может ли задача из Phase 3 зависеть от артефакта Phase 1?
- [ ] (P2) Q187: Как отследить цепочку: Spec_v1 → Plan_v1 → T-001 → code_file.py? Bidirectional graph?
- [ ] (P2) Q188: Если Phase 3 провалилась и нужно вернуться к Phase 2 — какой механизм? PhaseReverted event?
- [ ] (P2) Q189: Возможно ли выполнение двух независимых фаз параллельно? Какие инварианты нарушаются?
- [ ] (P2) Q190: Есть ли reusable phase templates? Как фаза "Add tests" переиспользуется в разных проектах?

## See Also

- [[agent-loop]]
- [[loop-outcome]]
- [[agent-handle]]
- [[context-kernel]]
- [[sandbox-manager]]
- [[audit-engine]]
- [[classified-recovery]]
- [[sdd-component-inventory]]
