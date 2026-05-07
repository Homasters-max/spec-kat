# TaskSet_v49 — Phase 49: Session Dedup Fixes

Spec: specs/Spec_v49_SessionDedupFixes.md
Plan: plans/Plan_v49.md

---

T-4901: BC-49-A — Add logging.basicConfig to CLI

Status:               DONE
Spec ref:             Spec_v49 §2 Architecture / BC-49-A — CLI Logging
Invariants:           I-CLI-LOG-LEVEL-1
spec_refs:            [Spec_v49 §2 BC-49-A, Spec_v49 §4 BC-49-A, I-CLI-LOG-LEVEL-1]
produces_invariants:  [I-CLI-LOG-LEVEL-1]
requires_invariants:  []
Inputs:               src/sdd/cli.py
Outputs:              src/sdd/cli.py
Acceptance:           `logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")` вызван в `@click.group()` callback cli() до dispatch любой подкоманды
Depends on:           —

---

T-4902: BC-49-B Part 1 — Add _AUDIT_ONLY_EVENTS + is_invalidatable() to EventReducer

Status:               DONE
Spec ref:             Spec_v49 §2 Architecture / BC-49-B — I-INVALID-4 audit-only exclusion; §4 Types & Interfaces BC-49-B
Invariants:           I-AUDIT-ONLY-SSOT-1, I-INVALID-AUDIT-ONLY-1, I-INVALIDATABLE-INTERFACE-1
spec_refs:            [Spec_v49 §2 BC-49-B, Spec_v49 §4 BC-49-B, I-AUDIT-ONLY-SSOT-1, I-INVALID-AUDIT-ONLY-1, I-INVALIDATABLE-INTERFACE-1]
produces_invariants:  [I-AUDIT-ONLY-SSOT-1, I-INVALID-AUDIT-ONLY-1, I-INVALIDATABLE-INTERFACE-1]
requires_invariants:  []
Inputs:               src/sdd/domain/state/reducer.py
Outputs:              src/sdd/domain/state/reducer.py
Acceptance:           `EventReducer._AUDIT_ONLY_EVENTS = frozenset({"SessionDeclared"})` объявлена в классе; classmethod `is_invalidatable(event_type)` возвращает True для "SessionDeclared" и неизвестных типов, False для state-mutating событий из _EVENT_SCHEMA (не-audit-only)
Depends on:           —

---

T-4903: BC-49-B Part 2 — Update InvalidateEventHandler to use is_invalidatable()

Status:               DONE
Spec ref:             Spec_v49 §2 Architecture / BC-49-B — invalidate_event.py; §4 Types & Interfaces BC-49-B
Invariants:           I-INVALIDATABLE-INTERFACE-1, I-INVALID-4, I-INVALID-AUDIT-ONLY-1
spec_refs:            [Spec_v49 §2 BC-49-B, Spec_v49 §4 BC-49-B, I-INVALIDATABLE-INTERFACE-1, I-INVALID-4]
produces_invariants:  [I-INVALIDATABLE-INTERFACE-1]
requires_invariants:  [I-AUDIT-ONLY-SSOT-1, I-INVALIDATABLE-INTERFACE-1]
Inputs:               src/sdd/commands/invalidate_event.py, src/sdd/domain/state/reducer.py
Outputs:              src/sdd/commands/invalidate_event.py
Acceptance:           I-INVALID-4 guard в `InvalidateEventHandler.handle()` вызывает `EventReducer.is_invalidatable(target_type)` вместо прямого `target_type in EventReducer._EVENT_SCHEMA`; прямой доступ к `_EVENT_SCHEMA` из invalidate_event.py для проверки инвалидируемости отсутствует
Depends on:           T-4902

---

T-4904: BC-49-C — Purify RecordSessionHandler.handle()

