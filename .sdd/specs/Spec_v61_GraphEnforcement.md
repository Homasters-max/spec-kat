# Spec_v61 — Phase 61: Graph-Guided Implement Enforcement + Evaluation

Status: Draft
Baseline: Spec_v55_GraphGuidedImplement.md

---

## 0. Goal

Phase 55 ввела Graph-Guided Implement как *наблюдаемый* протокол (STEP 4.5). Критическая дыра: протокол не принудительный — агент может игнорировать граф и система не обнаруживает нарушение. Phase 61 закрывает эту дыру через enforcement infrastructure (`GraphSessionState`, `sdd graph-guard`, `sdd write`) и верифицирует корректность через 8 управляемых сценариев (S1–S8 позитивные/негативные). Вердикт: Phase 55 OK → Phase 56+ архитектурные фазы; PHASE55.1_NEEDED → стабилизация.

---

## 1. Scope

### In-Scope

- BC-61-P1: Patch — `sdd trace --edge-types` (T-5503 scope gap: `trace.py` не получил `--edge-types`, только `explain.py`)
- BC-61-P2: Patch — `sdd sync-state` GuardViolationError (`actor="any"` → norm DENY; fix: `actor="llm"` в CommandSpec + norm entry)
- BC-61-P3: Gate — обязательный VALIDATE-шаг перед CHECK_DOD (invariants.status UNKNOWN → DoD fail; fix: guard в check-dod preconditions + автоматический напоминатель в SUMMARIZE)
- BC-61-P4: Env — `pytest-cov` в зависимостях (coverage threshold не верифицировался из-за отсутствия пакета)
- BC-61-E1: `GraphSessionState` — in-memory + persistent session tracker
- BC-61-E2: `sdd graph-guard check` — hard enforcement gate (I-GRAPH-GUARD-1)
- BC-61-E3: `sdd write <file>` — enforced write gate (I-TRACE-BEFORE-WRITE, I-GRAPH-PROTOCOL-1)
- BC-61-E4: Strict Scope Linking — `allowed_files = union(graph_outputs, task_inputs)`
- BC-61-E5: Deterministic anchor — `sdd resolve --node-id <id>` (bypass BM25)
- BC-61-T1: Eval fixtures (`src/sdd/eval/`) — synthetic graph test data
- BC-61-T2: Eval harness (`ScenarioResult`) — scenario runner
- BC-61-T3: Evaluation Report (`EvalReport_v61_GraphGuidedTest.md`)
- BC-61-T4: 8 evaluation scenarios (S1–S8): 4 positive, 4 negative
- BC-61-T5: Phase 55 DoD closure (invariants.status UNKNOWN → PASS/FAIL)

### Out of Scope

- Phase 57 scope (Graph-First + Architecture Context)
- RAG enforcement (deferred to Phase 58+)
- Automated regression hooks for graph-guard (deferred)

---

## 2. Architecture / BCs

### BC-61-P1: Patch — `sdd trace --edge-types`

**Проблема:** T-5503 (Phase 55) декларировал добавление `--edge-types` в обе команды — `explain.py` и `trace.py`. Фактически флаг был добавлен только в `explain.py` (и зарегистрирован в `cli.py`). `trace.py` и `trace_cmd` в `cli.py` не получили изменений. Документация (T-5521, tool-reference.md) задокументировала флаг согласно спеку, но реализация неполная.

**Fix:**

```
src/sdd/cli.py                          — добавить --edge-types в trace_cmd
src/sdd/graph_navigation/cli/trace.py  — добавить edge_types param в run(), thread to engine.query()
tests/unit/context_kernel/test_engine.py  — уже покрывает _expand_trace(allowed_kinds)
```

**Изменения:**

