# Spec_v18 — Phase 18: Spatial Index (SI)

Status: Draft
Baseline: Spec_v17_ValidationRuntime.md

---

## 0. Goal

Phase 17 завершила Validation Runtime — система верифицирована динамически.
Ядро стабильно, но агент по-прежнему строит контекст через плоские слои файлов:
`build_context.py` загружает 0–8 файлов вслепую, вызывая три системных патологии:
**раздутый контекст**, **галлюцинации о структуре** (нет карты — придумывают пути),
**медленный поиск** (N tool calls перед работой).

Phase 18 вводит **Spatial Index (SI)** — детерминированную, воспроизводимую карту системы:

```
System := ⟨Kernel, ValidationRuntime, SpatialIndex⟩
SI отвечает на вопрос: "что существует и как это называется?"
```

Каждый файл, команда, событие, задача, инвариант → узел с устойчивым `node_id`.
`sdd nav-get <id>` → детерминированный JSON без filesystem I/O на cache hit.

Критическое дополнение к исходному плану: **TERM-узлы** (DDD-слой) и **Navigation Protocol**
(зафиксированный порядок действий агента) вводятся **с самой первой фазы**, поскольку они
являются архитектурным фундаментом, а не надстройкой над готовым API.

### Архитектурный принцип: SI Layer

```
SI Layer := Navigation + Semantics + Protocol

  Navigation  — карта: что существует и где
  Semantics   — смысл: TERM/DDD-язык поверх структуры
  Protocol    — дисциплина: NavigationSession как runtime enforcement

Деградация при отсутствии любого компонента:
  без Navigation  → нет карты → агент угадывает пути
  без Semantics   → нет понимания → агент думает файлами, не концептами
  без Protocol    → нет дисциплины → агент дёргает FULL хаотично
```

Этот принцип — уровень системы, не просто часть Phase 18.
Каждая последующая фаза (19, 20) расширяет один из трёх компонентов, не заменяет.

**Агент является stateful.** `NavigationSession` — ядро поведения агента в сессии.
Это осознанное архитектурное решение: stateless-агент требовал бы более жёсткого протокола
без возможности enforcement; stateful с session-объектом позволяет проверять инварианты
I-NAV-1..5 в runtime, а не только как декларации в CLAUDE.md.

---

## 1. Scope

### In-Scope

- **BC-18-NAV: Navigation Protocol** — инварианты I-NAV-1..5, I-GIT-OPTIONAL в CLAUDE.md §INV; `NavigationSession` в navigator.py
- **BC-18-0: SpatialNode + TERM** — dataclasses `SpatialNode`, `SpatialEdge` (nodes.py); TERM = `SpatialNode(kind="TERM")` (BUG-4: TermNode упразднён)
- **BC-18-1: SpatialIndex** — `build_index()`, `load_index()`, `save_index()` (index.py); I-SI-4 (stable node_id)
- **BC-18-2: Staleness** — `current_git_hash()`, `is_stale()` через `git ls-files -s` (staleness.py)
- **BC-18-3: Navigator** — `resolve()` (4 режима), `not_found_response()` с fuzzy match (navigator.py)
- **BC-18-4: CLI commands** — `sdd nav-get`, `sdd nav-search`, `sdd nav-rebuild`, `sdd nav-session` (nav_get.py, nav_search.py, nav_rebuild.py, nav_session.py)
- **BC-18-5: Tests** — unit + integration (100% coverage BC-18-0..4)
- **BC-18-6: Paths + CLI wiring** — `infra/paths.py` + `cli.py` регистрация (4 команды)

### Out of Scope

- DuckDB-бэкенд и рёбра графа — Phase 19
- Временны́е запросы (nav-changed-since) — Phase 20
- `sdd resolve` unified entrypoint — Phase 19
- ML-ранжирование, shortest path, embedding search — никогда

---

## 2. Navigation Protocol (BC-18-NAV)

### Зачем фиксировать поведение агента

API без протокола — это инструмент без инструкции. Без явного порядка шагов агент будет:
дёргать nav-get хаотично, делать лишние FULL-загрузки, снова читать файлы напрямую.
Navigation Protocol — это не рекомендация, это **зафиксированные инварианты**.

### Canonical Agent Reasoning Sequence

```
STEP 1  Resolve concept         sdd nav-get <id> --mode SUMMARY
STEP 2  Expand neighbors        sdd nav-neighbors <id> --mode POINTER
STEP 3  Select target nodes     decide which neighbors need detail
STEP 4  Load SIGNATURE          sdd nav-get <id> --mode SIGNATURE  (для выбранных)
STEP 5  Load FULL               sdd nav-get <id> --mode FULL       (только если пишем код)
```

Инварианты (добавляются в CLAUDE.md §INV):

| ID | Statement |
|----|-----------|
| I-NAV-1 | Agent MUST NOT call `--mode FULL` before successful `--mode SUMMARY` or `--mode SIGNATURE` for that node |
| I-NAV-2 | Agent MUST resolve `node_id` via `sdd nav-get` or `sdd nav-search` before any direct filesystem access to the corresponding file |
| I-NAV-3 | Max 1 `--mode FULL` load per reasoning step (default); exception requires explicit justification in agent output |
| I-NAV-4 | Agent SHOULD resolve natural language queries via `sdd nav-search --kind TERM` before direct node lookup |
| I-NAV-5 | `--mode FULL` MUST be used only if the agent produces or modifies code in this reasoning step |
| I-NAV-6 | FULL limit applies per `step_id`; `step_id` MUST be incremented explicitly between reasoning steps |
| I-NAV-7 | `--mode FULL` MUST include explicit intent flag: `{"intent": "code_write" \| "code_modify"}` |
| I-NAV-8 | `NavigationIntent` has higher priority than `NavigationSession` constraints; session can only restrict, never expand beyond intent ceiling |
| I-NAV-9 | A "reasoning step" is exactly one LLM tool-call sequence terminated by either an LLM response to user or explicit `session.next_step()` call |

I-NAV-2 не запрещает файловый доступ — он требует сначала убедиться через индекс, что файл существует и идентифицирован корректно. Anti-hallucination через структуру.

I-NAV-4 резко снижает вероятность ложных node_id и хаотичного поиска: агент сначала ищет смысл,
потом переходит к структуре. TERM — первичная точка входа для естественного языка.

I-NAV-5 дополняет I-NAV-3: не только `max 1 FULL`, но и только при code production.
Предотвращает загрузку `FULL` "на всякий случай".

I-NAV-8 устраняет два конкурирующих control layer: `NavigationIntent` задаёт потолок
допустимых операций; `NavigationSession` может только сузить (проверить историю и счётчики),
но не расширить. Единственная точка решения — `resolve_action()`.

I-NAV-9 формализует границу шага: без этого разные части системы трактуют "step"
по-разному. Граница = один response агента пользователю или явный вызов `next_step()`.

### Default Entrypoint (natural language → TERM)

```
if input is natural language concept:
    STEP 0  sdd nav-search <query> --kind TERM    ← I-NAV-4
    STEP 1  sdd nav-get TERM:<id> --mode SUMMARY  ← получаем definition + links
    → переход к связанным nodes через links (COMMAND, EVENT, INVARIANT)
    → далее Canonical Sequence (STEP 1..5)
```

### NavigationSession (runtime enforcement)

`NavigationSession` — in-memory объект сессии агента. Не персистируется в EventLog.
Создаётся при старте reasoning-шага, уничтожается по его завершении.

