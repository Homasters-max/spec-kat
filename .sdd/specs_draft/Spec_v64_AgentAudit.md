# Spec_v64 — Phase 64: Agent Audit System (`sdd audit`)

Status: Draft
Baseline: Spec_v63_BehavioralTraceAnalysis.md (L-TRACE Phase 2)

---

## 0. Goal

Добавить первоклассную CLI-команду `sdd audit` для диагностики качества работы LLM-агента
по данным трассировки SDD-задач. Система работает в двух режимах: анализ одной задачи
(`sdd audit T-NNN`) и анализ всей фазы (`sdd audit phase N`). Python-слой вычисляет
метрики M1-M7 детерминированно; LLM-слой синтезирует выводы через `claude -p
--system-prompt`. Команда не привязана к конкретному проекту и работает в любом
SDD-репозитории. Параллельно устраняются дефекты трассировки (BUG-1, BUG-3, RACE-1,
RACE-2), которые искажают данные и делают аудит недостоверным.

---

## 1. Scope

### In-Scope

- BC-AUDIT: новый модуль `src/sdd/audit/` — data layer аудита
- Fix BUG-1: нормализация путей в `tracing/summary.py` (false-positive violations)
- Fix BUG-3: атомарный append в `tracing/writer.py` (flock + fsync)
- Fix RACE-1: session context через env var в `hooks/trace_tool.py`
- Fix RACE-2: append-only запись `audit_log.jsonl` в `infra/audit.py`
- Классификация violations при записи `summary.json`
- CLI команды `sdd audit T-NNN` и `sdd audit phase N`
- LLM synthesis через `claude -p --system-prompt` (без загрузки CLAUDE.md)
- Нормы NORM-TEST-001 и NORM-TEST-002 в `norm_catalog.yaml`

### Out of Scope

См. §10.

---

## 2. Architecture / BCs

### BC-AUDIT: Agent Audit

```
src/sdd/audit/
  __init__.py
  metrics.py        # вычисление M1-M7 из trace + summary данных
  transcript.py     # парсинг JSONL транскрипта по offset + boundary detection
  classifier.py     # классификация violations: FP_PATH_NORM | PHASE_LEAK | REAL_SCOPE
  synthesizer.py    # LLM synthesis via claude -p subprocess
  report.py         # запись audit_report.md
  commands/
    audit_task.py   # sdd audit T-NNN
    audit_phase.py  # sdd audit phase N
```

### Dependencies

```text
BC-AUDIT → BC-TRACE (tracing/*) : читает trace.jsonl, summary.json
BC-AUDIT → BC-CLI               : регистрация команд в REGISTRY
BC-AUDIT → external: claude CLI : LLM synthesis subprocess
```

---

## 3. Domain Events

Новых domain events не вводится. `sdd audit` — read-only команда, не мутирует EventStore.

Исключение: фиксация дефектов трассировки меняет поведение существующих событий
(`TraceEvent` записывается атомарно; violations классифицируются).

---

## 4. Types & Interfaces

