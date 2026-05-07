---
name: wiki
description: Personal knowledge base management — evolve, query, or curate wiki pages.
  Use when user wants to add knowledge, answer questions from the wiki, or curate pages.
---

# Wiki Skill

Choose one of three protocols based on the user's intent:

| Intent | Protocol |
|--------|----------|
| Add or process new knowledge from raw files | **wiki-evolve** |
| Answer a question from the wiki | **wiki-query** |
| Clean up, merge, or restructure existing pages | **wiki-curate** |
| Manage open questions on wiki pages | **wiki-open-questions** |
| Create or edit DocGraph task/phase/domain execution node | **wiki-docgraph** |

---

## wiki-evolve protocol

Process a pending raw file through the full ingest → extract → apply pipeline.

```
Step 0 (опционально):
  wiki status          → проверить наличие стейл-черновиков в runtime/tmp/
  wiki clean-tmp       ← если остались файлы от предыдущей сессии (I-WIKI-CLEAN-1)
  NOTE: finalize не удаляет extraction.json — он выживает между сессиями до явного wiki clean-tmp

Stage 0 (CLI):
  wiki ingest --pending --take 1   # из очереди pending (стандартный путь)
  wiki ingest <path>               # конкретный файл (когда пользователь передаёт путь явно)
  → prints ContextPacket path (runtime/cache/<sha256>.json)

Stage 1 (LLM):
  Read ContextPacket from the printed path (use Read tool with the full path).
  Analyse content_chunks (actual text), glossary_hints (known terms),
  related_pages (existing wiki pages ranked by relevance),
  and all_page_ids (complete list of all pages in the wiki — use to identify gaps).

  IMPORTANT: ensure runtime/tmp/ exists before writing:
    mkdir -p <vault>/runtime/tmp/

  Write runtime/tmp/extraction.json conforming to ExtractionResult schema.

  Example extraction.json:
  {
    "entities": [
      {"term": "rag-pipeline",  "type": "pattern", "confidence": 0.9,  "in_glossary": false},
      {"term": "vector-store",  "type": "tool",    "confidence": 0.85, "in_glossary": true},
      {"term": "retrieval-augmented-generation", "type": "idea", "confidence": 0.95, "in_glossary": false}
    ],
    "relations": [
      {"from_term": "rag-pipeline", "to_term": "vector-store",                    "type": "uses"},
      {"from_term": "rag-pipeline", "to_term": "retrieval-augmented-generation",  "type": "implements"}
    ],
    "conflicts": [
      {"page": "embedding-search", "note": "source prefers cosine; page says dot-product"}
    ],
    "glossary_proposals": [
      {"term": "RAG", "suggested_page": "rag-pipeline", "type": "pattern",
       "reason": "acronym used 5× without definition"}
    ]
  }

  page_id naming rules (MANDATORY):
    kebab-case: lowercase letters, digits, hyphens only
    NO dots  NO spaces  NO underscores
    ✓ "rag-pipeline"   ✗ "RAG_Pipeline"   ✗ "rag.pipeline"

  type guide:
    "idea"    → abstract concept, principle, mental model  ("separation-of-concerns")
    "pattern" → repeatable solution / recipe               ("rag-pipeline", "circuit-breaker")
    "tool"    → concrete technology, library, software     ("postgres", "chroma", "fastapi")

  confidence: include entities ≥ 0.7; omit vague mentions below that
  in_glossary: true ONLY if term appears in glossary_hints from ContextPacket

  → user runs: wiki validate-extraction
    exit non-zero → STOP, fix extraction.json and retry

  → user runs: wiki save-proposals   ← только если glossary_proposals > 0 (I-WIKI-SEQ-1)

Stage 2 (LLM):
  Read ExtractionResult from runtime/tmp/extraction.json.
  For each entity choose operation:

  OPERATION SELECTION:
    Batch-check existence: wiki exists <id1> <id2> ...   (faster than N wiki show calls)
    create  → page does not exist
    diff    → page exists + small addition + page size > 1000 chars
    rewrite → page exists + structural change OR page size ≤ 1000 chars

  SDD CLASSIFICATION RULE (применять когда domain: sdd):

    sdd_layer:
      L0 — определяет физику системы: EventLog, WriteKernel, Guards, CommandBus,
           ProjectionRegistry и их прямые зависимости. Полностью детерминирован,
           нет зависимости от L1/L2.
      L1 — исполняет задачи детерминированно через L0-примитивы. Ephemeral,
           replay-safe, session-scoped.
      L2 — анализирует, предлагает, оптимизирует. Eventual consistency.
           НИКОГДА не мутирует state напрямую.
      null — концепция/паттерн без чёткой привязки к слою

    sdd_domain:
      Core        — владеет инфраструктурой (EventLog, write path, projections)
      Blueprint   — владеет проектной моделью (specs, plans, phases, policy)
      Engine      — владеет runtime исполнения (AgentLoop, execution)
      Intelligence — владеет анализом (metrics, proposals, audit)
      null        — страница не является SDD-компонентом

    Если неоднозначно → [[sdd-component-inventory]] как авторитетный источник
    Если компонент вне SDD-системы → sdd_layer: null, sdd_domain: null

  .create.md FORMAT  (key MUST be "page_type", NOT "type"):
    ---
    page_type: pattern
    domain: sdd
    layer: architecture
    sdd_layer: L1          # L0 | L1 | L2 | null
    sdd_domain: Core       # Core | Blueprint | Engine | Intelligence | null
    tags: [pipeline, enforcement, sdd/l1, sdd/core, domain/sdd]
    sources: ["raw/filename.md"]
    ---
    # RAG Pipeline

    ## Summary
    One-paragraph description.

    ## How It Works
    Steps or mechanics, referencing [[other-page-id]] with wikilinks.

    ## When To Use
    Conditions that make this the right choice.

    ## Trade-offs
    Costs, limitations, gotchas.

    ## See Also
    - [[related-page-id]]

  diff workflow (LLM):
    wiki show <page_id>                                         # читаем текущий контент
    # → пишем runtime/tmp/<page_id>.new.md с полным новым контентом
    wiki gen-diff <page_id> --new-content runtime/tmp/<page_id>.new.md
    # → создаёт runtime/tmp/<page_id>.diff.md, удаляет .new.md автоматически

  .rewrite.md FORMAT:
    <full new page content — same structure as .create.md body>

    WARNING: NO leading frontmatter block (no "reason: structural_change" header).
    Start directly with the page frontmatter (page_type, domain, layer, ...).
    The CLI infers the operation from the filename suffix (.rewrite.md).
    A leading --- block is parsed as FM and overwrites id/domain/layer with empty values.

  WIKILINKS: [[page_id]] — no spaces, no extension.
  Each entity in ExtractionResult should appear in at least one wikilink.

  → user runs: wiki apply-drafts
    conflict → STOP, resolve manually then retry

Post-action (CLI):
  wiki finalize --file <raw/path.md>   ← выполняет: rebuild → lint → mark-ingested → git commit
  wiki sync-glossary                   ← интерактивный, пользователь вручную
                                          (.wiki/config/glossary_pending.yaml)
```