```python
@dataclass
class NavigationSession:
    step_id:               int                    # I-NAV-6: явно инкрементируется агентом
    resolved_nodes:        set[str]               # node_id, для которых выполнен nav-get
    loaded_modes:          dict[str, str]          # node_id → последний загруженный mode
    full_load_count_per_step: dict[int, int]      # step_id → кол-во FULL в этом шаге (I-NAV-6)
    term_searched:         bool                   # True если выполнен nav-search --kind TERM (I-NAV-4)
    intent:                "NavigationIntent | None" = None  # текущий intent шага

    def can_load_full(self, node_id: str) -> bool:
        """I-NAV-1: SUMMARY/SIGNATURE должен быть loaded до FULL."""
        prior = self.loaded_modes.get(node_id)
        return prior in ("SUMMARY", "SIGNATURE")

    def can_load_full_step(self, intent: "NavigationIntent | None" = None) -> bool:
        """I-NAV-3/5/6: max 1 FULL per step_id; только для code_write/code_modify."""
        step_count = self.full_load_count_per_step.get(self.step_id, 0)
        if step_count >= 1:
            return False  # I-NAV-3 / I-NAV-6
        if intent is None or intent.type not in ("code_write", "code_modify"):
            return False  # I-NAV-5
        return True

    def next_step(self) -> None:
        """I-NAV-6: агент ОБЯЗАН вызвать next_step() между reasoning steps."""
        self.step_id += 1
        self.term_searched = False
        self.intent = None

    def record_load(self, node_id: str, mode: str) -> None:
        self.resolved_nodes.add(node_id)
        self.loaded_modes[node_id] = mode
        if mode == "FULL":
            self.full_load_count_per_step[self.step_id] = \
                self.full_load_count_per_step.get(self.step_id, 0) + 1
```

**BUG-1 FIX: NavigationSession persistence**

CLI = stateless процессы. Без персистенции `NavigationSession` все I-NAV-1..6 — декларации,
не runtime enforcement. Решение: session file в `.sdd/state/nav_session.json`.

**Формат `.sdd/state/nav_session.json`:**
```json
{
  "session_id": "uuid-v4",
  "step_id": 3,
  "steps": {
    "3": {
      "full_load_count": 1,
      "resolved_nodes": ["COMMAND:complete"],
      "loaded_modes": {"COMMAND:complete": "SIGNATURE"}
    }
  },
  "intent": "code_modify",
  "term_searched": true,
  "updated_at": "2026-04-24T12:05:00Z"
}
```

**API (добавляется в `navigator.py`):**
```python
def load_session(sdd_root: str) -> NavigationSession | None:
    """Reads nav_session.json atomically. Returns None if file absent or invalid."""

def save_session(session: NavigationSession, sdd_root: str) -> None:
    """Atomic write: tmp file → os.replace (I-NAV-SESSION-1)."""

def clear_session(sdd_root: str) -> None:
    """Removes nav_session.json. Called by sdd nav-session clear."""
```

**Lifecycle в CLI commands:**
```
nav-get:
  1. load_session() → session (or None)
  2. resolve_action(intent, session, node_id, mode)
  3. record_load(node_id, mode)
  4. save_session()    ← atomic

next_step (sdd nav-session next):
  1. load_session()
  2. session.next_step()
  3. save_session()

sdd nav-session clear:
  clear_session()
```

**I-NAV-SESSION-1:** All `NavigationSession` state MUST be persisted in `.sdd/state/nav_session.json`.
CLI MUST load session at start and atomically save at end of each command.
Missing file = fresh session (not error). Invalid JSON = log warning + fresh session (corruption recovery).

**I-SESSION-2: Concurrency Safety**

`nav_session.json` — shared mutable state. Параллельные CLI-вызовы (несколько агентов, IDE integration)
создают race condition: last-write-wins corruption и рассинхронизацию `step_id`.

Решение: exclusive file lock на время read-modify-write операции.

```python
import fcntl, contextlib

@contextlib.contextmanager
def _session_lock(lock_path: str):
    """Exclusive advisory lock for nav_session.json. Cross-process safe on Linux/macOS."""
    with open(lock_path, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)  # blocks until lock acquired
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)

def load_session(sdd_root: str) -> NavigationSession | None:
    lock_path = nav_session_lock_file(sdd_root)
    with _session_lock(lock_path):
        # read nav_session.json
        ...

def save_session(session: NavigationSession, sdd_root: str) -> None:
    lock_path = nav_session_lock_file(sdd_root)
    with _session_lock(lock_path):
        # atomic: write to tmp → os.replace
        ...
```

Lock file path: `.sdd/state/nav_session.lock` (via `paths.nav_session_lock_file()`).

**I-SESSION-2:** `NavigationSession` read-modify-write MUST be protected by an exclusive advisory
lock (`.sdd/state/nav_session.lock`). Concurrent CLI processes MUST block, not race.
Lock acquisition timeout = 5s; exceeded → `nav_invariant_violation` с reason `"session_lock_timeout"`.

Windows note: `fcntl` недоступен на Windows. Phase 18 target = Linux/macOS (CI/dev environment).
Если потребуется Windows — отдельный I-SESSION-2-WIN с `msvcrt.locking` (Phase 19+).

`NavigationSession` живёт в `Navigator` как optional контекст:
```python
class Navigator:
    session: NavigationSession | None = None  # None = enforcement отключён (legacy / тесты)
```

Когда `session` задан (всегда в CLI после BUG-1 fix), `resolve()` проверяет инварианты
и возвращает ошибку вместо данных при нарушении:
```json
{"status": "nav_invariant_violation", "invariant": "I-NAV-1",
 "denial": {"mode": "FULL", "violated": ["I-NAV-1"], "reason": "summary_required"},
 "node_id": "FILE:src/sdd/cli.py", "message": "SUMMARY must precede FULL"}
```

---

## 3. Architecture / BCs

### BC-18-NAV: Navigation Protocol + NavigationSession + NavigationIntent

Инварианты I-NAV-1..7, I-GIT-OPTIONAL добавляются в CLAUDE.md §INV.
`NavigationSession` и `NavigationIntent` реализуются внутри `navigator.py` (не отдельный модуль).

### BC-18-0: SpatialNode + TERM + SpatialEdge

```
src/sdd/spatial/
  __init__.py      # package marker
  nodes.py         # SpatialNode, SpatialEdge
```

**BUG-4 FIX:** `TermNode` упразднён — его поля слиты в `SpatialNode`. Единая модель: все узлы
одного типа, kind="TERM" заполняет `definition` и `aliases`. Это устраняет type-safety дыру
при десериализации и дублирование полей.

```python
@dataclass(frozen=True)
class SpatialNode:
    node_id:    str               # "COMMAND:complete", "FILE:src/sdd/cli.py"
    kind:       str               # FILE|COMMAND|GUARD|REDUCER|EVENT|TASK|INVARIANT|TERM
    label:      str
    path:       str | None        # None для виртуальных узлов (INVARIANT, TERM)
    summary:    str               # ~80 токенов (см. правило ниже)
    signature:  str               # ~300 токенов
    meta:       dict
    git_hash:   str | None        # blob SHA из git ls-files -s; None для TERM/INVARIANT
    indexed_at: str               # ISO-8601

    # TERM-специфичные поля (только kind="TERM"; для остальных = defaults)
    definition: str = ""          # краткое DDD-определение (~100 токенов)
    aliases:    tuple[str, ...] = ()  # ["phase activation", "activate phase"]
    links:      tuple[str, ...] = ()  # node_id ссылки → means-рёбра в Phase 19

    # Правило генерации summary (соблюдается IndexBuilder, не LLM):
    #   1. module-level docstring (первая строка triple-quoted string)
    #   2. первый docstring class/function
    #   3. первый непустой комментарий (#)
    #   4. fallback: "{KIND}:{basename}" — никогда пустая строка (I-SUMMARY-2)
    # summary MUST be 1 line (I-SUMMARY-1). Нарушение → IndexBuilder exit 1.
    # signature = только interface (def/class/type аннотации); никакой prose (I-SIGNATURE-1)

@dataclass(frozen=True)
class SpatialEdge:
    """Schema contract for Phase 19 (DuckDB graph backend). Not persisted in Phase 18.
    Defined here to fix the cross-phase interface before Phase 19 implementation."""
    edge_id:  str        # sha256(src+":"+kind+":"+dst)[:16] — детерминированный
    src:      str        # node_id источника
    dst:      str        # node_id назначения
    kind:     str        # imports|emits|defined_in|depends_on|tested_by|verified_by|means
    meta:     dict
```

`SpatialNode` с `kind="TERM"` — полноправный узел индекса.
Включается в `SpatialIndex.nodes` наравне с остальными.
Edge `kind="means"` — связь TERM → COMMAND/EVENT/TASK/INVARIANT; реализуется в Phase 19.

**`SpatialNode.links` (для TERM-узлов) = первичный источник рёбер типа `means`.**
В Phase 19 при построении графа в DuckDB `links` используется напрямую без повторного вывода связей.
Это зафиксированный контракт: TERM.links → edges; никакой инференции поверх.