```python
# cli.py — trace_cmd
@click.option("--edge-types", "edge_types_raw", default=None,
              help="Comma-separated edge kinds to filter reverse BFS (e.g. imports)")
def trace_cmd(node_id, rebuild, debug, fmt, edge_types_raw):
    edge_types: frozenset[str] | None = None
    if edge_types_raw is not None:
        edge_types = frozenset(p.strip() for p in edge_types_raw.split(",") if p.strip())
    sys.exit(run(node_id, rebuild=rebuild, fmt=fmt, debug=debug, edge_types=edge_types))

# trace.py — run()
def run(node_id, *, rebuild=False, fmt="text", debug=False,
        project_root=".", edge_types: frozenset[str] | None = None) -> int:
    ...
    response = engine.query(graph, policy, doc_provider, node_id,
                            intent=intent, edge_types=edge_types)
```

**Backward compat:** без `--edge-types` → `edge_types=None` → поведение идентично текущему.

**Инварианты:** I-ENGINE-EDGE-FILTER-1 (уже верифицирован T-5504 для _expand_trace).

**Acceptance:** `sdd trace FILE:src/sdd/tasks/navigation.py --edge-types imports` → только `imports` in-edges; `--edge-types ""` → non-zero exit.

---

### BC-61-P2: Patch — `sdd sync-state` GuardViolationError

**Проблема:** `CommandSpec["sync-state"].actor = "any"`. `NormCatalog.is_allowed("any", "sync_state")` ищет записи с `entry.actor == "any"` — таких нет. При `strict=True` (default) → DENY → `GuardViolationError`. Фактически sync-state недоступен через CLI.

**Корень:** `NormCatalog.is_allowed(actor, action)` не обрабатывает `actor="any"` как wildcard. `CommandSpec.actor="any"` означает "любой может вызвать", но каталог интерпретирует это буквально.

**Fix — два изменения:**

```
src/sdd/commands/registry.py        — CommandSpec["sync-state"]: actor="any" → actor="llm"
.sdd/norms/norm_catalog.yaml        — убедиться что sync_state есть в NORM-ACTOR-004
                                      (уже есть — только починить actor в CommandSpec достаточно)
```

**Альтернатива (если "any" семантика нужна):** добавить в `NormCatalog.is_allowed()` обработку `actor="any"` как always-match:
```python
if actor == "any":
    return True  # CommandSpec явно объявил: любой актор допустим
```

**Рекомендуемый fix:** `actor="llm"` в CommandSpec — семантически корректно (sync-state вызывается только LLM в recovery).

**Инварианты:** I-RRL-1 (rule resolution deterministic).

**Acceptance:** `sdd sync-state --phase N` → exit 0 без GuardViolationError.

---

### BC-61-P3: Gate — обязательный VALIDATE перед CHECK_DOD

**Проблема:** `CheckDoDHandler` проверяет `state.invariants_status == "PASS"` и `state.tests_status == "PASS"`. Если в фазе не было ни одного `sdd validate T-NNN --result PASS`, оба поля остаются `UNKNOWN` → DoD падает. Нет ничего в протоколе, что предотвращает закрытие фазы без VALIDATE-сессии.

**Корень:** SUMMARIZE → CHECK_DOD не требует подтверждения что validate был запущен. Пользователь может сказать "закрой фазу" сразу после последнего IMPLEMENT, и система не предупреждает.

**Fix — два уровня:**

**Уровень 1 — check-dod.md (документация):**
```markdown
## Preconditions
...
- `invariants.status = PASS`  ← добавить: проверить через `sdd show-state` ПЕРЕД запуском
  Если UNKNOWN → обязателен `sdd validate T-<last> --result PASS` или VALIDATE-сессия
```

**Уровень 2 — SUMMARIZE session (автоматический guard):**
В `sessions/summarize-phase.md` добавить Step 0:
```bash
# Step 0: pre-check state (обнаружить UNKNOWN до EventLog snapshot)
sdd show-state | grep -E "invariants|tests"
# Если UNKNOWN → STOP, предупредить: "invariants.status=UNKNOWN. Запустите VALIDATE или sdd validate T-NNN --result PASS"
```

**Уровень 3 — hard guard в CheckDoDHandler (код):** уже существует как `DoDNotMet` — достаточно, ошибка информативная. Дополнительно: emit `ErrorEvent` с `human_reason` указывающим конкретный fix (`sdd validate T-NNN --result PASS`).

