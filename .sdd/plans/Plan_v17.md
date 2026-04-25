# Plan_v17 — Phase 17: Validation Runtime (VR)

Status: DRAFT
Spec: specs/Spec_v17_ValidationRuntime.md

---

## Milestones

### M0: ExecutionContext — Production Kernel Layer

```text
Spec:       §2 BC-VR-0, §6 M0, §5 I-EXEC-CONTEXT-1
BCs:        BC-VR-0
Invariants: I-EXEC-CONTEXT-1, I-KERNEL-WRITE-1
Depends:    — (Phase 16 COMPLETE)
Risks:      Единственное изменение в production коде; неверное размещение kernel_context
            вызовет false-negatives в VR-4; сначала пишем файл, потом интегрируем в registry.py
```

**Артефакты:**
- `src/sdd/core/execution_context.py` — `KernelContextError`, `_EXECUTION_CTX`, `kernel_context`, `assert_in_kernel`, `current_execution_context`
- `src/sdd/commands/registry.py` — `execute_command` обёрнут `with kernel_context("execute_command")`
- `tests/unit/test_handler_purity.py` — расширен: AST-скан I-EXEC-CONTEXT-1 (все write entry points обёрнуты)

---

### M1: System Harness — VR Entry Point Adapter

```text
Spec:       §2 BC-VR-1, §4 Harness API, §6 M1
BCs:        BC-VR-1
Invariants: I-VR-API-1, I-VR-HARNESS-1, I-VR-HARNESS-2, I-VR-HARNESS-3, I-VR-HARNESS-4
Depends:    M0
Risks:      Harness должен использовать ТОЛЬКО execute_command + get_current_state;
            любой прямой вызов внутренних модулей нарушит I-VR-API-1 и инвалидирует VR
```

**Артефакты:**
- `tests/harness/__init__.py`
- `tests/harness/api.py` — `execute_sequence`, `replay`, `fork`, `rollback`
- `tests/harness/fixtures.py` — `db_factory`, `event_factory`, `state_builder`, `make_minimal_event`
- `tests/harness/generators.py` — `valid_command_sequence`, `edge_payload`, `adversarial_sequence`, `independent_command_pair`
- `tests/unit/commands/test_harness.py` — покрывает I-VR-HARNESS-1..4

---

### M2: Property Engine — P-1..P-10 + Relational Properties

```text
Spec:       §2 BC-VR-2, §6 M2/M3, §7 UC-17-1, Appendix B
BCs:        BC-VR-2
Invariants: I-VR-STABLE-1..3, I-VR-STABLE-6..9, I-STATE-DETERMINISTIC-1,
            I-STATE-TRANSITION-1, I-CONFLUENCE-STRONG-1, I-PERF-SCALING-1
Depends:    M1
Risks:      P-10 проверяет slope ratio t(2N)/t(N) < 2.5 — не абсолютный порог;
            слишком маленький N даёт шум. P-8 (concurrency) требует threading;
            без tmp_path-изоляции (I-VR-HARNESS-4) тесты будут интерферировать
```

**Артефакты:**
- `pyproject.toml` — добавлен `hypothesis>=6.100` в `[dev]`
- `tests/property/__init__.py`
- `tests/property/test_determinism.py` — P-1: `replay(log, db1) == replay(log, db2)` bit-exact
- `tests/property/test_confluence.py` — P-2: independent paths → same final state
- `tests/property/test_prefix_consistency.py` — P-3: prefix replay ⊆ full replay
- `tests/property/test_invariant_safety.py` — P-4: no invariant violation survives commit
- `tests/property/test_no_hidden_state.py` — P-5: SDDState = f(event_log) only
- `tests/property/test_event_integrity.py` — P-6: log append-only, ordered
- `tests/property/test_idempotency.py` — P-7: execute × N → same state as × 1
- `tests/property/test_concurrency.py` — P-8: one success + one StaleStateError
- `tests/property/test_schema_evolution.py` — P-9: v1 upcast correct; unknown events skipped
- `tests/property/test_performance.py` — P-10: slope ratio t(2N)/t(N) < 2.5 при N ≥ 1000
- `tests/property/test_state_transitions.py` — RP-1 (TaskCompleted delta), RP-2 (PhaseStarted reset), RP-3 (DecisionRecorded no side-effect)

---

### M3: Fuzz Engine — Adversarial + Interleaving

```text
Spec:       §2 BC-VR-3, §6 M4, §7 UC-17-3
BCs:        BC-VR-3
Invariants: I-VR-STABLE-4, I-VR-STABLE-7, I-CONFLUENCE-STRONG-1
Depends:    M1, M2
Risks:      G5 interleaving требует независимых команд — генератор independent_command_pair
            должен гарантировать отсутствие shared state; неверный генератор даёт false-positives
```

**Артефакты:**
- `tests/fuzz/__init__.py`
- `tests/fuzz/test_adversarial.py` — G4: concurrent writes, stale head, duplicates, schema corrupt
- `tests/fuzz/test_interleaving.py` — G5: [cmd_a, cmd_b] и [cmd_b, cmd_a] → state_hash совпадает

---

### M4: Runtime Enforcement — Context-Based Traps

```text
Spec:       §2 BC-VR-4, §6 M5, §7 UC-17-2
BCs:        BC-VR-4
Invariants: I-VR-STABLE-5, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1,
            I-STATE-ACCESS-LAYER-1, I-HANDLER-PURE-1
Depends:    M0
Risks:      Зависит только от M0 (ExecutionContext); можно реализовывать параллельно с M2..M3.
            monkeypatch-ловушки должны проверять именно KernelContextError, не generic AssertionError
```

