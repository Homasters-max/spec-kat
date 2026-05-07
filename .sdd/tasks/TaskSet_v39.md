# TaskSet_v39 — Phase 39: Event–Reducer Consistency (SSOT Fix)

Spec: specs/Spec_v39_EventRegistrySSot.md
Plan: plans/Plan_v39.md

---

T-3901: Refactor EventReducer — reorder ClassVars + _HANDLER_EVENTS + _KNOWN_NO_HANDLER derived + remove assert

Status:               DONE
Spec ref:             Spec_v39 §2 BC-39-2 — Рефакторинг reducer.py
Invariants:           I-EREG-1, I-ST-10
spec_refs:            [Spec_v39 §2 BC-39-2, I-EREG-1, I-ST-10]
produces_invariants:  [I-EREG-1]
requires_invariants:  [I-ST-10]
Inputs:               src/sdd/domain/state/reducer.py, src/sdd/core/events.py
Outputs:              src/sdd/domain/state/reducer.py
Acceptance:           _KNOWN_NO_HANDLER == V1_L1_EVENT_TYPES - frozenset(_EVENT_SCHEMA.keys()) при
                      инспекции; import-time assert отсутствует; порядок: _EVENT_SCHEMA →
                      _HANDLER_EVENTS → _KNOWN_NO_HANDLER
Depends on:           —

---

T-3902: Smoke-test импорта EventReducer после BC-39-2 рефакторинга

Status:               DONE
Spec ref:             Spec_v39 §8 — Verification п.1
Invariants:           I-EREG-1
spec_refs:            [Spec_v39 §8 п.1, I-EREG-1]
produces_invariants:  []
requires_invariants:  [I-EREG-1]
Inputs:               src/sdd/domain/state/reducer.py (после T-3901)
Outputs:              — (только наблюдение)
Acceptance:           `python3 -c "from sdd.domain.state.reducer import EventReducer"` завершается
                      без ошибок; нет NameError или ImportError
Depends on:           T-3901

---

T-3903: Создать test_i_st_10_all_event_types_classified

Status:               DONE
Spec ref:             Spec_v39 §2 BC-39-3 — Явный pytest-тест
Invariants:           I-ST-10
spec_refs:            [Spec_v39 §2 BC-39-3, I-ST-10]
produces_invariants:  [I-ST-10]
requires_invariants:  [I-EREG-1]
Inputs:               src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Outputs:              tests/unit/core/test_event_registry_consistency.py
Acceptance:           test_i_st_10_all_event_types_classified PASS; при симуляции missing-события
                      тест выдаёт диагностику "Events in V1_L1_EVENT_TYPES but not classified: {...}"
Depends on:           T-3901

---

T-3904: Создать test_i_ereg_1_known_no_handler_is_derived

Status:               DONE
Spec ref:             Spec_v39 §2 BC-39-3 — Явный pytest-тест
Invariants:           I-EREG-1
spec_refs:            [Spec_v39 §2 BC-39-3, I-EREG-1]
produces_invariants:  [I-EREG-1]
requires_invariants:  [I-EREG-1]
Inputs:               src/sdd/core/events.py, src/sdd/domain/state/reducer.py
Outputs:              tests/unit/core/test_event_registry_consistency.py
Acceptance:           test_i_ereg_1_known_no_handler_is_derived PASS; при симуляции статического
                      литерала тест выдаёт диагностику "Diff: {...}"
Depends on:           T-3903

---

T-3905: Запустить оба новых теста и проверить диагностические сообщения

Status:               DONE
Spec ref:             Spec_v39 §8 — Verification пп.2–3
Invariants:           I-EREG-1, I-ST-10
spec_refs:            [Spec_v39 §8 пп.2-3, I-EREG-1, I-ST-10]
produces_invariants:  []
requires_invariants:  [I-EREG-1, I-ST-10]
Inputs:               tests/unit/core/test_event_registry_consistency.py
Outputs:              — (только наблюдение)
Acceptance:           test_i_st_10_all_event_types_classified PASS;
                      test_i_ereg_1_known_no_handler_is_derived PASS
