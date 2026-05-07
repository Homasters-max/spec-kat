# DocGraph Orchestration — Architectural Decisions

Результат архитектурного допроса по документу `DocGraph Orchestration.md`.
15 вопросов, все решения зафиксированы.

---

## Q1 — SSOT: Wiki vs EventLog

**Проблема:** §2.2 заявляет EventLog = SSOT, но `sync-wiki` компилирует Wiki → EventLog, то есть Wiki порождает EventLog.

**Решение:**
```
ДО sync-wiki:
  Wiki = SSOT для структуры (единственный источник намерения)

ПОСЛЕ sync-wiki:
  EventLog = SSOT для структуры (nodes, edges) + execution state (статусы, история)
  Wiki     = SSOT для семантики (описания, rationale, prose)

sync-wiki компилирует Wiki в Commands → EventLog.
После компиляции Wiki не имеет authority над структурой.
В конфликте (post-sync): EventLog MUST always win.
```

---

## Q2 — sync-wiki: протокол мутаций

**Проблема:** что делает PlanManager при повторном запуске sync-wiki, когда часть задач уже выполнена?

**Решение — полная матрица изменений:**

| Изменение | Разрешено | Обработка |
|---|---|---|
| Добавить узел | ✅ | TaskSpawned |
| Rename (name поле) | ✅ | metadata only, no events |
| Изменить зависимости | ❌ | запрещено после TaskSpawned |
| Удалить узел | ❌ | только через ARCHIVE |
| Изменить parent | ⚠️ | требует проверки DAG |
| Изменить scope | ⚠️ | только для OPEN задач |

**Алгоритм:**
```
for each node in Wiki:
  if node_id NOT in EventLog:
      emit TaskSpawned
  if node_id IN EventLog:
      validate (not deleted, deps valid)

for each node in EventLog:
  if node_id NOT in Wiki:
      ERROR (must archive, not delete)
```

**Инварианты:**
```
I-GRAPH-ID-1:           Node identity MUST be immutable (node_id ≠ name)
I-GRAPH-IMMUT-1:        Spawned nodes MUST NOT be deleted, only archived
I-GRAPH-DEP-IMMUT-1:    Dependencies MUST NOT change after TaskSpawned
                        (stronger than "after TaskStarted" — DAG must be stable
                        from the moment a node enters EventLog)
I-GRAPH-SYNC-1:         sync-wiki MUST reject destructive diffs
I-GRAPH-SYNC-ATOMIC-1:  sync-wiki MUST be atomic (all commands emitted or none)
```

---

## Q3 — id vs name в frontmatter

**Проблема:** DSL показывает `id: T-Login-Endpoint` — одновременно идентификатор и имя.

**Решение:**
```
id   = immutable slug (node_id), генерируется один раз, никогда не меняется
name = мutable display name, отдельное поле

TaskSpawned содержит node_id = id из frontmatter.
Переименование = изменение name, id не трогается.
Путь файла в filesystem не влияет на node_id.
```

---

## Q4 — DocGraph lifecycle vs SDD lifecycle

**Проблема:** DocGraph вводит `Draft → Approved → InProgress → Done`, SDD имеет `OPEN → IN_PROGRESS → DONE`.

**Решение:**
```
Draft → Approved = состояния Wiki-документа ДО компиляции (pre-EventLog)
После sync-wiki   = стандартный SDD lifecycle применяется

DocGraph lifecycle = жизненный цикл намерения, не исполнения.
После компиляции Wiki lifecycle теряет значение.
```

---

## Q5 — TaskReady: событие или проекция?

**Проблема:** кто и когда emit TaskReady когда зависимости выполнены?

**Решение:**
```
TaskReady — НЕ событие.
TaskReady = вычислимое состояние из проекции:
  f(TaskSpawned, DependencyRegistered, TaskCompleted)

PhaseOrchestrator при каждом AgentLoop цикле читает эту проекцию.
Emitting TaskReady как событие = избыточность, нарушение event sourcing discipline.
```