```python
@dataclass(frozen=True)
class ViolationRecord:
    file: str
    operation: str          # FILE_READ | FILE_WRITE
    category: str           # FP_PATH_NORM | PHASE_LEAK | ALLOWED_EXTERNAL | REAL_SCOPE

StepStatus = Literal["OK", "VIOLATION", "MISSING", "EXTRA"]
# OK        — шаг выполнен, нет invariant violations
# VIOLATION — шаг выполнен, но есть violations из summary ground truth
# MISSING   — шаг ожидался по PROTOCOL_STEPS_MAP, но отсутствует в trace
# EXTRA     — шаг найден в trace, но отсутствует в PROTOCOL_STEPS_MAP

@dataclass(frozen=True)
class ProtocolStep:
    """Шаг протокола implement.md с привязкой к правилам и инвариантам."""
    step_id: str            # "-1" | "0" | "1" | "2" | "3" | "4" | "4.5" | "5-6" | "8"
    rule_refs: tuple[str, ...]  # напр. ("I-SESSION-DECLARED-1", "SEM-13")
    command_pattern: str    # паттерн ожидаемой команды, напр. "sdd phase-guard check"
    status: StepStatus      # OK | VIOLATION | MISSING | EXTRA
    invariant_violations: tuple[str, ...]  # violations из summary.json для этого шага

@dataclass(frozen=True)
class AgentScore:
    """Оценка поведения агента. НЕ зависит от полноты данных трассировки.
    Вычисляется только по данным доступным из trace.jsonl + summary.json."""
    protocol_adherence: float       # M1, вес 0.20 — шаги выполнены в порядке
    scope_discipline: float         # M2, вес 0.20
    test_efficiency: float          # M3, вес 0.20
    implementation_focus: float     # M4, вес 0.10
    time_distribution: float        # M5, вес 0.10
    behavioral_quality: float       # M6, вес 0.10
    task_completion: float          # M7, вес 0.05
    step_correctness_ratio: float   # M8, вес 0.05 — доля шагов без invariant violations
    total: float
    grade: str                      # A | B | C | D

@dataclass(frozen=True)
class DataQuality:
    """Качество данных аудита — независимо от оценки агента.
    Отражает полноту трассировки, а не поведение агента."""
    transcript_linked_events: int   # trace events с совпавшим tool_use_id
    transcript_total_events: int    # всего trace events
    transcript_coverage_pct: float  # linked / total × 100
    transcript_fallback_used: bool  # True → offset heuristic (менее точно)
    summary_has_classifications: bool  # violations классифицированы при записи
    trace_has_gaps: bool            # gap > 120с без событий

@dataclass(frozen=True)
class TaskAuditData:
    task_id: str
    audit_version: str          # semver версия audit CLI, напр. "1.0.0"
    duration_secs: int
    phase_breakdown: tuple      # (label, secs, pct) per phase
    protocol_steps: tuple[ProtocolStep, ...]  # шаги из implement.md с invariant привязкой
    agent_score: AgentScore     # оценка агента — не штрафуется за пробелы в данных
    data_quality: DataQuality   # качество данных аудита — отдельное измерение
    violations: tuple[ViolationRecord, ...]
    patterns: tuple[str, ...]   # CH-* identifiers
    transcript_excerpt: str     # reasoning вокруг аномальных событий
```

### Public Interface

