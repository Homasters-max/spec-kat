# Spec_v62 — Execution Trace Layer (L-TRACE) + Graph Semantic Hardening

Status: Draft
Baseline: Spec_v61_GraphEnforcement.md

---

## 0. Goal

Phase 61 ввёл enforcement инфраструктуру: агент обязан следовать протоколу graph-guided implement.
Критическая дыра: система знает **что** агент сделал (через EventLog, GraphSessionState), но не видит
**почему** — в каком порядке, без обоснования, были ли пропущены шаги.
Симптом из EvalReport_v61: `traversal_depth_avg=1.0` при цели ≥1.5 — enforcement есть, семантика мелкая.

Phase 62 решает это в два независимых шага:

1. **L-TRACE (приоритет 1)** — детерминированный execution trace: каждое действие LLM в IMPLEMENT = событие в append-only лог. Накопить реальные данные о поведении агента.
2. **Graph Semantic Hardening (приоритет 2)** — 5 новых инвариантов поверх данных L-TRACE. Реализуется после прогона L-TRACE на реальных IMPLEMENT-сессиях.

---

## 1. Scope

### In-Scope

**Часть 1: L-TRACE MVP**

- BC-62-L1: `TraceEvent` dataclass + append-only writer (`src/sdd/tracing/`)
- BC-62-L2: Claude Code PostToolUse hooks — перехват Read/Edit/Write/Bash → trace events
- BC-62-L3: `current_session.json` — добавить поле `task_id` (via `record-session --task T-NNN`)
- BC-62-L4: `sdd trace-summary T-NNN` — replay trace.jsonl → summary.json + violations
- BC-62-L5: `sdd complete` вызывает `trace-summary` как обязательный внутренний шаг

**Часть 2: Graph Semantic Hardening**

- BC-62-G1: Extend `GraphSessionState` — 5 новых полей с backward-compatible дефолтами
- BC-62-G2: `I-TRACE-RELEVANCE-1` в `write_gate.py`
- BC-62-G3: `I-FALLBACK-STRICT-1` в `graph_guard.py`
- BC-62-G4: `I-GRAPH-DEPTH-1` в `graph_guard.py`
- BC-62-G5: `I-GRAPH-COVERAGE-REQ-1` + `I-EXPLAIN-USAGE-1` в `graph_guard.py`
- BC-62-G6: Eval scenarios S9–S15 + `EvalReport_v62`

### Out-of-Scope

- `THOUGHT`/`DECISION` events (явное логирование reasoning LLM) — Phase 63
- `timeline.txt` (человекочитаемый вывод) — Phase 63
- Dashboard / визуализация — будущее
- CI-интеграция violations — будущее
- I-GRAPH-EFFICIENCY-1 (max 5 graph calls) — исключён из минимального набора

---

## 2. Architecture

### L-TRACE: Слой в стеке

```
L0  EventLog (PostgreSQL)
L1  Graph
L2  ContextEngine
L3  RAG
L-TRACE  ExecutionTrace  ← NEW (отдельный JSONL, не EventStore)
```

L-TRACE независим от EventStore. Не пишет в PostgreSQL. Хранилище — JSONL-файлы на диске.

### Hook-механизм

LLM вызывает инструменты Claude Code (Read, Edit, Write, Bash). Для перехвата используются
**Claude Code PostToolUse hooks** — shell-скрипты, запускаемые автоматически после каждого вызова инструмента.

Маппинг инструментов → типы событий:

| Claude Code tool | Условие | TraceEvent.type |
|------------------|---------|-----------------|
| `Read` | любой | `FILE_READ` |
| `Edit`, `Write` | любой | `FILE_WRITE` |
| `Bash` | команда начинается с `sdd resolve\|explain\|trace` | `GRAPH_CALL` |
| `Bash` | всё остальное | `COMMAND` |

Hook — **тупой логгер**: пишет сырое событие, никакой валидации в реальном времени.
Вся аналитика (allowed_files, violations) — постфактум в `sdd trace-summary`.

### Источник task_id в hooks