---

## Q6 — Интеграция QueryEngine

**Проблема:** DocGraph вводит граф из Wiki frontmatter, QueryEngine уже строит граф из `f(Code, Specs, EventLog)`. Это два потенциально дублирующих источника.

**Решение:**
```
DocGraph ЗАМЕНЯЕТ SpecExtractor как источник структуры.
SpecExtractor → переименован в WikiSemanticExtractor (prose only).

Единый граф:
  EventExtractor      → структура DAG (из TaskSpawned, DependencyRegistered)
  WikiSemanticExtractor → семантика (prose, описания)
  CodeExtractor        → code nodes + code_depends

EventLog = SSOT для структуры графа.
Wiki     = SSOT для семантики.
```

**Инвариант:**
```
I-GRAPH-SSOT-2:      EventLog is SSOT for structure (nodes, edges, status).
                     Wiki is SSOT for semantics (description, rationale).
I-NO-DUAL-GRAPH-1:   There MUST be exactly one structural graph in the system
                     (EventLog-derived).
I-RUNTIME-NO-WIKI-1: Runtime MUST NOT read structure from Wiki.
                     All structural reads MUST go through EventExtractor.
```

**Переименование компонента:** `SpecExtractor → WikiSemanticExtractor`

---

## Q7 — render-wiki: триггер и владение полями

**Проблема:** когда запускается render-wiki, и какие frontmatter-поля ему разрешено писать?

**Решение:**
```
Триггер: auto после каждой мутации EventLog (как projection rebuild)

EventLog-owned fields (render-wiki пишет):
  - status
  - blocked_by (derived)

Human-owned fields (render-wiki НЕ трогает):
  - id, name, type
  - depends, part_of, affects
  - scope
  - весь prose

render-wiki MUST NOT modify human-owned fields.
```

**Инвариант:**
```
I-WIKI-OWNERSHIP-1: render-wiki MUST NOT overwrite human-owned fields,
                    even if their current values appear corrupted or inconsistent.
```

---

## Q8 — Идемпотентность sync-wiki

**Проблема:** что предотвращает повторный emit TaskSpawned при повторном запуске sync-wiki?

**Решение:**
```
Primary:  PlanManager читает текущую проекцию (какие узлы уже spawned),
          emit команды только для diff (новых узлов).

Safety:   Guard в WriteKernel как второй рубеж защиты.

Вариант idempotent=True не используется: ключ идемпотентности node_id
потребовал бы расширения модели.
```

**Инвариант:**
```
I-SYNC-SERIAL-1: sync-wiki MUST be serialized per phase/graph.
                 Parallel executions of sync-wiki for the same graph
                 MUST NOT be allowed.
```

---

## Q9 — Scope модель и полная схема frontmatter

**Проблема:** где объявляется scope задачи? Поле `scope` отсутствует в DSL.

**Решение:**
```
Phase: scope объявляется явно в frontmatter
Task:  наследует scope от phase по умолчанию;
       сужение опционально через явное поле scope
```

**Инвариант:**
```
I-SCOPE-IMMUT-1: Task scope MUST NOT change after TaskStarted.
                 Agents MUST NOT have write boundaries mutated mid-execution.
```

**Полная схема frontmatter (финальная):**
```yaml
---
id: t-login-endpoint          # immutable slug (node_id)
name: "Login Endpoint"        # mutable, human-owned
type: task                    # task | phase
status: OPEN                  # EventLog-owned, written by render-wiki
blocked_by: []                # EventLog-owned, derived

depends: []                   # execution dependency (DAG)
part_of: p-auth-core          # hierarchy (tree)
affects: []                   # traceability only (context enrichment, lowest priority)
scope: []                     # human-owned; inherits from phase if empty
---
```

---

## Q10 — Domain: execution или semantic?

