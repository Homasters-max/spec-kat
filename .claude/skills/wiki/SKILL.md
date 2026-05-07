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

---

## wiki-evolve protocol

Process a pending raw file through the full ingest → extract → apply pipeline.

```
Step 0 (опционально):
  wiki status          → проверить наличие стейл-черновиков в runtime/tmp/
  wiki clean-tmp       ← если остались файлы от предыдущей сессии (I-WIKI-CLEAN-1)

Stage 0 (CLI):
  wiki ingest --pending --take 1   # из очереди pending (стандартный путь)
  wiki ingest <path>               # конкретный файл (когда пользователь передаёт путь явно)
  → prints ContextPacket path (runtime/cache/<sha256>.json)

Stage 1 (LLM):
  Read ContextPacket from the printed path (use Read tool with the full path).
  Analyse content_chunks (actual text), glossary_hints (known terms),
  and related_pages (existing wiki pages ranked by relevance).

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
    create  → page does not exist   (wiki show <page_id> returns "not found")
    diff    → page exists + small addition + page size > 1000 chars
    rewrite → page exists + structural change OR page size ≤ 1000 chars

  .create.md FORMAT  (key MUST be "page_type", NOT "type"):
    ---
    page_type: pattern
    domain: wiki
    layer: architecture
    tags: [rag, retrieval, llm]
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

  .diff.md FORMAT:
    ---
    base_sha256: <run: sha256sum wiki/<type>/<page_id>.md | awk '{print $1}'>
    ---
    <unified diff in standard patch format>

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

  Step 1 — record in query_log (prints query_id):
    wiki log-query --query "<the user's original question>"

  Step 2 — optionally attach context snapshot:
    wiki log-query --query "<question>" --snapshot /path/to/context.json

  Step 3 — promote to ContextPacket for future wiki-evolve:
    wiki promote <query_id>

  Note: promote_suggestion in LLM output is a SIGNAL to run the above steps —
  not a query_id that already exists. Only wiki log-query writes to query_log.
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
  git add wiki/ derived/ && git commit -m "wiki: curate ..."
  wiki lint                          ← финальная проверка после всех deletes
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
```

---

## §FORMATS

### Рабочий формат `.diff.md` (pure unified diff, I-WIKI-DIFF-1)

```text
---
base_sha256: <sha256sum wiki/type/page-id.md | awk '{print $1}'>
---
--- wiki/pattern/page-id.md
+++ wiki/pattern/page-id.md
@@ -22,4 +22,5 @@
 ## See Also
 - [[existing-link]]
+- [[new-link]]
```

**Генерировать через Bash (безопаснее ручного написания):**

```bash
python3 -c "
import difflib, sys
page = 'wiki/pattern/page-id.md'
old = open(page).readlines()
new = old + ['- [[new-link]]\n']
sys.stdout.writelines(difflib.unified_diff(old, new, fromfile=page, tofile=page))
"
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