**Источник TERM-узлов:** `IndexBuilder` читает `CLAUDE.md §TOOLS` для команд и
`.sdd/config/project_profile.yaml` для доменных концептов. TERM-узлы задаются статически
в конфиг-файле `.sdd/config/glossary.yaml` (создаётся в Phase 18):

```yaml
# .sdd/config/glossary.yaml
terms:
  - id: "activate_phase"
    label: "Activate Phase"
    definition: "Human-only gate that transitions a PLANNED phase to ACTIVE state."
    aliases: ["phase activation", "activate phase", "sdd activate-phase"]
    links: ["COMMAND:activate-phase", "EVENT:PhaseActivated", "INVARIANT:NORM-ACTOR-001"]

  - id: "complete_task"
    label: "Complete Task"
    definition: "Mark a task T-NNN as DONE after implementation. Emits TaskImplementedEvent."
    aliases: ["task completion", "sdd complete", "complete T-NNN"]
    links: ["COMMAND:complete", "EVENT:TaskImplementedEvent"]
```

### BC-18-1: SpatialIndex с I-SI-4

```
src/sdd/spatial/
  index.py         # SpatialIndex, IndexBuilder, build_index(), load_index(), save_index()
```

**I-SI-4 (stable node_id):** `node_id` выводится из **стабильного идентификатора артефакта**,
не из содержимого файла и не из позиции строк.

| Kind | node_id format | Stable source |
|------|---------------|---------------|
| FILE | `FILE:src/sdd/cli.py` | относительный путь от project root |
| COMMAND | `COMMAND:complete` | имя команды в REGISTRY (ключ) |
| GUARD | `GUARD:scope` | имя модуля в `src/sdd/guards/` |
| REDUCER | `REDUCER:main` | всегда один; "main" — константа |
| EVENT | `EVENT:TaskImplementedEvent` | имя класса (стабильно, BC-0) |
| TASK | `TASK:T-1801` | ID задачи из TaskSet |
| INVARIANT | `INVARIANT:I-SI-1` | ID инварианта из CLAUDE.md |
| TERM | `TERM:activate_phase` | id из glossary.yaml |

**I-SI-4:** `node_id` MUST remain identical across consecutive `nav-rebuild` runs
if the artifact has not been renamed. Violation → `nav-rebuild` exit 1 с diff.

```python
class SpatialIndex:
    nodes:         dict[str, SpatialNode]  # node_id → node
    built_at:      str                     # ISO-8601
    git_tree_hash: str | None              # git rev-parse HEAD; None если git недоступен
    version:       int = 1
    meta:          dict = field(default_factory=dict)
    # meta содержит диагностические данные от IndexBuilder:
    # {
    #   "term_link_violations": [            # I-TERM-2: unresolved TERM.links
    #     {"term": "TERM:activate_phase",
    #      "missing": ["COMMAND:activate-phas"],   # опечатка → warning
    #      "severity": "warning"}
    #   ],
    #   "term_coverage_gaps": [              # I-TERM-COVERAGE-1: COMMAND без TERM
    #     "COMMAND:show-path"
    #   ]
    # }

    # I-GIT-OPTIONAL: система MUST работать без git (degraded mode).
    # git_tree_hash = None → is_stale() возвращает False → rebuild не блокирует.
    # CI / sandbox без git должны работать без ошибок.

class IndexBuilder:
    def build(self, project_root: str) -> SpatialIndex:
        """7 видов узлов + TERM из glossary.yaml"""

    def _build_file_nodes(self) -> list[SpatialNode]: ...
    def _build_command_nodes(self) -> list[SpatialNode]: ...
    def _build_guard_nodes(self) -> list[SpatialNode]: ...
    def _build_reducer_nodes(self) -> list[SpatialNode]: ...
    def _build_event_nodes(self) -> list[SpatialNode]: ...
    def _build_task_nodes(self) -> list[SpatialNode]: ...
    def _build_invariant_nodes(self) -> list[SpatialNode]: ...
    def _build_term_nodes(self) -> list[SpatialNode]: ...  # kind="TERM"; Phase 18 new
```

Путь к индексу: `.sdd/state/spatial_index.json` (через `paths.spatial_index_file()`).

### BC-18-2: Staleness

```
src/sdd/spatial/
  staleness.py     # current_git_hash(), is_stale(), staleness_report()
```

```python
def current_git_hash(path: str, project_root: str) -> str | None:
    # Fast: git ls-files -s <path> → blob SHA из .git/index (O(1))
    # Fallback: git hash-object <path> для untracked файлов
    # Returns None если не git repo или файл не существует

def is_stale(index: SpatialIndex, project_root: str) -> bool:
    # Сравнивает index.git_tree_hash с git rev-parse HEAD
    # Если расходятся → stale (нужен rebuild)
    # Если git недоступен → False (graceful: не блокировать работу)

def staleness_report(index: SpatialIndex, project_root: str) -> dict:
    # {"stale": bool, "index_tree": str|None, "head_tree": str|None, "reason": str}
```

### BC-18-3: Navigator

```
src/sdd/spatial/
  navigator.py     # Navigator, resolve(), not_found_response()
```

**Resolve modes (4 уровня):**

```
POINTER   → {node_id, kind, label, path}                          # ~15 токенов
SUMMARY   → POINTER + {summary, git_hash, indexed_at}             # ~80 токенов
SIGNATURE → SUMMARY + {signature}                                  # ~300 токенов
FULL      → SIGNATURE + {meta, definition (TERM), full_text}      # unbounded
```

`full_text` — содержимое файла (только для FILE-узлов; I-SI-3: читается только при FULL).
`definition` — поле `SpatialNode` для TERM-узлов (kind="TERM"), включается в FULL.

**WEAK-2 FIX: Staleness check в nav-get.**
`nav-get` проверяет `is_stale()` перед ответом. Если stale — добавляет `stale_warning: true`
в корень ответа (для любого mode кроме FULL, где и так даётся актуальный `full_text`).
Это обеспечивает UC-18-3 без блокировки: агент видит предупреждение и может запустить rebuild.

```python
# В nav_get.main() — после load_index(), до resolve():
if is_stale(index, project_root):
    response["stale_warning"] = True
    response["stale_reason"] = "git HEAD changed since last rebuild"
```

**not_found_response (anti-hallucination):**
```json
{
  "status": "not_found",
  "must_not_guess": true,
  "query": "<id>",
  "did_you_mean": ["COMMAND:complete", "COMMAND:check-scope"]
}
```

**WEAK-6 FIX: Нормализованный fuzzy match (I-FUZZY-1).**
Применять Levenshtein не ко всему `node_id`, а к **search key** по виду узла:

| Kind | Search key |
|------|-----------|
| `FILE:*` | basename без расширения: `FILE:src/sdd/cli.py` → `cli` |
| `COMMAND:*` | часть после `:`; `COMMAND:complete` → `complete` |
| `TERM:*` | часть после `:` + все aliases |
| Остальные | часть после `:` |

Threshold: distance ≤ 2 по search key. Финальный результат — полный `node_id`.
Если совпадение по alias у TERM-узла, включить TERM первым (TERM priority).

`did_you_mean` — всегда присутствует; может быть пустым списком, но никогда не отсутствует.

### NavigationIntent

**BUG-2 FIX + I-NAV-8 REFORM: Intent → Mode Policy Table (единственный источник истины)**

`"modify"` убран; два code-intent'а (`code_write` / `code_modify`) для Phase 21 granularity.

**Ключевое архитектурное решение:** `INTENT_CEILING` — data table, не логика.
`resolve_action` = pure policy lookup + ordered constraint checks list (никаких if-chain для
FULL-специфичных решений). I-NAV-8 теперь означает: одна таблица → одна точка изменения правил.