```python
class AuditCommand:
    def run_task(self, task_id: str, deep: bool = False) -> TaskAuditData: ...
    def run_phase(self, phase_id: int) -> list[TaskAuditData]: ...

class TranscriptParser:
    def extract_session(self, meta_path: Path,
                        trace_events: list) -> tuple[str, TranscriptCoverage]:
        """Primary: сопоставляет trace events с transcript по tool_use_id.
        Граница сессии = первый tool_use_id вне множества trace event ids.
        Fallback (если ни один tool_use_id не совпал): читает от offset до
        первого вхождения record-session другой задачи или sdd complete T-NNN.
        Возвращает (excerpt, coverage) где coverage.fallback_used=True при fallback."""

class ViolationClassifier:
    def classify(self, raw: str, task_inputs: frozenset[str],
                 allowed_external: frozenset[str]) -> ViolationRecord:
        """Вызывается из summary.py при записи summary.json.
        allowed_external: пути разрешённые implement.md протоколом
        (norm_catalog.yaml, session files, tool-reference.md и др.)"""
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-TRACE-PATH-1 | Все пути в trace events и summary violations нормализуются через `Path.resolve()` перед сравнением | 64 |
| I-TRACE-LOCK-1 | `append_event()` в `tracing/writer.py` MUST acquire `fcntl.flock(LOCK_EX)` перед записью и fsync после | 64 |
| I-SESSION-ISOLATED-1 | `hooks/trace_tool.py` читает `task_id` из env var `SDD_TASK_ID`, а НЕ из `current_session.json`. `current_session.json` используется только для debugging | 64 |
| I-AUDIT-APPEND-1 | `infra/audit.py` MUST использовать append-only запись (`open("a")` + flock). Read-modify-write запрещён | 64 |
| I-AUDIT-CLASSIFY-1 | `summary.json` MUST содержать `violations` как список `ViolationRecord` с полем `category ∈ {FP_PATH_NORM, PHASE_LEAK, ALLOWED_EXTERNAL, REAL_SCOPE}`. Запись без классификации — ERROR | 64 |
| I-AUDIT-SCORE-1 | `AgentScore` (M1-M8) вычисляется ТОЛЬКО из `trace.jsonl` + `summary.json`. MUST NOT использовать `DataQuality` поля как penalty. Отсутствие транскрипта НЕ снижает `agent_score.total` | 64 |
| I-AUDIT-STEPS-1 | `PROTOCOL_STEPS_MAP` MUST быть загружен из `sessions/implement.md` (не захардкожен). При изменении implement.md — `PROTOCOL_STEPS_MAP` обновляется автоматически. Версия implement.md фиксируется в `audit_report.md` | 64 |
| I-AUDIT-CORRECT-1 | `step_correctness_ratio` = `OK_steps / expected_steps` где `expected_steps = len(PROTOCOL_STEPS_MAP)`. MISSING и EXTRA снижают знаменатель не увеличивая числитель. EXTRA шаги штрафуются: каждый EXTRA = -1 к OK_steps (floor 0) | 64 |
| I-AUDIT-GROUND-1 | Ground truth для step evaluation — три источника: (1) `summary.json::violations[]` → VIOLATION; (2) `summary.json::behavioral_violations[]` → VIOLATION; (3) `PROTOCOL_STEPS_MAP` diff с trace → MISSING / EXTRA. LLM-интерпретация транскрипта НЕ является ground truth | 64 |
| I-AUDIT-QUALITY-1 | `DataQuality` и `AgentScore` — независимые измерения. `audit_report.md` MUST выводить их в отдельных секциях. Интерпретация: низкий `transcript_coverage_pct` означает неполные данные, не плохого агента | 64 |
| I-AUDIT-VERSION-1 | `audit_report.md` и JSON stdout MUST содержать поле `audit_version` (semver). `audit_version` берётся из `src/sdd/audit/__init__.py::AUDIT_VERSION` | 64 |
| I-AUDIT-LLM-1 | `synthesizer.py` MUST вызывать `claude -p` с флагом `--system-prompt` и без загрузки CLAUDE.md проекта | 64 |
| I-AUDIT-COVERAGE-1 | `data_quality.transcript_coverage_pct < 50%` → WARNING в stdout: "Low transcript coverage — agent_score based on trace only". MUST NOT block audit completion | 64 |
| I-AUDIT-READONLY-1 | `sdd audit` MUST NOT записывать события в EventStore. Единственные side-effects: запись `audit_report.md` | 64 |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-SPEC-EXEC-1 | CLI содержит только REGISTRY lookup + execute_and_project |
| I-DB-1 | `open_sdd_connection(db_path)` — db_path MUST be explicit non-empty str |
| I-HANDLER-PURE-1 | handle() методы возвращают только events |

---

## 6. Pre/Post Conditions

### `sdd audit T-NNN`

**Pre:**
- `.sdd/reports/T-NNN/trace.jsonl` EXISTS
- `.sdd/reports/T-NNN/summary.json` EXISTS
- `claude` CLI доступен (`which claude` → exit 0)

**Post:**
- `.sdd/reports/T-NNN/audit_report.md` записан
- stdout содержит JSON: `{"grade": "X", "score": N, "top_issues": [...]}`
- EventStore не изменён (I-AUDIT-READONLY-1)

### `sdd audit phase N`

**Pre:**
- `sdd show-state` возвращает `phase_current` или phase N в `phases_known`
- Для каждой DONE задачи фазы существуют `trace.jsonl` и `summary.json`

**Post:**
- `audit_report.md` записан для каждой задачи фазы
- `.sdd/reports/PhaseAudit_vN.md` записан (агрегированный отчёт)
- stdout содержит агрегированный JSON по фазе

### `append_event()` (BUG-3 fix)

**Pre:** `trace.jsonl` открыт для append
**Post:** строка записана атомарно; flock снят; fsync выполнен

### violation classification (BUG-1 fix)

**Pre:** `violation.file` — absolute path; `task.inputs` — relative paths из TaskSet
**Post:** оба приведены через `Path.resolve()` перед сравнением; `category` установлен

### PROTOCOL_STEPS_MAP (metrics.py — привязка к implement.md)

Ground truth шагов берётся из `sessions/implement.md`, не захардкожен (I-AUDIT-STEPS-1).

```python
# src/sdd/audit/metrics.py
PROTOCOL_STEPS_MAP: tuple[dict, ...] = (
    {
        "step_id": "-1",
        "command_pattern": "sdd record-session",
        "rule_refs": ("I-SESSION-DECLARED-1", "I-SESSION-TASK-1"),
        "violation_signals": ("SessionDeclared missing",),
    },
    {
        "step_id": "0",
        "command_pattern": "sdd path",
        "rule_refs": ("§BOOTSTRAP STATE RULE",),
        "violation_signals": (),  # path resolution — нет invariant violations
    },
    {
        "step_id": "1",
        "command_pattern": "sdd phase-guard check",
        "rule_refs": ("SEM-13",),
        "violation_signals": ("phase_guard skipped", "PHASE_GUARD_FAIL"),
    },
    {
        "step_id": "2",
        "command_pattern": "sdd task-guard check",
        "rule_refs": ("SEM-13",),
        "violation_signals": ("task_guard skipped",),
    },
    {
        "step_id": "3",
        "command_pattern": "sdd check-scope read",
        "rule_refs": ("NORM-SCOPE-001", "NORM-SCOPE-003", "I-IMPLEMENT-GRAPH-1"),
        # violations из summary.json::violations[] с category=REAL_SCOPE
        "violation_signals": ("REAL_SCOPE",),
    },
    {
        "step_id": "4",
        "command_pattern": "sdd norm-guard check",
        "rule_refs": ("SEM-13",),
        "violation_signals": ("NORM_GUARD_FAIL",),
    },
    {
        "step_id": "4.5",
        "command_pattern": "sdd explain|sdd resolve|sdd trace",
        "rule_refs": ("NORM-GRAPH-001", "I-IMPLEMENT-GRAPH-1", "I-IMPLEMENT-SCOPE-1"),
        # behavioral_violations из summary.json
        "violation_signals": ("BLIND_WRITE", "THRASHING"),
    },
    {
        "step_id": "5-6",
        "command_pattern": "FILE_READ|FILE_WRITE",
        "rule_refs": ("CEP-1", "CEP-2", "CEP-6", "DDD-3", "SDD-14"),
        "violation_signals": ("REAL_SCOPE", "PHASE_LEAK"),
    },
    {
        "step_id": "8",
        "command_pattern": "sdd complete",
        "rule_refs": ("I-TASK-MODE-1",),
        "violation_signals": ("complete missing",),
    },
)