Depends on:           T-3904

---

T-3906: Полный прогон тест-сьюта — проверка отсутствия регрессий (TP-1)

Status:               DONE
Spec ref:             Spec_v39 §8 — Verification п.5
Invariants:           I-ST-10, I-EREG-1, I-HANDLER-PURE-1
spec_refs:            [Spec_v39 §8 п.5, I-HANDLER-PURE-1]
produces_invariants:  []
requires_invariants:  [I-EREG-1, I-ST-10]
Inputs:               tests/ (весь каталог), src/sdd/domain/state/reducer.py
Outputs:              — (только наблюдение)
Acceptance:           Все существующие тесты (1012+) PASS; новые тесты T-3903/T-3904 тоже PASS;
                      `sdd show-state` возвращает корректный результат (п.6 §8)
Depends on:           T-3905

---

T-3907: Верифицировать Event-Addition Rule в TaskSet_template.md (BC-39-4)

Status:               DONE
Spec ref:             Spec_v39 §2 BC-39-4 — Правило в TaskSet-шаблоне
Invariants:           I-EREG-SCOPE-1
spec_refs:            [Spec_v39 §2 BC-39-4, I-EREG-SCOPE-1]
produces_invariants:  [I-EREG-SCOPE-1]
requires_invariants:  []
Inputs:               .sdd/templates/TaskSet_template.md
Outputs:              .sdd/templates/TaskSet_template.md
Acceptance:           Секция Event-Addition Rule (I-EREG-SCOPE-1) присутствует; ссылки на
                      test_i_st_10_all_event_types_classified и test_i_ereg_1_known_no_handler_is_derived
                      корректны; разделение no-handler / has-handler чёткое;
                      содержимое соответствует Spec_v39 §2 BC-39-4 дословно
Depends on:           T-3905

---

T-3908: Финальная валидация — все §8 verification checks Phase 39

Status:               DONE
Spec ref:             Spec_v39 §8 — Verification пп.1–6
Invariants:           I-EREG-1, I-EREG-SCOPE-1, I-ST-10
spec_refs:            [Spec_v39 §8, I-EREG-1, I-EREG-SCOPE-1, I-ST-10]
produces_invariants:  []
requires_invariants:  [I-EREG-1, I-EREG-SCOPE-1, I-ST-10]
Inputs:               src/sdd/domain/state/reducer.py, tests/unit/core/test_event_registry_consistency.py,
                      .sdd/templates/TaskSet_template.md
Outputs:              — (только наблюдение)
Acceptance:           Все 6 пунктов Spec_v39 §8 PASS:
                      1. import EventReducer — OK;
                      2. test_i_st_10 PASS;
                      3. test_i_ereg_1 PASS;
                      4. добавление no-handler типа только в events.py → тест PASS, reducer.py не трогается;
                      5. все 1012+ тестов PASS;
                      6. sdd show-state работает
Depends on:           T-3906, T-3907

---

<!-- Granularity: 8 tasks (TG-2: recommended 10–30; justified by minimal 3-BC scope). -->
<!-- Every task is independently implementable and independently testable (TG-1). -->

---

### Event-Addition Rule (I-EREG-SCOPE-1)

Если Task добавляет новый event type:

THEN Outputs MUST include:
  - src/sdd/core/events.py              (V1_L1_EVENT_TYPES — всегда)
  - src/sdd/domain/state/reducer.py    (ТОЛЬКО если тип имеет handler:
                                        _EVENT_SCHEMA + _fold())

DoD MUST include:
  - test_i_st_10_all_event_types_classified PASS
  - test_i_ereg_1_known_no_handler_is_derived PASS

NOTE: reducer.py НЕ нужен в Outputs для no-handler событий (Spec_v39).