```python
from typing import Literal
from typing import Callable

# I-NAV-8 REFORM: ceiling as data, not code
MODE_ORDER: list[str] = ["POINTER", "SUMMARY", "SIGNATURE", "FULL"]

INTENT_CEILING: dict[str, str] = {
    # intent type  → max allowed mode (ceiling)
    "explore":     "SUMMARY",    # структурный обзор; FULL избыточен
    "locate":      "SUMMARY",    # найти узел; POINTER достаточен для подтверждения
    "analyze":     "SIGNATURE",  # изучить интерфейс; код не нужен
    "code_write":  "FULL",       # новый файл; полный доступ
    "code_modify": "FULL",       # правка существующего; полный доступ
}

def _modes_up_to(ceiling: str) -> frozenset[str]:
    """All modes from POINTER up to (inclusive) ceiling."""
    return frozenset(MODE_ORDER[:MODE_ORDER.index(ceiling) + 1])

@dataclass(frozen=True)
class NavigationIntent:
    type: Literal["explore", "locate", "analyze", "code_write", "code_modify"]

    def ceiling(self) -> str:
        """I-NAV-8: single source of truth for max allowed mode."""
        return INTENT_CEILING[self.type]

    def allowed_modes(self) -> frozenset[str]:
        return _modes_up_to(self.ceiling())
```

**Таблица допустимых режимов (из INTENT_CEILING):**

| Intent | POINTER | SUMMARY | SIGNATURE | FULL | Ceiling | Семантика |
|--------|---------|---------|-----------|------|---------|-----------|
| explore | ✔ | ✔ | ✗ | ✗ | SUMMARY | структурный обзор |
| locate | ✔ | ✔ | ✗ | ✗ | SUMMARY | найти и подтвердить узел |
| analyze | ✔ | ✔ | ✔ | ✗ | SIGNATURE | изучить интерфейс |
| code_write | ✔ | ✔ | ✔ | ✔ | FULL | написать новый код |
| code_modify | ✔ | ✔ | ✔ | ✔ | FULL | изменить существующий код |

`NavigationIntent` задаётся агентом на каждый step перед началом навигации.
При нарушении ceiling → `nav_invariant_violation` I-NAV-8 (с intent) или I-NAV-7 (без intent).

I-NAV-7: запрос на FULL MUST содержать явный `intent` в теле вызова:
```json
{"node_id": "FILE:src/sdd/cli.py", "mode": "FULL", "intent": "code_write"}
```

### resolve_action — Unified Navigation Decision Function

Единственная точка принятия решения о допустимых операциях (I-NAV-8).
`Navigator.resolve()` вызывает `resolve_action` — никаких inline проверок в других местах.

**BUG-3 FIX + I-NAV-8 REFORM:** `resolve_action` = **pure policy lookup + ordered constraint registry**.
Никакого if-chain для FULL-специфичных решений — вся логика как data (таблицы), не код.
Это делает правила аудируемыми: изменить правило = изменить строку в таблице, не код.

```python
@dataclass(frozen=True)
class DenialTrace:
    """Structured denial — identifies specific violated invariant for Phase 19 reasoning."""
    mode:     str         # запрошенный mode, который был запрещён
    violated: list[str]   # конкретные нарушенные: ["I-NAV-1"] или ["I-NAV-3", "I-NAV-6"]
    reason:   str         # machine-readable: "summary_required" | "step_limit_exceeded" |
                          #   "code_intent_required" | "intent_ceiling_exceeded" | "session_lock_timeout"

@dataclass(frozen=True)
class AllowedOperations:
    modes:  frozenset[str]       # подмножество {POINTER, SUMMARY, SIGNATURE, FULL}
    denial: DenialTrace | None   # None если режим разрешён

# Session constraint registry for FULL mode (I-NAV-8 REFORM: constraints as data, not if-chain)
# Each entry: (mode_guard, predicate, violated_invariants, reason)
# Evaluated in order; first matching predicate → denial (short-circuit)
_FULL_CONSTRAINTS: list[tuple[
    str,                         # mode this constraint applies to
    Callable[[NavigationSession, str, NavigationIntent | None], bool],  # True = denied
    list[str],                   # violated invariants
    str,                         # reason code
]] = [
    (
        "FULL",
        lambda s, n, i: not s.can_load_full(n),
        ["I-NAV-1"],
        "summary_required",
    ),
    (
        "FULL",
        lambda s, n, i: s.full_load_count_per_step.get(s.step_id, 0) >= 1,
        ["I-NAV-3", "I-NAV-6"],
        "step_limit_exceeded",
    ),
    (
        "FULL",
        lambda s, n, i: i is None or i.type not in ("code_write", "code_modify"),
        ["I-NAV-5"],
        "code_intent_required",
    ),
]

def resolve_action(
    intent:         NavigationIntent | None,
    session:        NavigationSession,
    node_id:        str,
    requested_mode: str,
) -> AllowedOperations:
    """I-NAV-8: intent ceiling is single source of truth (INTENT_CEILING table).
    Session constraints applied via _FULL_CONSTRAINTS registry (no if-chain).
    I-NAV-9: called once per tool call within current step_id."""

    # Step 1: intent ceiling — pure table lookup (I-NAV-8)
    ceiling_modes = intent.allowed_modes() if intent else _modes_up_to("SUMMARY")

    if requested_mode not in ceiling_modes:
        return AllowedOperations(
            modes=ceiling_modes,
            denial=DenialTrace(
                mode=requested_mode,
                violated=["I-NAV-8"] if intent else ["I-NAV-7"],
                reason="intent_ceiling_exceeded" if intent else "code_intent_required",
            ),
        )

    # Step 2: session constraint registry — table-driven, no if-chain (I-NAV-8 REFORM)
    for mode_guard, predicate, violated, reason in _FULL_CONSTRAINTS:
        if requested_mode == mode_guard and predicate(session, node_id, intent):
            return AllowedOperations(
                modes=ceiling_modes - {mode_guard},
                denial=DenialTrace(mode=mode_guard, violated=violated, reason=reason),
            )

    return AllowedOperations(modes=ceiling_modes, denial=None)
```

JSON при нарушении:
```json
{"status": "nav_invariant_violation",
 "invariant": "I-NAV-1",
 "denial": {"mode": "FULL", "violated": ["I-NAV-1"], "reason": "summary_required"},
 "node_id": "FILE:src/sdd/cli.py", "message": "SUMMARY must precede FULL"}
```

`Navigator.resolve()` вызывает `resolve_action(intent, session, node_id, requested_mode)`.
Если `denial` не None → `nav_invariant_violation` с `denial.violated[0]` как `invariant`.

**Детерминированный fuzzy sort** (I-SI-2 требует воспроизводимости):
```
sort key (ascending): (distance, kind_priority, node_id lexicographically)

kind_priority:
  TERM       → 0  (первый — семантика)
  COMMAND    → 1
  TASK       → 2
  INVARIANT  → 3
  GUARD      → 4
  REDUCER    → 5
  EVENT      → 6
  FILE       → 7  (последний — структура)
```

Равный `distance` при разных `kind` → определяется `kind_priority`, потом `node_id` лексикографически.
Никакого нестабильного порядка Python set/dict не используется.

**`nav-search` namespace priority** (для общего запроса без `--kind`):
```
Если нет фильтра --kind, результаты ранжируются по тому же ключу:
  TERM > COMMAND > TASK > FILE
```

```python
class Navigator:
    def __init__(self, index: SpatialIndex,
                 session: NavigationSession | None = None): ...

    def resolve(self, node_id: str, mode: str = "SUMMARY",
                intent: NavigationIntent | None = None) -> dict:
        """I-SI-2: one id → same output for same index. I-SI-3: no open() on cache hit.
        Если session задан: вызывает resolve_action(intent, session, node_id).
        Если mode не в allowed.modes → nav_invariant_violation с denied."""

    def search(self, query: str, kind: str | None = None, limit: int = 10) -> list[dict]:
        """Fuzzy search по label, aliases (TERM), node_id. Включает TERM-узлы.
        Pipeline: collect → deterministic sort → limit (I-SEARCH-2)."""

    def not_found_response(self, query: str) -> dict:
        """Всегда возвращает must_not_guess: true. did_you_mean детерминирован."""
```

### BC-18-4: CLI Commands

```
src/sdd/spatial/commands/
  __init__.py
  nav_get.py       # sdd nav-get <id> [--mode POINTER|SUMMARY|SIGNATURE|FULL] [--intent TYPE]
  nav_search.py    # sdd nav-search <query> [--kind KIND] [--limit N]
  nav_rebuild.py   # sdd nav-rebuild [--project-root PATH] [--dry-run]
  nav_session.py   # sdd nav-session {next|clear|show}  (BUG-1 FIX: session lifecycle)
```