def evaluate_steps(
    trace_commands: list[str],
    summary_violations: list[ViolationRecord],
    behavioral_violations: list[str],
) -> list[ProtocolStep]:
    """I-AUDIT-GROUND-1: три источника ground truth.
    PROTOCOL_STEPS_MAP diff → MISSING / EXTRA.
    summary violations → VIOLATION."""
    violation_signals = (
        {v.category for v in summary_violations if v.category in ("REAL_SCOPE", "PHASE_LEAK")}
        | set(behavioral_violations)
    )
    steps = []
    matched_trace = set()
    for spec in PROTOCOL_STEPS_MAP:
        executed = any(spec["command_pattern"] in cmd for cmd in trace_commands)
        if executed:
            matched_trace.add(spec["step_id"])
            has_violation = any(sig in violation_signals
                                for sig in spec["violation_signals"])
            status: StepStatus = "VIOLATION" if has_violation else "OK"
        else:
            status = "MISSING"
        steps.append(ProtocolStep(
            step_id=spec["step_id"],
            rule_refs=tuple(spec["rule_refs"]),
            command_pattern=spec["command_pattern"],
            status=status,
            invariant_violations=tuple(
                sig for sig in spec["violation_signals"] if sig in violation_signals
            ),
        ))
    # EXTRA: команды в trace не покрытые ни одним шагом PROTOCOL_STEPS_MAP
    expected_patterns = {s["command_pattern"] for s in PROTOCOL_STEPS_MAP}
    for cmd in trace_commands:
        if not any(p in cmd for p in expected_patterns):
            steps.append(ProtocolStep(
                step_id="EXTRA",
                rule_refs=(),
                command_pattern=cmd,
                status="EXTRA",
                invariant_violations=(),
            ))
    return steps

def compute_step_correctness_ratio(steps: list[ProtocolStep]) -> float:
    """I-AUDIT-CORRECT-1: M8 = OK_steps / expected_steps.
    EXTRA штрафует: каждый EXTRA = -1 к числителю (floor 0)."""
    expected = sum(1 for s in steps if s.status != "EXTRA")
    ok = sum(1 for s in steps if s.status == "OK")
    extra_penalty = sum(1 for s in steps if s.status == "EXTRA")
    return max(0.0, ok - extra_penalty) / expected if expected else 0.0