**Проблема:** §3 вводит Domain (D-*) — новый уровень иерархии, которого нет в SDD.

**Решение:**
```
Domain = semantic-only в v1.

НЕ компилируется в EventLog.
НЕ порождает событий.
Execution не зависит от Domain.

Существует в Wiki и WikiSemanticExtractor как:
  - semantic boundary for context + reasoning
  - global constraints, architectural principles, shared vocabulary
  - semantic clustering для навигации LLM

Execution Graph:   Phase → Task
Semantic Graph:    Domain → Phase → Task
```

**Инварианты:**
```
I-DOMAIN-EXEC-1: Domain MUST NOT produce events.
I-DOMAIN-EXEC-2: Execution MUST NOT depend on Domain.
I-DOMAIN-SCOPE-1: Scope inheritance MUST NOT include Domain (only Phase → Task).
```

**Триггер для Domain v2:** если появляется execution-зависимость между фазами
внутри одного домена, которая не выражается через DAG задач →
тогда DomainSpawned + DomainStateProjection + DomainOrchestrator.

---

## Q11 — Место sync-wiki в workflow

**Проблема:** когда именно запускается sync-wiki?

**Решение:**
```
sync-wiki = явная human-операция, manual gate.

Workflow:
  Human: пишет Wiki-файлы с frontmatter
  Human: sdd sync-wiki              ← явный gate
  EventLog: получает TaskSpawned, DependencyRegistered
  LLM: IMPLEMENT T-login-endpoint

Вариант auto-on-session-start отклонён: может неожиданно применить
незавершённые правки Wiki.
Вариант file watcher отклонён: ломает атомарность компиляции.
```

**Инвариант:**
```
I-SYNC-FRESHNESS-1: Phase activation MUST verify that sync-wiki was executed
                    after the last modification of any Wiki file in the phase.
                    Activating a phase with stale compilation is FORBIDDEN.
```

---

## Q12 — DocGraph заменяет Plan_vN.md и TaskSet_vN.md

**Проблема:** DocGraph и Plan_vN.md/TaskSet_vN.md описывают одно и то же.

**Решение:**
```
DocGraph ЗАМЕНЯЕТ Plan_vN.md и TaskSet_vN.md как источник структуры плана.
Wiki-файлы с frontmatter = новый canonical source.

Числовые phase_id (int) остаются только как порядковый номер фазы
(для switch-phase, activate-phase) — не как task identity.

Старые T-NNN идентификаторы: обратная совместимость не требуется.
Slug-идентификаторы (T-login-endpoint) = новый стандарт.

Каждый sync-wiki имплицитно определяет GraphVersion (vN):
  GraphVersion = hash(EventLog position after sync)
  → позволяет воспроизвести план фазы на момент запуска
  → заменяет роль TaskSet_vN.md как snapshot артефакта
```

---

## Q13 — Wiki как Projection: версионирование и атомарность

**Проблема:** render-wiki пишет файлы, ContextKernel их читает — race condition + partial write + inconsistent multi-file state.

**Решение:**
```
Wiki = materialized view (Projection) с snapshot semantics.

Архитектура:
  EventLog
    ↓
  render-wiki
    ↓
  Wiki Store (filesystem, versioned)
    ↓
  WikiSnapshotLoader
    ↓
  ContextKernel

Реализация — directory versioning:
  /wiki/v001/
  /wiki/v002/
  /wiki/v003/   ← latest

render-wiki:
  1. build new version in /wiki/tmp_v004/
  2. fsync
  3. atomic rename → /wiki/v004/
  4. update pointer current = v004

AgentLoop контракт:
  1. load projections snapshot (EventLog-based)
  2. load wiki snapshot (same logical EventLog position)
  3. execute step
```