---

## wiki-query protocol

Answer a question using wiki content. **READ-ONLY** (I-WIKI-QUERY-1) — no wiki writes allowed.

```
Stage 0 (CLI):
  wiki search <terms>   → ranked list of top_k page IDs + scores
  wiki show <page_id>   → full page content
  (repeat wiki show for as many pages as needed)

Stage 1 (LLM):
  Synthesise answer from retrieved pages.
  Output must include:
    - answer:             direct response to the user's question
    - citations:          list of page_ids used
    - insights:           new connections or gaps noticed
    - promote_suggestion: query_id to promote if this query reveals reusable knowledge

Post-action (optional, user decision):
  If the query reveals reusable knowledge worth ingesting later:

  Option A — если sha256 пакета известен (стандартный путь в сессии):
    wiki promote --sha256 <sha256>   ← загружает из runtime/cache/ напрямую, без log-query

  Option B — через query_log (когда нужна привязка к тексту запроса):
    Step 1 — record in query_log (prints query_id):
      wiki log-query --query "<the user's original question>"
    Step 2 — optionally attach context snapshot:
      wiki log-query --query "<question>" --snapshot /path/to/context.json
    Step 3 — promote:
      wiki promote <query_id>

  Note: promote_suggestion in LLM output is a SIGNAL to run the above steps —
  not a query_id that already exists. Only wiki log-query writes to query_log.

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

## wiki-docgraph protocol

Создание и редактирование DocGraph-узлов (wiki-файлы с `type: domain|phase|task`). Не путать с wiki knowledge pages (`page_type: idea|pattern|tool`) — схемы frontmatter несовместимы (I-DOCGRAPH-FM-1).

**Таблица типов:**

| `type`   | Префикс ID | Компилируется в EventLog? | Имеет `status`? | Роль                   |
|----------|------------|---------------------------|-----------------|------------------------|
| `domain` | `d-`       | Нет                       | Нет             | Semantic cluster       |
| `phase`  | `p-`       | Да                        | Да              | Execution boundary     |
| `task`   | `t-`       | Да                        | Да              | Atomic work item       |

**Поля-владельцы (критическая таблица):**

| Поле         | Владелец  | LLM может редактировать?          |
|--------------|-----------|-----------------------------------|
| `id`         | Human     | Никогда (immutable slug)          |
| `name`       | Human     | Да (переименование)               |
| `type`       | Human     | Никогда                           |
| `status`     | EventLog  | Никогда (render-wiki пишет)       |
| `blocked_by` | EventLog  | Никогда (render-wiki пишет)       |
| `depends`    | Human     | Только до TaskSpawned             |
| `part_of`    | Human     | Требует DAG проверки              |
| `affects`    | Human     | Да                                |
| `scope`      | Human     | Только до TaskStarted             |

```
РЕЖИМ A — Создание нового execution-узла (task / phase):

  Frontmatter (точная схема):
    ---
    id: t-<slug>         # immutable slug; kebab-case; НИКОГДА не меняется
    name: "Title"        # mutable display name
    type: task           # task | phase
    status: OPEN         # ⛔ EventLog-owned; render-wiki пишет
    blocked_by: []       # ⛔ EventLog-owned; render-wiki пишет
    depends: []          # DAG edges; FROZEN после TaskSpawned
    part_of: p-<id>      # родительская фаза (для task) или домен (для phase)
    affects: []          # traceability hints (P5, lowest priority)
    scope: []            # empty = наследует от phase; FROZEN после TaskStarted
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
    id: d-<slug>
    name: "Domain Name"
    type: domain
    # ЗАПРЕЩЕНЫ поля: status, blocked_by, depends, scope  (I-DOCGRAPH-DOMAIN-2)
    ---

  Prose = архитектурные правила, shared vocabulary, ограничения домена.
  sync-wiki пропускает domain-узлы. render-wiki их не трогает.
  После создания domain → sync-wiki НЕ нужен.

