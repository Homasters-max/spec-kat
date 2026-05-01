# Plan_v62 — Phase 62: Execution Trace Layer (L-TRACE) + Graph Semantic Hardening

Status: DRAFT
Spec: specs/Spec_v62_ExecutionTraceLayer.md

---

## Logical Context

type: extension
anchor_phase: 61
rationale: "Расширяет enforcement инфраструктуру Phase 61: добавляет детерминированный execution trace (L-TRACE) для сбора реальных данных о поведении агента, затем применяет 5 новых Graph Semantic инвариантов поверх этих данных."

---

## Milestones

### M1: TraceEvent + append-only writer (BC-62-L1)

```text
Spec:       §1 Scope — Часть 1: L-TRACE MVP (BC-62-L1)
            §5 Types & Interfaces — TraceEvent dataclass
BCs:        BC-62-L1
Invariants: I-TRACE-ORDER-1 (события в trace.jsonl упорядочены по ts)
Depends:    — (новый модуль src/sdd/tracing/, создаётся с нуля)
Risks:      Неверная структура TraceEvent заблокирует все остальные BC
```

### M2: PostToolUse hooks — перехват инструментов (BC-62-L2)

```text
Spec:       §2 Architecture — Hook-механизм
            §6 CLI Interface — Hook-конфигурация (settings.json)
BCs:        BC-62-L2
Invariants: I-TRACE-COMPLETE-1 (FILE_WRITE должен иметь предшествующий GRAPH_CALL)
Depends:    M1 (append_event() должен существовать)
Risks:      R-1: формат PostToolUse hook input от Claude Code требует верификации перед реализацией
            R-5: task_id отсутствует в не-IMPLEMENT сессиях — hook должен gracefully пропускать
```

### M3: task_id в current_session.json + record-session расширение (BC-62-L3)

```text
Spec:       §1 Scope — BC-62-L3
            §6 CLI Interface — sdd record-session --task T-NNN
BCs:        BC-62-L3
Invariants: I-SESSION-DECLARED-1 (сессия объявляется до любых действий)
Depends:    M1 (current_session.json читается hook-ом для получения task_id)
Risks:      Backward compatibility: существующие сессии без task_id не должны ломаться
```

### M4: sdd trace-summary T-NNN (BC-62-L4)

```text
Spec:       §1 Scope — BC-62-L4
            §2 Architecture — Вычисление allowed_files (постфактум)
            §2 Architecture — Инференция нарушений (два уровня)
            §5 Types & Interfaces — TraceSummary dataclass
            §6 CLI Interface — sdd trace-summary
BCs:        BC-62-L4
Invariants: I-TRACE-COMPLETE-1 (hard violation → exit 1)
            I-TRACE-SCOPE-1 (soft SCOPE_VIOLATION → stdout, exit 0)
            I-TRACE-ORDER-1 (sorted by ts)
Depends:    M1, M2, M3
Risks:      trace-summary не должен содержать бизнес-логику и graph-логику (только анализ трейса)
```

### M5: sdd complete интегрирует trace-summary (BC-62-L5)

```text
Spec:       §1 Scope — BC-62-L5
            §6 CLI Interface — sdd complete T-NNN
BCs:        BC-62-L5
Invariants: I-TRACE-COMPLETE-1 (violations выводятся, но не блокируют — Phase 63 добавит блокировку)
Depends:    M4
Risks:      R-4: violations информативны на Phase 62, не блокируют; риск игнорирования
```

### M6: GraphSessionState расширение — 5 новых полей (BC-62-G1)

```text
Spec:       §1 Scope — Часть 2: Graph Semantic Hardening (BC-62-G1)
            §5 Types & Interfaces — GraphSessionState расширение
BCs:        BC-62-G1
Invariants: backward-compatible дефолты для всех новых полей
Depends:    M1–M5 (L-TRACE должен быть реализован и прогнан на реальных сессиях)
Risks:      R-2: Phase 61 GraphSessionState JSON файлы должны оставаться валидными
```

### M7: Новые инварианты в write_gate.py и graph_guard.py (BC-62-G2–G5)

```text
Spec:       §4 New Invariants — Graph Semantic Hardening инварианты
            §1 Scope — BC-62-G2, BC-62-G3, BC-62-G4, BC-62-G5
BCs:        BC-62-G2 (I-TRACE-RELEVANCE-1 в write_gate.py)
            BC-62-G3 (I-FALLBACK-STRICT-1 в graph_guard.py)
            BC-62-G4 (I-GRAPH-DEPTH-1 в graph_guard.py)
            BC-62-G5 (I-GRAPH-COVERAGE-REQ-1 + I-EXPLAIN-USAGE-1 в graph_guard.py)
Invariants: I-TRACE-RELEVANCE-1, I-FALLBACK-STRICT-1, I-GRAPH-DEPTH-1,
            I-GRAPH-COVERAGE-REQ-1, I-EXPLAIN-USAGE-1
Depends:    M6
Risks:      Новые guards не должны ломать Phase 61 позитивные сценарии S1–S8
```

### M8: Eval сценарии S9–S15 + EvalReport_v62 (BC-62-G6)

```text
Spec:       §7 Evaluation Methodology — Часть 2: сценарии S9–S15
            §9 Acceptance Criteria
BCs:        BC-62-G6
Invariants: все Graph Semantic Hardening инварианты (покрытие через S9–S15)
Depends:    M7
Risks:      Phase 61 regression: ≥1374 тестов должны оставаться PASS
```

---

## Risk Notes

- R-1: `sdd trace-hook` получает stdin от Claude Code — формат PostToolUse hook input должен быть верифицирован перед реализацией BC-62-L2. Митигация: изучить документацию и тестовые примеры hooks перед написанием кода.
- R-2: Новые поля GraphSessionState с backward-compatible дефолтами — Phase 61 JSON файлы должны оставаться валидными. Митигация: все новые поля используют `field(default_factory=...)` или примитивные дефолты.
- R-3: Clock skew при одновременных hook-вызовах — возможны одинаковые `ts`. Допустимо (tie-breaking не критичен для violations), порядок: `enumerate(sorted(events, key=lambda e: e.ts))`.
- R-4: Violations в `sdd complete` — информативны, не блокируют на Phase 62. Блокировка рассматривается в Phase 63. Риск: violations могут игнорироваться без явного подтверждения.
- R-5: `task_id` отсутствует для не-IMPLEMENT сессий — hook должен gracefully пропускать запись при отсутствии поля в current_session.json. Митигация: явная проверка на наличие поля перед записью.
