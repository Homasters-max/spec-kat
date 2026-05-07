# Plan_v61 — Phase 61: Graph-Guided Implement Enforcement + Evaluation

Status: DRAFT
Spec: specs/Spec_v61_GraphEnforcement.md

---

## Logical Context

```
type: backfill
anchor_phase: 55
rationale: "Phase 55 ввела Graph-Guided Implement как наблюдаемый протокол (STEP 4.5), но без enforcement infrastructure. Phase 61 закрывает enforcement gap, пропущенный в Phase 55, и верифицирует корректность через 8 управляемых eval-сценариев."
```

---

## Milestones

### M1: Patches & Environment

```text
Spec:       §1 Scope (BC-61-P1..P4), §2 Architecture BCs
BCs:        BC-61-P1, BC-61-P2, BC-61-P3, BC-61-P4
Invariants: I-ENGINE-EDGE-FILTER-1 (P1), I-RRL-1 (P2)
Depends:    — (независимые исправления)
Risks:      P1-edge-types — backward compat критична (без флага поведение должно совпадать);
            P2-sync-state — actor="any" vs "llm" может затронуть CommandSpec validation;
            P3-gate — изменения в session docs не верифицируются тестами автоматически;
            P4-pytest-cov — установка пакета меняет coverage behavior (новые failures возможны)
```

**Задачи M1:**
- BC-61-P1: добавить `--edge-types` в `trace_cmd` (cli.py) и `run()` (trace.py)
- BC-61-P2: исправить `actor="any"` → `actor="llm"` в CommandSpec["sync-state"]
- BC-61-P3: расширить preconditions в `check-dod.md` и `summarize-phase.md` (Step 0 pre-check)
- BC-61-P4: добавить `pytest-cov` в `pyproject.toml` dependencies

---

### M2: GraphSessionState + Deterministic Anchor

```text
Spec:       §2 BC-61-E1, §2 BC-61-E5, §5 Types & Interfaces
BCs:        BC-61-E1, BC-61-E5
Invariants: I-SEARCH-DIRECT-1
Depends:    M1 (P4 — pytest-cov для тестов)
Risks:      E1 — runtime sessions dir должен создаваться атомарно (atomic_write из Phase 55 M6);
            E5 — bypass BM25 меняет семантику resolve; нужна аккуратная интеграция в GraphEngine
```

**Задачи M2:**
- BC-61-E1: создать `src/sdd/graph_navigation/session_state.py` (GraphSessionState dataclass, load/save через atomic_write)
- BC-61-E1: создать `src/sdd/graph_navigation/sessions/` runtime directory support
- BC-61-E5: добавить `--node-id` в `sdd resolve` (cli.py + resolve.py) с bypass BM25 → direct node lookup

---

### M3: Enforcement Gates

```text
Spec:       §2 BC-61-E2, §2 BC-61-E3, §2 BC-61-E4, §6 CLI Interface
BCs:        BC-61-E2, BC-61-E3, BC-61-E4
Invariants: I-GRAPH-PROTOCOL-1, I-GRAPH-GUARD-1, I-TRACE-BEFORE-WRITE, I-SCOPE-STRICT-1, I-GRAPH-ANCHOR-CHAIN
Depends:    M2 (E1 — GraphSessionState required by all gates)
Risks:      E2-graph-guard — CLI exit code contract строгий; нарушения должны быть человекочитаемы в JSON stderr;
            E3-write-gate — "sdd write" конфликтует с shell builtins на некоторых платформах (проверить);
            E4-strict-scope — изменение scope_policy.py может затронуть существующие check-scope тесты
```

**Задачи M3:**
- BC-61-E2: создать `src/sdd/graph_navigation/cli/graph_guard.py` + зарегистрировать `sdd graph-guard check`
- BC-61-E3: создать `src/sdd/graph_navigation/cli/write_gate.py` + зарегистрировать `sdd write`
- BC-61-E4: обновить `scope_policy.py` → `resolve_scope()` принимает `session_id`, использует `state.allowed_files`
- M3: добавить новые commands в `cli.py` и `pyproject.toml` console_scripts

---

### M4: Eval Infrastructure

```text
Spec:       §2 BC-61-T1, §2 BC-61-T2, §2 BC-61-T3
BCs:        BC-61-T1, BC-61-T2, BC-61-T3
Invariants: — (инфраструктурные артефакты, не domain invariants)
Depends:    M2 (E5 — deterministic anchor нужен для стабильных тестов),
            M3 (enforcement gates нужны как объект тестирования)
Risks:      T1-fixtures — eval/ файлы влияют на production graph (маркировать # EVAL ONLY);
            T3-report — scaffold должен быть создан до запуска сценариев, иначе T4 не имеет куда писать
```

**Задачи M4:**
- BC-61-T1: создать `src/sdd/eval/__init__.py`, `eval_fixtures.py`, `eval_deep.py` с BM25-ключевыми словами в docstrings
- BC-61-T2: создать `src/sdd/eval/eval_harness.py` (ScenarioResult dataclass, run_graph_cmd util)
- BC-61-T3: создать `.sdd/reports/EvalReport_v61_GraphGuidedTest.md` (scaffold с S1-S8 в PENDING)

---

### M5: Evaluation Scenarios + DoD Closure

```text
Spec:       §2 BC-61-T4, §2 BC-61-T5, §7 Evaluation Methodology, §9 Acceptance Criteria
BCs:        BC-61-T4, BC-61-T5
Invariants: I-GRAPH-PROTOCOL-1, I-SCOPE-STRICT-1, I-TRACE-BEFORE-WRITE, I-GRAPH-GUARD-1
Depends:    M1, M2, M3, M4 (все предыдущие milestones)
Risks:      T4-S1-S8 — 4 negative сценария проверяют enforcement; если E2/E3 реализованы не точно → ложные провалы;
            T5-DoD-closure — Phase 55 invariants.status=UNKNOWN → нужен sdd validate для закрытия
```

**Задачи M5:**
- BC-61-T4: реализовать и запустить сценарии S1–S8 (тесты в `tests/integration/test_eval_s*.py`)
- BC-61-T4: заполнить EvalReport_v61_GraphGuidedTest.md результатами (no PENDING lines)
- BC-61-T5: выполнить DoD closure для Phase 55 — `sdd validate T-<last_55> --result PASS` если `invariants.status=UNKNOWN`
- M5: финальный прогон `pytest tests/unit/ -q` (Phase 55 regression check)

---

## Risk Notes

- R-1: `sdd trace --edge-types` (P1) — backward compat: без флага поведение MUST совпадать; использовать `edge_types=None` как sentinel
- R-2: `actor="any"` в CommandSpec (P2) — аудит всех CommandSpec с actor="any"; нет других таких случаев?
- R-3: eval/ файлы в production graph (T1) — добавить маркер `# EVAL ONLY`; рассмотреть exclusion из release index через `.sdd/config/`
- R-4: BM25 нестабильность (E5) — `--node-id` обязателен для всех eval тестов; BM25 только для human-facing поиска
- R-5: GraphSessionState конкурентная запись (E1) — использовать `atomic_write` из Phase 55 M6; проверить что `fsync` вызывается
- R-6: Phase 61 активация гейтируется Phase 60 (I-PHASE-SEQ-1) — план создаётся сейчас, активация после Phase 60 COMPLETE