Hook читает `.sdd/runtime/current_session.json`. Поле `task_id` добавляется при объявлении
IMPLEMENT-сессии через `sdd record-session --type IMPLEMENT --phase N --task T-NNN`.

### Вычисление allowed_files (постфактум)

`sdd trace-summary` строит контекст в три логических шага:

1. `parse_trace()` — читает trace.jsonl, возвращает список `TraceEvent` в порядке `ts`
2. `build_context()` — загружает `GraphSessionState` для session_id (если есть);
   вычисляет `allowed_files = explain_nodes ∪ trace_path ∪ task_inputs`.
   `GRAPH_CALL` события — сигнал "граф использовался", не источник allowed_files.
3. `detect_violations()` — применяет правила к контексту

`meta.allowed` появляется **только в summary.json**, не в trace.jsonl событиях.
`trace-summary` не содержит бизнес-логику и graph-логику — только анализ трейса.

### Инференция нарушений (два уровня)

**Hard (I-TRACE-COMPLETE-1):** `FILE_WRITE` без **любого** предшествующего `GRAPH_CALL` в той же сессии.
Не требует совпадения пути — достаточно факта использования графа.

**Soft (SCOPE_VIOLATION):** `FILE_WRITE` или `FILE_READ` где `path ∉ allowed_files`.
Отдельный тип нарушения, не блокирует, но отображается в summary.

### Хранилище

```
.sdd/reports/T-XXX/
    trace.jsonl     ← события, одно JSON-объект на строку
    summary.json    ← агрегат + violations (генерируется sdd trace-summary)
```

Файлы создаются при первом событии задачи. Один IMPLEMENT-запуск = один trace.

---

## 3. Domain Events

Новых SDD domain events не вводится. `ExecutionTrace` — инфраструктурный артефакт,
не проходит через EventStore (PostgreSQL). `current_session.json` расширяется полем `task_id`
(не является SDD-событием).

---

## 4. New Invariants

### L-TRACE инварианты

| ID | Statement |
|----|-----------|
| I-TRACE-COMPLETE-1 | Каждый `FILE_WRITE` MUST иметь хотя бы один предшествующий `GRAPH_CALL` в той же сессии (любой — не требует совпадения пути) |
| I-TRACE-SCOPE-1 | (soft) `FILE_WRITE` и `FILE_READ` где `path ∉ allowed_files` → `SCOPE_VIOLATION` в summary; не блокирует |
| I-TRACE-ORDER-1 | События в trace.jsonl MUST быть упорядочены по `ts` (монотонно неубывающий); порядок восстанавливается `enumerate(sorted_by_ts)` |

### Graph Semantic Hardening инварианты

| ID | Statement | Gate |
|----|-----------|------|
| I-TRACE-RELEVANCE-1 | `write_target ∈ state.trace_path` | `write_gate.py` |
| I-FALLBACK-STRICT-1 | fallback разрешён только при `resolve exit=NOT_FOUND` + `task_inputs` заданы; `fallback_used=True` в session | `graph_guard.py` |
| I-GRAPH-DEPTH-1 | `traversal_depth_max ≥ 2` ИЛИ `depth_justification` задан | `graph_guard.py` |
| I-GRAPH-COVERAGE-REQ-1 | все `write_targets ⊆ trace_path ∪ explain_nodes` | `graph_guard.py` |
| I-EXPLAIN-USAGE-1 | все `explain_nodes ⊆ trace_path ∪ write_targets` | `graph_guard.py` |

---

## 5. Types & Interfaces

### TraceEvent

```python
@dataclass
class TraceEvent:
    ts: float           # unix timestamp; единственный источник порядка
    type: str           # "GRAPH_CALL" | "FILE_READ" | "FILE_WRITE" | "COMMAND"
    payload: dict
    session_id: str
    task_id: str
```

`step` отсутствует — race conditions при append из hook. Порядок = `enumerate(sorted(events, key=lambda e: e.ts))`.

