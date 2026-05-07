---
page_type: idea
domain: sdd
layer: architecture
sdd_layer: null
sdd_domain: null
tags:
- sdd/blueprint
- pipeline
- domain/sdd
updated: '2026-05-06'
sources: []
---
# SDD Domain — Blueprint

## Summary

Blueprint-домен владеет проектной моделью: specs, plans, phases, policy. Строгая последовательность фаз через FSM. Human gates контролируют переходы; LLM gates управляют имплементацией.

## Назначение и границы

Blueprint отвечает за **структуру и прогресс проекта**: какие фазы существуют, какие задачи активны, что является DoD. Blueprint знает о бизнес-логике планирования, но не знает о runtime исполнения (Engine) и не делает аналитику (Intelligence).

Владеет: Spec FSM, Plan FSM, Phase FSM, Policy rules, DoD criteria.

Не владеет: физикой записи (Core), исполнением агента (Engine), предложениями оптимизации (Intelligence).

## L1 Blueprint компоненты

[[policy-kernel]] — детерминированный интерпретатор policy-правил

## L2 Blueprint компоненты

[[spec-manager]], [[plan-manager]], [[phase-orchestrator]], [[constitution-parser]]

## Phase FSM

```
PLANNED → [human: activate-phase N] → ACTIVE →
[llm: check-dod] → COMPLETE
```

Инварианты: I-PHASE-SEQ-1 (no skip), I-PHASE-AUTH-1 (только PhaseInitialized мутирует phase_current), I-PLAN-IMMUTABLE-AFTER-ACTIVATE.

## Антипаттерны

- Автоматическая активация фазы без human gate.
- Изменение Plan_vN.md после activate-phase.
- Blueprint компонент напрямую вызывает Engine runtime.

## See Also

- [[sdd-vertical-slice]]
- [[sdd-domain-core]]
- [[sdd-domain-engine]]
- [[sdd-layer-l1]]
- [[sdd-layer-l2]]
