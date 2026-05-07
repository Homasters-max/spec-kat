# TaskSet_v1 — Phase 1: Foundation

Spec: specs/Spec_v1_Foundation.md
Plan: plans/Plan_v1.md

---

T-101: pyproject.toml + package skeleton

Status:               DONE
Spec ref:             Spec_v1 §0 Goal, §2 Dependencies
Invariants:           (toolchain prerequisite for all tasks)
spec_refs:            [Spec_v1 §0, Spec_v1 §2]
produces_invariants:  []
requires_invariants:  []
Inputs:               —
Outputs:              pyproject.toml, src/sdd/__init__.py, src/sdd/core/__init__.py, src/sdd/infra/__init__.py
Acceptance:           ruff check src/ exits 0; mypy src/sdd/ exits 0 on empty package; pytest --collect-only exits 0
Depends on:           —

---

T-102: core/errors.py — SDDError hierarchy

Status:               DONE
Spec ref:             Spec_v1 §4.1 — SDDError Hierarchy
Invariants:           (base error types; no standalone invariant, depended on by all BCs)
spec_refs:            [Spec_v1 §4.1]
produces_invariants:  []
requires_invariants:  []
Inputs:               pyproject.toml, src/sdd/__init__.py
Outputs:              src/sdd/core/errors.py
Acceptance:           All 9 exception classes defined (SDDError, ScopeViolation, PhaseGuardError, MissingContext, Inconsistency, VersionMismatch, MissingState, InvalidState, NormViolation); `from sdd.core.errors import SDDError` succeeds; mypy strict passes
Depends on:           T-101

---

T-103: core/events.py — DomainEvent dataclasses + EventLevel + classify_event_level

Status:               DONE
Spec ref:             Spec_v1 §3 Domain Events, §4.3 EventLevel + classify_event_level
Invariants:           I-PK-4
spec_refs:            [Spec_v1 §3, Spec_v1 §4.3, I-PK-4]
produces_invariants:  [I-PK-4]
requires_invariants:  []
Inputs:               src/sdd/__init__.py, src/sdd/core/errors.py
Outputs:              src/sdd/core/events.py
Acceptance:           DomainEvent, ErrorEvent, CommandEvent frozen dataclasses defined; EventLevel.L1/L2/L3 constants; V1_L1_EVENT_TYPES and V2_L1_EVENT_TYPES frozensets defined (identical per I-EL-6); classify_event_level("TaskImplemented") == "L1"; classify_event_level("ToolUseStarted") == "L3"; classify_event_level("MetricRecorded") == "L2"; mypy strict passes
Depends on:           T-102

---

T-104: core/types.py — Command dataclass + CommandHandler Protocol

Status:               DONE
Spec ref:             Spec_v1 §4.2 — CommandHandler Protocol
Invariants:           I-CMD-1a
spec_refs:            [Spec_v1 §4.2, I-CMD-1a]
produces_invariants:  [I-CMD-1a]
requires_invariants:  []
Inputs:               src/sdd/core/events.py, src/sdd/core/errors.py
Outputs:              src/sdd/core/types.py
Acceptance:           Command dataclass has command_id: str, command_type: str, payload: Mapping[str, Any] fields; CommandHandler Protocol declares handle(command) -> List[DomainEvent]; payload uses MappingProxyType at construction; mypy structural check passes
Depends on:           T-103

---

T-115: core/__init__.py — re-exports public BC-CORE API

Status:               DONE
Spec ref:             Spec_v1 §2 BC-CORE __init__.py
Invariants:           (public API contract for BC-CORE)
spec_refs:            [Spec_v1 §2]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/core/errors.py, src/sdd/core/events.py, src/sdd/core/types.py
Outputs:              src/sdd/core/__init__.py
Acceptance:           `from sdd.core import SDDError, DomainEvent, ErrorEvent, CommandEvent, EventLevel, CommandHandler, classify_event_level` succeeds without error; no circular imports
Depends on:           T-102, T-103, T-104

---

T-117: tests/unit/domain/test_types.py — I-CMD-1a