```

---

## 7. Use Cases

### UC-64-1: Аудит одной задачи

**Actor:** Human (или LLM в следующей сессии)
**Trigger:** `sdd audit T-5601`
**Pre:** task DONE, trace + summary существуют
**Steps:**
1. Python layer читает `trace.jsonl` → нормализует timestamps → строит timeline
2. Python layer читает `summary.json` → извлекает classified violations + behavioral_violations
3. Python layer сопоставляет trace events с `PROTOCOL_STEPS_MAP` → строит `protocol_steps[]`
4. Python layer вычисляет `step_correctness_ratio` из `protocol_steps` + summary ground truth (I-AUDIT-GROUND-1)
5. Python layer вычисляет M1-M8 → определяет grade
4. Python layer парсит транскрипт от `transcript_offset` до boundary
5. Python layer строит промпт с данными задачи
6. `claude -p "$prompt" --system-prompt "SDD audit analyzer..."` → LLM синтез
7. Запись `audit_report.md`; вывод compact JSON в stdout

**Post:** `audit_report.md` содержит timeline + метрики + паттерны + рекомендации

### UC-64-2: Фазовый аудит

**Actor:** Human на CHECK_DOD или SUMMARIZE сессии
**Trigger:** `sdd audit phase 56`
**Pre:** фаза содержит ≥1 DONE задачу
**Steps:**
1. `sdd show-state` → список task_id фазы со статусом DONE
2. Для каждой задачи последовательно: UC-64-1 (пишет `audit_report.md`)
3. Чтение всех `audit_report.md` фазы в память
4. Финальный `claude -p "$phase_prompt" --system-prompt "..."` → фазовый синтез
5. Запись `.sdd/reports/PhaseAudit_vN.md`

**Post:** тренды M1-M7 по задачам, системные паттерны, рекомендации для следующего спека

### UC-64-3: Устранение RACE-1

**Actor:** hooks/trace_tool.py при каждом tool_use
**Trigger:** Claude Code hook event
**Pre:** `SDD_TASK_ID` env var установлен `sdd record-session`
**Steps:**
1. Читает task_id из `os.environ["SDD_TASK_ID"]` (не из файла)
2. Пишет TraceEvent в `trace/T-NNN/trace.jsonl` через flock
**Post:** событие записано в правильный трейс даже при параллельных сессиях

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-TRACE (tracing/*) | BC-AUDIT reads | trace.jsonl, summary.json как источники данных |
| BC-CLI | BC-AUDIT → | регистрация `audit` команды в REGISTRY |
| Claude CLI (external) | BC-AUDIT → | LLM synthesis subprocess |

### summary.py расширение (BUG-1 + I-AUDIT-CLASSIFY-1)

`summary.json` содержит только raw data. Scores НЕ вычисляются при записи summary (I-AUDIT-SCORE-1).

```python
# tracing/summary.py — classify_violations() вызывается при записи summary
# Semi-dynamic: базовый список + module-root heuristic
# Фиксированные протокольные файлы (всегда разрешены implement.md)
_ALLOWED_EXTERNAL_FIXED: frozenset[str] = frozenset({
    ".sdd/norms/norm_catalog.yaml",
    ".sdd/docs/sessions/implement.md",
    ".sdd/docs/sessions/validate.md",
    ".sdd/docs/ref/tool-reference.md",
    ".sdd/docs/ref/kernel-contracts.md",
    ".sdd/runtime/current_session.json",
    ".sdd/runtime/State_index.yaml",
})

def build_allowed_external(project_root: Path) -> frozenset[Path]:
    """Module-root heuristic: добавляет все файлы из директорий,
    которые являются корнями модулей задачи (содержат __init__.py),
    кроме самого task scope — это легитимные reads соседних модулей
    при навигации через sdd explain/trace.
    Правило: если путь находится в src/ и содержит __init__.py на уровне выше —
    это модульный контекст, не нарушение scope."""
    fixed = frozenset((project_root / p).resolve() for p in _ALLOWED_EXTERNAL_FIXED)
    module_roots = frozenset(
        f.resolve()
        for f in project_root.glob("src/**/__init__.py")
    )
    return fixed | module_roots

def classify_violations(raw_violations: list[str],
                        task_inputs: frozenset[str]) -> list[ViolationRecord]:
    normalized_inputs = frozenset(Path(p).resolve() for p in task_inputs)
    normalized_external = frozenset(
        (project_root / p).resolve() for p in ALLOWED_EXTERNAL
    )
    result = []
    for v in raw_violations:
        file_path = Path(extract_file(v)).resolve()  # I-TRACE-PATH-1
        if file_path in normalized_inputs:
            category = "FP_PATH_NORM"
        elif file_path in normalized_external:
            category = "ALLOWED_EXTERNAL"
        elif is_other_task_report(file_path):
            category = "PHASE_LEAK"
        else:
            category = "REAL_SCOPE"
        result.append(ViolationRecord(file=str(file_path),
                                      operation=extract_op(v),
                                      category=category))
    return result
