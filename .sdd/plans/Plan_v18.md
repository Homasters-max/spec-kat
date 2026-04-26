# Plan_v18 — Phase 18: Spatial Index (SI)

Status: DRAFT
Spec: specs/Spec_v18_SpatialIndex.md

---

## Milestones

### M0: Navigation Protocol + Glossary Config

```text
Spec:       §2 — Navigation Protocol (BC-18-NAV); §7 M0 Pre/Post
BCs:        BC-18-NAV
Invariants: I-NAV-1..9, I-CONTEXT-1, I-GIT-OPTIONAL, I-NAV-SESSION-1, I-SESSION-2
Depends:    Phase 17 COMPLETE, VR_Report_v17.json status STABLE
Risks:      I-NAV-1..9 добавлены в CLAUDE.md §INV — пропуск делает все навигационные
            инварианты декларациями без enforcement; glossary.yaml — единственный
            источник TERM-узлов (I-DDD-0), без него M2 не завершена
```

Deliverables:
- I-NAV-1..5, I-CONTEXT-1, I-GIT-OPTIONAL добавлены в CLAUDE.md §INV (раздел §INV)
- I-NAV-6..9, I-NAV-SESSION-1, I-SESSION-2 добавлены туда же
- `.sdd/config/glossary.yaml` создан; ≥8 TERM-записей с заполненными `links`
  (покрывают ключевые команды из §TOOLS и инварианты из §INV)

---

### M1: SpatialNode + SpatialEdge Dataclasses

```text
Spec:       §3 BC-18-0; §5 Types; §6 I-SUMMARY-1/2, I-SIGNATURE-1; §7 M1 Pre/Post
BCs:        BC-18-0
Invariants: I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1, I-DDD-1
Depends:    M0
Risks:      BUG-4 FIX: TermNode упразднён; смешение TermNode + SpatialNode ломает
            type-safety при десериализации и дублирует поля — нельзя допускать
            оба класса одновременно (I-DDD-1 регрессионный тест)
```

Deliverables:
- `src/sdd/spatial/__init__.py` (package marker)
- `src/sdd/spatial/nodes.py` — `SpatialNode` (frozen dataclass), `SpatialEdge`
  - `SpatialNode.kind` ∈ {FILE, COMMAND, GUARD, REDUCER, EVENT, TASK, INVARIANT, TERM}
  - TERM-поля `definition`, `aliases`, `links` с defaults ("", (), ())
  - `SpatialEdge` — schema contract для Phase 19, не runtime artifact
- `tests/unit/spatial/test_nodes.py` PASS
  - frozen; TERM поля; I-SUMMARY-1/2; I-SIGNATURE-1

---

### M2: SpatialIndex + IndexBuilder

```text
Spec:       §3 BC-18-1; §5 JSON schema; §6 I-SI-1/4, I-DDD-0/1, I-TERM-1/2,
            I-TERM-COVERAGE-1, I-SUMMARY-1/2, I-SIGNATURE-1; §7 M2 Pre/Post
BCs:        BC-18-1
Invariants: I-SI-1, I-SI-4, I-SI-5, I-DDD-0, I-DDD-1, I-TERM-1, I-TERM-2,
            I-TERM-COVERAGE-1, I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1
Depends:    M1
Risks:      I-SI-4 (stable node_id): неправильный source для node_id (напр. hash файла
            вместо пути/имени команды) → diff при каждом rebuild, невоспроизводимость;
            I-DDD-0: TERM-узлы только из glossary.yaml, не heuristic
```

Deliverables:
- `src/sdd/spatial/index.py` — `SpatialIndex`, `IndexBuilder`
  - `build()` строит 8 видов узлов (FILE, COMMAND, GUARD, REDUCER, EVENT, TASK,
    INVARIANT, TERM из glossary.yaml)
  - `load_index()`, `save_index()` через `paths.spatial_index_file()`
  - `SpatialIndex.meta` содержит `term_link_violations` и `term_coverage_gaps`
  - `git_tree_hash` из `git rev-parse HEAD`; None при недоступном git (I-GIT-OPTIONAL)