Status:               DONE
Spec ref:             Spec_v1 §5 I-CMD-1a, §9 row 6
Invariants:           I-CMD-1a
spec_refs:            [Spec_v1 §5 I-CMD-1a, Spec_v1 §9]
produces_invariants:  [I-CMD-1a]
requires_invariants:  [I-CMD-1a]
Inputs:               src/sdd/core/types.py, src/sdd/core/events.py, src/sdd/core/__init__.py
Outputs:              tests/__init__.py, tests/unit/__init__.py, tests/unit/domain/__init__.py, tests/unit/domain/test_types.py
Acceptance:           pytest tests/unit/domain/test_types.py passes; test_command_has_command_id verifies Command.command_id field exists; test_commandhandler_protocol verifies structural subtyping via runtime check
Depends on:           T-115

---

T-105: infra/db.py — DuckDB schema + open_sdd_connection + SDD_MIGRATION_REGISTRY

Status:               DONE
Spec ref:             Spec_v1 §2 BC-INFRA db.py, §6 open_sdd_connection pre/post, §8 Migration
Invariants:           I-PK-1, I-EL-8
spec_refs:            [Spec_v1 §2, Spec_v1 §6, Spec_v1 §8, I-PK-1, I-EL-8]
produces_invariants:  [I-PK-1, I-EL-8]
requires_invariants:  []
Inputs:               src/sdd/__init__.py, src/sdd/core/__init__.py
Outputs:              src/sdd/infra/db.py
Acceptance:           open_sdd_connection(":memory:") returns DuckDBPyConnection; events table has all v2 columns: seq, event_id, event_type, payload, appended_at, level, event_source, caused_by_meta_seq, expired; SDD_MIGRATION_REGISTRY applies migrations 1-3 (incl. ADD COLUMN event_source DEFAULT 'runtime', ADD COLUMN caused_by_meta_seq BIGINT); second call on same path returns same schema without error (I-PK-1); SDD_EVENTS_DB constant defined
Depends on:           T-115

---

T-116: SDD_SEQ_CHECKPOINT + dynamic sequence restart in open_sdd_connection

Status:               DONE
Spec ref:             Spec_v1 §5 I-EL-5b, CLAUDE.md §0.12 SDD-SEQ-1
Invariants:           I-EL-5b
spec_refs:            [Spec_v1 §5 I-EL-5b, I-EL-5b]
produces_invariants:  [I-EL-5b]
requires_invariants:  [I-PK-1]
Inputs:               src/sdd/infra/db.py
Outputs:              src/sdd/infra/db.py
Acceptance:           SDD_SEQ_CHECKPOINT = 1 defined in db.py; open_sdd_connection executes `CREATE OR REPLACE SEQUENCE sdd_event_seq START {next_seq}` where next_seq = max(SDD_SEQ_CHECKPOINT, current_max + 1) on every call; three sequential open+append+close cycles produce strictly increasing seq values across all three sessions (I-EL-5b)
Depends on:           T-105

---

T-113: tests/conftest.py — shared DB fixtures

Status:               DONE
Spec ref:             Plan_v1 M4 (T-113 shared fixtures)
Invariants:           (test infrastructure prerequisite)
spec_refs:            [Plan_v1 M4]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/infra/db.py
Outputs:              tests/conftest.py
Acceptance:           in_memory_db fixture provides open_sdd_connection(":memory:") scoped to function; tmp_db_path fixture provides unique tmp file path; fixtures importable by all test modules via conftest.py discovery
Depends on:           T-116

---

T-106: tests/unit/infra/test_db.py

Status:               DONE
Spec ref:             Spec_v1 §9 row 1
Invariants:           I-PK-1, I-EL-5b, I-EL-8
spec_refs:            [Spec_v1 §9, I-PK-1, I-EL-5b, I-EL-8]
produces_invariants:  [I-PK-1, I-EL-5b, I-EL-8]
requires_invariants:  [I-PK-1, I-EL-5b, I-EL-8]
Inputs:               src/sdd/infra/db.py, tests/conftest.py
Outputs:              tests/unit/infra/__init__.py, tests/unit/infra/test_db.py
Acceptance:           pytest tests/unit/infra/test_db.py passes; test_open_connection_idempotent (I-PK-1); test_schema_has_v2_columns (all v2 columns present); test_seq_monotonic (seq strictly increasing across 3 reconnections — I-EL-5b)
Depends on:           T-116, T-113

---

T-107: infra/event_log.py — sdd_append, sdd_append_batch, sdd_replay, meta_context, EventInput