**Артефакты:**
- `tests/integration/test_runtime_enforcement.py` — 4 теста:
  1. `execute_and_project` → `assert_in_kernel` PASS внутри kernel_context
  2. Прямой `EventStore.append` вне контекста → `KernelContextError`
  3. `rebuild_state` вне `project_all` → trap
  4. `get_current_state` вне guards/projections → trap

---

### M5: Evolution Validator — Backward + Forward Compatibility

```text
Spec:       §2 BC-VR-5, §6 M6, §7 UC-17-4
BCs:        BC-VR-5
Invariants: I-VR-STABLE-8, I-EVENT-UPCAST-1, I-EVOLUTION-FORWARD-1
Depends:    M1
Risks:      Нужен fixture `compatibility/fixtures/v1_events.json` с реальными v1-событиями;
            forward test вставляет synthetic FutureV2Event — replay не должен падать (unknown skip)
```

**Артефакты:**
- `compatibility/fixtures/v1_events.json` — набор исторических v1 событий
- `tests/integration/test_evolution.py` — 6 тестов:
  1. `test_event_schema_upcast_correctness` — v1 → upcast → SDDState корректен
  2. `test_forward_unknown_event_safe` — `replay(v1 + synthetic_v2)` не падает
  3. `test_upcast_no_data_loss` — все поля v1 события сохранены после upcast
  4. `test_unknown_fields_ignored` — extra поля в event payload игнорируются
  5. `test_backward_compat_state_hash` — upcast не меняет state_hash vs прямой v1 replay
  6. `test_evolution_idempotent` — повторный upcast того же события — без изменений

---

### M6: Failure Semantics — Deterministic Error Verification

```text
Spec:       §2 BC-VR-8, §6 M7, §7 UC-17-5
BCs:        BC-VR-8
Invariants: I-FAIL-DETERMINISTIC-1
Depends:    M1
Risks:      Тесты должны проверять именно тип ошибки (SDDError subclass) + message template,
            а не generic Exception; нарушение детерминированности → floating messages → FP
```

**Артефакты:**
- `tests/integration/test_failure_semantics.py` — 3 теста:
  1. Invalid command × 2 → одинаковый `error_type` + `message`
  2. `StaleStateError` × 2 → воспроизводимо (одинаковый seq, одинаковый error)
  3. Corrupted log → `replay` → конкретный `SDDError` (не generic Exception)

---

### M7: Mutation Engine — Kill Rate Verification

```text
Spec:       §2 BC-VR-6, §6 M8, §7 UC-17-7, Appendix A
BCs:        BC-VR-6
Invariants: I-VR-MUT-1, I-MUT-CRITICAL-1, I-VR-STABLE-10
Depends:    M2, M3
Risks:      mutmut медленный — запускается только в `make vr-mutation` (не в `vr-fast`);
            CRITICAL set (M1..M6) должен быть убит на 100% — выжившие → явный вывод с именем
```

**Артефакты:**
- `pyproject.toml` — добавлен `mutmut` в `[dev]`
- `.mutmut.toml` — 6 target-модулей + runner
- `scripts/assert_kill_rate.py` — `--min 0.95 --critical-min 1.0`; при fail → явный вывод выживших CRITICAL мутантов

---

### M8: CI Integration + VR Report

```text
Spec:       §2 BC-VR-7, §6 M9, §7 UC-17-6, §9 Verification
BCs:        BC-VR-7
Invariants: I-VR-REPORT-1, I-VR-STABLE-10
Depends:    M0, M1, M2, M3, M4, M5, M6, M7
Risks:      `generate_vr_report.py` читает результаты из pytest-json-report или вызывает pytest
            programmatically; UNSTABLE → exit 1 → CI fail; ручная правка VR_Report запрещена
```

**Артефакты:**
- `Makefile` — targets: `vr-fast`, `vr-full`, `vr-stress`, `vr-mutation`, `vr-release`, обновлены `check`, `ci`
- `scripts/generate_vr_report.py` — собирает P-1..P-10, RP, kill rate, commit hash, seed → JSON
- `.sdd/reports/VR_Report_v17.json` — `status: "STABLE"` iff все проверки PASS

---

## Execution Order

```
M0 (ExecutionContext) → M1 (Harness) → M2 (Property) → M3 (Fuzz) → M7 (Mutation)
                                     ↘ M4 (Enforcement) — параллельно с M2
                                     ↘ M5 (Evolution)   — параллельно с M2
                                     ↘ M6 (Failure)     — параллельно с M2
                                                          → M8 (CI + Report)
```

Линейный путь для однопоточной реализации: M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8.

---

## Risk Notes

- R-1: **Production-код минимален.** Только `execution_context.py` + одна строка в `registry.py`. Любое расширение за этот scope нарушает I-KERNEL-EXT-1. Строгий контроль diff на M0.
- R-2: **Hypothesis determinism.** `--hypothesis-seed=0` обязателен для воспроизводимости в CI. `vr-stress` использует random seed специально для поиска новых контрпримеров.
- R-3: **P-10 slope ratio.** Абсолютный порог времени зависит от железа. Тест проверяет только соотношение t(2N)/t(N) < 2.5, что инвариантно к среде.
- R-4: **mutmut время.** `make vr-mutation` не входит в быстрый цикл `vr-fast`. Запускается отдельно в nightly или перед `vr-release`.
- R-5: **CRITICAL мутанты.** Если хотя бы один CRITICAL мутант выжил, `assert_kill_rate.py` завершается exit 1 с именем мутанта и модулем. Тест suite нужно усилить, не понижать порог.
- R-6: **VR_Report ручная правка.** Запрещена. Единственный путь обновления — `make vr-release`. Нарушение инвалидирует I-VR-REPORT-1.