- `tests/unit/spatial/test_index.py` PASS
  - I-SI-1 (уникальность), I-SI-4 (стабильность), determinism
  - I-DDD-0 (TERM только из glossary.yaml), I-DDD-1 (links = source of means)
  - I-TERM-COVERAGE-1 warning; meta violations; I-SUMMARY-1/2; I-SIGNATURE-1

---

### M3: Staleness

```text
Spec:       §3 BC-18-2; §6 I-GIT-OPTIONAL, I-SI-5; §7 M3 Pre/Post
BCs:        BC-18-2
Invariants: I-GIT-OPTIONAL, I-SI-5
Depends:    M2
Risks:      Staleness через git ls-files -s (O(1) fast path) — использование
            git hash-object вместо ls-files замедлит все rebuild на больших репо;
            I-GIT-OPTIONAL: `is_stale()=False` при недоступном git не должен
            блокировать работу в CI без git
```

Deliverables:
- `src/sdd/spatial/staleness.py` — `current_git_hash()`, `is_stale()`,
  `staleness_report()`
  - fast path: `git ls-files -s <path>` (blob SHA из .git/index)
  - fallback: `git hash-object <path>` для untracked
  - graceful: None при отсутствии git
- `tests/unit/spatial/test_staleness.py` PASS
  - mock subprocess; success/fail/None; I-GIT-OPTIONAL; I-SI-5 mismatch

---

### M4: Navigator + NavigationSession + NavigationIntent

```text
Spec:       §2 NavigationSession; §3 BC-18-3, NavigationIntent, resolve_action;
            §6 I-NAV-1..9, I-SI-2/3, I-FUZZY-1, I-SEARCH-2, I-NAV-SESSION-1,
            I-SESSION-2; §7 M4 Pre/Post
BCs:        BC-18-3
Invariants: I-NAV-1..9, I-SI-2, I-SI-3, I-FUZZY-1, I-SEARCH-2,
            I-NAV-SESSION-1, I-SESSION-2
Depends:    M2 (SpatialIndex), M3 (staleness) — параллельно с M3 допустимо
Risks:      BUG-1 FIX: NavigationSession MUST персистировать через nav_session.json;
            без этого I-NAV-1..6 — декларации, не enforcement.
            BUG-2 FIX: нет типа "modify" в NavigationIntent; 5 типов строго.
            BUG-3 FIX: resolve_action() возвращает DenialTrace с конкретным violated.
            I-NAV-8 REFORM: _FULL_CONSTRAINTS как data registry, не if-chain;
            изменение правила = изменение строки в таблице.
            I-SESSION-2: fcntl.flock — race condition без lock → corruption session file
```

Deliverables:
- `src/sdd/spatial/navigator.py` — `Navigator`, `NavigationSession`,
  `NavigationIntent`, `DenialTrace`, `AllowedOperations`, `resolve_action()`
  - `INTENT_CEILING` dict + `_FULL_CONSTRAINTS` registry (no if-chain)
  - 4 режима resolve: POINTER, SUMMARY, SIGNATURE, FULL
  - `not_found_response()` всегда `must_not_guess: true`, `did_you_mean` всегда присутствует
  - fuzzy match по search key (basename/id suffix/aliases), threshold ≤ 2 (I-FUZZY-1)
  - детерминированная сортировка: (distance, kind_priority, node_id lex) (I-SI-2)
  - `load_session()`, `save_session()`, `clear_session()` с `fcntl.flock`
    на `.sdd/state/nav_session.lock` (I-SESSION-2)
  - lock timeout 5s → `nav_invariant_violation` reason `session_lock_timeout`
- `tests/unit/spatial/test_navigator.py` PASS
  - все I-NAV-*, resolve_action DenialTrace (BUG-3), INTENT_CEILING 5 types (BUG-2)
  - I-SEARCH-2 pipeline; I-FUZZY-1 search_key; concurrency mock (I-SESSION-2)

---

### M5: CLI Commands + Paths + CLI Wiring

```text
Spec:       §3 BC-18-4, BC-18-6; §4 Domain Events; §7 M5 Pre/Post
BCs:        BC-18-4, BC-18-6
Invariants: I-NAV-SESSION-1, I-SESSION-2, I-SI-3, I-SI-4, I-TERM-COVERAGE-1, I-TERM-2
Depends:    M2, M3, M4
Risks:      nav-get MUST load/save session per call (I-NAV-SESSION-1) — пропуск делает
            сессионные инварианты неработающими; stale_warning MUST добавляться до
            return ответа (WEAK-2); Phase 18 не эмитирует domain events в EventLog
            (§4) — любая попытка записи в EventStore = ошибка реализации
```