Пример GRAPH_CALL:
```json
{"ts": 1714470000.123, "type": "GRAPH_CALL",
 "payload": {"cmd": "resolve", "query": "eval fixture target",
             "result": ["FILE:eval_fixtures.py"]},
 "session_id": "eval-s1", "task_id": "T-6201"}
```

Пример FILE_WRITE:
```json
{"ts": 1714470010.5, "type": "FILE_WRITE",
 "payload": {"path": "src/sdd/tracing/trace_event.py", "tool": "Edit"},
 "session_id": "eval-s1", "task_id": "T-6201"}
```

Пример COMMAND с subtype:
```json
{"ts": 1714470020.0, "type": "COMMAND",
 "payload": {"cmd": "pytest tests/unit/", "category": "TEST", "exit_code": 0},
 "session_id": "eval-s1", "task_id": "T-6201"}
```

`payload.category` для COMMAND: `"TEST"` (pytest, coverage) | `"SYSTEM"` (git, bash, прочее).

### TraceSummary

```python
@dataclass
class TraceSummary:
    task_id: str
    session_id: str
    total_events: int
    graph_calls: int
    file_reads: int
    file_writes: int
    commands: int
    violations: list[str]   # ["I-TRACE-COMPLETE-1: FILE_WRITE on X without prior GRAPH_CALL", ...]
```

### GraphSessionState (расширение для Части 2)

Новые поля с backward-compatible дефолтами:
```python
traversal_depth_max: int = 0
fallback_used: bool = False
explain_nodes: FrozenSet[str] = frozenset()
write_targets: FrozenSet[str] = frozenset()
depth_justification: str = ""
```

---

## 6. CLI Interface

### Новые команды

```
sdd trace-summary T-NNN
    1. parse_trace()      → список TraceEvent, отсортированных по ts
    2. build_context()    → загружает GraphSessionState; вычисляет
                            allowed_files = explain_nodes ∪ trace_path ∪ task_inputs
    3. detect_violations() → применяет I-TRACE-COMPLETE-1, I-TRACE-SCOPE-1, I-TRACE-ORDER-1
    Пишет .sdd/reports/T-NNN/summary.json
    Выводит violations в stdout (видны LLM перед подтверждением)
    → exit 0: нет hard violations (I-TRACE-COMPLETE-1)
    → exit 1: hard violations найдены (список в JSON stderr)
    SCOPE_VIOLATION (soft) всегда выводится в stdout, не влияет на exit code
```

### Изменения существующих команд

```
sdd record-session --type IMPLEMENT --phase N --task T-NNN
    Расширяет current_session.json: добавляет поле "task_id": "T-NNN"
    (task_id отсутствует для не-IMPLEMENT типов)

sdd complete T-NNN
    Вызывает sdd trace-summary T-NNN как обязательный внутренний шаг
    Если violations найдены — выводит их, но не блокирует complete
    (violations информативны на Phase 62; блокировка — Phase 63)
```

### Hook-конфигурация (settings.json)

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Read|Edit|Write|Bash",
        "hooks": [{"type": "command", "command": "sdd trace-hook"}]
      }
    ]
  }
}
```

`sdd trace-hook` — shell-обёртка: читает stdin (JSON от Claude Code), читает current_session.json,
определяет тип события, вызывает `append_event()`.

---

## Preconditions

- Phase 61 COMPLETE (GraphSessionState, graph-guard, write gate реализованы и прошли eval)
- `src/sdd/tracing/` модуль не существует (создаётся с нуля)
- Claude Code hooks поддерживают PostToolUse для инструментов Read, Edit, Write, Bash

---

## 7. Evaluation Methodology

### Часть 1 (L-TRACE): smoke-тесты

```bash
# Создать TraceEvent, записать, прочитать
python3 -c "from sdd.tracing.trace_event import TraceEvent; ..."

# I-TRACE-ORDER-1: события отсортированы по ts (монотонно)
# I-TRACE-COMPLETE-1: FILE_WRITE без предшествующего GRAPH_CALL → hard violation
# I-TRACE-SCOPE-1: FILE_WRITE вне allowed_files → soft SCOPE_VIOLATION