**Изменяемые файлы:**
```
.sdd/docs/sessions/check-dod.md     — расширить preconditions
.sdd/docs/sessions/summarize-phase.md — добавить Step 0 pre-check
src/sdd/commands/update_state.py    — CheckDoDHandler: расширить DoDNotMet message
```

**Acceptance:** Фаза без VALIDATE → `sdd validate --check-dod` → exit 1 с сообщением `"invariants.status=UNKNOWN: run 'sdd validate T-NNN --result PASS' first"`.

---

### BC-61-P4: Env — `pytest-cov` в зависимостях проекта

**Проблема:** `project_profile.yaml` определяет `test` и `test_full` с флагами `--cov=src/sdd --cov-report=term-missing --cov-fail-under=80`. `pytest-cov` не входит в зависимости, не установлен в окружении → coverage threshold (80%) не верифицируется при `sdd validate-invariants` и CHECK_DOD.

**Корень:** `pyproject.toml` не содержит `pytest-cov` в `[project.optional-dependencies]` или `[tool.pytest]` dependencies.

**Fix:**

```
pyproject.toml    — добавить pytest-cov в dev/test dependencies:
                    [project.optional-dependencies]
                    test = [..., "pytest-cov>=4.0"]
                    ИЛИ в [dependency-groups] если используется PEP 735
```

**Дополнительно:** проверить что `pip install -e ".[test]"` достаточно для полного окружения разработки.

**Acceptance:** `pytest tests/unit/ --cov=src/sdd --cov-fail-under=80` → exit 0 (не `unrecognized arguments`).

---

### BC-61-E1: GraphSessionState

```
src/sdd/graph_navigation/
  session_state.py    # GraphSessionState dataclass + load/save
  sessions/           # .sdd/runtime/sessions/<session_id>.json (runtime dir)
```

`GraphSessionState` хранит per-session: `resolved`, `explained`, `traced`, `graph_outputs`, `task_inputs`, `anchor_nodes`.

Инварианты:
- `protocol_satisfied = resolved AND bool(explained) AND bool(traced)`
- `allowed_files = frozenset(graph_outputs) | task_inputs`
- `is_anchor_chain_call(node) = node in anchor_nodes OR node in graph_outputs`

Персистирование: `.sdd/runtime/sessions/<session_id>.json` через `atomic_write` (из Phase 55 M6).

### BC-61-E2: graph-guard CLI

```
src/sdd/graph_navigation/cli/
  graph_guard.py      # sdd graph-guard check --session <id>
```

Exit 0 → I-GRAPH-PROTOCOL-1 satisfied.
Exit 1 → JSON stderr `{"error": "GRAPH_PROTOCOL_VIOLATION", "violations": [...]}`.

### BC-61-E3: write gate CLI

```
src/sdd/graph_navigation/cli/
  write_gate.py       # sdd write <file> --session <id>
```

Проверяет: protocol_satisfied, file_path in traced, file_path in allowed_files.
Exit 0 → proceed. Exit 1 → `{"error": "WRITE_BLOCKED", "violations": [...]}`.

### BC-61-E4: Strict Scope Linking

Обновление `scope_policy.py` (или `check_scope.py`): `resolve_scope()` принимает `session_id` и использует `state.allowed_files` вместо только `task_inputs`. Silent bypass detection через `audit_log.jsonl`.

### BC-61-E5: Deterministic anchor

Добавить `--node-id <node_id>` флаг в `sdd resolve`. Bypass BM25, прямая выборка через `graph_service.get_node(node_id)`. Нужен для стабильных тестов.

### BC-61-T1: Eval Fixtures

```
src/sdd/eval/
  __init__.py
  eval_fixtures.py    # EvalFixtureTarget, EvalGuardCheck, EvalSparseGraph,
                      # EvalHiddenDep, EvalMultiHop
  eval_deep.py        # imports eval_fixtures → 2-hop chain (S6)
```

