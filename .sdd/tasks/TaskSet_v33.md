# TaskSet_v33 — Phase 33: CommandSpec Guard Factory

Spec: specs/Spec_v33_CommandSpecGuardFactory.md
Plan: plans/Plan_v33.md

---

T-3301: Add `_default_build_guards()`, `guard_factory` field and `build_guards()` to CommandSpec

Status:               DONE
Spec ref:             Spec_v33 §2 BC-33, §4 Types & Interfaces — CommandSpec structure
Invariants:           I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3
spec_refs:            [Spec_v33 §2 BC-33, Spec_v33 §4, I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3]
produces_invariants:  [I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3]
requires_invariants:  [I-SPEC-EXEC-1, I-HANDLER-PURE-1]
Inputs:               src/sdd/commands/registry.py
Outputs:              src/sdd/commands/registry.py
Acceptance:           `CommandSpec(name="x", ...).build_guards(cmd)` calls `_default_build_guards` when `guard_factory=None`; calls custom factory when `guard_factory` is set; `@dataclass(frozen=True)` still applies (field uses `hash=False, compare=False`)
Depends on:           —

---

T-3302: Replace `_build_spec_guards` call in `execute_command` with `spec.build_guards(cmd)`; delete `_build_spec_guards`

Status:               DONE
Spec ref:             Spec_v33 §2 BC-33-REGISTRY, §8 Integration — "Изменения в execute_command"
Invariants:           I-CMD-GUARD-FACTORY-1
spec_refs:            [Spec_v33 §2 BC-33-REGISTRY, Spec_v33 §8, I-CMD-GUARD-FACTORY-1]
produces_invariants:  [I-CMD-GUARD-FACTORY-1]
requires_invariants:  [I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3]
Inputs:               src/sdd/commands/registry.py
Outputs:              src/sdd/commands/registry.py
Acceptance:           `execute_command` body contains `spec.build_guards(cmd)` and does NOT contain `_build_spec_guards`; no conditional on `spec.requires_active_phase`, `spec.apply_task_guard`, or `spec.name` in `execute_command` body (the conditional logic lives in `_default_build_guards`)
Depends on:           T-3301

---

T-3303: Add `_switch_phase_guards` factory to `switch_phase.py`; set `guard_factory` in REGISTRY["switch-phase"]

Status:               DONE
Spec ref:             Spec_v33 §2 BC-33-SWITCH, §4 switch_phase.py guard factory, §8 Nota Bene
Invariants:           I-CMD-GUARD-FACTORY-4, I-CMD-GUARD-FACTORY-1
spec_refs:            [Spec_v33 §2 BC-33-SWITCH, Spec_v33 §4, I-CMD-GUARD-FACTORY-4, I-CMD-GUARD-FACTORY-1]
produces_invariants:  [I-CMD-GUARD-FACTORY-4]
requires_invariants:  [I-CMD-GUARD-FACTORY-1, I-CMD-GUARD-FACTORY-2]
Inputs:               src/sdd/commands/switch_phase.py, src/sdd/commands/registry.py
Outputs:              src/sdd/commands/switch_phase.py, src/sdd/commands/registry.py
Acceptance:           `REGISTRY["switch-phase"].guard_factory` is `_switch_phase_guards`; factory returns list of exactly 3 guards [phase_guard, switch_phase_guard, norm_guard]; no `if spec.name == "switch-phase"` branch in `_default_build_guards`
Depends on:           T-3301, T-3302

---

T-3304: Unit tests — `build_guards()` delegation and `_default_build_guards` spec-flag behavior

Status:               DONE
Spec ref:             Spec_v33 §9 Verification — tests #2, #3, #5
Invariants:           I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3
spec_refs:            [Spec_v33 §9, I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3]
produces_invariants:  [I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3]
requires_invariants:  [I-CMD-GUARD-FACTORY-2, I-CMD-GUARD-FACTORY-3]
Inputs:               src/sdd/commands/registry.py
Outputs:              tests/unit/commands/test_guard_factory.py
Acceptance:           `test_build_guards_default_delegates_to_default_factory` PASS; `test_build_guards_custom_delegates_to_guard_factory` PASS; `test_default_factory_reads_spec_flags` PASS (requires_active_phase=False → no phase guard; apply_task_guard=False → no task guard)
Depends on:           T-3301

---

T-3305: Unit tests — `execute_command` calls `spec.build_guards(cmd)` exactly once; AST check: no `spec.name` branch

Status:               DONE
Spec ref:             Spec_v33 §9 Verification — tests #1, #6
Invariants:           I-CMD-GUARD-FACTORY-1
spec_refs:            [Spec_v33 §9, I-CMD-GUARD-FACTORY-1]
produces_invariants:  [I-CMD-GUARD-FACTORY-1]
requires_invariants:  [I-CMD-GUARD-FACTORY-1]
Inputs:               src/sdd/commands/registry.py
Outputs:              tests/unit/commands/test_guard_factory.py
Acceptance:           `test_execute_command_calls_build_guards` PASS (mock spec.build_guards; assert called_once_with(cmd)); `test_registry_no_conditional_on_spec_name` PASS (AST parse of registry.py; assert no `Compare` node with `spec.name` inside `execute_command` body)
Depends on:           T-3302, T-3304

---

T-3306: Unit tests — switch-phase guard factory returns full guard list and extracts phase_id

Status:               DONE
Spec ref:             Spec_v33 §9 Verification — tests #4, #7
Invariants:           I-CMD-GUARD-FACTORY-4
spec_refs:            [Spec_v33 §9, I-CMD-GUARD-FACTORY-4]
produces_invariants:  [I-CMD-GUARD-FACTORY-4]
requires_invariants:  [I-CMD-GUARD-FACTORY-4]
Inputs:               src/sdd/commands/switch_phase.py, src/sdd/commands/registry.py
Outputs:              tests/unit/commands/test_guard_factory.py
Acceptance:           `test_custom_guard_factory_receives_full_guard_list` PASS (factory returns 3-element list: phase_guard, switch_guard, norm_guard); `test_switch_phase_guard_factory_extracts_phase_id` PASS (cmd.phase_id=5 → switch_guard parametrised with 5)
Depends on:           T-3303, T-3305

<!-- Granularity: 10–30 tasks per phase (TG-2). Regroup if exceeded (TG-3). -->
<!-- Every task must be independently implementable and independently testable (TG-1). -->