**Инварианты:**
```
I-WIKI-SNAPSHOT-1:  ContextKernel MUST read Wiki via snapshot, NOT via direct filesystem reads.
I-WIKI-SNAPSHOT-2:  Each snapshot MUST correspond to a single EventLog position.
I-SNAPSHOT-ALIGN-1: Projection snapshot and Wiki snapshot MUST correspond
                    to the same EventLog position.
I-WIKI-ATOMIC-1:    render-wiki MUST be atomic (all files or none).
I-WIKI-NO-PARTIAL-1: Partial writes MUST NOT be visible to readers.
I-WIKI-IMMUT-1:     Snapshots are immutable once created.
I-WIKI-READ-ONLY-1: ContextKernel MUST treat snapshot as read-only.
I-WIKI-LAG-1:       Wiki snapshot lag MUST be bounded (≤ 1 iteration).
```

**render-wiki modes:**
```
eager (default):  после каждого commit
batched (optional): каждые N events или конец loop
```

**Roadmap:**
```
v1: filesystem versioned snapshots
v2: in-memory WikiProjection (нет IO, идеальная консистентность)
```

**Инвариант:**
```
I-WIKI-GC-1: Old Wiki snapshots MUST be garbage-collected or compacted.
             Unbounded snapshot accumulation on filesystem is FORBIDDEN.
             GC policy: keep last N snapshots (N configurable, default = 10).
```

---

## Q14 — Полная схема frontmatter и роль `affects`

**Финальная схема frontmatter** зафиксирована в Q9.

**Роль `affects`:**
```
WikiSemanticExtractor следует по affects-рёбрам с приоритетом ниже,
чем depends/part_of, и только если бюджет токенов не исчерпан.

affects = подсказка LLM про смежные области.
НЕ обязательный контекст. Priority 5 (последний, как в §10.1).
НЕ влияет на execution.
```

---

## Q16 — graph-query-engine: трёхадаптерная архитектура

**Проблема:** Q6 переименовывает `SpecExtractor → WikiSemanticExtractor`, но не специфицирует точный интерфейс трёх адаптеров: что именно каждый производит, откуда читает, и как изменяется fingerprint.

**Решение — явное разделение адаптеров:**

```
EventExtractor:
  Источник:   EventLog-projection (TaskSpawned, DependencyRegistered,
                                   TaskCompleted, TaskArchived)
  Производит: структура DAG — nodes {id, status, scope} + edges {depends, part_of}
  SSOT:       EventLog

WikiSemanticExtractor:
  Источник:   WikiSnapshot (prose-файлы по node_id, NOT filesystem напрямую)
  Производит: семантика — Summary, Acceptance Criteria, Notes, Domain context
  Навигация:  task → part_of → phase → part_of → domain (три уровня)
              affects: приоритет P5, только если token budget не исчерпан (Q14)
  SSOT:       Wiki

CodeExtractor:
  Источник:   filesystem / git (code files)
  Производит: code nodes + code_depends edges
  SSOT:       git

Граф = merge(EventExtractor.result, WikiSemanticExtractor.result, CodeExtractor.result)
```

**Fingerprint (обновлённый):**
```
fingerprint = hash(event_offset + wiki_snapshot_version + code_hash)
              ↑ было: hash(code_hash + spec_hash + event_offset)
              spec_hash — устаревший, заменён wiki_snapshot_version
```

**Инварианты:**
```
I-QE-ADAPTER-1:      QueryEngine MUST NOT read Wiki files directly.
                     All Wiki access MUST go through WikiSemanticExtractor(WikiSnapshot).
I-QE-ADAPTER-2:      QueryEngine MUST NOT read EventLog directly.
                     All structure MUST come through EventExtractor(EventLogProjection).
I-QE-FINGERPRINT-1:  fingerprint = hash(event_offset + wiki_snapshot_version + code_hash).
                     spec_hash is retired — MUST NOT appear in fingerprint computation.
```

---

## Q17 — PlanManager: входной шов DocGraph

