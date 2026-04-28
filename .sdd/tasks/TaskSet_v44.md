# TaskSet_v44 — Phase 44: Routing Switch (SAFE, minimal diff)

Spec: specs/Spec_v44_RoutingSwitch.md
Plan: plans/Plan_v44.md

---

T-4401: registry.py — replace event_store_file() with event_store_url()

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-A — Полная замена event_store_file() в CLI-модулях
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-A, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/registry.py (строки 630, 806, 847)
Outputs:              src/sdd/commands/registry.py
Acceptance:           grep event_store_file src/sdd/commands/registry.py → пустой результат
Depends on:           —

---

T-4402: show_state.py — replace event_store_file() with event_store_url()

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-A — Полная замена event_store_file() в CLI-модулях
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-A, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/show_state.py (строка 129)
Outputs:              src/sdd/commands/show_state.py
Acceptance:           grep event_store_file src/sdd/commands/show_state.py → пустой результат
Depends on:           —

---

T-4403: activate_phase.py — replace event_store_file() with event_store_url()

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-A — Полная замена event_store_file() в CLI-модулях
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-A, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/activate_phase.py (строка 186)
Outputs:              src/sdd/commands/activate_phase.py
Acceptance:           grep event_store_file src/sdd/commands/activate_phase.py → пустой результат
Depends on:           —

---

T-4404: switch_phase.py — replace event_store_file() with event_store_url()

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-A — Полная замена event_store_file() в CLI-модулях
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-A, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/switch_phase.py (строка 140)
Outputs:              src/sdd/commands/switch_phase.py
Acceptance:           grep event_store_file src/sdd/commands/switch_phase.py → пустой результат
Depends on:           —

---

T-4405: metrics_report.py — replace event_store_file() with event_store_url()

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-A — Полная замена event_store_file() в CLI-модулях
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-A, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/metrics_report.py (строка 183)
Outputs:              src/sdd/commands/metrics_report.py
Acceptance:           grep event_store_file src/sdd/commands/metrics_report.py → пустой результат
Depends on:           —

---

T-4406: validate_invariants.py — replace event_store_file() with event_store_url()

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-A — Полная замена event_store_file() в CLI-модулях
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-A, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/validate_invariants.py (строка 455)
Outputs:              src/sdd/commands/validate_invariants.py
Acceptance:           grep event_store_file src/sdd/commands/validate_invariants.py → пустой результат
Depends on:           —

---

T-4407: next_tasks.py — replace event_store_file() with event_store_url()

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-A — Полная замена event_store_file() в CLI-модулях
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-A, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/next_tasks.py (строка 27)
Outputs:              src/sdd/commands/next_tasks.py
Acceptance:           grep event_store_file src/sdd/commands/next_tasks.py → пустой результат
Depends on:           —

---

T-4408: reconcile_bootstrap.py + invalidate_event.py — replace event_store_file() with event_store_url()

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-A — Полная замена event_store_file() в CLI-модулях
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-A, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/reconcile_bootstrap.py (строка 50), src/sdd/commands/invalidate_event.py (строка 113)
Outputs:              src/sdd/commands/reconcile_bootstrap.py, src/sdd/commands/invalidate_event.py
Acceptance:           grep event_store_file src/sdd/commands/reconcile_bootstrap.py src/sdd/commands/invalidate_event.py → пустой результат
Depends on:           —

---

T-4409: infra/projections.py — replace event_store_file() with event_store_url()

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-A — Полная замена event_store_file() в CLI-модулях
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-A, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/infra/projections.py (строка 65)
Outputs:              src/sdd/infra/projections.py
Acceptance:           grep event_store_file src/sdd/infra/projections.py → пустой результат
Depends on:           —

---

T-4410: update_state.py — argparse eager evaluation fix

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-B — Argparse eager evaluation fix
Invariants:           I-CLI-DB-RESOLUTION-1
spec_refs:            [Spec_v44 §2 BC-44-B, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/update_state.py (строки 394, 395, 404, 409, 410)
Outputs:              src/sdd/commands/update_state.py
Acceptance:           test_update_state_argparse_no_eager_eval PASS; import update_state → event_store_url() не вызвана
Depends on:           —

---

T-4411: query_events.py + report_error.py — argparse eager evaluation fix

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-B — Argparse eager evaluation fix
Invariants:           I-CLI-DB-RESOLUTION-1
spec_refs:            [Spec_v44 §2 BC-44-B, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/commands/query_events.py (строка 65), src/sdd/commands/report_error.py (строка 99)
Outputs:              src/sdd/commands/query_events.py, src/sdd/commands/report_error.py
Acceptance:           test_query_events_argparse_no_eager_eval PASS; test_report_error_argparse_no_eager_eval PASS
Depends on:           —

---

T-4412: cli.py — remove hardcoded DuckDB path

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-C — cli.py hardcoded path
Invariants:           I-CLI-DB-RESOLUTION-1
spec_refs:            [Spec_v44 §2 BC-44-C, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/cli.py (инлайн-конструкция _root / "state" / "sdd_events.duckdb")
Outputs:              src/sdd/cli.py
Acceptance:           grep sdd_events.duckdb src/sdd/cli.py → пустой результат; sdd show-state работает после замены
Depends on:           —

---

T-4413: log_tool.py — subprocess DB routing fix

Status:               DONE
Spec ref:             Spec_v44 §2, BC-44-D — log_tool.py subprocess routing fix
Invariants:           I-CLI-DB-RESOLUTION-1, I-DB-1
spec_refs:            [Spec_v44 §2 BC-44-D, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-EVENT-STORE-URL-1]
Inputs:               src/sdd/log_tool.py
Outputs:              src/sdd/log_tool.py
Acceptance:           test_log_tool_uses_event_store_url_fallback PASS; без SDD_DB_PATH и SDD_DATABASE_URL → DuckDB path
Depends on:           —

---

T-4414: test_paths.py — enforcement tests BC-44-E

Status:               DONE
Spec ref:             Spec_v44 §2 BC-44-E; §9 Unit Tests 1–6
Invariants:           I-CLI-DB-RESOLUTION-1
spec_refs:            [Spec_v44 §2 BC-44-E, Spec_v44 §9, I-CLI-DB-RESOLUTION-1]
produces_invariants:  [I-CLI-DB-RESOLUTION-1]
requires_invariants:  [I-CLI-DB-RESOLUTION-1]
Inputs:               tests/unit/infra/test_paths.py (существующий или новый файл)
Outputs:              tests/unit/infra/test_paths.py
Acceptance:           pytest tests/unit/infra/test_paths.py → все 6 тестов PASS (test_no_event_store_file_calls_in_cli, test_no_duckdb_hardcodes_in_cli, test_update_state_argparse_no_eager_eval, test_query_events_argparse_no_eager_eval, test_report_error_argparse_no_eager_eval, test_log_tool_uses_event_store_url_fallback)
Depends on:           T-4401, T-4402, T-4403, T-4404, T-4405, T-4406, T-4407, T-4408, T-4409, T-4410, T-4411, T-4412, T-4413

---

<!-- Granularity: 14 tasks (TG-2: 10–30). Each task independently implementable and testable (TG-1). -->
<!-- All Plan milestones covered: M1→T-4401..T-4409, M2→T-4410..T-4411, M3→T-4412, M4→T-4413, M5→T-4414 (SDD-3). -->

---

### Event-Addition Rule (I-EREG-SCOPE-1)

Phase 44 не вводит новых domain events (Spec_v44 §3). Правило I-EREG-SCOPE-1 не применяется.