РЕЖИМ C — Редактирование prose существующего узла:

  Прочитать: wiki show <node-id>
  Определить: что изменяется?

  Если изменяется ТОЛЬКО prose (Summary, Acceptance Criteria, Notes):
    → писать runtime/tmp/<node-id>.diff.md — ТОЛЬКО prose секции
    → НЕ ВКЛЮЧАТЬ в diff: status, blocked_by (EventLog-owned)
    → вызывать: wiki apply-drafts
    → sync-wiki НЕ нужен (prose ≠ structure)

  Если изменяются структурные поля (depends / part_of / scope):
    → предупредить: "Структурное изменение после TaskSpawned ЗАПРЕЩЕНО (Q2, I-GRAPH-DEP-IMMUT-1)"
    → depends: нельзя менять после TaskSpawned
    → scope:   нельзя менять после TaskStarted
    → ОБЯЗАТЕЛЬНО напомнить: "sdd sync-wiki — обязателен перед activate-phase"
```

---

## wiki-curate protocol

Identify and fix quality issues in the wiki (orphans, duplicates, structural problems).

```
Stage 0 (CLI):
  wiki lint             → prints orphans, broken links, duplicates
  wiki search <terms>   → find pages related to the curation target
  wiki log --n 50       → review past queries for context (optional)

