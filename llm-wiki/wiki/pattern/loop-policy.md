---
id: pattern/loop-policy
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- automation
- pipeline
- write-path
- domain/sdd
version: 2
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/orchestrator-agentloop-plan.md
---
# LoopPolicy

Vocabulary policy-ключей для [[agent-loop]]: budget limits, per-error retry-стратегии, phase write permissions и Sandbox TTL. Хранится в [[policy-projection]]; читается при каждом входе в FSM-состояние PLAN.

## How It Works

```python
step_budget: int                     # макс. шагов за сессию (default: 50); hard stop
retry_budget: dict[str, int]         # error_type → макс. retry; fallback: "DEFAULT"
  # пример: {"NO_EXPLAIN_BEFORE_WRITE": 3, "TASK_ISOLATED": 2, "DEFAULT": 2}
re_explain_budget: int               # макс. RE_EXPLAIN переходов за сессию (default: 2)
phase_write_allowed: bool            # false в VALIDATE-фазе → write tool_calls отклоняются
gate_freeze_ttl_hours: int           # TTL frozen Sandbox при GATE (default: 24)
                                     # по истечении → SandboxManager.discard() + ErrorEvent
```

**Defaults — контракт, не примеры:**

| Ключ | Default | Семантика |
|------|---------|-----------|
| `step_budget` | 50 | hard stop; `task_complete` проверяется до budget |
| `re_explain_budget` | 2 | макс. RE_EXPLAIN-переходов за сессию |
| `retry_budget["DEFAULT"]` | 2 | fallback если `error_type` не задан явно |
| `phase_write_allowed` | `true` | `false` в VALIDATE-фазе |
| `gate_freeze_ttl_hours` | 24 | TTL Sandbox при GATE; 0 → немедленный discard |

**Lazy bootstrap:** если `memory.read.policy(scope=phase_id)` не находит запись, возвращает `PolicySnapshot` с defaults и `policy_version = "0.0.0-bootstrap"`. Human переопределяет через `memory.write.policy(scope=phase_id, ...)`.

**Backward compat:** `retry_limit: int` (scalar, старый формат) → [[agent-loop]] читает как `{"DEFAULT": retry_limit}`.

**Чтение policy:**

```python
policy = memory.read.policy(scope=phase_id)  # at_offset = current EventLog offset
```

[[agent-loop]] фиксирует `last_policy_offset` и перечитывает только если `policy_projection.last_update_offset > last_policy_offset` (LOOP-1). Budget enforcement остаётся в `decide()` — [[error-classifier]] не управляет счётчиками.

## When To Use

Читается [[agent-loop]] при инициализации (FSM-состояние PLAN) и при каждом RE_EXPLAIN если policy обновилась. Никогда не читается в DECIDE напрямую — только через `loop_state.policy`.

## Trade-offs

- `step_budget` — hard stop: даже успешный шаг не завершает loop если `task_complete != true`.
- Per-error `retry_budget` позволяет дифференцировать надёжность по типу ошибки без центрального `MAX_RETRIES`.
- `gate_freeze_ttl_hours` как policy-ключ делает TTL наблюдаемым и настраиваемым без code changes.

## Open Questions

- [ ] (P0) Q12 PARTIAL: Backoff алгоритм (exponential/fixed) не задан. Какой конкретно используется?
- [ ] (P3) Q216: Как записываются LLM API costs? В EventLog как metric event или отдельный store?
- [ ] (P3) Q217: При каком % budget usage агент предупреждает? При 100% — HUMAN_GATE или ABORT?
- [ ] (P3) Q220: Суммарный бюджет на фазу? Как распределяется между задачами?

## See Also

- [[agent-loop]]
- [[policy-projection]]
- [[loop-outcome]]
- [[error-classifier]]