```

### record_session.py расширение (RACE-1 fix)

```python
# commands/record_session.py — после записи current_session.json
os.environ["SDD_TASK_ID"] = task_id
os.environ["SDD_SESSION_ID"] = session_id
```

---

## 9. Verification

| # | Test Name | Invariant(s) |
|---|-----------|--------------|
| 1 | `test_audit_path_normalization` | I-TRACE-PATH-1 |
| 2 | `test_audit_flock_concurrent_writes` | I-TRACE-LOCK-1 (10 threads) |
| 3 | `test_audit_env_var_isolation` | I-SESSION-ISOLATED-1 |
| 4 | `test_audit_append_only` | I-AUDIT-APPEND-1 |
| 5 | `test_audit_violation_classification_fp` | I-AUDIT-CLASSIFY-1: FP_PATH_NORM |
| 6 | `test_audit_violation_classification_external` | I-AUDIT-CLASSIFY-1: ALLOWED_EXTERNAL |
| 7 | `test_audit_violation_classification_leak` | I-AUDIT-CLASSIFY-1: PHASE_LEAK |
| 8 | `test_audit_scores_not_in_summary` | I-AUDIT-SCORE-1: summary.json не содержит scores{} |
| 9 | `test_audit_agent_score_no_transcript_penalty` | I-AUDIT-SCORE-1: agent_score.total идентичен при coverage=100% и coverage=0% |
| 10 | `test_audit_data_quality_independent` | I-AUDIT-QUALITY-1: data_quality не влияет на agent_score |
| 10b | `test_audit_step_status_ok` | evaluate_steps: OK когда executed + no violations |
| 10c | `test_audit_step_status_missing` | evaluate_steps: MISSING когда шаг отсутствует в trace |
| 10d | `test_audit_step_status_extra_penalizes_m8` | I-AUDIT-CORRECT-1: EXTRA снижает M8 |
| 10e | `test_audit_step_ground_truth_only_summary` | I-AUDIT-GROUND-1: transcript не влияет на correctness |
| 10f | `test_audit_protocol_steps_map_loaded_from_implement_md` | I-AUDIT-STEPS-1: PROTOCOL_STEPS_MAP не захардкожен |
| 11 | `test_audit_version_in_output` | I-AUDIT-VERSION-1 |
| 12 | `test_audit_no_eventstore_write` | I-AUDIT-READONLY-1 |
| 13 | `test_audit_transcript_boundary_by_tool_use_id` | TranscriptParser: граница через tool_use_id |
| 14 | `test_audit_transcript_boundary_fallback` | TranscriptParser: fallback при отсутствии tool_use_id |
| 15 | `test_audit_coverage_warning_threshold` | I-AUDIT-COVERAGE-1: WARNING при coverage < 50% |
| 16 | `test_audit_allowed_external_module_root` | build_allowed_external: __init__.py heuristic |
| 17 | `test_audit_phase_aggregation` | UC-64-2 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| LightRAG индексация audit_report.md | Phase 65+ (после стабилизации) |
| Real-time enforcement (хук запрещает дубль pytest) | Phase 65+ |
| BUG-4 (summary при прерванной сессии) | Phase 65+ |
| BUG-5 (коллизия task_id) | Phase 65+ |
| RACE-4 (PostgreSQL optimistic lock) | уже корректен |
| Web UI для audit_report.md | не в roadmap |
| Метрики M8+ (за пределами M1-M7) | по результатам отладочной фазы |

---

## Risk Notes

| ID | Риск | Митигация |
|----|------|-----------|
| R-1 | `claude -p` subprocess может не иметь доступа к Claude в CI/CD | `sdd audit --no-llm` флаг — Python layer без LLM синтеза |
| R-2 | Исторические `summary.json` (до Phase 64) не содержат классификацию | `sdd audit` graceful fallback: violations без category = "UNCLASSIFIED" |
| R-3 | transcript_path указывает на удалённую сессию | fallback: аудит без транскрипта, только trace + summary |
| R-4 | Параллельный запуск `sdd audit phase N` в нескольких терминалах | I-TRACE-LOCK-1 защищает запись; audit_report.md перезаписывается идемпотентно |