Docstrings содержат BM25-ключевые слова. Imports создают `imports`-рёбра в графе.

### BC-61-T2: Eval Harness

```
src/sdd/eval/
  eval_harness.py     # ScenarioResult, run_graph_cmd
```

### BC-61-T3: Evaluation Report

```
.sdd/reports/
  EvalReport_v61_GraphGuidedTest.md   # инкрементальный отчёт
```

### BC-61-T4: Evaluation Scenarios

| ID | Type | Description |
|----|------|-------------|
| S1 | positive | Normal path — resolve→explain→trace→write |
| S2 | negative | Enforcement check — graph-guard exit 1 при отсутствии graph-step |
| S3 | positive | Sparse graph — NOT_FOUND fallback |
| S4 | positive | Hidden dependency — trace перед write, явный acknowledgment |
| S5 | negative | Scope boundary — check-scope exit 1 для файла вне allowed_files |
| S6 | positive | Multi-hop — BFS depth ≥2 |
| S7 | negative | Write without graph — sdd write exit 1 без protocol |
| S8 | negative | Anchor chain — explain unrelated node не авторизует чтение |

### Dependencies

```text
BC-61-P1 → BC-61-T4  : trace --edge-types нужен для S9 (если добавить trace-filter сценарий)
BC-61-P2 → (блокирует recovery workflows в любой фазе)
BC-61-P3 → BC-61-T4  : VALIDATE gate должен быть исправлен до eval scenarios
BC-61-P4 → BC-61-T4  : coverage threshold верифицируется в acceptance criteria
BC-61-E1 → BC-61-E2  : GraphSessionState required by graph-guard
BC-61-E1 → BC-61-E3  : GraphSessionState required by write gate
BC-61-E1 → BC-61-E4  : GraphSessionState required by strict scope
BC-61-E5 → BC-61-T4  : deterministic anchor required for stable tests
BC-61-T1 → BC-61-T4  : fixtures required for scenarios
BC-61-T2 → BC-61-T4  : harness required for scenarios
BC-61-T3 → BC-61-T4  : report scaffold required before scenarios
BC-61-E2,E3,E4 → BC-61-T4 : enforcement must exist before testing it
```

---

## 3. Domain Events

Новых domain events не вводится. `GraphSessionState` — инфраструктурный артефакт, не проходит через EventStore.

---

## 4. New Invariants

| ID | Statement |
|----|-----------|
| I-GRAPH-PROTOCOL-1 | `resolve ≥1 AND explain ≥1 AND trace ≥1` перед любым write в write_scope |
| I-SCOPE-STRICT-1 | `allowed_files = union(graph_outputs, task_inputs)`; любой read вне — violation |
| I-TRACE-BEFORE-WRITE | write blocked if `file_path not in state.traced` |
| I-GRAPH-GUARD-1 | `sdd graph-guard check --session <id>` → exit 1 если I-GRAPH-PROTOCOL-1 не выполнен |
| I-GRAPH-ANCHOR-CHAIN | explain/trace авторизуют чтение только если вызваны от declared anchor_nodes |
| I-SEARCH-DIRECT-1 | `sdd resolve --node-id <id>` → bypass BM25, exact node lookup, exit 0 если node exists |

---

## 5. Types & Interfaces

```python
@dataclass
class GraphSessionState:
    session_id: str
    resolved: bool = False
    explained: set[str] = field(default_factory=set)
    traced: set[str] = field(default_factory=set)
    graph_outputs: set[str] = field(default_factory=set)
    task_inputs: frozenset[str] = field(default_factory=frozenset)
    anchor_nodes: frozenset[str] = field(default_factory=frozenset)

    @property
    def protocol_satisfied(self) -> bool: ...
    @property
    def allowed_files(self) -> frozenset[str]: ...
    def is_anchor_chain_call(self, node: str) -> bool: ...

@dataclass
class ScenarioResult:
    scenario_id: str
    protocol_satisfied: bool
    scope_violations: int
    trace_before_write: bool
    anchor_coverage: float
    guard_exit_code: int | None
    write_exit_code: int | None
    verdict: str = "PENDING"
    notes: str = ""
```