**Проблема:** Q12 объявляет DocGraph заменяет `Plan_vN.md`/`TaskSet_vN.md`, но не специфицирует как именно PlanManager получает input — что такое `DocGraphInput`, и где формируется `GraphVersion`.

**Решение:**

```
Старый шов:
  PlanCreationCommand → PlanManager → PlanCreated

Новый шов:
  DocGraphInput → PlanManager → [TaskSpawned*, DependencyRegistered*, GraphVersionRecorded]

DocGraphInput = {
    nodes:              list[DocGraphNode],       # parsed by DocGraphParser
    current_projection: EventLogProjection        # какие узлы уже spawned
}

PlanManager.process(input: DocGraphInput):
    diff = compute_diff(input.nodes, input.current_projection)
    → для новых узлов:   emit TaskSpawned
    → для существующих:  validate (dep immutability Q2, no-delete rule)
    → для destructive:   reject с I-GRAPH-SYNC-1
    → при успехе всего:  emit GraphVersionRecorded { event_pos, wiki_files_hash }

GraphVersion = hash(event_pos после последнего sync-wiki batch)
  — заменяет TaskSet_vN.md как snapshot-артефакт
  — хранится в EventLog как часть GraphVersionRecorded
  — позволяет воспроизвести план фазы на момент запуска
```

**Инварианты:**
```
I-PM-INPUT-1:     PlanManager MUST NOT read Plan_vN.md or TaskSet_vN.md.
                  DocGraphInput is the only valid input path (post-DocGraph). DECLARED.
I-PM-GRAPHVER-1:  GraphVersion MUST be derived from EventLog position (event_pos),
                  never from a separate file artifact. ENFORCED via GraphVersionRecorded.
```

---

## Q18 — WikiSnapshotLoader: интерфейс и AgentLoop контракт

**Проблема:** Q13 описывает directory versioning (`/wiki/vN/`), но не определяет интерфейс `WikiSnapshotLoader` и строгий контракт AgentLoop относительно порядка загрузки snapshots.

**Решение — интерфейс:**

```python
class WikiSnapshotLoader:
    def load_at(self, event_pos: int) -> WikiSnapshot:
        """Load wiki snapshot aligned to this EventLog position.
        Raises SnapshotNotFound — NO fallback to nearest.  (I-WSL-1)
        """

    def latest(self) -> WikiSnapshot:
        """Load the most recent snapshot. Lag ≤ 1 iteration.  (I-WIKI-LAG-1)"""

    def current_pointer(self) -> tuple[int, str]:
        """Returns (event_pos, snapshot_version) of current snapshot pointer."""

class WikiSnapshot:
    event_pos: int              # EventLog position this was rendered at
    version:   str              # "v001", "v002", ...
    nodes:     dict[str, WikiNodeContent]  # node_id → prose content
```

**AgentLoop контракт (строгий порядок):**

```
Step 1: event_pos  = EventLog.current_position()
Step 2: event_proj = ProjectionRegistry.snapshot_at(event_pos)   ← структура
Step 3: wiki_snap  = WikiSnapshotLoader.load_at(event_pos)       ← семантика
         ↑ I-SNAPSHOT-ALIGN-1: ОБА snapshot MUST быть на одном event_pos
Step 4: context    = ContextKernel.build_base(task_id, event_proj, wiki_snap)
Step 5: LLM execute
Step 6: sdd complete T-slug → EventLog.append → event_pos++
Step 7: render-wiki → /wiki/v(N+1)/ → update pointer (event_pos++)
```

Нарушение порядка шагов 1–3 → несогласованный context (I-SNAPSHOT-ALIGN-1 violation).

**Инварианты:**
```
I-WSL-1:  WikiSnapshotLoader MUST raise SnapshotNotFound if snapshot for
          requested event_pos does not exist. Fallback to nearest is FORBIDDEN.
I-WSL-2:  WikiSnapshotLoader MUST be the only component that resolves
          snapshot paths. Direct /wiki/vN/ filesystem reads are FORBIDDEN
          outside WikiSnapshotLoader.
```