**Output format:**

Каждый успешный ответ `nav-get` включает `git_tree_hash` из индекса — context anchor для
воспроизводимости reasoning и основа temporal queries в Phase 20:

```json
// sdd nav-get COMMAND:complete --mode SUMMARY  (exit 0)
{"node_id": "COMMAND:complete", "kind": "COMMAND", "label": "sdd complete",
 "path": "src/sdd/commands/update_state.py",
 "summary": "Mark task T-NNN DONE. Emits TaskImplementedEvent via Write Kernel.",
 "git_hash": "a1b2c3d4", "indexed_at": "2026-04-24T12:00:00Z",
 "git_tree_hash": "abc123def456", "deterministic": true}

// sdd nav-get TERM:activate_phase --mode FULL  (exit 0)
// BUG-4 FIX: TERM = SpatialNode с kind="TERM"; definition/aliases/links — flat поля
{"node_id": "TERM:activate_phase", "kind": "TERM", "label": "Activate Phase",
 "path": null, "summary": "Human-only gate...", "signature": "Linked: COMMAND:activate-phase...",
 "git_hash": null, "indexed_at": "2026-04-24T12:00:00Z",
 "definition": "Human-only gate that transitions a PLANNED phase to ACTIVE state.",
 "aliases": ["phase activation", "activate phase"],
 "links": ["COMMAND:activate-phase", "EVENT:PhaseActivated", "INVARIANT:NORM-ACTOR-001"]}

// sdd nav-get COMMAND:nonexistent  (exit 1)
{"status": "not_found", "must_not_guess": true,
 "query": "COMMAND:nonexistent", "did_you_mean": ["COMMAND:complete"]}

// sdd nav-rebuild  (exit 0)
{"status": "ok", "nodes_written": 135, "terms_written": 8,
 "built_at": "2026-04-24T12:00:00Z", "git_tree_hash": "abc123"}

// sdd nav-search "activate phase" --kind TERM  (exit 0)
[{"node_id": "TERM:activate_phase", "kind": "TERM", "label": "Activate Phase",
  "score": 1.0}]
```

### BC-18-5: Tests

```
tests/unit/spatial/
  test_nodes.py           # SpatialNode, SpatialEdge конструкция; frozen; fields
                          # TERM = SpatialNode(kind="TERM") с definition/aliases/links
                          # I-SUMMARY-1: summary == 1 line; I-SUMMARY-2: fallback not empty; I-SIGNATURE-1: no prose
  test_index.py           # build_index: I-SI-1 уникальность, I-SI-4 стабильность, determinism
                          # I-DDD-0: TERM only from glossary.yaml; I-DDD-1: links = source of means
  test_navigator.py       # resolve modes; not_found always must_not_guess; TERM resolve
                          # I-SI-2: fuzzy sort deterministic (distance, kind_priority, node_id lex)
                          # I-FUZZY-1: search key = suffix/basename (not full node_id); threshold ≤ 2
                          # resolve_action(): DenialTrace с конкретным violated (BUG-3)
                          # resolve_action(): I-NAV-1 → reason="summary_required"
                          # resolve_action(): I-NAV-3/6 → reason="step_limit_exceeded"
                          # resolve_action(): I-NAV-7/8 → reason="code_intent_required|intent_ceiling_exceeded"
                          # NavigationIntent.allowed_modes(): 5 types (BUG-2: explore/locate/analyze/code_write/code_modify)
                          # I-NAV-9: next_step() — step boundary; FULL limit resets per step_id
                          # I-SEARCH-2: pipeline order (collect→sort→limit→render)
  test_staleness.py       # mock subprocess; git hash success/fail/None
                          # I-GIT-OPTIONAL: git недоступен → is_stale()=False, hash=None
                          # I-SI-5: node.git_hash mismatch с index.git_tree_hash → stale=True

tests/unit/commands/
  test_nav_get.py         # exit 0/1; I-SI-3 нет open() после load_index
                          # git_tree_hash присутствует в каждом успешном ответе
                          # stale_warning: true при stale index (WEAK-2)
                          # session load/save per call (I-NAV-SESSION-1)
  test_nav_search.py      # TERM в результатах поиска; aliases match
                          # namespace priority: TERM > COMMAND > TASK > FILE
                          # I-SEARCH-2: pipeline collect→sort→limit→render
                          # I-FUZZY-1: alias fuzzy match включает TERM aliases
  test_nav_rebuild.py     # dry-run не пишет файл; I-SI-4 diff на rename
                          # I-TERM-1: невалидный link → warning в output
                          # I-TERM-COVERAGE-1: COMMAND без TERM-покрытия → warning в output
  test_nav_session.py     # next increments step_id; clear removes file
                          # load missing = fresh session (I-NAV-SESSION-1)
                          # invalid JSON = fresh session + warning (graceful degradation)

tests/integration/
  test_nav_rebuild_integration.py   # real project root; I-SI-1; nodes > 0; TERM > 0
                                    # no TermNode class in codebase (BUG-4 regression guard)
```

### BC-18-6: Paths + CLI Wiring

**`src/sdd/infra/paths.py`** — добавить:
```python
def spatial_index_file(sdd_root: str | None = None) -> str:
    return os.path.join(sdd_root or _sdd_root(), "state", "spatial_index.json")

def nav_session_file(sdd_root: str | None = None) -> str:
    """BUG-1 FIX: session persistence path (I-NAV-SESSION-1)."""
    return os.path.join(sdd_root or _sdd_root(), "state", "nav_session.json")

def nav_session_lock_file(sdd_root: str | None = None) -> str:
    """I-SESSION-2: exclusive advisory lock path for concurrent CLI safety."""
    return os.path.join(sdd_root or _sdd_root(), "state", "nav_session.lock")
```

**`src/sdd/cli.py`** — добавить 4 команды:
```python
# В parse_args():
"nav-get":     nav_get.main,
"nav-search":  nav_search.main,
"nav-rebuild": nav_rebuild.main,
"nav-session": nav_session.main,   # BUG-1 FIX: session lifecycle
```

**`.sdd/config/glossary.yaml`** — создать с минимальным начальным набором TERM-узлов
(8+ концептов из CLAUDE.md §TOOLS и §INV).

---

## 4. Domain Events

Phase 18 не эмитирует domain events в EventLog.
`nav-rebuild` — read-only операция по отношению к SDD-ядру; пишет только `spatial_index.json`.

---

## 5. Types & Interfaces

### SpatialIndex JSON (`spatial_index.json`)

```json
{
  "version": 1,
  "built_at": "2026-04-24T12:00:00Z",
  "git_tree_hash": "abc123def456",
  "nodes": {
    "COMMAND:complete": {
      "node_id": "COMMAND:complete",
      "kind": "COMMAND",
      "label": "sdd complete",
      "path": "src/sdd/commands/update_state.py",
      "summary": "Mark task T-NNN DONE...",
      "signature": "def main(args): ...",
      "meta": {},
      "git_hash": "a1b2c3",
      "indexed_at": "2026-04-24T12:00:00Z"
    },
    "TERM:activate_phase": {
      "node_id": "TERM:activate_phase",
      "kind": "TERM",
      "label": "Activate Phase",
      "path": null,
      "summary": "Human-only gate that transitions a PLANNED phase to ACTIVE state.",
      "signature": "Linked: COMMAND:activate-phase, EVENT:PhaseActivated, INVARIANT:NORM-ACTOR-001",
      "meta": {},
      "git_hash": null,
      "indexed_at": "2026-04-24T12:00:00Z",
      "definition": "Human-only gate that transitions a PLANNED phase to ACTIVE state.",
      "aliases": ["phase activation", "activate phase", "sdd activate-phase"],
      "links": ["COMMAND:activate-phase", "EVENT:PhaseActivated", "INVARIANT:NORM-ACTOR-001"]
    }
  }
}
```

---

## 6. Invariants

### New Invariants — Spatial Index Layer

