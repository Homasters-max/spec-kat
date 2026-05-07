# Контекст для передачи в новую сессию
_Обновлён: 2026-04-27_

---

## Текущее состояние проекта

**Проект:** SDD (Software Development Director) — система управления разработкой через event sourcing + LLM-агент.

**Технический стек:** Python, DuckDB (EventLog → мигрирует в Phase 32), PostgreSQL (graph layer + EventLog после Phase 32), psycopg, Click CLI, pytest.

**Инфраструктура:** `src/sdd/` — CLI-пакет. `.sdd/` — данные (specs, plans, tasks, state, EventLog).

**`phase_current = 30`** (COMPLETE). `phases_known` включает фазы до 34 (33 и 34 — COMPLETE).

---

## Roadmap: линейная последовательность

### Активационный порядок (I-PHASE-SEQ-1: каждая фаза = предыдущая + 1)

| Шаг | Phase | Spec-файл | Зависит от | Статус |
|-----|-------|-----------|------------|--------|
| **→1** | **31** GovernanceCommands | `Spec_v31_GovernanceCommands.md` | Phase 30 (done) | **NEXT — запускать сейчас** |
| 2 | 32 PostgresMigration | `Spec_v32_PostgresMigration.md` | Phase 31 | Draft |
| 3 | 35 TestHarnessElevation | `Spec_v35_TestHarnessElevation.md` | Phase 33+34 (done!) | Draft — 33+34 уже в phases_known |
| 4 | 36 GraphNavigation | `Spec_v36_GraphNavigation.md` | Phase 18 + Phase 32 | Draft |
| 5 | 37 TemporalNavigation | `Spec_v37_TemporalNavigation.md` | Phase 36 | Draft |
| 6 | 38 MutationGovernance | `Spec_v38_MutationGovernance.md` | Phase 37 | Draft |

> **Примечание Phase 35:** после activate-phase 32 (current=32), фазы 33 и 34 уже COMPLETE в phases_known.
> Переход к 35 требует обработки зазора 32→35. Проверить поведение guard при попытке activate-phase 35.

---

## Что сделано в предыдущих сессиях (2026-04-27)

### Сессия 1 — Проверка и выравнивание ссылок

1. **Spec_v19_v1_GraphNavigation.md** — ошибочно помечен Archived → возвращён в `Status: Draft — ACTIVE`
2. **Spec_v20_TemporalNavigation.md** — Baseline указывал на `del/Spec_v19_GraphNavigation.md` → исправлен
3. **Spec_v21_MutationGovernance.md** — 7 ссылок "Phase 22" → исправлены на "Phase 34+"
4. **dev-cycle-map.md** — добавлен раздел §0 с таблицей приоритетов

### Сессия 2 — Устранение конфликта нумерации

1. `Spec_v33_GraphNavigation.md` → переименован в `Spec_v36_GraphNavigation.md` (Phase 36)
2. Создан `Spec_v35_TestHarnessElevation.md` из `Plan_v35.md`
3. Обнаружен конфликт: phase_current=30, фазы 19/20/21 не могут быть активированы (< current+1=31)

### Сессия 3 — Реструктуризация roadmap

1. **Spec_v19** → архивирован в `del/` (Phase 36 supersedes; Phase 19 нецелесообразен как временный этап)
2. **Spec_v20** → переименован в `Spec_v37_TemporalNavigation.md`, Baseline обновлён на Phase 36
3. **Spec_v21** → переименован в `Spec_v38_MutationGovernance.md`, Baseline обновлён на Phase 37
4. Линейный порядок: 31 → 32 → 35 → 36 → 37 → 38

---

## Ключевые инварианты (часто нужны)

| ID | Суть |
|----|------|
| I-SESSION-DECLARED-1 | LLM эмитит SessionDeclared в начале каждой сессии |
| I-SESSION-AUTO-1 | В конце DECOMPOSE LLM авто-запускает `sdd activate-phase N --executed-by llm` |
| I-HANDLER-PURE-1 | `handle()` возвращает только events, без subprocess |
| I-PHASE-SEQ-1 | `activate-phase` требует `phase_id == current + 1` |
| I-GRAPH-FS-ISOLATION-1 | GraphLoader не делает `open()` — только через `SpatialIndex.read_content()` |
| I-GRAPH-EMITS-1 | `emits` ребро требует все 4 условия (AST) |
| I-DDD-1 | Все TERM.links проверяются через typed_registry |
| I-OSML-3 | OSMLGuard НЕ блокирует `record-change` (anti-deadlock) |
| I-PLAN-IMMUTABLE-AFTER-ACTIVATE | Plan_vN.md не менять после activate-phase (или через `sdd amend-plan`) |
| I-SESSION-PHASE-NULL-1 | DRAFT_SPEC сессия использует `phase_id=None` |