---

## Q19 — PhaseOrchestrator: freshness guard детализация

**Проблема:** I-SYNC-FRESHNESS-1 требует "Phase activation MUST verify sync-wiki was executed after last modification", но не специфицирует механизм хранения и сравнения freshness. Filesystem timestamps ненадёжны (Git, Docker, rsync их сбрасывают).

**Решение — EventLog-based freshness:**

```
sync-wiki при каждом запуске записывает в EventLog:
  SyncWikiExecuted {
      phase_id:        int,
      event_pos:       int,
      wiki_files_hash: str,   # sha256(sorted(file_contents) для всех wiki-файлов фазы)
      timestamp:       datetime
  }

PhaseOrchestrator при activate-phase:
  1. Читает последний SyncWikiExecuted для phase_id из EventLog
  2. Вычисляет current_hash = sha256(sorted(wiki-файлы фазы))
  3. Сравнивает с SyncWikiExecuted.wiki_files_hash:
       → совпадает:           продолжает activate-phase
       → не совпадает:        emit PhaseActivationBlocked {
                                  reason:        "SYNC_FRESHNESS_VIOLATION",
                                  last_sync_at:  timestamp,
                                  stale_files:   list[path]   # diff показывает что изменилось
                              }
       → SyncWikiExecuted не найден:  также PhaseActivationBlocked
                                       (фаза никогда не синхронизировалась = stale)
```

**Инварианты:**
```
I-SYNC-FRESHNESS-2:  PhaseOrchestrator MUST read freshness from EventLog
                     (SyncWikiExecuted event), NOT from filesystem timestamps.
I-SYNC-FRESHNESS-3:  Absence of SyncWikiExecuted for a phase MUST be treated
                     as SYNC_FRESHNESS_VIOLATION (never synced ≠ ok).
```

---

## Q20 — docgraph-dual-ssot: standalone концепт

**Проблема:** ключевая идея "двух SSOT" нигде не собрана как единый концепт. `I-GRAPH-SSOT-2`, `I-NO-DUAL-GRAPH-1`, `I-RUNTIME-NO-WIKI-1` объявлены в разных местах, но не объяснены совместно. LLM-навигация вынуждена реконструировать принцип из Q1+Q6 каждый раз.

**Решение — wiki-страница `idea/docgraph-dual-ssot`:**

```
Lifecycle авторитета:

  ДО sync-wiki:
    Wiki = SSOT для структуры (единственный источник намерения)
    EventLog = отражает предыдущее состояние

  ПОСЛЕ sync-wiki:
    EventLog = SSOT для структуры (nodes, edges, statuses)
    Wiki     = SSOT для семантики (prose, rationale, descriptions)

Правило конфликтов (post-sync):
  EventLog ALWAYS wins для структурных данных (node existence, deps, status)
  Wiki ALWAYS wins для семантических данных (prose, что значит задача)

Три enforcement points:
  1. QueryEngine:         EventExtractor (structure) + WikiSemanticExtractor (semantics)
                          — никогда не пересекаются источники (I-QE-ADAPTER-1/2)
  2. PlanManager:         читает только DocGraphInput (parsed Wiki)
                          после компиляции — читает только EventLogProjection
  3. ContextKernel:       aligned snapshots (I-SNAPSHOT-ALIGN-1)
                          — структура и семантика на одном event_pos
```

Тип страницы: `idea/` — архитектурный принцип, не компонент.

---

## Q15 — DoD: enforced vs declared инварианты

**Проблема:** из ~15 новых инвариантов — какие enforced кодом в v1?

**Enforced кодом (v1) — исходный список:**
```
I-GRAPH-ACYCLIC-1:      DAG validation в DocGraphValidator
I-GRAPH-SYNC-1:         sync-wiki reject destructive diffs
I-WIKI-ATOMIC-1:        atomic render-wiki (directory versioning)
I-GRAPH-ID-1:           immutable node_id (guard в WriteKernel)
```