pytest tests/unit/tracing/ -q
```

### Часть 2 (Graph Semantic Hardening): сценарии S9–S15

| ID | Инвариант | Тип | Описание |
|----|-----------|-----|---------|
| S9 | I-TRACE-RELEVANCE-1 | negative | write_target ≠ trace_path → exit 1 |
| S10 | I-FALLBACK-STRICT-1 | negative | fallback_used + allowed_files пусто → exit 1 |
| S11 | I-GRAPH-DEPTH-1 | negative | depth_max=1 + no justification → exit 1 |
| S12 | I-GRAPH-COVERAGE-REQ-1 | negative | write_target ∉ trace_path ∪ explain_nodes → exit 1 |
| S13 | I-EXPLAIN-USAGE-1 | negative | explain_node ∉ trace_path ∪ write_targets → exit 1 |
| S14 | all | positive | depth=2, targets covered, explain used, no fallback → exit 0 |
| S15 | I-FALLBACK-STRICT-1 | positive | fallback_used + task_inputs заданы → exit 0 |

**Вердикт Phase 62 Часть 2:**
```
PASS:
  S9–S13: enforcement правильно вернул exit 1
  S14–S15: корректный протокол → exit 0
  pytest tests/unit/ -q: ≥1374 PASS (regression)

PHASE62.1_NEEDED:
  graph_guard/write_gate некорректно обрабатывают новые поля
  OR новые поля GraphSessionState ломают Phase 61 сессии

FAIL:
  ≥2 positive сценария не проходят
```

---

## 8. Risk Notes

- R-1: `sdd trace-hook` получает stdin от Claude Code — формат PostToolUse hook input должен быть верифицирован перед реализацией
- R-2: Новые поля GraphSessionState с дефолтами — Phase 61 GraphSessionState JSON файлы должны оставаться валидными (backward compatibility)
- R-3: порядок событий по `ts` — clock skew на одной машине маловероятен, но при одновременных hook-вызовах возможны одинаковые `ts`; допустимо (tie-breaking не критичен для violations)
- R-4: violations в `sdd complete` — информативны, не блокируют; риск игнорирования. Блокировка рассматривается в Phase 63.
- R-5: `task_id` в current_session.json отсутствует для не-IMPLEMENT сессий — hook должен gracefully пропускать запись при отсутствии поля

---

## 9. Acceptance Criteria

```bash
# L-TRACE: базовый smoke
sdd record-session --type IMPLEMENT --phase 62 --task T-6201
# current_session.json содержит "task_id": "T-6201"

# hook пишет событие (через Read → PostToolUse)
cat .sdd/reports/T-6201/trace.jsonl | head -1 | python3 -m json.tool

# summary без violations
sdd trace-summary T-6201   # → exit 0

# FILE_WRITE без предшествующего GRAPH_CALL → violation
sdd trace-summary T-TEST   # → exit 1, stderr содержит I-TRACE-COMPLETE-1

# sdd complete вызывает trace-summary
sdd complete T-6201        # stdout содержит trace summary

# Unit tests
pytest tests/unit/tracing/ -q                   # все pass
pytest tests/unit/ -q                           # Phase 61 regression: ≥1374 pass

# Graph Semantic Hardening (после прогона L-TRACE на реальных сессиях)
pytest tests/integration/test_eval_s9_s15.py -q  # S9-S15 все pass
grep "PENDING" .sdd/reports/EvalReport_v62.md   # → 0 lines
```

---

## 10. Phase Sequence Note

Phase 62 активируется после Phase 61 COMPLETE.
`logical_type: extension` — расширяет enforcement инфраструктуру Phase 61.
`anchor_phase: 61`

Порядок выполнения внутри Phase 62:
```
Часть 1 (L-TRACE):
  T-6201-L → T-6202-L → T-6203-L → T-6204-L
  ↓
  [прогнать реальные IMPLEMENT сессии, изучить trace.jsonl]
  ↓
Часть 2 (Graph Semantic Hardening):
  T-6201 → T-6202 → T-6203 → T-6204 → T-6205 → T-6206 → T-6207
```