Deliverables:
- `src/sdd/spatial/commands/__init__.py`
- `src/sdd/spatial/commands/nav_get.py` — `sdd nav-get <id> [--mode] [--intent]`
  - staleness check → `stale_warning: true` (WEAK-2)
  - session load/save (I-NAV-SESSION-1); `git_tree_hash` в каждом ответе
- `src/sdd/spatial/commands/nav_search.py` — `sdd nav-search <query> [--kind] [--limit]`
  - namespace priority: TERM > COMMAND > TASK > FILE
- `src/sdd/spatial/commands/nav_rebuild.py` — `sdd nav-rebuild [--dry-run]`
  - dry-run не пишет файл; I-SI-4 diff при rename → exit 1;
  - warnings для I-TERM-COVERAGE-1 и I-TERM-2
- `src/sdd/spatial/commands/nav_session.py` — `sdd nav-session {next|clear|show}`
  - next: инкремент step_id; clear: удаление файла; show: текущий state
- `src/sdd/infra/paths.py` — `spatial_index_file()`, `nav_session_file()`,
  `nav_session_lock_file()`
- `src/sdd/cli.py` — 4 команды зарегистрированы в REGISTRY
- `tests/unit/commands/test_nav_get.py` PASS
- `tests/unit/commands/test_nav_search.py` PASS
- `tests/unit/commands/test_nav_rebuild.py` PASS
- `tests/unit/commands/test_nav_session.py` PASS
  - concurrency safety mock; lock timeout → violation (I-SESSION-2)

---

### M6: Integration

```text
Spec:       §3 BC-18-5 integration; §9 Verification; §7 M6 Pre/Post
BCs:        BC-18-5 (integration)
Invariants: I-SI-1, I-SI-4, I-DDD-0
Depends:    M5
Risks:      Регрессионный тест на отсутствие класса TermNode в codebase (BUG-4);
            nodes>100 подтверждает что IndexBuilder корректно обходит все модули;
            terms≥8 подтверждает glossary.yaml корректно загружается;
            два последовательных nav-rebuild должны давать идентичные node_ids (I-SI-4)
```

Deliverables:
- `tests/integration/test_nav_rebuild_integration.py` PASS
  - `sdd nav-rebuild` exit 0 на реальном project root
  - `nodes_written > 100`, `terms_written ≥ 8`
  - I-SI-1 дублей нет; I-SI-4 два rebuild → идентичные node_ids
  - `git_tree_hash` присутствует
  - no TermNode class in codebase (BUG-4 regression guard)

---

## Risk Notes

- R-1: **BUG-4 (TermNode)** — класс TermNode должен быть полностью упразднён;
  `SpatialNode(kind="TERM")` — единственная модель. Регрессионный integration-тест
  проверяет отсутствие TermNode в codebase.

- R-2: **I-NAV-SESSION-1 + I-SESSION-2 (session file)** — CLI stateless, без
  persistence I-NAV-1..9 не работают как enforcement. fcntl.flock обязателен;
  Windows out of scope для Phase 18 (Linux/macOS CI).

- R-3: **I-SI-4 (stable node_id)** — источник node_id должен быть стабильным
  идентификатором артефакта (путь, имя команды, имя класса), а не хешем содержимого.
  Нарушение → nav-rebuild diff при каждом запуске.

- R-4: **I-NAV-8 REFORM (_FULL_CONSTRAINTS as data)** — все проверки FULL-доступа
  только через `_FULL_CONSTRAINTS` registry; никаких inline if-chain для FULL.
  Нарушение = нарушение I-NAV-8, аудируемость теряется.

- R-5: **I-GIT-OPTIONAL** — система должна работать без git (degraded mode) для
  CI/sandbox-окружений. `is_stale()=False` и `git_tree_hash=None` не должны
  вызывать ошибки нигде по стеку.

- R-6: **Phase 18 не эмитирует domain events** (§4) — `nav-rebuild` — read-only
  для SDD-ядра. Любой вызов EventStore в коде Phase 18 = ошибка реализации.