---

## 6. CLI Interface

```
sdd graph-guard check --session <session_id>
    → exit 0: protocol satisfied
    → exit 1: violations list in JSON stderr

sdd write <file_path> --session <session_id>
    → exit 0: write permitted
    → exit 1: WRITE_BLOCKED in JSON stderr

sdd resolve <query> [--node-id <node_id>] [--format json]
    --node-id: bypass BM25, direct node lookup (I-SEARCH-DIRECT-1)

sdd check-scope read <file_path> --session <id> --inputs <file> [--anchor-nodes <node_id>]
    --session: loads state.allowed_files for strict check
    --anchor-nodes: enables I-GRAPH-ANCHOR-CHAIN validation
```

---

## 7. Evaluation Methodology

### Protocol Correctness (hard — invariants, не метрики)

| Invariant | Positive scenarios | Negative scenarios |
|-----------|-------------------|-------------------|
| I-GRAPH-PROTOCOL-1 | PASS | enforcement blocks violation → PASS |
| I-SCOPE-STRICT-1 | PASS | S5 detects violation → PASS |
| I-TRACE-BEFORE-WRITE | PASS | S7 blocks write → PASS |
| I-GRAPH-GUARD-1 | PASS (exit 0) | S2/S7 correctly exit 1 → PASS |

**Негативные сценарии считаются PASS если enforcement правильно заблокировал.**

### Efficiency Metrics (soft — мониторинг)

| Метрика | Target |
|---------|--------|
| avg graph_calls per task | ≥2 |
| anchor_coverage avg | ≥80% |
| traversal_depth avg | ≥1.5 |

### Вердикт

```
PASS: все 4 positive сценария: protocol_satisfied=True AND scope_viol=0
      AND все 4 negative сценария: enforcement правильно заблокировал
      AND Phase 55 unit tests: PASS

PHASE55.1_NEEDED:
      sdd graph-guard некорректно работает
      OR sdd write не блокирует нарушения
      OR Phase 55 unit tests FAIL

FAIL:
      ≥2 positive сценария не проходят
      OR enforcement полностью отсутствует
```

---

## 8. Risk Notes

- R-1: `sdd trace` не поддерживал `--edge-types` (T-5503 scope gap) → **закрыт BC-61-P1**
- R-2: `check-scope --anchor-nodes` может не поддерживаться → S8 = PARTIAL, gap документируется
- R-3: eval/ файлы влияют на production graph → маркер `# EVAL ONLY` + опционально исключить из release index
- R-4: BM25 нестабильность → `--node-id` для всех eval-тестов
- R-5: GraphSessionState конкурентная запись → `atomic_write` из Phase 55 M6

---

## 9. Acceptance Criteria

```bash
# Enforcement
sdd graph-guard check --session <no-graph-sid>          # → exit 1
sdd write src/sdd/eval/eval_fixtures.py --session <sid-no-proto> # → exit 1

# Full protocol
sdd resolve --node-id FILE:src/sdd/eval/eval_fixtures.py
sdd explain FILE:src/sdd/eval/eval_fixtures.py --edge-types imports
sdd trace FILE:src/sdd/eval/eval_fixtures.py
sdd graph-guard check --session <sid>                   # → exit 0
sdd write src/sdd/eval/eval_fixtures.py --session <sid>  # → exit 0

# Tests
pytest tests/unit/graph_navigation/ -q    # all pass
pytest tests/integration/test_eval_s*.py -q  # all pass
pytest tests/unit/ -q                     # Phase 55 regression: all pass

# Report
grep "PENDING" .sdd/reports/EvalReport_v61_GraphGuidedTest.md  # → 0 lines
```

---

## 10. Phase Sequence Note

Phase 61 планируется после 56-60. Активация возможна только после завершения Phase 60.
`logical_type: backfill` — заполняет enforcement gap, пропущенный в Phase 55.
`anchor_phase: 55`