| ID | Statement | Phase | Verification |
|----|-----------|-------|-------------|
| I-CONTEXT-1 | Agent MUST NOT access filesystem directly if equivalent info exists in Spatial Index | 18 | CLAUDE.md §INV; NORM-NAV-001 (Phase 20) |
| I-NAV-1 | Agent MUST NOT call `--mode FULL` before `--mode SUMMARY` or `--mode SIGNATURE` for that node | 18 | NavigationSession.can_load_full(); CLAUDE.md §INV |
| I-NAV-2 | Agent MUST resolve `node_id` via `sdd nav-get` before direct filesystem access | 18 | CLAUDE.md §INV |
| I-NAV-3 | Max 1 `--mode FULL` per reasoning step; exception requires explicit justification | 18 | NavigationSession.can_load_full_step(); CLAUDE.md §INV |
| I-NAV-4 | Agent SHOULD resolve natural language queries via `sdd nav-search --kind TERM` before direct node lookup | 18 | CLAUDE.md §INV; NavigationSession.term_searched |
| I-NAV-5 | `--mode FULL` MUST be used only if agent produces or modifies code in this reasoning step | 18 | NavigationSession.can_load_full_step(intent); CLAUDE.md §INV |
| I-NAV-6 | FULL limit applies per `step_id`; `step_id` MUST be incremented via `next_step()` between reasoning steps | 18 | NavigationSession.full_load_count_per_step; CLAUDE.md §INV |
| I-NAV-7 | `--mode FULL` MUST include explicit `intent: code_write\|code_modify` in the request | 18 | resolve_action(); CLAUDE.md §INV |
| I-NAV-8 | `INTENT_CEILING` table is single source of truth for max allowed mode; `resolve_action()` = ceiling lookup + `_FULL_CONSTRAINTS` registry; no if-chain in FULL decision logic | 18 | resolve_action() sole decision point; INTENT_CEILING table; _FULL_CONSTRAINTS registry |
| I-NAV-9 | A reasoning step = one LLM tool-call sequence terminated by response to user or explicit `next_step()`; `step_id` MUST increment at each boundary | 18 | NavigationSession.next_step(); CLAUDE.md §INV |
| I-SI-1 | Every indexed file has exactly one node (validated by `nav-rebuild`) | 18 | `test_nav_rebuild.py` |
| I-SI-2 | `nav(id)` → same JSON output for same id and same index mtime; fuzzy sort deterministic | 18 | `test_navigator.py` |
| I-SI-3 | No filesystem scan if index hit exists (no `open()` after `load_index()`) | 18 | `test_nav_get.py` |
| I-SI-4 | `node_id` MUST be globally stable across rebuilds if artifact not renamed | 18 | `test_index.py` |
| I-SI-5 | All `node.git_hash` values MUST correspond to `index.git_tree_hash` snapshot; mismatch → stale | 18 | `test_index.py` git_hash consistency |
| I-DDD-0 | TERM-узлы MUST be built from `glossary.yaml`; no heuristic derivation | 18 | `test_index.py` |
| I-DDD-1 | `SpatialNode.links` (for kind=TERM) is the primary source of `means` edges; no inference on top | 18 | `test_index.py`; Phase 19 contract |
| I-TERM-1 | `SpatialNode.links` (TERM) with unknown `node_id` → staleness warning; unknown kind=COMMAND\|EVENT → error | 18 | `test_index.py` TERM link validation |
| I-TERM-COVERAGE-1 | Every COMMAND node SHOULD have at least one TERM node with a link to it; missing coverage → warning in `nav-rebuild` output (not error) | 18 | `test_nav_rebuild.py` coverage_warning |
| I-SEARCH-2 | `limit` MUST be applied after sort, before rendering/expansion; pipeline: collect → sort → limit → render | 18 | `test_navigator.py` search_pipeline_order |
| I-GIT-OPTIONAL | System MUST operate without git (degraded mode): `git_tree_hash=None`, `is_stale()=False` | 18 | `test_staleness.py` git-unavailable branch |
| I-SUMMARY-1 | `summary` MUST be 1 line; extracted deterministically (no LLM) | 18 | `test_index.py` summary_length check |
| I-SUMMARY-2 | `summary` fallback when no docstring/comment found: `"{KIND}:{basename}"` — never empty string | 18 | `test_index.py` summary_fallback check |
| I-SIGNATURE-1 | `signature` MUST contain only interface (def/class/types); no prose | 18 | `test_index.py` signature_format check |
| I-NAV-SESSION-1 | All `NavigationSession` state MUST be persisted in `.sdd/state/nav_session.json`; CLI MUST load at start and atomically save at end; missing file = fresh session (not error); invalid JSON = fresh session + warning | 18 | `test_nav_get.py` session_persistence; `test_nav_session.py` |
| I-SESSION-2 | `NavigationSession` read-modify-write MUST be protected by exclusive advisory lock (`.sdd/state/nav_session.lock` via `fcntl.flock`); concurrent CLI processes MUST block; timeout 5s → `nav_invariant_violation` reason `session_lock_timeout` | 18 | `test_nav_session.py` concurrency; `test_nav_get.py` lock_acquired |
| I-TERM-2 | All `SpatialNode.links` (kind=TERM) MUST resolve to existing `node_id` at `nav-rebuild` time; unresolved links → `SpatialIndex.meta["term_link_violations"]` with severity=warning; `nav-rebuild` exit 0 but reports violations | 18 | `test_nav_rebuild.py` term_link_validation; `test_index.py` meta_violations |
| I-FUZZY-1 | Fuzzy match applied to search key (not full node_id): FILE→basename, COMMAND/TERM/others→id suffix; threshold ≤ 2; TERM aliases included in search keys | 18 | `test_navigator.py` fuzzy_search_key |
| I-GEB-2 | EventLog is immutable; rollback MUST create compensating `RollbackEvent`, not mutate or soft-delete existing events | 21 (prepared 18) | Phase 21 implementation; I-3 preserved |

### Preserved Invariants (Phase 17)

I-VR-STABLE-1..10, I-HANDLER-PURE-1, I-KERNEL-WRITE-1, I-KERNEL-PROJECT-1, I-VR-API-1 — без изменений.

---

## 7. Pre/Post Conditions

### M0 — Navigation Protocol + Glossary config

**Pre:**
- Phase 17 COMPLETE, `VR_Report_v17.json` status STABLE

**Post:**
- I-NAV-1..5, I-CONTEXT-1, I-GIT-OPTIONAL добавлены в CLAUDE.md §INV
- `.sdd/config/glossary.yaml` создан (≥8 TERM-записей с заполненными `links`)

### M1 — Nodes dataclasses

**Pre:** M0 COMPLETE

**Post:**
- `src/sdd/spatial/__init__.py`, `nodes.py` созданы
- `SpatialNode`, `SpatialEdge` — frozen dataclasses (TermNode упразднён, BUG-4 fix)
- `SpatialNode` имеет поля `definition`, `aliases`, `links` (defaults="" / () / ())
- `SpatialEdge` помечен как Phase 19 schema contract, не runtime artifact Phase 18
- `tests/unit/spatial/test_nodes.py` PASS

### M2 — SpatialIndex + IndexBuilder

**Pre:** M1 COMPLETE

**Post:**
- `index.py` создан
- `build_index()` строит 7 типов узлов + TERM из glossary.yaml
- I-SI-1, I-SI-4 верифицированы unit-тестами
- `tests/unit/spatial/test_index.py` PASS

### M3 — Staleness

**Pre:** M2 COMPLETE

**Post:**
- `staleness.py` создан
- `is_stale()` работает через `git ls-files -s` (mock в тестах)
- `tests/unit/spatial/test_staleness.py` PASS

### M4 — Navigator + NavigationSession + NavigationIntent

**Pre:** M2 COMPLETE

**Post:**
- `navigator.py` создан; `NavigationSession`, `NavigationIntent`, `DenialTrace`, `resolve_action()` реализованы
- 4 режима resolve; not_found всегда `must_not_guess: true`
- TERM-узлы (kind="TERM" в SpatialNode) доступны через nav-search по aliases
- fuzzy sort детерминирован: (distance, kind_priority, node_id lex); fuzzy match — по search key (I-FUZZY-1)
- I-SEARCH-2: pipeline collect→sort→limit→render
- NavigationSession персистирует через `load_session()/save_session()` (I-NAV-SESSION-1)
- `resolve_action()` возвращает `DenialTrace` с конкретным violated invariant (BUG-3 fix)
- `tests/unit/spatial/test_navigator.py` PASS

