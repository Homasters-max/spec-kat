# TaskSet_v34 — Phase 34: EventLog Deep Module

Spec: specs/Spec_v34_EventLogDeepModule.md
Plan: plans/Plan_v34.md

---

T-3401: Создать core/json_utils.py с canonical_json()

Status:               DONE
Spec ref:             Spec_v34 §2 (BC-34a), §4 (core/json_utils.py), §5 (I-EL-CANON-1)
Invariants:           I-EL-CANON-1
spec_refs:            [Spec_v34 §2, Spec_v34 §4, I-EL-CANON-1]
produces_invariants:  [I-EL-CANON-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/infra/event_log.py (источник canonical_json для копирования)
Outputs:              src/sdd/core/json_utils.py (новый файл с canonical_json())
Acceptance:           test_canonical_json_in_core: импорт `from sdd.core.json_utils import canonical_json` проходит; функция возвращает стабильный JSON с отсортированными ключами
Depends on:           —

---

T-3402: Обновить callers canonical_json на импорт из core/json_utils

Status:               DONE
Spec ref:             Spec_v34 §8 (canonical_json — callers)
Invariants:           I-EL-CANON-1
spec_refs:            [Spec_v34 §8, I-EL-CANON-1]
produces_invariants:  [I-EL-CANON-1]
requires_invariants:  [I-EL-CANON-1]
Inputs:               src/sdd/commands/_base.py, src/sdd/infra/event_log.py
Outputs:              src/sdd/commands/_base.py (обновлён импорт), src/sdd/infra/event_log.py (canonical_json удалена из файла)
Acceptance:           `grep -r "canonical_json" src/sdd/infra/event_log.py` — не находит определения функции; `python3 -c "from sdd.commands._base import *"` — нет ImportError
Depends on:           T-3401

---

T-3403: Добавить класс EventLogError в event_log.py

Status:               DONE
Spec ref:             Spec_v34 §4 (EventLogError)
Invariants:           I-EL-UNIFIED-1, I-EL-UNIFIED-2
spec_refs:            [Spec_v34 §4, I-EL-UNIFIED-1]
produces_invariants:  [I-EL-UNIFIED-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/infra/event_log.py, src/sdd/core/errors.py
Outputs:              src/sdd/infra/event_log.py (добавлен EventLogError(SDDError))
Acceptance:           `from sdd.infra.event_log import EventLogError` — нет ошибки; `issubclass(EventLogError, SDDError)` — True
Depends on:           T-3402

---

T-3404: Реализовать EventLog.__init__ и EventLog.append()

Status:               DONE
Spec ref:             Spec_v34 §4 (EventLog Public Interface), §5 (I-EL-UNIFIED-2, I-EL-BATCH-ID-1, I-KERNEL-WRITE-1), §6 (Pre/Post)
Invariants:           I-EL-UNIFIED-2, I-EL-BATCH-ID-1, I-KERNEL-WRITE-1, I-OPTLOCK-1, I-OPTLOCK-ATOMIC-1, I-IDEM-SCHEMA-1, I-IDEM-LOG-1, I-INVALID-CACHE-1, I-DB-1
spec_refs:            [Spec_v34 §4, Spec_v34 §6, I-EL-UNIFIED-2, I-EL-BATCH-ID-1, I-KERNEL-WRITE-1]
produces_invariants:  [I-EL-UNIFIED-2, I-EL-BATCH-ID-1]
requires_invariants:  [I-DB-1, I-ERROR-1]
Inputs:               src/sdd/infra/event_log.py, src/sdd/infra/event_store.py (логика для переноса), src/sdd/core/execution_context.py, src/sdd/infra/db.py, src/sdd/infra/paths.py
Outputs:              src/sdd/infra/event_log.py (класс EventLog с __init__ и append())
Acceptance:           test_event_log_append_simple, test_event_log_append_locked_optimistic, test_event_log_append_idempotent, test_event_log_append_batch_id_multi, test_event_log_append_batch_id_single_null — все PASS
Depends on:           T-3403

---

T-3405: Реализовать EventLog.replay() и EventLog.max_seq()

Status:               DONE
Spec ref:             Spec_v34 §4 (replay, max_seq), §6 (Pre/Post replay), §7 (UC-34-2)
Invariants:           I-INVALID-CACHE-1, I-ES-1
spec_refs:            [Spec_v34 §4, Spec_v34 §6, I-INVALID-CACHE-1]
produces_invariants:  [I-INVALID-CACHE-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/infra/event_log.py (в процессе разработки — добавление методов)
Outputs:              src/sdd/infra/event_log.py (методы replay() и max_seq() добавлены в класс EventLog)
Acceptance:           test_event_log_replay_filters_invalidated — PASS; `EventLog(db_path).max_seq()` возвращает None для пустой БД
Depends on:           T-3404

---

T-3406: Реализовать EventLog.exists_command(), exists_semantic(), get_error_count()

Status:               DONE
Spec ref:             Spec_v34 §4 (instance methods), §5 (I-EL-DEEP-1), §7 (UC-34-3)
Invariants:           I-EL-DEEP-1
spec_refs:            [Spec_v34 §4, I-EL-DEEP-1]
produces_invariants:  [I-EL-DEEP-1]
requires_invariants:  [I-DB-1]
Inputs:               src/sdd/infra/event_log.py (добавление instance-методов вместо module-level)
Outputs:              src/sdd/infra/event_log.py (exists_command, exists_semantic, get_error_count как методы EventLog)
Acceptance:           test_event_log_exists_command, test_event_log_exists_semantic, test_event_log_get_error_count — PASS; module-level `exists_command` / `exists_semantic` / `get_error_count` отсутствуют
Depends on:           T-3405

---

T-3407: Добавить guard в sdd_append_batch() против вызова внутри execute_command

Status:               DONE
Spec ref:             Spec_v34 §4 (sdd_append_batch), §5 (I-EL-NON-KERNEL-1)
Invariants:           I-EL-NON-KERNEL-1
spec_refs:            [Spec_v34 §4, I-EL-NON-KERNEL-1]
produces_invariants:  [I-EL-NON-KERNEL-1]
requires_invariants:  [I-KERNEL-WRITE-1]
Inputs:               src/sdd/infra/event_log.py (sdd_append_batch), src/sdd/core/execution_context.py
Outputs:              src/sdd/infra/event_log.py (sdd_append_batch проверяет контекст и рейзит KernelContextError)
Acceptance:           test_sdd_append_batch_raises_inside_kernel — PASS; вызов sdd_append_batch внутри execute_command → KernelContextError
Depends on:           T-3406

---

T-3408: Мигрировать registry.py с EventStore на EventLog

Status:               DONE
Spec ref:             Spec_v34 §8 (registry.py, Callers Mandatory Import Updates, UC-34-1)
Invariants:           I-KERNEL-WRITE-1, I-EL-UNIFIED-1, I-2, I-3
spec_refs:            [Spec_v34 §8, I-KERNEL-WRITE-1, I-2, I-3]
produces_invariants:  [I-KERNEL-WRITE-1]
requires_invariants:  [I-EL-UNIFIED-2, I-EL-DEEP-1]
Inputs:               src/sdd/commands/registry.py, src/sdd/infra/event_log.py (EventLog готов)
Outputs:              src/sdd/commands/registry.py (EventStore → EventLog, EventStoreError → EventLogError)
Acceptance:           test_write_kernel_full_chain_event_log, test_kernel_write_guard_via_event_log — PASS; `grep "EventStore" src/sdd/commands/registry.py` — пусто
Depends on:           T-3407

---

T-3409: Мигрировать src/ commands на EventLog (reconcile_bootstrap, validate_invariants, report_error, update_state)

Status:               DONE
Spec ref:             Spec_v34 §8 (Callers — src/)
Invariants:           I-EL-UNIFIED-1
spec_refs:            [Spec_v34 §8, I-EL-UNIFIED-1]
produces_invariants:  [I-EL-UNIFIED-1]
requires_invariants:  [I-EL-UNIFIED-2]
Inputs:               src/sdd/commands/reconcile_bootstrap.py, src/sdd/commands/validate_invariants.py, src/sdd/commands/report_error.py, src/sdd/commands/update_state.py
Outputs:              src/sdd/commands/reconcile_bootstrap.py, src/sdd/commands/validate_invariants.py, src/sdd/commands/report_error.py, src/sdd/commands/update_state.py (EventStore → EventLog)
Acceptance:           `grep -r "EventStore" src/sdd/commands/` — пусто; импорты во всех 4 файлах обновлены
Depends on:           T-3408

---

T-3410: Мигрировать infra/metrics.py на EventLog.append с allow_outside_kernel="metrics"

Status:               DONE
Spec ref:             Spec_v34 §8 (Non-kernel callers — metrics.py)
Invariants:           I-KERNEL-WRITE-1, I-EL-BATCH-ID-1
spec_refs:            [Spec_v34 §8, I-KERNEL-WRITE-1]
produces_invariants:  [I-KERNEL-WRITE-1]
requires_invariants:  [I-EL-UNIFIED-2, I-EL-BATCH-ID-1]
Inputs:               src/sdd/infra/metrics.py
Outputs:              src/sdd/infra/metrics.py (вызовы EventStore → EventLog.append(..., allow_outside_kernel="metrics"))
Acceptance:           test_metrics_non_kernel_write — PASS; запись TaskCompleted + MetricRecorded через metrics.py не вызывает KernelContextError
Depends on:           T-3409

---

T-3411: Создать tests/unit/infra/test_event_log_class.py

Status:               DONE
Spec ref:             Spec_v34 §9 (Verification table, тесты 1–16)
Invariants:           I-EL-UNIFIED-2, I-EL-DEEP-1, I-EL-CANON-1, I-EL-LEGACY-1, I-EL-BATCH-ID-1, I-EL-NON-KERNEL-1, I-DB-TEST-1, I-DB-TEST-2
spec_refs:            [Spec_v34 §9, I-EL-UNIFIED-2, I-EL-DEEP-1, I-EL-BATCH-ID-1]
produces_invariants:  [I-EL-UNIFIED-2, I-EL-DEEP-1, I-EL-CANON-1, I-EL-LEGACY-1, I-EL-BATCH-ID-1, I-EL-NON-KERNEL-1]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               src/sdd/infra/event_log.py (EventLog полностью реализован), tests/harness/fixtures.py
Outputs:              tests/unit/infra/test_event_log_class.py (новый файл: все 16 тестов из §9)
Acceptance:           pytest tests/unit/infra/test_event_log_class.py — все 16 тестов PASS
Depends on:           T-3410

---

T-3412: Мигрировать test_event_store.py по таблице §8

Status:               DONE
Spec ref:             Spec_v34 §8 (test_event_store.py — таблица миграции)
Invariants:           I-EL-UNIFIED-2, I-DB-TEST-1
spec_refs:            [Spec_v34 §8, I-EL-UNIFIED-2]
produces_invariants:  [I-EL-UNIFIED-2]
requires_invariants:  [I-DB-TEST-1, I-DB-TEST-2]
Inputs:               tests/unit/infra/test_event_store.py, tests/unit/infra/test_event_log_class.py
Outputs:              tests/unit/infra/test_event_store.py (test_append_is_atomic мигрирован в test_event_log_class.py; test_append_only_write_path удалён; test_crash_before_append_leaves_files_unchanged переписан)
Acceptance:           pytest tests/unit/infra/test_event_store.py — PASS; `grep "test_append_only_write_path" tests/unit/infra/test_event_store.py` — пусто
Depends on:           T-3411

---

T-3413: Обновить импорты во всех test-файлах (harness + integration + property + unit)

Status:               DONE
Spec ref:             Spec_v34 §8 (Callers — tests/)
Invariants:           I-EL-UNIFIED-1
spec_refs:            [Spec_v34 §8, I-EL-UNIFIED-1]
produces_invariants:  [I-EL-UNIFIED-1]
requires_invariants:  [I-EL-UNIFIED-2]
Inputs:               tests/harness/fixtures.py, tests/integration/test_runtime_enforcement.py, tests/integration/test_incident_backfill.py, tests/integration/test_failure_semantics.py, tests/property/test_concurrency.py, tests/property/test_schema_evolution.py, tests/property/test_performance.py, tests/unit/commands/test_command_idempotency.py, tests/unit/commands/test_validate_acceptance.py, tests/unit/infra/test_write_kernel_guard.py, tests/unit/infra/test_event_invalidation.py, tests/fuzz/test_adversarial.py
Outputs:              все перечисленные файлы (EventStore → EventLog, EventStoreError → EventLogError)
Acceptance:           `grep -r "EventStore" tests/` — пусто (кроме комментариев и строковых литералов в test_kernel_contract)
Depends on:           T-3412

---

T-3414: Обновить test_kernel_contract.py и удалить event_store.py

Status:               DONE
Spec ref:             Spec_v34 §8 (test_kernel_contract.py:35 и :78), §5 (I-EL-UNIFIED-1)
Invariants:           I-EL-UNIFIED-1
spec_refs:            [Spec_v34 §8, I-EL-UNIFIED-1]
produces_invariants:  [I-EL-UNIFIED-1]
requires_invariants:  [I-EL-UNIFIED-2, I-EL-DEEP-1]
Inputs:               tests/regression/test_kernel_contract.py, src/sdd/infra/event_store.py
Outputs:              tests/regression/test_kernel_contract.py (строка 35: проверка отсутствия event_store.py; строка 78: сохранена sdd_append_batch); src/sdd/infra/event_store.py (удалён)
Acceptance:           test_event_store_module_deleted — PASS; pytest tests/regression/test_kernel_contract.py — PASS; `ls src/sdd/infra/event_store.py` — "No such file"
Depends on:           T-3413

---

T-3415: Обновить kernel-contracts.md

Status:               DONE
Spec ref:             Spec_v34 §8 (Kernel-Contracts Update), §5 (I-KERNEL-WRITE-1 updated)
Invariants:           I-KERNEL-WRITE-1, I-EL-UNIFIED-1
spec_refs:            [Spec_v34 §8, I-KERNEL-WRITE-1]
produces_invariants:  [I-KERNEL-WRITE-1]
requires_invariants:  [I-EL-UNIFIED-1]
Inputs:               .sdd/docs/ref/kernel-contracts.md
Outputs:              .sdd/docs/ref/kernel-contracts.md (строка EventStore.append() удалена; EventLog поверхности обновлены по таблице §8; I-KERNEL-WRITE-1 переформулирован)
Acceptance:           `grep "EventStore" .sdd/docs/ref/kernel-contracts.md` — пусто; `grep "EventLog.append" .sdd/docs/ref/kernel-contracts.md` — находит запись в frozen surfaces
Depends on:           T-3414
