# Plan: Доработка skills/wiki для работы с DocGraph

## Context

DocGraph Orchestration (зафиксировано в `raw/DocGraph Orchestration - Architectural Decisions.md`,
включая Q16–Q20 из архитектурного анализа) вводит двойную роль wiki-файлов:

1. **Страницы знаний** (`page_type: idea|pattern|tool`) — текущий skill уже обрабатывает
2. **Execution nodes** (`type: task|phase|domain`) — DocGraph frontmatter DSL,
   компилируемый `sync-wiki` в EventLog

Текущий `skills/wiki/SKILL.md` не знает о второй роли:
- нет протокола для создания/редактирования DocGraph-узлов
- нет инвариантов о полях-владельцах (EventLog-owned vs human-owned)
- нет gate-напоминания про `sync-wiki` и `activate-phase`
- не отражён rename `SpecExtractor → WikiSemanticExtractor` (Q6)
- не отражён `WikiSnapshotLoader` как шов между Wiki и ContextKernel (Q18)
- нет страниц для 8 новых компонентов
- нет страницы `docgraph-dual-ssot` (Q20)

---

## Изменение 1 — SKILL.md: новый протокол `wiki-docgraph`

**Файл:** `.claude/skills/wiki/SKILL.md`

### 1a. Добавить строку в таблицу Intent → Protocol

```markdown
| Create or edit DocGraph task/phase/domain execution node | **wiki-docgraph** |
```

### 1b. Новый раздел `## wiki-docgraph protocol`

Протокол для работы с DocGraph-узлами (wiki-файлы с `type: domain|phase|task`).

**Таблица типов (ОБЯЗАТЕЛЬНА в разделе):**

| `type`   | Префикс ID | Компилируется в EventLog? | Имеет `status`? | Роль                      |
|----------|-----------|--------------------------|-----------------|---------------------------|
| `domain` | `d-`      | ❌ Нет                   | ❌ Нет          | Semantic cluster (Q10)    |
| `phase`  | `p-`      | ✅ Да                    | ✅ Да           | Execution boundary        |
| `task`   | `t-`      | ✅ Да                    | ✅ Да           | Atomic work item          |

**Три режима:**

```
РЕЖИМ A — Создание нового execution-узла (task / phase):

  Frontmatter (точная схема из Q9):
    ---
    id: t-<slug>         # immutable slug (node_id); kebab-case; НИКОГДА не меняется (Q3)
    name: "Title"        # mutable display name; переименование = менять только это поле
    type: task           # task | phase
    status: OPEN         # ⛔ НЕ РЕДАКТИРОВАТЬ — EventLog-owned; render-wiki пишет (Q7)
    blocked_by: []       # ⛔ НЕ РЕДАКТИРОВАТЬ — EventLog-owned; render-wiki пишет (Q7)
    depends: []          # DAG edges (list of node_ids); FROZEN после TaskSpawned (Q2)
    part_of: p-<id>      # для task: родительская фаза; для phase: родительский домен (d-<id>)
    affects: []          # traceability hints (P5, lowest priority, Q14)
    scope: []            # empty = наследует от phase; FROZEN после TaskStarted (Q9)
    ---

  Prose структура:
    # <name>
    ## Summary
    ## Acceptance Criteria   (только для task)
    ## Notes                 (optional)

  После создания → показать пользователю:
    "[sync-wiki gate] Структурный узел создан.
     Запустите: sdd sync-wiki — для компиляции в EventLog.
     ОБЯЗАТЕЛЕН перед activate-phase (I-SYNC-FRESHNESS-1)."

РЕЖИМ B — Создание нового domain-узла (semantic-only):

  Frontmatter:
    ---
    id: d-<slug>         # префикс d-; immutable
    name: "Domain Name"
    type: domain
    # ЗАПРЕЩЕНЫ поля: status, blocked_by, depends, scope  (I-DOCGRAPH-DOMAIN-2)
    ---

  Prose домена = архитектурные правила, глобальные ограничения, shared vocabulary.
  sync-wiki ПРОПУСКАЕТ domain-узлы (DocGraphParser их игнорирует).
  render-wiki НИКОГДА не трогает domain-узлы (нет EventLog-owned полей).

  После создания domain → sync-wiki НЕ нужен.

РЕЖИМ C — Редактирование prose существующего узла:

  Читать: wiki show <node-id>
  Определить: что изменяется?

  Если изменяется ТОЛЬКО prose (Summary, Acceptance Criteria, Notes):
    → писать runtime/tmp/<node-id>.diff.md — ТОЛЬКО prose секции
    → НЕ ВКЛЮЧАТЬ в diff: status, blocked_by (EventLog-owned)
    → вызывать: wiki apply-drafts
    → sync-wiki НЕ нужен (prose ≠ structure)

  Если изменяются структурные поля (depends / part_of / scope):
    → предупредить: "Структурное изменение после TaskSpawned ЗАПРЕЩЕНО (Q2, I-GRAPH-DEP-IMMUT-1)"
    → depends: НЕЛЬЗЯ менять после TaskSpawned
    → scope:   НЕЛЬЗЯ менять после TaskStarted
    → part_of: требует проверки DAG
    → ОБЯЗАТЕЛЬНО напомнить: "sdd sync-wiki — обязателен перед activate-phase"
```