Status:               DONE
Spec ref:             Spec_v49 §2 Architecture / BC-49-C — Remove handler-level dedup; §4 Types & Interfaces BC-49-C
Invariants:           I-HANDLER-SESSION-PURE-1, I-HANDLER-PURE-1, I-DEDUP-KERNEL-AUTHORITY-1
spec_refs:            [Spec_v49 §2 BC-49-C, Spec_v49 §4 BC-49-C, I-HANDLER-SESSION-PURE-1, I-HANDLER-PURE-1, I-DEDUP-KERNEL-AUTHORITY-1]
produces_invariants:  [I-HANDLER-SESSION-PURE-1, I-DEDUP-KERNEL-AUTHORITY-1]
requires_invariants:  [I-HANDLER-PURE-1]
Inputs:               src/sdd/commands/record_session.py
Outputs:              src/sdd/commands/record_session.py
Acceptance:           метод `_session_declared_today()` удалён; `import open_sdd_connection` удалён если не используется; `handle()` всегда возвращает `[SessionDeclaredEvent(...)]` без IO; никакого DB-соединения в handle()
Depends on:           —

---

T-4905: Tests BC-49-A — CLI logging unit tests

Status:               DONE
Spec ref:             Spec_v49 §9 Verification — tests 1–2
Invariants:           I-CLI-LOG-LEVEL-1
spec_refs:            [Spec_v49 §9, I-CLI-LOG-LEVEL-1]
produces_invariants:  [I-CLI-LOG-LEVEL-1]
requires_invariants:  [I-CLI-LOG-LEVEL-1]
Inputs:               src/sdd/cli.py
Outputs:              tests/unit/cli/test_cli_logging.py
Acceptance:           `test_cli_basicconfig_called_before_subcommand` PASS; `test_cli_info_log_visible_in_stderr` PASS
Depends on:           T-4901

---

T-4906: Tests BC-49-B Part 1 — EventReducer interface unit tests

Status:               DONE
Spec ref:             Spec_v49 §9 Verification — tests 3–6
Invariants:           I-AUDIT-ONLY-SSOT-1, I-INVALID-AUDIT-ONLY-1, I-INVALIDATABLE-INTERFACE-1, I-INVALID-4
spec_refs:            [Spec_v49 §9, I-AUDIT-ONLY-SSOT-1, I-INVALID-AUDIT-ONLY-1, I-INVALIDATABLE-INTERFACE-1]
produces_invariants:  [I-AUDIT-ONLY-SSOT-1, I-INVALID-AUDIT-ONLY-1, I-INVALIDATABLE-INTERFACE-1]
requires_invariants:  [I-AUDIT-ONLY-SSOT-1, I-INVALIDATABLE-INTERFACE-1]
Inputs:               src/sdd/infra/reducer.py
Outputs:              tests/unit/infra/test_reducer_invalidatable.py
Acceptance:           `test_audit_only_events_in_reducer_contains_session_declared` PASS; `test_is_invalidatable_returns_true_for_session_declared` PASS; `test_is_invalidatable_returns_false_for_state_mutating` PASS; `test_is_invalidatable_returns_true_for_unknown_type` PASS
Depends on:           T-4902

---

T-4907: Tests BC-49-B Part 2 — Invalidation behavior unit tests

Status:               DONE
Spec ref:             Spec_v49 §9 Verification — tests 7–8
Invariants:           I-INVALID-AUDIT-ONLY-1, I-INVALID-4
spec_refs:            [Spec_v49 §9, I-INVALID-AUDIT-ONLY-1, I-INVALID-4]
produces_invariants:  [I-INVALID-AUDIT-ONLY-1]
requires_invariants:  [I-INVALIDATABLE-INTERFACE-1, I-INVALID-4]
Inputs:               src/sdd/commands/invalidate_event.py, src/sdd/infra/reducer.py
Outputs:              tests/unit/commands/test_invalidate_event.py
Acceptance:           `test_invalidate_session_declared_succeeds` PASS; `test_invalidate_state_mutating_still_blocked` PASS
Depends on:           T-4903

---

T-4908: Tests BC-49-C — Handler purity unit tests

