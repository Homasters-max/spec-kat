---
source: CLAUDE.md §0.15 + §0.16a + §0.16b
last_synced: 2026-04-24
update_trigger: when frozen interfaces change or new invariants added to §0.15/§0.16
---

# Ref: Kernel Contracts
<!-- Loaded by §HARD-LOAD Rule 1 before any write command -->

## Frozen Public Interfaces (I-KERNEL-EXT-1)

Extension rule: MAY add optional parameters with defaults or new backward-compatible return fields only.
Removing/renaming positional args or required params = breaking → requires new spec + human approval.

| Module | Frozen surface |
|--------|----------------|
| `core/types.py` | `Command` dataclass fields; `CommandHandler` Protocol |
| `core/events.py` | `DomainEvent` base fields; `EventLevel`; `classify_event_level()` |
| `core/errors.py` | `SDDError` subclass hierarchy: `Inconsistency`, `MissingState`, `InvalidState`, `MissingContext`, `ScopeViolation`, `NormViolation`, `StaleStateError`, `KernelInvariantError`, `ProjectionError` |
| `infra/event_log.py` | `sdd_append()`, `sdd_append_batch()`, `sdd_replay()` signatures |
| `infra/event_store.py` | `EventStore.append()` interface |
| `domain/state/reducer.py` | `reduce()` signature; I-REDUCER-1 filter contract |
| `domain/guards/context.py` | `GuardContext`, `GuardResult`, `GuardOutcome` |
| `domain/guards/pipeline.py` | `run_guard_pipeline(ctx, guards, stop_on_deny)` |
| `commands/registry.py` | `CommandSpec`, `REGISTRY`, `execute_command()`, `project_all()`, `execute_and_project()` |
| `infra/paths.py` | All path functions; stdlib-only imports (I-PATH-2) |

## CLI Contract (CLI-1..3)

- CLI-1: sub-command names, required flags, positional args are frozen once shipped
- CLI-2: optional flags MAY be added with defaults (non-breaking)
- CLI-3: exit codes and JSON stderr schema are frozen (`error_type`, `message`, `exit_code`)

## Write Kernel Invariants (Phase 15)

**execute_command pipeline stages:**

| Stage | Operation |
|-------|-----------|
| `BUILD_CONTEXT` | `head_seq = EventStore.max_seq()` + `get_current_state()` → SDDState + GuardContext |
| `GUARD` | `run_guard_pipeline()` → GuardResult |
| `EXECUTE` | `handler.handle()` → events (pure, zero I/O) |
| `COMMIT` | `EventStore.append(expected_head=head_seq)` |
| `PROJECT` | `project_all()` → YAML/TaskSet rebuilt (STRICT mode) |

**Key invariants:**

| Invariant | Statement |
|-----------|-----------|
| I-2 | All write commands via REGISTRY[name] → execute_and_project |
| I-3 | All side-effects in Write Kernel only |
| I-HANDLER-PURE-1 | `handle()` returns events only — no EventStore, no rebuild_state |
| I-KERNEL-WRITE-1 | `EventStore.append` exclusively inside `execute_command` in `registry.py` |
| I-KERNEL-PROJECT-1 | `rebuild_state` exclusively inside `project_all` in `registry.py` |
| I-GUARD-STATELESS-1 | Guard callables are pure functions — zero I/O, zero state writes |
| I-OPTLOCK-1 | `execute_command` verifies `EventStore.max_seq() == head_seq` before append |
| I-IDEM-1 | Idempotent via `command_id = sha256(asdict(payload))[:32]` |
| I-ERROR-1 | Write Kernel MUST emit ErrorEvent before raising at every failure stage |
| I-REBUILD-STRICT-1 | Default `RebuildMode = STRICT`; YAML not read during normal rebuild |
| I-REBUILD-EMERGENCY-2 | `rebuild_state(EMERGENCY)` requires `SDD_EMERGENCY=1` env var |
| I-READ-ONLY-EXCEPTION-1 | Read-only commands MAY bypass REGISTRY but MUST NOT call EventStore.append, rebuild_state, handler.handle(), or mutate State_index.yaml |
| I-REGISTRY-COMPLETE-1 | Every write command has REGISTRY entry: complete, validate, check-dod, activate-phase, sync-state, record-decision |
| I-SDDRUN-DEAD-1 | `CommandRunner` MUST NOT exist in `src/sdd/` |
| I-PIPELINE-HOME-1 | `run_guard_pipeline` in `guards/pipeline.py` only |

## Phase 10 — Kernel Hardening Invariants

| Invariant | Verification |
|-----------|-------------|
| I-FAIL-1: SDDError → exit 1 + JSON stderr; Exception → exit 2 + JSON stderr | `pytest tests/unit/test_cli_exec_contract.py` |
| I-CLI-API-1: JSON error fields `error_type`, `message`, `exit_code` frozen | `pytest tests/unit/test_cli_exec_contract.py` |
| I-ENV-1: `sdd --help` with minimal env (no PYTHONPATH) | `pytest tests/integration/test_env_independence.py` |
| I-EXEC-ISOL-1: tests use `tmp_path`-isolated DuckDB; project DB never touched | `pytest tests/integration/test_pipeline_deterministic.py` |
| I-PURE-1: `compute_trend()` and `detect_anomalies()` make zero I/O | `pytest tests/unit/infra/test_metrics_purity.py` |
| I-LEGACY-0a: no `sys.path` mutation toward `.sdd/` in `src/sdd/**/*.py` | `sdd validate-invariants --check I-LEGACY-0a` |
| I-LEGACY-0b: no `subprocess` calls to `.sdd/tools/` in `src/sdd/**/*.py` | `sdd validate-invariants --check I-LEGACY-0b` |
| I-ENTRY-1: no `__main__` blocks except `cli.py` and `hooks/*.py` | `sdd validate-invariants --check I-ENTRY-1` |

## Responsibility Matrix

| Command | Actor | Notes |
|---------|-------|-------|
| `activate-phase N` | **human** | Emits PhaseStarted + TaskSetDefined |
| `complete T-NNN` | llm | Emits TaskImplemented |
| `validate T-NNN` | llm | Emits TaskValidated |
| `check-dod` | llm | Emits PhaseCompleted on success |
| `sync-state` | llm | Triggers project_all; no domain events |
| `record-decision` | llm | Emits DecisionRecordedEvent (audit only) |
| `validate-config` | llm | Read-only; no REGISTRY entry |
| `show-*`, `query-*` | llm | Read-only; no REGISTRY entry |

## Documentation Drift Protection (I-DOC-1)

| Invariant | Statement |
|-----------|-----------|
| I-DOC-1 | `cli.schema.yaml` is the SINGLE SOURCE OF TRUTH for CLI contracts. `tool-reference.md` MUST be updated to match `cli.schema.yaml` after any change to required flags, optional flags, or failure modes. Verified manually during code review of `src/sdd/commands/*.py` changes. |

## Event Schema Rules (EV-1..4)

- EV-1: DuckDB schema migrations additive-only (`ADD COLUMN IF NOT EXISTS`)
- EV-2: Event payload fields additive-only; removing/renaming V1_L1_EVENT_TYPES fields = breaking
- EV-3: `schema_version` is always 1; upcast mechanism requires new spec
- EV-4: Reducer MUST replay all historical events without error (production guarantee)

**Full Phase 15 test suite:**
```bash
make check-handler-purity
pytest tests/unit/test_handler_purity.py tests/unit/test_registry_contract.py \
       tests/unit/commands/test_registry.py tests/unit/infra/test_projections.py \
       tests/unit/guards/test_pipeline.py tests/integration/test_full_chain.py -v
```