### M5 — CLI Commands

**Pre:** M2, M3, M4 COMPLETE

**Post:**
- `src/sdd/spatial/commands/{nav_get,nav_search,nav_rebuild,nav_session}.py` созданы
- `nav-get` проверяет staleness и добавляет `stale_warning: true` в ответ (WEAK-2 fix)
- `src/sdd/infra/paths.py` расширен `spatial_index_file()` и `nav_session_file()`
- `src/sdd/cli.py` зарегистрированы 4 команды (включая nav-session)
- Unit-тесты CLI PASS (включая `test_nav_session.py`)

### M6 — Integration

**Pre:** M5 COMPLETE

**Post:**
- `sdd nav-rebuild` exit 0 на реальном project root
- `nodes_written > 100`, `terms_written ≥ 8`
- I-SI-1: дублей нет; I-SI-4: два rebuild → одинаковые node_ids
- `tests/integration/test_nav_rebuild_integration.py` PASS

---

## 8. Use Cases

### UC-18-1: Agent Resolves Command Before Reading File

**Actor:** LLM-агент
**Trigger:** задача требует понять поведение команды `complete`
**Pre:** Phase 18 ACTIVE, `spatial_index.json` актуален
**Steps:**
1. `sdd nav-get COMMAND:complete --mode SUMMARY` → JSON exit 0
2. Если нужны детали: `sdd nav-get COMMAND:complete --mode SIGNATURE`
3. Только если пишем код: `--mode FULL` (I-NAV-3: max 1 раз)
**Post:** агент получил нужный контекст без прямого чтения файлов

### UC-18-2: Agent Searches via DDD Term

**Actor:** LLM-агент
**Trigger:** агент видит в задаче "activate phase", не знает точный node_id
**Pre:** Phase 18 ACTIVE
**Steps:**
1. `sdd nav-search "activate phase" --kind TERM` → `TERM:activate_phase`
2. `sdd nav-get TERM:activate_phase --mode SUMMARY` → definition + aliases
3. Переход к связанным узлам через SIGNATURE (links: COMMAND:activate-phase)
**Post:** агент нашёл концепт через DDD-язык, не через путь к файлу

### UC-18-3: Stale Index Detection

**Actor:** агент перед началом задачи
**Trigger:** `sdd nav-rebuild` с проверкой staleness
**Pre:** git HEAD изменился после последнего rebuild
**Steps:**
1. `sdd nav-get FILE:src/sdd/cli.py --mode SUMMARY` → в meta: `{"stale_warning": true}`
2. Агент: `sdd nav-rebuild` → обновляет индекс
**Post:** I-SI-2 обеспечен — агент работает с актуальным индексом

### UC-18-5: NavigationSession Blocks Protocol Violation

**Actor:** LLM-агент
**Trigger:** агент пытается загрузить FULL без предшествующего SUMMARY
**Pre:** Phase 18 ACTIVE, `NavigationSession` активна
**Steps:**
1. `sdd nav-get FILE:src/sdd/cli.py --mode FULL` (без предшествующего SUMMARY)
2. Navigator проверяет `session.can_load_full("FILE:src/sdd/cli.py")` → `False`
3. Ответ: `{"status": "nav_invariant_violation", "invariant": "I-NAV-1", ...}` exit 1
4. Агент исправляется: сначала `--mode SUMMARY`, потом `--mode FULL`
**Post:** I-NAV-1 соблюдён; инварианты — система, не декларация

### UC-18-6: Natural Language → TERM → Node (I-NAV-4)

**Actor:** LLM-агент
**Trigger:** задача содержит фразу "как работает активация фазы"
**Pre:** Phase 18 ACTIVE
**Steps:**
1. `sdd nav-search "activate phase" --kind TERM` → `TERM:activate_phase` (I-NAV-4)
2. `sdd nav-get TERM:activate_phase --mode SUMMARY` → definition + links
3. links: `["COMMAND:activate-phase", "EVENT:PhaseActivated", "INVARIANT:NORM-ACTOR-001"]`
4. `sdd nav-get COMMAND:activate-phase --mode SIGNATURE` → только если нужно
**Post:** агент нашёл смысл через DDD-язык; никакого grep-thinking

### UC-18-4: Not Found Anti-Hallucination

**Actor:** LLM-агент
**Trigger:** `sdd nav-get COMMAND:nonexistent`
**Pre:** Phase 18 ACTIVE
**Steps:**
1. Navigator → `not_found_response()` → exit 1
2. `{"status": "not_found", "must_not_guess": true, "did_you_mean": [...]}`
3. Агент использует `did_you_mean` для уточнения, не угадывает
**Post:** I-NAV-2 предотвращает hallucination о несуществующих узлах

---

## 9. Verification

### Phase 18 Complete iff

```bash
# Все тесты Phase 18
pytest tests/unit/spatial/ tests/unit/commands/test_nav_*.py \
       tests/integration/test_nav_rebuild_integration.py -q

# I-SI-1, I-SI-4
sdd nav-rebuild
sdd nav-rebuild  # второй раз — node_ids должны совпадать

# Navigation modes
sdd nav-get COMMAND:complete --mode SIGNATURE    # exit 0, непустой signature
sdd nav-get NONEXISTENT:xyz                      # exit 1, must_not_guess: true

# DDD TERM layer
sdd nav-search "activate phase"                  # возвращает TERM:activate_phase
sdd nav-get TERM:activate_phase --mode FULL      # exit 0, непустой definition

# Staleness
# Изменить файл вручную без rebuild → is_stale() == True
```

### Test Suite

| # | File | Invariants |
|---|------|------------|
| 1 | `tests/unit/spatial/test_nodes.py` | SpatialNode frozen; TERM поля (definition/aliases/links default); I-SUMMARY-1, I-SUMMARY-2, I-SIGNATURE-1 |
| 2 | `tests/unit/spatial/test_index.py` | I-SI-1, I-SI-4, determinism; TERM в nodes как SpatialNode(kind=TERM); I-DDD-0, I-DDD-1; I-TERM-COVERAGE-1 warning |
| 3 | `tests/unit/spatial/test_navigator.py` | I-SI-2, I-SI-3, must_not_guess; TERM resolve; resolve_action() DenialTrace (BUG-3); _FULL_CONSTRAINTS registry (no if-chain, I-NAV-8); INTENT_CEILING table (5 intents, BUG-2); I-SEARCH-2; I-FUZZY-1 search_key |
| 4 | `tests/unit/spatial/test_staleness.py` | git mock success/fail/None; I-GIT-OPTIONAL; I-SI-5 |
| 5 | `tests/unit/commands/test_nav_get.py` | exit 0/1; I-SI-3 нет open(); git_tree_hash; stale_warning при stale index (WEAK-2); session load/save (I-NAV-SESSION-1) |
| 6 | `tests/unit/commands/test_nav_search.py` | TERM в результатах, aliases match; namespace priority; I-FUZZY-1 alias fuzzy |
| 7 | `tests/unit/commands/test_nav_rebuild.py` | dry-run, I-SI-4 diff на rename; I-TERM-COVERAGE-1 warning в output |
| 8 | `tests/unit/commands/test_nav_session.py` | next increments step_id; clear removes file; load missing = fresh; invalid JSON = fresh + warning; atomic save (I-NAV-SESSION-1); concurrent write safety mock (I-SESSION-2); lock timeout → violation |
| 9 | `tests/integration/test_nav_rebuild_integration.py` | I-SI-1, nodes>100, terms≥8, git_tree_hash present; no TermNode class in codebase |

### Stabilization Criteria