**Enforced кодом (v1) — добавлены в Q16–Q20 (архитектурный анализ):**
```
I-QE-ADAPTER-1/2:       QueryEngine читает Wiki/EventLog только через адаптеры (Q16)
I-QE-FINGERPRINT-1:     fingerprint = hash(event_offset+wiki_snapshot_version+code_hash) (Q16)
I-PM-GRAPHVER-1:        GraphVersion via GraphVersionRecorded event (Q17)
I-WSL-1:                WikiSnapshotLoader raises SnapshotNotFound — no fallback (Q18)
I-WSL-2:                только WikiSnapshotLoader читает /wiki/vN/ paths (Q18)
I-SYNC-FRESHNESS-2:     freshness из SyncWikiExecuted event, не filesystem timestamps (Q19)
I-SYNC-FRESHNESS-3:     отсутствие SyncWikiExecuted = SYNC_FRESHNESS_VIOLATION (Q19)
```

**Declared (документация, v2):**
```
I-DOMAIN-EXEC-1/2:      следует из отсутствия кода, не из guard
I-WIKI-IMMUT-1:         enforced косвенно через directory versioning
I-GRAPH-SCOPE-2:        сложно автоматически проверить без полного scope resolver
I-PM-INPUT-1:           PlanManager не читает Plan_vN.md (декларативно до удаления файлов)
```

**Метаправило:**
```
I-INVARIANT-META-1: Every new invariant MUST declare its enforcement level:
                      ENFORCED — verified by code (guard, test, or runtime check)
                      DECLARED — documentation only, not enforced by code
                    Invariants without declared enforcement level
                    MUST be treated as DECLARED.
```

---

## Итоговая архитектура (финальная модель)

```
Human: пишет Wiki-файлы (frontmatter DSL)
  ↓
sdd sync-wiki (human gate, serial per phase — I-SYNC-SERIAL-1)
  ↓
  DocGraphParser    → распарсить frontmatter → list[DocGraphNode]
  DocGraphValidator → validate DAG (acyclicity, destructive diff check)
  PlanManager       → diff vs EventLogProjection → emit Commands
  ↓
  Commands → WriteKernel → EventLog
    (TaskSpawned, DependencyRegistered, GraphVersionRecorded, SyncWikiExecuted)
  ↓
ProjectionRegistry rebuild
  + render-wiki (atomic, directory versioning — I-WIKI-ATOMIC-1)
       ↓
    /wiki/vN/ snapshot  ← WikiSnapshotLoader управляет pointer
  ↓
[activate-phase — human gate]
  PhaseOrchestrator: freshness check (SyncWikiExecuted в EventLog — I-SYNC-FRESHNESS-2/3)
  → если stale: PhaseActivationBlocked
  → если fresh:  proceed
  ↓
AgentLoop iteration:
  Step 1: event_pos  = EventLog.current_position()
  Step 2: event_proj = ProjectionRegistry.snapshot_at(event_pos)    ← структура
  Step 3: wiki_snap  = WikiSnapshotLoader.load_at(event_pos)        ← семантика
           ↑ I-SNAPSHOT-ALIGN-1: оба snapshot на одном event_pos
  Step 4: ContextKernel.build_base(task_id, event_proj, wiki_snap):
             EventExtractor(event_proj)         → DAG structure
             WikiSemanticExtractor(wiki_snap)   → prose, Domain context (P1–P4)
             CodeExtractor(filesystem)          → code nodes (P3)
             affects-edges                      → P5, только если budget позволяет
  Step 5: LLM execute (IMPLEMENT T-slug)
  Step 6: sdd complete T-slug → WriteKernel → EventLog → event_pos++
  Step 7: render-wiki → /wiki/v(N+1)/ → update pointer
```