Status:               DONE
Spec ref:             Spec_v1 §4.4–§4.7, §6 sdd_append/sdd_replay/sdd_append_batch pre/post
Invariants:           I-PK-2, I-PK-3, I-PK-4, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12
spec_refs:            [Spec_v1 §4.4, Spec_v1 §4.5, Spec_v1 §4.6, Spec_v1 §4.7, Spec_v1 §6, I-PK-2, I-PK-3, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12]
produces_invariants:  [I-PK-2, I-PK-3, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12]
requires_invariants:  [I-PK-1, I-EL-5b, I-EL-8]
Inputs:               src/sdd/infra/db.py, src/sdd/core/__init__.py
Outputs:              src/sdd/infra/event_log.py
Acceptance:           sdd_append, sdd_append_batch, sdd_replay, meta_context, EventInput, _make_event_id all defined; sdd_append raises ValueError for event_source ∉ {"meta","runtime"} (I-EL-1); sdd_append with duplicate event_id → ON CONFLICT DO NOTHING, no exception (I-PK-2); sdd_replay() defaults to level="L1" source="runtime" (I-EL-10); meta_context propagates caused_by_meta_seq via contextvars.ContextVar (I-EL-8a); no duckdb.connect call in this file (I-EL-9); event_id = SHA-256(event_type + canonical_payload + str(ts)) where canonical_payload = json.dumps(payload, sort_keys=True) and full input encoded as UTF-8 before hashing: hashlib.sha256((event_type + canonical_payload + str(ts)).encode("utf-8")).hexdigest() (I-EL-12); archive_expired_l3() sets expired=True, no DELETE (I-EL-7); sdd_append_batch writes atomically in single transaction (I-EL-11)
Depends on:           T-116, T-115

---

T-108: tests/unit/infra/test_event_log.py

Status:               DONE
Spec ref:             Spec_v1 §9 row 2
Invariants:           I-PK-2, I-PK-3, I-PK-4, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12
spec_refs:            [Spec_v1 §9, I-PK-2, I-PK-3, I-PK-4, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12]
produces_invariants:  [I-PK-2, I-PK-3, I-PK-4, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12]
requires_invariants:  [I-PK-2, I-PK-3, I-EL-1, I-EL-2, I-EL-7, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12]
Inputs:               src/sdd/infra/event_log.py, src/sdd/infra/db.py, tests/conftest.py
Outputs:              tests/unit/infra/test_event_log.py
Acceptance:           pytest tests/unit/infra/test_event_log.py passes; test_sdd_append_idempotent; test_replay_ordered_by_seq; test_replay_filters_level_source; test_l3_archived_not_deleted; test_batch_atomic (inject failure mid-batch, verify rollback); test_i_el_9_no_direct_connect (subprocess grep); test_replay_defaults; test_meta_context_sets_caused_by; test_event_id_deterministic: verifies same (event_type, payload_dict, timestamp_ms) → same event_id using canonical_payload = json.dumps(payload, sort_keys=True), full input encoded UTF-8 before SHA-256 — ensures cross-env stability
Depends on:           T-107, T-113

---

T-109: infra/audit.py — log_action, AuditEntry, make_entry_id, atomic_write

Status:               DONE
Spec ref:             Spec_v1 §2 BC-INFRA audit.py
Invariants:           I-PK-5
spec_refs:            [Spec_v1 §2, I-PK-5]
produces_invariants:  [I-PK-5]
requires_invariants:  [I-PK-1]
Inputs:               src/sdd/core/__init__.py, src/sdd/infra/db.py
Outputs:              src/sdd/infra/audit.py
Acceptance:           log_action, AuditEntry, make_entry_id, atomic_write importable; make_entry_id(action, actor, context) returns deterministic SHA-256 hex string; atomic_write(path, content) uses tempfile on same mount + os.replace (no partial writes — I-PK-5); AuditEntry.event_type != any V1_L1_EVENT_TYPES member (not a domain event); mypy strict passes
Depends on:           T-116, T-115

---

T-110: tests/unit/infra/test_audit.py

Status:               DONE
Spec ref:             Spec_v1 §9 row 3
Invariants:           I-PK-5
spec_refs:            [Spec_v1 §9, I-PK-5]
produces_invariants:  [I-PK-5]
requires_invariants:  [I-PK-5]
Inputs:               src/sdd/infra/audit.py, tests/conftest.py
Outputs:              tests/unit/infra/test_audit.py
Acceptance:           pytest tests/unit/infra/test_audit.py passes; test_atomic_write_no_partial (simulate crash between write and replace — partial file never visible); test_log_action_deterministic_id (same inputs → same entry_id)
Depends on:           T-109, T-113