**Поля-владельцы (критическая таблица):**

| Поле         | Владелец     | Пишет         | LLM может редактировать? |
|--------------|-------------|---------------|--------------------------|
| `id`         | Human       | Human (once)  | ❌ Никогда               |
| `name`       | Human       | Human         | ✅ Да (переименование)   |
| `type`       | Human       | Human (once)  | ❌ Никогда               |
| `status`     | EventLog    | render-wiki   | ❌ Никогда               |
| `blocked_by` | EventLog    | render-wiki   | ❌ Никогда               |
| `depends`    | Human       | Human (pre-spawn) | ⚠️ Только до TaskSpawned |
| `part_of`    | Human       | Human         | ⚠️ Требует DAG проверки  |
| `affects`    | Human       | Human         | ✅ Да                    |
| `scope`      | Human       | Human (pre-start) | ⚠️ Только до TaskStarted |

### 1c. Новые инварианты в §INVARIANTS

```
I-DOCGRAPH-FM-1     DocGraph nodes (type: task|phase) MUST use DocGraph frontmatter schema
                    (id/name/type/status/blocked_by/depends/part_of/affects/scope).
                    wiki knowledge schema (page_type/domain/layer/tags) ЗАПРЕЩЕНО смешивать.
                    Lint ERROR если найдены оба schema в одном файле.

I-DOCGRAPH-OWNED-1  Поля status и blocked_by MUST NOT редактироваться вручную.
                    Они EventLog-owned: render-wiki пишет их автоматически (Q7, I-WIKI-OWNERSHIP-1).

I-DOCGRAPH-ID-1     id DocGraph-узла — immutable slug. Переименование = менять поле name.
                    Путь файла в filesystem не влияет на node_id (Q3).

I-DOCGRAPH-DOMAIN-1 Узлы type: domain НЕ компилируются в EventLog. PlanManager/sync-wiki
                    их полностью игнорируют. Семантика только: prose для WikiSemanticExtractor
                    (Q10, I-DOMAIN-EXEC-1/2).

I-DOCGRAPH-DOMAIN-2 Frontmatter type: domain MUST NOT содержать поля: status, blocked_by,
                    depends, scope. Наличие этих полей = Lint Error.

I-DOCGRAPH-SYNC-1   После изменения структурных полей (depends/part_of/scope) LLM MUST
                    напомнить пользователю: "sdd sync-wiki — обязателен перед activate-phase"
                    (Q11, I-SYNC-FRESHNESS-1/2/3).

I-DOCGRAPH-PROSE-1  WikiSemanticExtractor читает prose DocGraph-узлов из WikiSnapshot.
                    Prose = источник семантики. EventLog = источник структуры (Q6, I-GRAPH-SSOT-2).
                    WikiSemanticExtractor MUST NOT read wiki files directly (I-QE-ADAPTER-1).

I-WIKI-SNAP-1       wiki-query для DocGraph-контекста: структурные данные (status, deps) —
                    из EventLog (sdd show-state). Prose — из wiki show. ЗАПРЕЩЕНО путать источники.
```

### 1d. wiki-query: добавить NOTE о DocGraph

В секции `wiki-query protocol` добавить NOTE:

```
NOTE (DocGraph context):
  Структурные данные DocGraph-узлов (status, depends, blocked_by) живут в EventLog,
  не в wiki prose. Для структурных запросов:
    sdd show-state       → текущее состояние задач/фазы
    sdd query-events     → история событий (в т.ч. SyncWikiExecuted, GraphVersionRecorded)
  wiki show <node-id> → только prose (Summary, Acceptance Criteria, Notes)
  affects-рёбра: приоритет P5 (последний), только при наличии бюджета токенов (Q14)
  WikiSemanticExtractor навигирует: task → phase → domain (три уровня prose = один контекстный пакет)
```

---

## Изменение 2 — Критические ограничения (уточнения)