---

## Новые инварианты (полный список)

Формат: `ID — enforcement level — краткое описание`

```
ENFORCED:
  I-GRAPH-ID-1            ENFORCED  node_id immutable, guard в WriteKernel
  I-GRAPH-IMMUT-1         ENFORCED  no delete, only archive
  I-GRAPH-DEP-IMMUT-1     ENFORCED  deps frozen after TaskSpawned
  I-GRAPH-SYNC-1          ENFORCED  reject destructive diffs
  I-GRAPH-SYNC-ATOMIC-1   ENFORCED  all commands emitted or none
  I-GRAPH-ACYCLIC-1       ENFORCED  DAG validation in DocGraphValidator
  I-WIKI-ATOMIC-1         ENFORCED  atomic render-wiki (directory versioning)
  I-WIKI-OWNERSHIP-1      ENFORCED  render-wiki never touches human-owned fields
  I-SYNC-SERIAL-1         ENFORCED  no parallel sync-wiki per graph
  I-SCOPE-IMMUT-1         ENFORCED  task scope frozen after TaskStarted
  I-SYNC-FRESHNESS-1      ENFORCED  phase activation checks sync freshness
  I-WIKI-SNAPSHOT-1       ENFORCED  ContextKernel reads only snapshots
  I-WIKI-GC-1             ENFORCED  old snapshots garbage-collected

DECLARED:
  I-GRAPH-SSOT-2          DECLARED  EventLog=structure SSOT, Wiki=semantic SSOT
  I-NO-DUAL-GRAPH-1       DECLARED  one structural graph only
  I-RUNTIME-NO-WIKI-1     DECLARED  runtime reads structure only via EventExtractor
  I-DOMAIN-EXEC-1         DECLARED  Domain produces no events
  I-DOMAIN-EXEC-2         DECLARED  execution does not depend on Domain
  I-DOMAIN-SCOPE-1        DECLARED  scope inheritance Phase→Task only
  I-WIKI-SNAPSHOT-2       DECLARED  snapshot aligned to EventLog position
  I-SNAPSHOT-ALIGN-1      DECLARED  projection + wiki snapshot at same EventLog position
  I-WIKI-NO-PARTIAL-1     DECLARED  no partial writes visible
  I-WIKI-IMMUT-1          DECLARED  snapshots immutable once created
  I-WIKI-READ-ONLY-1      DECLARED  ContextKernel treats snapshot as read-only
  I-WIKI-LAG-1            DECLARED  staleness ≤ 1 iteration
  I-INVARIANT-META-1      DECLARED  all invariants must declare enforcement level
  I-PM-INPUT-1            DECLARED  PlanManager reads only DocGraphInput, not Plan_vN.md

ДОБАВЛЕНЫ в Q16–Q20:
  I-QE-ADAPTER-1          ENFORCED  QueryEngine reads Wiki only via WikiSemanticExtractor(WikiSnapshot)
  I-QE-ADAPTER-2          ENFORCED  QueryEngine reads structure only via EventExtractor(Projection)
  I-QE-FINGERPRINT-1      ENFORCED  fingerprint=hash(event_offset+wiki_snapshot_version+code_hash); spec_hash retired
  I-PM-GRAPHVER-1         ENFORCED  GraphVersion derived from EventLog position via GraphVersionRecorded
  I-WSL-1                 ENFORCED  WikiSnapshotLoader raises SnapshotNotFound — no fallback to nearest
  I-WSL-2                 ENFORCED  only WikiSnapshotLoader resolves snapshot paths; direct /wiki/vN/ reads forbidden
  I-SYNC-FRESHNESS-2      ENFORCED  freshness read from SyncWikiExecuted event, not filesystem timestamps
  I-SYNC-FRESHNESS-3      ENFORCED  absent SyncWikiExecuted = SYNC_FRESHNESS_VIOLATION (not ok)
```