---

T-111: infra/config_loader.py — 3-level YAML override

Status:               DONE
Spec ref:             Spec_v1 §2 BC-INFRA config_loader.py
Invariants:           I-PK-4 (config loader is pure)
spec_refs:            [Spec_v1 §2, I-PK-4]
produces_invariants:  []
requires_invariants:  []
Inputs:               pyproject.toml, src/sdd/__init__.py
Outputs:              src/sdd/infra/config_loader.py
Acceptance:           load_config(project_profile_path, phase_n_path=None) returns merged dict; phase_N.yaml values override project_profile.yaml which overrides base defaults; missing phase_N.yaml falls back to project_profile.yaml without error; function pure (no side effects beyond YAML file reads); mypy strict passes
Depends on:           T-101

---

T-112: tests/unit/infra/test_config_loader.py

Status:               DONE
Spec ref:             Spec_v1 §9 row 4
Invariants:           I-PK-4
spec_refs:            [Spec_v1 §9, I-PK-4]
produces_invariants:  [I-PK-4]
requires_invariants:  []
Inputs:               src/sdd/infra/config_loader.py, tests/conftest.py
Outputs:              tests/unit/infra/test_config_loader.py
Acceptance:           pytest tests/unit/infra/test_config_loader.py passes; test_3level_override (phase overrides project overrides base); test_missing_phase_config_falls_back (no exception when phase_N.yaml absent)
Depends on:           T-111, T-113

---

T-118: infra/metrics.py — record_metric, MetricEvent, atomic batch with TaskCompleted (I-M-1)

Status:               DONE
Spec ref:             Spec_v1 §4.8 record_metric, §5 I-M-1
Invariants:           I-M-1, I-EL-11
spec_refs:            [Spec_v1 §4.8, I-M-1, I-EL-11]
produces_invariants:  [I-M-1]
requires_invariants:  [I-EL-11]
Inputs:               src/sdd/infra/event_log.py, src/sdd/core/__init__.py
Outputs:              src/sdd/infra/metrics.py
Acceptance:           record_metric(metric_id, value, task_id, phase_id, context, db_path) importable; two distinct modes — (a) with task_id: internally builds and writes sdd_append_batch([TaskCompleted, MetricRecorded]) in single transaction (I-M-1); (b) without task_id: writes only MetricRecorded event via sdd_append; MetricRecorded event written with level=L2 in both modes; function signature does NOT expose a "TaskCompleted context" parameter — batching is automatic and internal when task_id is provided; mypy strict passes
Depends on:           T-107

---

T-119: tests/unit/infra/test_metrics.py

Status:               DONE
Spec ref:             Spec_v1 §9 row 5
Invariants:           I-M-1, I-EL-11
spec_refs:            [Spec_v1 §9, I-M-1, I-EL-11]
produces_invariants:  [I-M-1, I-EL-11]
requires_invariants:  [I-M-1, I-EL-11]
Inputs:               src/sdd/infra/metrics.py, src/sdd/infra/event_log.py, tests/conftest.py
Outputs:              tests/unit/infra/test_metrics.py
Acceptance:           pytest tests/unit/infra/test_metrics.py passes; test_record_metric_batch_with_task_completed (both events in DB after call); test_i_m_1_enforced (inject DB failure after TaskCompleted write — MetricRecorded also absent, verifying atomicity)
Depends on:           T-118, T-113

---

T-114: infra/__init__.py — re-exports public BC-INFRA API

Status:               DONE
Spec ref:             Spec_v1 §2 BC-INFRA __init__.py
Invariants:           (public API contract for BC-INFRA)
spec_refs:            [Spec_v1 §2]
produces_invariants:  []
requires_invariants:  []
Inputs:               src/sdd/infra/db.py, src/sdd/infra/event_log.py, src/sdd/infra/audit.py, src/sdd/infra/config_loader.py, src/sdd/infra/metrics.py
Outputs:              src/sdd/infra/__init__.py
Acceptance:           `from sdd.infra import open_sdd_connection, sdd_append, sdd_append_batch, sdd_replay, meta_context, record_metric, log_action, load_config` succeeds; no circular imports; mypy strict passes
Depends on:           T-105, T-107, T-109, T-111, T-118