- SKILL.md редактируется **только через прямой Edit** — не wiki-страница, `wiki apply-drafts` не применяется
- DocGraph frontmatter schema НИКОГДА не смешивается с wiki knowledge schema (I-DOCGRAPH-FM-1)
- `status` и `blocked_by` — EventLog-owned; LLM никогда их не пишет (I-DOCGRAPH-OWNED-1)
- `sync-wiki` — human gate, LLM напоминает но не запускает (Q11, §ROLES)
- `id` — immutable: после создания slug НИКОГДА не меняется; переименование = только `name` (Q3)
- Зависимости (`depends`) FROZEN после TaskSpawned — LLM блокирует попытки изменить (Q2, I-GRAPH-DEP-IMMUT-1)
- `SpecExtractor` устарел: везде в wiki и SKILL.md заменить на `WikiSemanticExtractor` (Q6)
- `WikiSnapshotLoader` — единственный разрешённый путь к /wiki/vN/ snapshot (Q18, I-WSL-2)
- `PhaseOrchestrator` использует `SyncWikiExecuted` из EventLog для freshness check (Q19, I-SYNC-FRESHNESS-2)

---

## Изменение 3 — wiki-evolve: новые страницы (8 страниц)

**Цель:** инъестировать `raw/DocGraph Orchestration - Architectural Decisions.md` через wiki-evolve.

### Новые страницы (`page_type: pattern`, `domain: sdd`, если не указано иное)

#### 1. `doc-graph-node` — концепция узла DocGraph

`page_type: idea`, `domain: sdd`

Концепция DocGraph-узла: типы (domain/phase/task), иерархия D→P→T, полная frontmatter-схема (Q9).
Два жизненных цикла: Wiki lifecycle (Draft→Approved = до компиляции) и SDD lifecycle (OPEN→DONE = после sync-wiki).
Таблица полей-владельцев (EventLog-owned vs human-owned, Q7).
Immutable id vs mutable name (Q3).
Scope наследование Phase→Task (Q9, I-SCOPE-IMMUT-1).
Ссылки: `[[sync-wiki]]`, `[[render-wiki]]`, `[[doc-graph-parser]]`.

#### 2. `doc-graph-parser` — парсер frontmatter DSL

`page_type: pattern`, `domain: sdd`

Компонент sync-wiki pipeline: читает wiki-файлы с `type: task|phase`, парсирует frontmatter DSL → `list[DocGraphNode]`.
Игнорирует `type: domain` (не компилируются, Q10).
Валидирует обязательные поля (id, name, type, depends, part_of).
Output: `DocGraphInput = {nodes: list[DocGraphNode], current_projection: EventLogProjection}` (Q17).
Ссылки: `[[doc-graph-validator]]`, `[[plan-manager]]`, `[[doc-graph-node]]`.

#### 3. `doc-graph-validator` — валидатор DAG

`page_type: pattern`, `domain: sdd`

Компонент sync-wiki pipeline: принимает `list[DocGraphNode]` от DocGraphParser.
Enforced проверки v1 (Q15, I-INVARIANT-META-1):
- `I-GRAPH-ACYCLIC-1`: DAG validation (нет циклов в depends/part_of)
- `I-GRAPH-SYNC-1`: reject destructive diffs (удаление узла, изменение deps после spawn)
- `I-GRAPH-DEP-IMMUT-1`: deps frozen after TaskSpawned
Матрица допустимых изменений из Q2 (таблица: Добавить/Rename/Изменить зависимости/Удалить/Изменить parent/Изменить scope).
Ссылки: `[[doc-graph-parser]]`, `[[plan-manager]]`, `[[write-kernel]]`.

#### 4. `sync-wiki` — команда компиляции Wiki → EventLog

`page_type: pattern`, `domain: sdd`

Human gate: явная операция, не авто-триггер (Q11).
Pipeline: `DocGraphParser → DocGraphValidator → PlanManager → WriteKernel`.
Атомарность: `I-GRAPH-SYNC-ATOMIC-1` — все команды emitted или ни одной.
Сериализация: `I-SYNC-SERIAL-1` — нельзя параллельно запускать для одного graph.
Записывает в EventLog: `SyncWikiExecuted {phase_id, event_pos, wiki_files_hash}` (Q19).
Записывает `GraphVersionRecorded` (Q17, I-PM-GRAPHVER-1).
Идемпотентность: PlanManager читает current projection → emit только для diff (Q8).
Ссылки: `[[doc-graph-parser]]`, `[[doc-graph-validator]]`, `[[plan-manager]]`, `[[render-wiki]]`, `[[phase-orchestrator]]`.