1. `sdd nav-rebuild` exit 0; `spatial_index.json` в `.sdd/state/`
2. `sdd nav-get COMMAND:complete --mode SIGNATURE` exit 0, непустой `signature`, `git_tree_hash` присутствует
3. `sdd nav-get NONEXISTENT:xyz` exit 1 с `must_not_guess: true`, непустой `did_you_mean`; fuzzy match по search key (I-FUZZY-1)
4. `sdd nav-search "activate phase"` → `TERM:activate_phase` на первой позиции (namespace priority)
5. `sdd nav-rebuild` дважды → идентичные `node_id` для всех узлов (I-SI-4)
6. `is_stale()` = True после правки файла без rebuild
7. `is_stale()` = False при недоступном git (I-GIT-OPTIONAL)
8. NavigationSession (через session file): FULL без предшествующего SUMMARY → `nav_invariant_violation` `denial.violated=["I-NAV-1"]`, `reason="summary_required"` (BUG-1 + BUG-3)
9. NavigationSession: повторный FULL в том же step_id → `denial.violated=["I-NAV-3","I-NAV-6"]`, `reason="step_limit_exceeded"`
10. resolve_action(): FULL без intent → `denial.violated=["I-NAV-7"]`, `reason="code_intent_required"`
11. resolve_action(): `intent=explore` + FULL → `denial.violated=["I-NAV-8"]`, `reason="intent_ceiling_exceeded"` (BUG-2 fix: нет "modify")
12. resolve_action(): `intent=code_modify` + session I-NAV-1 fail → FULL denied (session restricts)
13. `sdd nav-session next` → step_id инкрементирован; FULL доступен заново в новом шаге (I-NAV-6/9)
14. I-TERM-1: неизвестный node_id в SpatialNode.links(TERM) → warning, exit 0; unknown COMMAND → error
15. I-SEARCH-2: `nav-search --limit 3` возвращает top-3 после полного sort
16. `sdd nav-get FILE:src/sdd/cli.py --mode SUMMARY` → `stale_warning: true` после изменения файла без rebuild (WEAK-2)
17. `sdd nav-search "activate phase" --kind TERM` → TERM первым (I-NAV-4 entrypoint)
18. TERM-узел в ответе содержит поля `definition`, `aliases`, `links` на top-level (BUG-4: flat model)
19. `sdd nav-rebuild` emits warning для COMMAND без TERM-покрытия (I-TERM-COVERAGE-1)
20. `sdd nav-rebuild` с невалидным link в glossary.yaml → `meta.term_link_violations` в output (I-TERM-2)
21. `resolve_action()` содержит zero if-chain для FULL — только `_FULL_CONSTRAINTS` registry (I-NAV-8 reform)
22. Параллельные `sdd nav-get` вызовы (2 процесса одновременно) → без corruption в session file (I-SESSION-2)
23. Lock timeout 5s → `nav_invariant_violation` с `reason="session_lock_timeout"` (I-SESSION-2)
24. `pytest tests/unit/spatial/ tests/unit/commands/ tests/integration/test_nav_rebuild_integration.py` — 100%

---

## 10. Out of Scope

| Item | Owner |
|------|-------|
| DuckDB backend, рёбра графа | Phase 19 |
| `sdd nav-neighbors`, `sdd nav-invariant` | Phase 19 |
| `sdd resolve` unified entrypoint | Phase 19 |
| TERM → graph edges (means edge в DuckDB) | Phase 19 |
| Temporal queries (nav-changed-since) | Phase 20 |
| TaskCheckpoint events | Phase 20 |
| NORM-NAV-001 в norm_catalog | Phase 20 |
| ML ranking, embedding search, shortest path | никогда |
| GitEventBridge, `sdd rollback` | Phase 21 |
| I-GEB-1 (git commit ↔ event_id consistency) | Phase 21 |

---

## 11. Архитектурная заготовка: Git-EventLog Integration (Phase 21)

### Проблема

Git хранит **что изменилось** (code state at points in time).
EventLog хранит **почему** (causality chain of SDD events).
Сейчас эти два источника истины не связаны: невозможно воспроизвести,
при каком event_id был какой код, и нельзя автоматически откатиться.

### Целевая архитектура

```
Layer 1: Truth
  Git        → code state snapshot (per qualifying event)
  EventLog   → event causality chain (DuckDB, not in git)

Bridge: GitEventBridge (Phase 21)
  On qualifying event → git commit with event metadata
  EventLog.meta stores commit_hash for each committed event

Rollback: sdd rollback --to-event <event_id>
  1. Find commit_hash from EventLog where event_id matches
  2. git stash  (save uncommitted work)
  3. git checkout <commit_hash> -- <code files only, NOT .sdd/state/>
  4. EventStore.append(RollbackEvent(target_event_id=event_id, ...))
     ← BUG-5 FIX: compensating event, NOT soft-delete (I-GEB-2; EventLog append-only)
  5. Rebuild State_index.yaml from remaining events
  6. sdd nav-rebuild  (обновить Spatial Index)
```

### GitEventBridge (спецификация для Phase 21)

```python
GIT_COMMIT_EVENTS = {
    "TaskImplementedEvent",   # после каждой реализации задачи
    "PhaseCompletedEvent",    # при завершении фазы
}

class GitEventBridge:
    def on_event(self, event: Event) -> str | None:
        """Commits after qualifying events. Returns commit_hash or None."""
        if event.type not in GIT_COMMIT_EVENTS:
            return None
        msg = f"sdd(auto): {event.type} event_id={event.event_id}"
        if hasattr(event, "task_id"):
            msg += f" task={event.task_id}"
        commit_hash = _git_commit_all_tracked(msg)
        _enrich_event_meta(event.event_id, {"git_commit_hash": commit_hash})
        return commit_hash
```

**Формат commit message:**
```
sdd(auto): TaskImplementedEvent event_id=<uuid> task=T-1801

Co-committed-by: sdd-cli/<version>
```

### Что Phase 18 готовит для Phase 21

Phase 18 не реализует GitEventBridge, но создаёт необходимые предусловия:

| Заготовка | Где | Для чего |
|-----------|-----|---------|
| `SpatialIndex.git_tree_hash` | index.py | context anchor; rollback verifies via spatial index |
| `git_tree_hash` в каждом `nav-get` ответе | navigator.py | агент может проверить актуальность |
| I-GIT-OPTIONAL | staleness.py | система работает без git → CI не ломается при Phase 21 |
| `node.git_hash` per-node (I-SI-5) | nodes.py | per-file rollback granularity |

### Инвариант Phase 21 (I-GEB-1, фиксируем сейчас)

```
I-GEB-1:
  Every git_commit_hash stored in EventLog.meta
  MUST correspond to a reachable commit in current git history.
  Violation → sdd rollback --to-event <event_id> exit 1 с диагностикой.
```

### Что НЕ входит в Git-EventLog интеграцию

- `.sdd/state/sdd_events.duckdb` **не попадает в git** (бинарный файл, меняется часто)
- `State_index.yaml` **попадает в git** (текстовый, это projection для code review)
- `spatial_index.json` **не попадает в git** (регенерируется через nav-rebuild)
- git rollback затрагивает только code files; EventLog усекается отдельно

### I-GEB-2: Compensating Events, не мутация EventLog

EventLog строго append-only (I-3: all state = reduce(events)).
Ни soft-delete, ни UPDATE не допускаются — они ломают replay semantics и mental model
"EventLog = truth".

**Rollback через compensating event:**
```python
@dataclass
class RollbackEvent:
    event_type:          str = "RollbackEvent"
    event_id:            str  # новый uuid
    target_event_id:     str  # до какого события откат
    rollback_to_git_hash: str  # commit_hash из EventLog.meta
    reason:              str  # "user-initiated rollback"
    ts:                  str  # ISO-8601

# Appended в конец EventLog — никаких UPDATE/DELETE
EventStore.append(RollbackEvent(...))
```

Reducer при rebuild_state: встретив `RollbackEvent`, игнорирует все events с
`event_seq > target_event.event_seq` — чистая функция, воспроизводима.

**Полный pipeline rollback (Phase 21):**
```
sdd rollback --to-event <event_id>:
  1. Find commit_hash from EventLog.meta where event_id matches
  2. git stash  (uncommitted work)
  3. git checkout <commit_hash> -- <code files only, NOT .sdd/state/>
  4. EventStore.append(RollbackEvent(target_event_id=event_id, ...))
  5. rebuild_state()  → State_index.yaml
  6. sdd nav-rebuild  → spatial_index.json
  Output: {"rolled_back_to": event_id, "rollback_event_id": new_uuid, "stashed": true}
```

Это сохраняет полный audit trail: можно воспроизвести, что было до отката и почему.