---

## Phase 31 — что реализует (для PLAN сессии)

**Goal:** закрыть 4 архитектурных gap из dev-cycle-map.md §5

**BCs:**
- BC-31-1: `SpecApproved` event + `sdd approve-spec --phase N` (human-only gate)
- BC-31-2: `PlanAmended` event + `sdd amend-plan --phase N --reason "..."` + I-PLAN-IMMUTABLE-AFTER-ACTIVATE enforcement
- BC-31-3: `SessionDeclaredEvent.phase_id: Optional[int]` = None для DRAFT_SPEC + I-SESSION-PHASE-NULL-1
- BC-31-4: `_check_i_sdd_hash` в validate_invariants.py (реализует NORM-GATE-002)

---

## Phase 36 — что реализует (для PLAN сессии)

**Goal:** добавить рёбра в граф + единый DDD entrypoint `sdd resolve` (unified `$SDD_DATABASE_URL`)

**BCs (11 штук):**
- BC-36-0: `graph.spatial_nodes/edges/node_tags` схема (schema.py) + `open_graph_connection()`
- BC-36-1: `SpatialIndex` расширение: `iter_files/terms/invariants/tasks()`, `typed_registry()`, `read_content()`, `content_map`
- BC-36-2: `IndexBuilder` — INVARIANT-узлы переезжают с CLAUDE.md → `invariants.yaml`
- BC-36-3: `GraphLoader` — FS-free (loader.py); строит рёбра через SpatialIndex API
- BC-36-4: `GraphQuerier` — `get_node/search_nodes/neighbors()` через psycopg + WITH RECURSIVE CTE
- BC-36-4a: `open_graph_connection()` — unified connection helper; `SDD_DATABASE_URL`
- BC-36-5: TERM Integration — typed `means`-рёбра; I-DDD-1
- BC-36-6: `sdd resolve` — unified DDD entrypoint (nav_resolve.py)
- BC-36-7: `sdd nav-neighbors`, `sdd nav-invariant` (nav_neighbors.py, nav_invariant.py)
- BC-36-8: Tests (unit + integration, Postgres test DB via `$SDD_TEST_DSN`)
- BC-36-9: Backend registration — nav-rebuild `--backend postgres`
- BC-36-10: `invariants.yaml` + `sdd nav-export`

**Requires:** Phase 32 COMPLETE (`$SDD_DATABASE_URL`, схема `p_sdd`)

**Приоритеты рёбер:** emits(1.0) > guards(0.9) > implements(0.8) > depends_on(0.7) > means(0.6) > tested_by(0.5) > defined_in/verified_by(0.4) > imports(0.3)

---

## Ссылки на ключевые файлы

```
CLAUDE.md                                    — мастер-протокол (§WORKFLOW, §INV, §SEM, §ROLES)
.sdd/specs_draft/dev-cycle-map.md            — карта цикла + приоритеты фаз
.sdd/specs_draft/Spec_v31_GovernanceCommands.md  — NEXT: Phase 31
.sdd/specs_draft/Spec_v32_PostgresMigration.md   — после Phase 31
.sdd/specs/Spec_v35_TestHarnessElevation.md        — после Phase 33+34 (done)
.sdd/specs_draft/Spec_v36_GraphNavigation.md     — после Phase 32
.sdd/specs_draft/Spec_v37_TemporalNavigation.md  — после Phase 36
.sdd/specs_draft/Spec_v38_MutationGovernance.md  — после Phase 37
.sdd/specs_draft/del/Spec_v19_v1_GraphNavigation.md — архив (superseded by Phase 36)
.sdd/docs/sessions/                          — session files (plan-phase.md, decompose.md, etc.)
.sdd/docs/ref/tool-reference.md              — все sdd команды
.sdd/norms/norm_catalog.yaml                 — SENAR нормы
```

---

## Следующие шаги

**Рекомендуемое:** запустить Phase 31

```
PLAN Phase 31
```

Требует только `Spec_v31_GovernanceCommands.md` в `specs_draft/` (есть) и SDD lifecycle:
`DRAFT_SPEC → PLAN → DECOMPOSE → IMPLEMENT → VALIDATE → SUMMARIZE → CHECK_DOD`
