---
id: pattern/commit-discard-gate
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- pipeline
- write-path
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/sdd-v2-architecture-deepening.md
---
# Commit/Discard Gate

## Summary

Commit/Discard Gate — двухфазный протокол завершения TaskRun, определяющий когда [[sandbox-manager]] коммитит или откатывает изменения агента. Решает логическое противоречие оригинального порядка (`commit → AuditEngine → ScenarioGen`): gate переносится до коммита, M9 вычисляется до принятия решения, L2 не управляет L1 state-мутациями.

## How It Works

**Фаза A: Freeze + Score**

1. Агент завершил шаг → `SandboxManager.freeze()` — snapshot файловой системы зафиксирован, дальнейшие writes невозможны.
2. `AuditEngine.score(task_id, scenario_spec)` вычисляет M1-M9 используя замороженный snapshot. `scenario_spec` передаётся как **входной параметр** (не запрашивается у [[scenario-gen]] внутри) — L1/L2 boundary сохраняется.
3. Из score извлекается `critical_passed: bool` — M9 > 0 и все critical checks прошли.

**Фаза B: Commit Gate (L1)**

4. `critical_passed == true` → `SandboxManager.commit()` — изменения входят в основной репозиторий.
5. `critical_passed == false` → `SandboxManager.discard()` — snapshot удаляется.

**Фаза C: ScenarioGen (L2, после commit)**

6. `ScenarioGen.generate_full_spec(task_id)` — полная ScenarioSpec записывается как `ScenarioGenerated` event. Это non-blocking L2-операция.

**Откуда ScenarioSpec до ScenarioGen?** При `start-task` создаётся минимальная ScenarioSpec как часть TaskDefinition — только critical checks. [[scenario-gen]] на L2 расширяет её после коммита, формируя regression suite.

**Аудит при discard:** `critical_passed == false` → `ScenarioGenerated` event с `outcome: DISCARDED` всё равно эмитится для полноты аудита.

## When To Use

Конец каждого TaskRun — независимо от того, сколько write-циклов (`resolve → explain → write`) выполнил агент. Единственный момент когда [[sandbox-manager]] принимает решение о commit.

## Trade-offs

**Плюсы:** commit gate живёт полностью в L1 (SandboxManager + [[audit-engine]]) — L2 не управляет state; M9 вычисляется до коммита на frozen snapshot — детерминированно; аудит сохраняется даже при discard.

**Минусы:** минимальная ScenarioSpec в TaskDefinition требует дисциплины при создании задач (critical checks нужно декларировать заранее, не после); AuditEngine.score блокирует commit — нужно быть достаточно быстрым.

**Нарушение I-HARNESS-BOUNDARY-1:** перенос gate-логики в `ScenarioGen.check_critical()` нарушил бы этот инвариант — L2 не должен управлять L1 state-мутациями. Gate должен жить в L1.

## See Also

- [[sandbox-manager]] — freeze / commit / discard
- [[audit-engine]] — вычисляет AgentScore и critical_passed
- [[scenario-gen]] — L2, генерирует полную ScenarioSpec после commit
- [[metric-collector]] — интерфейс для M1-M9 в AuditEngine
- [[score-context]] — read-only view передаваемый в AuditEngine.score