---

T-120: tests/compatibility/test_v1_schema.py — I-EL-6 partial

Status:               DONE
Spec ref:             Spec_v1 §9 row 6, §8 Integration (v1 compatibility)
Invariants:           I-EL-6 (partial — full coverage in Phase 7)
spec_refs:            [Spec_v1 §9, Spec_v1 §8, I-EL-6]
produces_invariants:  [I-EL-6]
requires_invariants:  [I-PK-2, I-EL-10]
Inputs:               src/sdd/core/events.py, src/sdd/infra/event_log.py, tests/compatibility/fixtures/v1_events.json
Outputs:              tests/compatibility/__init__.py, tests/compatibility/test_v1_schema.py, tests/compatibility/fixtures/v1_events.json
Acceptance:           pytest tests/compatibility/test_v1_schema.py passes; test_v1_l1_events_have_required_fields: each entry in V1_L1_EVENT_TYPES can be instantiated with event_type, event_id, appended_at, level, event_source, caused_by_meta_seq fields; v1_events.json fixture contains ≥1 sample L1 event per required field
Depends on:           T-107, T-115

---

T-121: Run full phase validation — ValidationReport_Phase1.md

Status:               DONE
Spec ref:             Spec_v1 §5 §PHASE-INV, §R.7 Validate protocol
Invariants:           I-PK-1, I-PK-2, I-PK-3, I-PK-4, I-PK-5, I-EL-1, I-EL-2, I-EL-5a, I-EL-5b, I-EL-7, I-EL-8, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12, I-CMD-1a, I-M-1
spec_refs:            [Spec_v1 §5 §PHASE-INV]
produces_invariants:  [I-PK-1, I-PK-2, I-PK-3, I-PK-4, I-PK-5, I-EL-1, I-EL-2, I-EL-5a, I-EL-5b, I-EL-7, I-EL-8, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12, I-CMD-1a, I-M-1]
requires_invariants:  [I-PK-1, I-PK-2, I-PK-3, I-PK-4, I-PK-5, I-EL-1, I-EL-2, I-EL-5a, I-EL-5b, I-EL-7, I-EL-8, I-EL-8a, I-EL-9, I-EL-10, I-EL-11, I-EL-12, I-CMD-1a, I-M-1]
Inputs:               .sdd/tools/validate_invariants.py, .sdd/config/project_profile.yaml, .sdd/tasks/TaskSet_v1.md
Outputs:              .sdd/reports/ValidationReport_Phase1.md
Acceptance:           validate_invariants.py --phase 1 exits 0; all §PHASE-INV invariants PASS; pytest tests/ coverage ≥ 80% for src/sdd/infra/ modules; ruff check src/ = 0 violations; mypy src/sdd/ = 0 errors; ValidationReport_Phase1.md written with per-invariant status
Depends on:           T-106, T-108, T-110, T-112, T-117, T-119, T-120, T-114

---

T-122: Phase 1 Summary + Metrics report

Status:               DONE
Spec ref:             CLAUDE.md §K.1 Summarize Phase N, §K.1 Metrics Report
Invariants:           (phase close-out — no new invariants)
spec_refs:            [CLAUDE.md §K.1]
produces_invariants:  []
requires_invariants:  []
Inputs:               .sdd/reports/ValidationReport_Phase1.md, .sdd/tools/metrics_report.py, .sdd/runtime/State_index.yaml
Outputs:              .sdd/reports/Phase1_Summary.md, .sdd/reports/Metrics_Phase1.md
Acceptance:           metrics_report.py --phase 1 --trend --anomalies exits 0 and writes Metrics_Phase1.md; Phase1_Summary.md written per PhaseSummary_template.md; Phase1_Summary.md references Metrics_Phase1.md and includes improvement hypotheses
Depends on:           T-121

---

<!-- Granularity: 21 tasks (TG-2 ✓). All tasks independently implementable and testable (TG-1 ✓). -->
<!-- Milestone mapping: M1→T-101..T-117, M2→T-105,T-116,T-106, M3→T-107,T-108, M4→T-109,T-110,T-111,T-112,T-113, M5→T-118,T-119, M6→T-114,T-115,T-120, M7→T-121,T-122 -->