Stage 1 (LLM):
  Analyse lint output + page contents.

  Write runtime/tmp/curate_plan.md with YAML frontmatter:
    ---
    operations:
      - {page_id: <id>, op: create|diff|rewrite|delete, rationale: "..."}
    ---
    ## Curation Plan
    Human-readable description of planned changes.

  Write all draft files for non-delete operations (same formats as wiki-evolve Stage 2):
    runtime/tmp/<page_id>.create.md
    runtime/tmp/<page_id>.diff.md
    runtime/tmp/<page_id>.rewrite.md

[HUMAN GATE] — user reviews actual drafts:
  wiki status                    → список draft files и wiki health
  cat runtime/tmp/*.diff.md      → конкретные изменения
  user runs: wiki curate-apply

Stage 2 (CLI):
  curate-apply:
    parses curate_plan.md frontmatter (WikiRepo._parse_frontmatter)
    pre-flight: exit 1 если отсутствуют черновики для non-delete операций
    WARN если в tmp/ есть файлы не из плана (не блокируем, scoped apply их проигнорирует)
    scoped apply: только page_id из плана
    [DELETE PENDING]: выводит инструкции для ручного wiki delete --confirm
    rebuild
    lint: exit 1 на FM errors; WARN на broken_links (ожидаемо при pending deletes); WARN на orphans
    cleanup: удаляет curate_plan.md после успеха

Post-action (user):
  wiki delete <page_id> --confirm   ← для каждого op: delete из плана
  wiki commit -m "wiki: curate ..."  ← rebuild → lint → git commit
  wiki lint                          ← финальная проверка после всех deletes
```

---

## wiki-open-questions protocol

Встраивание открытых вопросов inline в существующие страницы wiki. **Не создавать отдельный документ.**

```
Формат блоков — два стандартных блока в КОНЦЕ страницы
(перед ## See Also, или в самом конце если See Also нет):

  ## Open Questions

  - [ ] (P0) Как гарантируется total order EventLog?
  - [ ] (P1) Нужен ли snapshotting для replay оптимизации?

  ## Decisions

  - [x] (P0) EventLog = append-only, total order через event_index → [[eventstore-guard]]

Приоритеты:
  (P0) — ломает систему; ДОЛЖЕН быть закрыт до релиза
  (P1) — ломает фичи
  (P2) — оптимизация, nice-to-have

Три правила:
  1. Вопрос НЕ удаляется — он переносится в Decisions
  2. Решённый вопрос: убрать из Open Questions → добавить в Decisions
     (с приоритетом + утверждение + [[wikilink]])
  3. Все P0 ДОЛЖНЫ быть закрыты перед релизом

Фильтр добавления — вопрос разрешено добавлять только если влияет на:
  - determinism  (воспроизводимость поведения)
  - correctness  (правильность результата)
  - production   (runtime, безопасность, данные)

Формат решения — утверждение, не просто ссылка:
  ❌ - [x] EventLog → [[eventstore-guard]]
  ✓  - [x] (P0) EventLog = append-only, total order через event_index → [[eventstore-guard]]
```

**Workflow — добавление вопроса:**

```
Возник архитектурный вопрос (влияет на determinism/correctness/production)
→ wiki show <page_id>                — найти нужную страницу
→ создать runtime/tmp/<id>.diff.md   — добавить строку в ## Open Questions
   (если блока нет → создать оба блока в конце страницы)
   (если блок есть → только append, не дублировать блок)
→ wiki apply-drafts
```

**Workflow — решение вопроса:**

```
Вопрос решён
→ создать runtime/tmp/<id>.diff.md с двумя изменениями:
   1. удалить строку из ## Open Questions
   2. добавить в ## Decisions: - [x] (PN) <утверждение> → [[wikilink]]
→ wiki apply-drafts
→ если P0 — обновить derived/open-questions.md через wiki-curate
```

**Trigger использования:**

```
Перед изменением любого компонента:
→ wiki show <page_id>
→ проверить ## Open Questions
→ если есть P0 → сначала решить или задокументировать причину откладывания
```

**Обязательные страницы** (добавить Open Questions блок при первой возможности):

```
- event-sourcing     - execution-guard
- reducer            - replay-engine
- context-kernel
```

**Поиск открытых вопросов:**

```bash
# Найти все P0:
grep -r "- \[ \] (P0)" /obsidian-vault/llm-wiki/wiki/

# Найти все открытые вопросы:
grep -r "- \[ \]" /obsidian-vault/llm-wiki/wiki/
```

**Обновление derived/open-questions.md** — через wiki-curate (.rewrite.md) когда:

```
- закрыт или открыт любой P0
- >5 изменений вопросов с последнего обновления
- перед релизом
```

---

## §INVARIANTS

```
I-WIKI-FM-1        Каждый wiki-файл ДОЛЖЕН иметь YAML frontmatter: id, page_type, domain, layer, tags, version, created, updated, sources
I-WIKI-INGEST-1    mark-ingested ДОЛЖЕН вызываться с --file <path>; без него → exit 1
I-WIKI-LINK-1      Каждая entity из ExtractionResult → ≥1 [[wikilink]] в черновиках Stage 2
I-WIKI-DIFF-1      .diff.md — pure unified diff (difflib); ЗАПРЕЩЕНЫ git-style "--- a/..."
I-WIKI-LINT-1      wiki lint exit 0 до git commit
I-WIKI-GLOSSARY-1  glossary_pending.yaml → ВСЕГДА .wiki/config/glossary_pending.yaml
I-WIKI-SEQ-1       Порядок СТРОГИЙ: ingest → extraction → validate → [save-proposals если proposals>0] → drafts → apply-drafts → finalize(rebuild→lint→mark-ingested→commit) → [sync-glossary]
I-WIKI-CLEAN-1     runtime/tmp/ пуст в начале новой wiki-evolve сессии (проверять перед Stage 1)
I-WIKI-DOMAIN-1    domain ∈ wiki_config.domains — lint ERROR
I-WIKI-LAYER-1     layer ∈ wiki_config.layers — lint ERROR
I-WIKI-DELETE-1    wiki delete --confirm: удаляет входящие ссылки + glossary entry + rebuild; lint после → 0 broken links
I-WIKI-MARKUP-1    Callouts (>[!NOTE]) — только в derived/synthesis/; запрещены в wiki/idea|pattern|tool/
I-WIKI-MARKUP-2    Блоки кода ВСЕГДА с языком: ```python, ```yaml, ```json, ```bash; голый ``` запрещён
I-WIKI-MARKUP-3    [[wikilink]] используется только для реальных страниц; для описания синтаксиса — `[[...]]` в backticks
I-WIKI-CONFLICT-1  apply-drafts завершается exit 1 на первом конфликте (SHA256 mismatch или
                   страница не найдена); применённые черновики НЕ откатываются; пользователь
                   разрешает конфликт вручную и перезапускает apply-drafts
I-WIKI-QUERY-1     wiki-query НЕ ДОЛЖЕН писать в wiki/ или .wiki/config/; разрешены только
                   log-query и promote (оба пишут в .wiki/state/)
I-WIKI-OQ-0        ## Open Questions и ## Decisions размещаются в КОНЦЕ страницы — перед ## See Also
                   или в самом конце; ЗАПРЕЩЕНО размещать в середине страницы
I-WIKI-OQ-1        ## Open Questions: формат строк — "- [ ] (P0|P1|P2) <текст>"; строки НЕ
                   удаляются — только переносятся в ## Decisions
I-WIKI-OQ-2        ## Decisions: формат строк — "- [x] (P0|P1|P2) <утверждение> → [[wikilink]]";
                   wikilink обязателен — WARNING если отсутствует
I-DOCGRAPH-FM-1    DocGraph nodes (type: task|phase) MUST use DocGraph frontmatter schema
                   (id/name/type/status/blocked_by/depends/part_of/affects/scope).
                   wiki knowledge schema (page_type/domain/layer/tags) ЗАПРЕЩЕНО смешивать.
                   Lint ERROR если найдены оба schema в одном файле.
I-DOCGRAPH-OWNED-1 Поля status и blocked_by MUST NOT редактироваться вручную.
                   Они EventLog-owned: render-wiki пишет их автоматически (Q7).
I-DOCGRAPH-ID-1    id DocGraph-узла — immutable slug. Переименование = менять поле name.
                   Путь файла в filesystem не влияет на node_id.
I-DOCGRAPH-DOMAIN-1 Узлы type: domain НЕ компилируются в EventLog. PlanManager/sync-wiki
                    их полностью игнорируют. Семантика только: prose для WikiSemanticExtractor.
I-DOCGRAPH-DOMAIN-2 Frontmatter type: domain MUST NOT содержать поля: status, blocked_by,
                    depends, scope. Наличие этих полей = Lint Error.
I-DOCGRAPH-SYNC-1  После изменения структурных полей (depends/part_of/scope) LLM MUST
                   напомнить пользователю: "sdd sync-wiki — обязателен перед activate-phase".
I-DOCGRAPH-PROSE-1 WikiSemanticExtractor читает prose DocGraph-узлов из WikiSnapshot.
                   Prose = источник семантики. EventLog = источник структуры.
                   WikiSemanticExtractor MUST NOT read wiki files directly.
I-WIKI-SNAP-1      wiki-query для DocGraph-контекста: структурные данные (status, deps) —
                   из EventLog (sdd show-state). Prose — из wiki show. ЗАПРЕЩЕНО путать источники.
```

---

## §FORMATS

Форматы, которые LLM пишет вручную: `.create.md` и `.rewrite.md`.  
`.diff.md` генерируется через `wiki gen-diff` — LLM никогда не пишет его вручную (I-WIKI-DIFF-1).

---

## §COMMANDS

| Команда | Описание |
|---------|----------|
| `wiki page-info <page_id>` | Метаданные страницы: path, size, sha256. Выходит 0 даже если страница не найдена. |
| `wiki exists <id1> <id2> ...` | Batch-проверка существования страниц. Быстрее N вызовов `wiki show`. |
| `wiki gen-diff <page_id> --new-content <path>` | Вычисляет diff между текущей страницей и новым файлом → пишет `runtime/tmp/<id>.diff.md`. Удаляет `--new-content` файл после генерации. |
| `wiki commit -m "msg"` | rebuild → lint → git commit. Стейджит только `wiki/`, `derived/`, `ingest_log.jsonl`. Выходит 1 если lint не прошёл. |
| `wiki lint --errors-only` | Выводит только errors + broken_links. Exit 1 если хотя бы одно из них непусто. |
| `wiki lint --json` | Выводит полный report как JSON. |

**`wiki page-info` — пример вывода:**
```text
exists  : true
page_id : wiki-curate
path    : wiki/pattern/wiki-curate.md
size    : 1842
sha256  : d4e5f6...
```

**`wiki exists` — пример вывода:**
```text
page_id                        exists   size
--------------------------------------------------
wiki-curate                    true     1842
wiki-open-questions            false       —
wiki-evolve-protocol           true     3107
```

**`wiki gen-diff` — LLM workflow:**
```bash
wiki show <page_id>                                           # читаем текущий контент
# → пишем runtime/tmp/<page_id>.new.md с полным новым контентом
wiki gen-diff <page_id> --new-content runtime/tmp/<page_id>.new.md
# → создаёт runtime/tmp/<page_id>.diff.md, удаляет .new.md
wiki apply-drafts
```

---

## §TAXONOMY

Теги дополняют `domain`/`layer`, не дублируют их. Максимум 5 семантических тегов + 1 обязательный domain-тег. Kebab-case, английский.

**Domain-тег (обязательный, Obsidian-фильтр):** каждая страница ДОЛЖНА содержать тег `domain/<domain>` (например, `domain/sdd`, `domain/wiki`). Этот тег не входит в лимит 5 семантических тегов. В Obsidian отображается как иерархический тег `domain > sdd` и фильтруется через Tags pane или поиск `#domain/sdd`.

### По домену применения

| Тег | Применение |
|-----|-----------|
| `knowledge-base` | хранение и организация знаний |
| `pipeline` | последовательность обработки данных |
| `cli` | command-line инструменты |
| `search` | механизмы поиска |
| `git` | git workflow |
| `markdown` | работа с markdown |
| `llm` | взаимодействие с LLM |

### По архитектурному слою

| Тег | Применение |
|-----|-----------|
| `seam` | граница между компонентами |
| `ssot` | Single Source of Truth паттерны |
| `automation` | детерминированный код без LLM |
| `validation` | проверка данных, схем |
| `write-path` | пути записи в SSOT |
| `read-only` | readonly операции |
| `dedup` | дедупликация |

### По жизненному циклу знаний

| Тег | Применение |
|-----|-----------|
| `ingestion` | ввод новых знаний |
| `extraction` | извлечение сущностей |
| `maintenance` | поддержка качества |
| `curation` | редактирование |
| `open-questions` | страницы с нерешёнными вопросами |

### По технологии

| Тег | Применение |
|-----|-----------|
| `python` | Python-специфичные концепции |
| `pydantic` | использует pydantic |
| `bm25` | алгоритмы ранжирования |
| `yaml` | конфигурация YAML |

---

## §OBSIDIAN

Стандарт разметки wiki-страниц для совместимости с Obsidian и plain Markdown.

### Блоки кода

Всегда с явным языком — никогда голый ` ``` ` (I-WIKI-MARKUP-2):

```text
```python    # Python код, типы, dataclass
```yaml      # конфиг, frontmatter примеры
```json      # JSON структуры, extraction.json
```bash      # shell команды, CLI вызовы
```sql       # запросы
```toml      # pyproject.toml и аналоги
```text      # вывод команд, plain text примеры
```

### Callouts (I-WIKI-MARKUP-1)

Используются **только** в `derived/synthesis/`. В `wiki/idea|pattern|tool/` — **запрещены**:

```markdown
> [!NOTE] Заголовок
> Содержимое заметки

> [!WARNING] Важно
> Нарушение инварианта

> [!TIP] Совет
> Опциональный совет
```

### Wikilinks (I-WIKI-MARKUP-3)

```markdown
[[page-id]]              # ссылка на страницу wiki
![[page-id]]             # embed — только в derived/synthesis/
```

Для описания синтаксиса wikilinks использовать `` `[[...]]` `` в backticks — никогда bare `[[...]]`.

### Таблицы

Стандартный GFM. Выравнивание — только левое (`:---`):

```markdown
| Колонка 1 | Колонка 2 | Колонка 3 |
|-----------|-----------|-----------|
| значение  | значение  | значение  |
```

### Frontmatter wiki-страниц

```yaml
---
id: pattern/wiki-evolve
page_type: pattern
domain: wiki
layer: architecture
tags: [pipeline, write-path, ingestion, domain/wiki]
version: 1
created: 2026-05-01
updated: 2026-05-01
sources:
  - raw/LLM_Wiki_Spec_v1.md
---
```

| Поле | Кто задаёт | Значения |
|------|-----------|---------|
| `id` | CLI (auto) | `{page_type}/{page_id}` |
| `page_type` | LLM (черновик) | `idea \| pattern \| tool` |
| `domain` | LLM (черновик) | из `wiki_config.domains` |
| `layer` | LLM (черновик) | из `wiki_config.layers` |
| `tags` | LLM (черновик) | kebab-case, ≤5 семантических + `domain/<domain>` обязательно |
| `version` | CLI (auto) | integer, начиная с 1 |
| `created` | CLI (auto при create) | ISO date |
| `updated` | CLI (auto при любом write) | ISO date |
| `sources` | LLM (черновик) | список `raw/*.md` файлов |