Status:               DONE
Spec ref:             Spec_v49 §9 Verification — tests 9–10
Invariants:           I-HANDLER-SESSION-PURE-1, I-HANDLER-PURE-1
spec_refs:            [Spec_v49 §9, I-HANDLER-SESSION-PURE-1, I-HANDLER-PURE-1]
produces_invariants:  [I-HANDLER-SESSION-PURE-1]
requires_invariants:  [I-HANDLER-PURE-1]
Inputs:               src/sdd/commands/record_session.py
Outputs:              tests/unit/commands/test_record_session_dedup.py
Acceptance:           `test_handler_handle_returns_event_without_io` PASS; `test_handler_handle_is_pure_no_db_call` PASS
Depends on:           T-4904

---

T-4909: Test UC-49-3 — Re-emit after invalidation

Status:               DONE
Spec ref:             Spec_v49 §7 Use Cases / UC-49-3; §9 Verification — test 11
Invariants:           I-DEDUP-KERNEL-AUTHORITY-1, I-SESSION-INVALIDATION-1
spec_refs:            [Spec_v49 §7 UC-49-3, Spec_v49 §9, I-DEDUP-KERNEL-AUTHORITY-1, I-SESSION-INVALIDATION-1]
produces_invariants:  [I-DEDUP-KERNEL-AUTHORITY-1, I-SESSION-INVALIDATION-1]
requires_invariants:  [I-HANDLER-SESSION-PURE-1, I-INVALID-AUDIT-ONLY-1, I-DEDUP-KERNEL-AUTHORITY-1]
Inputs:               src/sdd/infra/projections.py, src/sdd/infra/projector.py, src/sdd/commands/record_session.py, src/sdd/commands/invalidate_event.py
Outputs:              tests/unit/infra/test_projector_sessions.py
Acceptance:           `test_reemit_after_invalidation_creates_new_event` PASS; event_log содержит 2 SessionDeclared для той же (type, phase_id) после invalidate+re-emit
Depends on:           T-4903, T-4904

---

T-4910: Smoke Verification — UC-49-1, UC-49-2, UC-49-3

Status:               DONE
Spec ref:             Spec_v49 §9 Verification — Smoke scenarios; §7 Use Cases UC-49-1..3
Invariants:           I-CLI-LOG-LEVEL-1, I-INVALID-AUDIT-ONLY-1, I-DEDUP-KERNEL-AUTHORITY-1
spec_refs:            [Spec_v49 §9 Smoke, Spec_v49 §7, I-CLI-LOG-LEVEL-1, I-INVALID-AUDIT-ONLY-1, I-DEDUP-KERNEL-AUTHORITY-1]
produces_invariants:  []
requires_invariants:  [I-CLI-LOG-LEVEL-1, I-INVALID-AUDIT-ONLY-1, I-DEDUP-KERNEL-AUTHORITY-1]
Inputs:               src/sdd/cli.py, src/sdd/commands/record_session.py, src/sdd/commands/invalidate_event.py, src/sdd/domain/state/reducer.py
Outputs:              .sdd/reports/ValidationReport_T-4910.md
Acceptance:           UC-49-1: `sdd record-session ... 2>&1 | grep "Session deduplicated"` → exit 0; UC-49-2: `sdd invalidate-event --seq <SessionDeclared_seq> --force` → exit 0; UC-49-3: повторный `sdd record-session` после инвалидации → 2 SessionDeclared в event_log
Depends on:           T-4901, T-4902, T-4903, T-4904, T-4905, T-4906, T-4907, T-4908, T-4909

---

<!-- Granularity: 10–30 tasks per phase (TG-2). Regroup if exceeded (TG-3). -->
<!-- Every task must be independently implementable and independently testable (TG-1). -->

---

### Event-Addition Rule (I-EREG-SCOPE-1)

Phase 49 не добавляет новых event types (Spec_v49 §3).
Event-Addition Rule не применяется.
