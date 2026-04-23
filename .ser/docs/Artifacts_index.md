# Artifacts Index

Registry of all SDD artifacts in the SER project.
Source of truth for artifact status — update when artifacts are created, promoted, or completed.

---

## Runtime State

| Path | Purpose | Managed by | Status |
|------|---------|------------|--------|
| `runtime/State_index.yaml` | SSOT operational state (projection of TaskSet + validation) | LLM (Sync State / Validate / Check DoD) | Active |

---

## Specs

| Path | Phase | Status |
|------|-------|--------|
| `specs/SDD_Spec_v1.md` | BC-9 | Approved |
| `specs/Spec_v2_Phase2.md` | 2 | Approved (retroactive — Phase 2 COMPLETE per Phases_index.md; formal update pending human review) |
| ~~`specs/Spec_v1_Phase1.md`~~ | 1 | _missing — Phase 1 completed without formal spec_ |
| `specs/Spec_v3_Phase3.md` | 3 | TODO |
| `specs/Spec_v4_Phase4.md` | 4 | TODO |

---

## Plans

| Path | Phase | Status |
|------|-------|--------|
| `plans/Plan_v1.md` | 1 | _missing — Phase 1 completed without plan_ |
| `plans/Plan_v2.md` | 2 | TODO |
| `plans/Plan_v3.md` | 3 | TODO |
| `plans/Plan_v4.md` | 4 | TODO |

---

## Task Sets

| Path | Phase | Status |
|------|-------|--------|
| `tasks/TaskSet_v1.md` | 1 | _missing — Phase 1 completed without task set_ |
| `tasks/TaskSet_v2.md` | 2 | TODO |
| `tasks/TaskSet_v3.md` | 3 | TODO |
| `tasks/TaskSet_v4.md` | 4 | TODO |

---

## Validation Reports

| Path | Task | Status |
|------|------|--------|
| _(none yet)_ | — | — |

---

## Phase Summaries

| Path | Phase | Status |
|------|-------|--------|
| `reports/Phase1_Summary.md` | 1 | _missing — Phase 1 completed without summary_ |
| `reports/Phase2_Summary.md` | 2 | TODO |

---

## SENAR Control Plane (.sdd/)

| Path | Purpose | Status |
|------|---------|--------|
| `CLAUDE.md` | Master unified SDD protocol (§0/§R/§K split-load) | Active — supersedes CLAUDE_v2/v3/v3-PLAN |
| `.sdd/system_prompt.md` | Agent session loading instructions | Active |
| `.sdd/norms/norm_catalog.yaml` | SENAR norm catalog (14 norms) | Active |
| `.sdd/norms/senar_config.yaml` | SENAR actor/audit/gate config | Active |
| `.sdd/state/EventLog.jsonl` | SDD process event log (append-only) | Active |
| `.sdd/tools/norm_catalog.py` | Norm loader (no deps) | Active |
| `.sdd/tools/check_scope.py` | Read/write scope guard | Active |
| `.sdd/tools/senar_audit.py` | SENAR audit trail logger | Active |
| `.sdd/tools/phase_guard.py` | PhaseGuard + SDDEventRejected emitter | Active |
| `.sdd/tools/sync_state.py` | State derivation from TaskSet (atomic) | Active |
| `.sdd/tools/update_state.py` | Sole mutation path: TaskSet + State | Active |
| `.sdd/tools/validate_invariants.py` | I-SDD invariant compliance checker | Active |
| `.sdd/tools/report_error.py` | Structured SENAR incident reporter | Active |
| `runtime/audit_log.jsonl` | SENAR audit trail (append-only) | Active |

---

## Templates

| Path | Purpose |
|------|---------|
| `templates/Spec_template.md` | Scaffold for new Spec_vN |
| `templates/Plan_template.md` | Scaffold for Plan_vN |
| `templates/TaskSet_template.md` | Scaffold for TaskSet_vN |
| `templates/ValidationReport_template.md` | Scaffold for ValidationReport_T-NNN |
| `templates/PhaseSummary_template.md` | Scaffold for PhaseN_Summary |

---

## Reference Docs

| Path | Purpose |
|------|---------|
| `docs/SDD_Quick_Reference.md` | Полный цикл SDD + SSOT: шаги, файлы, роли (quick-reference) |
| `docs/ARCHITECTURE.md` | Master architecture: 52 invariants, 8 BCs |
| `docs/bounded_contexts.md` | BC-1..BC-8 descriptions |
| `docs/glossary.md` | 50+ term definitions |
| `docs/use_cases.md` | UC-1..UC-9 workflows |
| `docs/index.md` | Cross-reference index by concept, invariant, event |
| `docs/PLAN.md` | Phase 1–4 implementation plan (Russian) |

---

## Versioning Rules

```text
VR-1  Spec_vN ↔ Phase N
VR-2  Plan_vN MUST use Spec_vN
VR-3  TaskSet_vN MUST use Plan_vN
VR-4  Mixing versions → ERROR (e.g. Plan_v3 with Spec_v2 is forbidden)
```