#### 5. `render-wiki` — обратная проекция EventLog → Wiki

`page_type: pattern`, `domain: sdd`

Триггер: auto после каждого commit в EventLog (как projection rebuild, Q7).
Atomic directory versioning: `/wiki/tmp_vN/ → fsync → rename → /wiki/vN/ → update pointer` (Q13, I-WIKI-ATOMIC-1).
EventLog-owned поля (что пишет): `status`, `blocked_by` (derived).
Human-owned поля (что НЕ трогает): `id, name, type, depends, part_of, affects, scope`, весь prose (I-WIKI-OWNERSHIP-1).
Modes: `eager` (default, после каждого commit) / `batched` (каждые N events).
GC: `I-WIKI-GC-1` — хранить последние N snapshots (default=10).
Ссылки: `[[wiki-snapshot-loader]]`, `[[sync-wiki]]`, `[[doc-graph-node]]`.

#### 6. `wiki-semantic-extractor` — замена SpecExtractor

`page_type: pattern`, `domain: sdd`

Замена `SpecExtractor` (Q6, I-QE-ADAPTER-1): читает prose из WikiSnapshot, НЕ из файловой системы напрямую.
Навигация: `task → part_of → phase → part_of → domain` (три уровня prose = один контекстный пакет).
Приоритеты контента: P1=task prose, P2=phase prose, P3=domain prose, P4=code context, P5=affects-рёбра.
Scope: если `budget_exceeded` → affects-рёбра пропускаются (Q14).
Input: `WikiSnapshot` (через `WikiSnapshotLoader`).
SSOT: Wiki для семантики; EventLog для структуры (I-GRAPH-SSOT-2).
Ссылки: `[[wiki-snapshot-loader]]`, `[[graph-query-engine]]`, `[[context-kernel]]`, `[[doc-graph-node]]`.

#### 7. `wiki-snapshot-loader` — загрузчик snapshot для ContextKernel

`page_type: pattern`, `domain: sdd`

Единственный компонент, разрешённый для чтения `/wiki/vN/` snapshot (Q18, I-WSL-2).
Интерфейс:
```python
load_at(event_pos: int) -> WikiSnapshot   # I-WSL-1: raises SnapshotNotFound, no fallback
latest() -> WikiSnapshot                  # lag ≤ 1 iteration (I-WIKI-LAG-1)
current_pointer() -> tuple[int, str]      # (event_pos, snapshot_version)
```
AgentLoop контракт (строгий порядок шагов 1–3 из Q18).
I-SNAPSHOT-ALIGN-1: projection snapshot и wiki snapshot MUST быть на одном event_pos.
Ссылки: `[[render-wiki]]`, `[[context-kernel]]`, `[[wiki-semantic-extractor]]`.

#### 8. `docgraph-dual-ssot` — принцип двойного SSOT

`page_type: idea`, `domain: sdd`

Ключевой архитектурный принцип DocGraph (Q1, Q6, Q20):

Lifecycle авторитета:
- ДО sync-wiki: Wiki = SSOT для структуры (единственный источник намерения)
- ПОСЛЕ sync-wiki: EventLog = SSOT для структуры; Wiki = SSOT для семантики

Правило конфликтов (post-sync): EventLog ALWAYS wins для структурных данных.

Три enforcement points (Q20):
1. QueryEngine: `EventExtractor` (structure) + `WikiSemanticExtractor` (semantics) — источники не пересекаются (I-QE-ADAPTER-1/2)
2. PlanManager: только `DocGraphInput` → после компиляции только `EventLogProjection` (I-PM-INPUT-1)
3. ContextKernel: aligned snapshots (I-SNAPSHOT-ALIGN-1)

Declared инварианты: `I-GRAPH-SSOT-2`, `I-NO-DUAL-GRAPH-1`, `I-RUNTIME-NO-WIKI-1`.
Ссылки: `[[sync-wiki]]`, `[[render-wiki]]`, `[[graph-query-engine]]`, `[[plan-manager]]`, `[[context-kernel]]`.

---

## Изменение 4 — wiki-evolve: обновить существующие страницы

### `graph-query-engine` — три адаптера (Q6 + Q16)

Что обновить:
- Заменить формулу: `Graph = f(Code, Specs, EventLog)` → `Graph = f(Code, EventLog, WikiProse)`
- Заменить `SpecExtractor` на `WikiSemanticExtractor` везде
- Добавить явное описание трёх адаптеров с источниками (Q16)
- Обновить fingerprint: `hash(event_offset + wiki_snapshot_version + code_hash)` (retire spec_hash, Q16, I-QE-FINGERPRINT-1)
- Добавить инварианты I-QE-ADAPTER-1/2, I-QE-FINGERPRINT-1
- Ссылки: добавить `[[wiki-semantic-extractor]]`, `[[wiki-snapshot-loader]]`

### `plan-manager` — DocGraph integration (Q12 + Q17)

Что обновить:
- Добавить новый входной шов: `DocGraphInput → PlanManager` (Q17)
- Описать `DocGraphInput = {nodes: list[DocGraphNode], current_projection: EventLogProjection}`
- Добавить матрицу допустимых мутаций (Q2, таблица разрешено/запрещено)
- Добавить `GraphVersion = hash(event_pos)` + `GraphVersionRecorded` event (Q17, I-PM-GRAPHVER-1)
- Отметить: Plan_vN.md/TaskSet_vN.md заменены (I-PM-INPUT-1)
- Ссылки: добавить `[[doc-graph-parser]]`, `[[doc-graph-validator]]`, `[[sync-wiki]]`

### `context-kernel` — WikiSnapshotLoader + закрыть Q75 (Q13 + Q18)

Что обновить:
- Добавить `WikiSnapshotLoader` в `build_base` сигнатуру
- Заменить `SpecExtractor` на `WikiSemanticExtractor` в описании
- Добавить AgentLoop контракт (строгий порядок шагов 1–4, Q18)
- Закрыть Open Question Q75 → Decisions:
  `- [x] (P1) Q75: Context воспроизводим через paired snapshots (event_pos + wiki_snapshot_version = I-SNAPSHOT-ALIGN-1) → [[wiki-snapshot-loader]]`
- Ссылки: добавить `[[wiki-snapshot-loader]]`, `[[wiki-semantic-extractor]]`

### `phase-orchestrator` — freshness guard (Q11 + Q19)

Что обновить:
- Добавить секцию "Sync Freshness Check" при activate-phase
- Описать механизм: читает `SyncWikiExecuted` из EventLog (I-SYNC-FRESHNESS-2), вычисляет current hash
- Описать `PhaseActivationBlocked { reason: "SYNC_FRESHNESS_VIOLATION", stale_files }` (Q19)
- Отсутствие `SyncWikiExecuted` = violation (I-SYNC-FRESHNESS-3)
- Ссылки: добавить `[[sync-wiki]]`

---

## Порядок выполнения

```
1. wiki-evolve raw/DocGraph Orchestration - Architectural Decisions.md
   → создать 8 новых страниц (doc-graph-node, doc-graph-parser, doc-graph-validator,
     sync-wiki, render-wiki, wiki-semantic-extractor, wiki-snapshot-loader, docgraph-dual-ssot)
   → обновить 4 существующих (graph-query-engine, plan-manager, context-kernel, phase-orchestrator)

2. Редактировать .claude/skills/wiki/SKILL.md (прямой Edit):
   a) таблица intent → добавить строку wiki-docgraph
   b) новый раздел ## wiki-docgraph protocol (три режима A/B/C + таблица полей-владельцев)
   c) §INVARIANTS → 8 новых инвариантов (I-DOCGRAPH-FM-1 ... I-WIKI-SNAP-1)
   d) wiki-query → NOTE о DocGraph

3. После apply-drafts:
   wiki finalize --file "raw/DocGraph Orchestration - Architectural Decisions.md"
```

---

## Верификация

```bash
# Новые страницы созданы:
wiki show doc-graph-node
wiki show doc-graph-parser
wiki show doc-graph-validator
wiki show sync-wiki
wiki show render-wiki
wiki show wiki-semantic-extractor
wiki show wiki-snapshot-loader
wiki show docgraph-dual-ssot

# Существующие страницы обновлены:
wiki show graph-query-engine    # WikiSemanticExtractor + три адаптера + новый fingerprint
wiki show plan-manager          # DocGraphInput + GraphVersion + матрица мутаций
wiki show context-kernel        # WikiSnapshotLoader + Q75 закрыт в Decisions
wiki show phase-orchestrator    # SyncWikiExecuted freshness check

# Lint чистый:
wiki lint

# Skill содержит новый протокол:
grep -n "wiki-docgraph" .claude/skills/wiki/SKILL.md
grep -n "I-DOCGRAPH" .claude/skills/wiki/SKILL.md
grep -n "WikiSemanticExtractor" .claude/skills/wiki/SKILL.md

# SpecExtractor полностью заменён:
grep -r "SpecExtractor" /obsidian-vault/llm-wiki/wiki/   # должно вернуть 0 результатов
```
