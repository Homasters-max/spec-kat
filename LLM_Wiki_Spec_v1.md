# LLM Wiki — Spec v1 (DRAFT)

**Status:** DRAFT  
**Author:** Dmitry Katyrev  
**Date:** 2026-04-28  
**Source idea:** [[LLM_Wiki]]

---

## §1 — Цель и контекст

Инструмент для построения и поддержки персональной базы знаний на основе собственных markdown-заметок. Архитектура: **SKILL + CLI** (по образцу SDD).

Ключевой принцип: **максимум автоматизации, минимум LLM**.  
Код делает всё детерминированное. LLM вызывается только для смыслового обновления (extract + synthesize).

---

## §2 — Инварианты

| ID | Формулировка |
|----|--------------|
| I-WIKI-1 | `idea / pattern / tool` = первичные узлы (SSOT, создаются из raw). `synthesis` = вторичный слой (LLM-derived, пересобирается). |
| I-WIKI-2 | diff-first: LLM обновляет страницы через `apply_diff(WikiDiff)`. Full rewrite разрешён только при `page.size < SMALL_PAGE_THRESHOLD` (из wiki_config) или `change_type == "structural"`. `change_type == "structural"` = `diff_ratio > 0.8` (≥80% строк изменилось). Решение принимает `wiki apply-drafts` автоматически, не LLM. ENFORCED: `WikiRepo.save_page()` не существует. Full rewrite = `rewrite_page(id, page, reason: RewriteReason)`. |
| I-WIKI-3 | Glossary обновляется ТОЛЬКО через canonical mapping (I-GLOSSARY-1). Нет дублирующих сущностей. |
| I-WIKI-4 | Extraction НЕ создаёт markdown. Synthesis НЕ добавляет новые сущности, отсутствующие в ExtractionResult. |
| I-GLOSSARY-1 | Одна сущность = одна canonical page. Все алиасы → туда. Glossary = SSOT canonical mapping для известных сущностей. Discovery новых сущностей → через `ExtractionResult.entities` → `glossary_proposals` → явный sync post-action (I-WIKI-DISCOVERY-1). |
| I-WIKI-DISCOVERY-1 | LLM может предлагать новые сущности через `ExtractionResult.entities`. Запись в `glossary.yaml` — только через явный glossary sync в post-action `/wiki-evolve`. Прямая запись в glossary из Stage 1 или Stage 2 ЗАПРЕЩЕНА. |
| I-WIKI-QUALITY-1 | Каждое знание должно периодически пересматриваться (`/wiki-curate`), иначе entropy → рост → деградация. |
| I-WIKI-QUERY-1 | `/wiki-query` НЕ имеет права писать напрямую в SSOT или derived. Запись — только через `/wiki-evolve`. |
| I-TECH-1 | Каждая внешняя зависимость обёрнута в интерфейс (SearchEngine, WikiRepo, LLMClient, GitRepo). |
| I-WIKI-PENDING-1 | Единственный источник "pending" = `GitRepo.pending_files()`. `ingest_log.jsonl` — только audit trail "ingested". `status: "pending"` в `ingest_log` ЗАПРЕЩЁН. |
| I-WIKI-SEAM-1 | Шов Stage 0 → Stage 1 = `ContextPacket`. Прямая передача raw str или dict ЗАПРЕЩЕНА. |
| I-WIKI-EXTRACT-1 | Шов Stage 1 → Stage 2 = `ExtractionResult` (pydantic). LLM output ДОЛЖЕН пройти pydantic валидацию до Stage 2. Невалидный JSON → STOP, не молчаливый fallback. |
| I-WIKI-CONFLICT-1 | При `ApplyResult.conflict=True` → STOP. Conflict разрешается вручную. Автоматический retry запрещён. |

Нарушение любого инварианта → STOP.

---

## §3 — Структура директорий

```
.wiki/
  config/
    wiki_config.yaml       # настройки: domain, llm_model, SMALL_PAGE_THRESHOLD
    glossary.yaml          # Entity Registry (SSOT, I-GLOSSARY-1)
  skills/
    wiki-evolve.md         # session protocol
    wiki-query.md          # session protocol
    wiki-curate.md         # session protocol
  state/
    ingest_log.jsonl       # append-only audit trail: что обработано (dedup)
    query_log.jsonl        # append-only: history queries + insights

raw/                       # SSOT input (immutable, только чтение)
  *.md

wiki/                      # SSOT knowledge
  idea/
  pattern/
  tool/

derived/                   # всё пересобираемое (не SSOT)
  synthesis/
  index.md
  graph.json

runtime/                   # ephemeral
  cache/                   # ContextPacket cache: <sha256>.json
  tmp/                     # extraction.json (ExtractionResult), <page_id>.md (черновики), glossary_pending.yaml
```

**State machine:** git как SSOT состояния.  
- `raw/` = uncommitted → pending для evolve  
- `wiki/` + `derived/` = committed → обработано  
- `ingest_log.jsonl` — audit trail обработанных файлов (только `status: "ingested"`). Dedup-фильтр: `pending = uncommitted raw/ files WHERE sha256 NOT IN ingest_log`.

---

## §4 — Типы страниц wiki

### Первичные (SSOT, I-WIKI-1)

| Тип | Директория | Описание |
|-----|-----------|----------|
| idea | `wiki/idea/` | Атомарная мысль / инсайт |
| pattern | `wiki/pattern/` | Переиспользуемое решение / архитектура |
| tool | `wiki/tool/` | Инструмент / технология |

### Производные (LLM-only, пересобираются)

| Тип | Директория | Описание |
|-----|-----------|----------|
| synthesis | `derived/synthesis/` | Агрегация из idea + pattern (LLM-only; `wiki rebuild` не трогает) |
| index | `derived/index.md` | Навигационный ToC для Claude Code в `/wiki-query` Stage 1: компактный список `id \| type \| title \| updated \| sources` (rebuild) |
| graph | `derived/graph.json` | Граф связей (rebuild; CLI команда `wiki graph` отложена в v2) |

**example** — секция внутри pattern, не отдельный тип.  
**reference** — опционально, если нужно хранить источники.

**Frontmatter страниц (минимальный набор):**
```yaml
---
id: pattern/rag
type: pattern
version: 1          # инкрементируется при каждом apply_diff или rewrite_page
created: 2026-04-28
updated: 2026-04-28
sources: []         # raw/ файлы, из которых извлечено знание
---
```
`version` — основа для дебага эволюции знаний. Не для optimistic lock (это `base_sha256` в WikiDiff).

---

## §5 — Entity Registry (Glossary)

Файл: `.wiki/config/glossary.yaml`

```yaml
- term: "LLM"
  page: "pattern/llm.md"
  aliases: ["large language model", "языковая модель"]
  type: "pattern"

- term: "RAG"
  page: "pattern/rag.md"
  aliases: ["retrieval augmented generation"]
  type: "pattern"
```

**Функции CLI (без LLM):**
1. **Автолинковка** — при ingest CLI заменяет упоминания терминов на `[[ссылки]]`
2. **Нормализация** — алиасы → canonical term → одна сущность
3. **Hints для классификации** — предлагает тип (idea/pattern/tool), LLM принимает финальное решение

**Discovery vs canonical mapping:**  
Glossary = SSOT только для *известных* сущностей. Когда LLM в Stage 1 обнаруживает новую сущность, она попадает в `ExtractionResult.entities` (не в glossary напрямую). После успешного evolve `glossary_proposals` предлагаются для sync. Это предотвращает bottleneck: glossary не требует обновления до ingest.

---

## §6 — CLI команды

```
wiki ingest <file>              # парсит raw → строит и кэширует ContextPacket
wiki ingest --pending           # dry-run: показать список pending файлов (без обработки)
wiki ingest --pending --take 1  # взять один pending файл → ContextPacket в cache
wiki evolve                     # alias: запустить /wiki-evolve skill (документация)
wiki rebuild                    # пересобрать derived/index.md + derived/graph.json (НЕ synthesis)
wiki search <query>             # BM25 по wiki (без LLM; индекс в памяти)
wiki show <id|type>             # показать страницу или список
wiki lint                       # orphan, дубли, broken links (без LLM)
wiki log                        # последние записи ingest_log + query_log
wiki promote <query_id>         # сформировать ContextPacket из promote_suggestion (без re-ingest)
wiki validate-extraction        # pydantic валидация runtime/tmp/extraction.json (I-WIKI-EXTRACT-1)
wiki apply-drafts               # сканирует runtime/tmp/*.md → create/apply_diff/rewrite_page
wiki sync-glossary              # интерактивный review runtime/glossary_pending.yaml → glossary.yaml
wiki curate-apply               # применить план /wiki-curate после dry-run подтверждения
```

### `wiki ingest <file>` — детали

CLI делает до LLM (без API вызовов):
1. Парсит YAML frontmatter
2. Извлекает заголовки H1–H3
3. Разбивает контент на смысловые чанки по заголовкам (→ `content_chunks: list[str]`)
4. Находит `[[wikilinks]]`
5. Lookup в glossary.yaml → автолинковка + нормализация (→ `list[GlossaryHint]`)
6. BM25 search → релевантные страницы wiki (→ `list[SearchResult]` со score)
7. Собирает `ContextPacket` и сериализует в `runtime/cache/<sha256>.json`

Не пишет в `ingest_log.jsonl` — это ответственность `/wiki-evolve` post-action.

### `wiki validate-extraction` — детали

Читает `runtime/tmp/extraction.json`, запускает pydantic валидацию `ExtractionResult`.  
Exit 0 → Stage 2 может начинаться. Exit non-zero → STOP (I-WIKI-EXTRACT-1).

### `wiki apply-drafts` — детали

Сканирует `runtime/tmp/`, для каждого `<page_id>.md`:
1. Если `wiki/<page_id>.md` не существует → `WikiRepo.create_page()`
2. Если `page.size < SMALL_PAGE_THRESHOLD` → `WikiRepo.rewrite_page(reason="small_page")`
3. Если `diff_ratio > 0.8` → `WikiRepo.rewrite_page(reason="structural_change")`
4. Иначе → `WikiRepo.apply_diff()` (default, I-WIKI-2)

При `ApplyResult.conflict=True` → STOP (I-WIKI-CONFLICT-1). После завершения очищает `runtime/tmp/`.

### `wiki rebuild` — детали

Детерминированный, без LLM:
1. Перестраивает `derived/index.md` из frontmatter всех страниц
2. Перестраивает `derived/graph.json` из `[[wikilinks]]`

`derived/synthesis/` — LLM-only, `wiki rebuild` её **не трогает**.

---

## §7 — Skills (session protocols)

### `/wiki-evolve`

**Назначение:** обновление знаний (write path)

```
Stage 0 — CLI (без LLM):
  wiki ingest --pending --take 1  → один ContextPacket (из runtime/cache/ или построить)
                                    ContextPacket содержит: raw_content, content_chunks,
                                    glossary_hints, related_pages
  (wiki ingest --pending без --take = dry-run: показать очередь)

Stage 1 — Extract (LLM, дешёвый):
  Вход: ContextPacket (I-WIKI-SEAM-1)
  Claude Code пишет ExtractionResult в runtime/tmp/extraction.json
  ❌ НЕ пишет markdown (I-WIKI-4)

  wiki validate-extraction        → pydantic валидация ExtractionResult (I-WIKI-EXTRACT-1)
                                    exit non-zero → STOP

  ExtractionResult содержит:
    entities: list[ExtractedEntity]       # включая новые, не в glossary
    relations: list[Relation]
    conflicts: list[ConflictNote]
    glossary_proposals: list[GlossaryProposal]  # новые сущности для sync (I-WIKI-DISCOVERY-1)

Stage 2 — Synthesize (LLM, targeted):
  Вход: ExtractionResult (из runtime/tmp/extraction.json) + существующие страницы
  Claude Code пишет черновики страниц в runtime/tmp/<page_id>.md

  wiki apply-drafts               → CLI решает create/diff/rewrite автоматически (I-WIKI-2)
                                    При conflict=True → STOP (I-WIKI-CONFLICT-1)

Post-actions (CLI, без LLM):
  wiki rebuild
  wiki lint
  git commit
  → запись в ingest_log.jsonl: {file, sha256, ts, status: "ingested"}  ← единственный writer
  → сохранить glossary_proposals в runtime/glossary_pending.yaml (I-WIKI-DISCOVERY-1)
  → сообщить пользователю: "N proposals в glossary_pending.yaml; запустить wiki sync-glossary"
```

### `/wiki-query`

**Назначение:** использование знаний (read-only, I-WIKI-QUERY-1)

```
Stage 0 — CLI:
  wiki search <extracted_terms>   → list[SearchResult] (BM25 со score)
  wiki show <ids>                 → контент страниц

Stage 1 — LLM:
  Вход: вопрос + страницы + index.md
  Выход (structured):
    answer: "..."
    citations: ["[[pattern/X]]", "[[idea/Y]]"]
    insights:
      - type: "gap" | "conflict" | "synthesis"
        note: "..."
        pages: [...]
    promote_suggestion:
      type: "synthesis" | "idea" | "pattern" | null
      reason: "..."
      context_snapshot:   # предварительно сформированный ContextPacket
        content: <answer + insights>
        related_pages: <страницы из Stage 0, уже загружены>
        # → wiki promote <query_id> использует это напрямую, без re-ingest

Post-action (CLI):
  → запись в query_log.jsonl (включая context_snapshot если promote_suggestion != null)

Запись в wiki — ТОЛЬКО через wiki promote <query_id> → /wiki-evolve
```

### `/wiki-curate`

**Назначение:** контроль качества (I-WIKI-QUALITY-1)

```
Stage 0 — CLI:
  wiki lint                → orphan, дубли, broken links
  wiki search <terms>      → кластеры похожих страниц
  query_log.jsonl          → частые вопросы = слабые места

Stage 1 — LLM (dry-run):
  Claude Code формирует план изменений и показывает пользователю:
  - merge дублирующих страниц
  - упрощение/сжатие pattern
  - выявление semantic conflicts
  - удаление мусорных idea
  - реорганизация связей
  ❌ НЕ пишет в wiki/ до подтверждения (человеческий gate)

[human: wiki curate-apply]  ← явное подтверждение обязательно

Stage 2 — Apply (LLM):
  Claude Code пишет черновики в runtime/tmp/<page_id>.md

  wiki apply-drafts        → CLI применяет create/diff/rewrite
  wiki rebuild
  wiki lint
  git commit               ← пользователь запускает вручную после review
```

---

## §8 — Tech stack

```
typer          # CLI framework
pydantic       # LLM structured output (ExtractionResult, все LLM-шовные типы)
pyyaml         # frontmatter + glossary.yaml
regex          # [[wikilinks]], headings, frontmatter parsing
rank_bm25      # search (через SearchEngine interface)
hashlib        # SHA256 для dedup + LLM cache
difflib        # diff/patch для I-WIKI-2 (WikiDiff)
subprocess     # git operations
```

**LLM:** Claude Code как агент (primary). Skill-файлы (`wiki-evolve.md` и др.) — инструкции для Claude Code.  
`LLMClient` из I-TECH-1 — не используется в v1 (Claude Code = агент, не SDK-клиент).  
**Нет:** баз данных, embedding-инфраструктуры, серверов, Anthropic SDK в v1.

### Типы данных

```python
from dataclasses import dataclass
from pydantic import BaseModel
from typing import Literal
from pathlib import Path


# ── Search ────────────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    page: Page
    score: float   # BM25 normalized score 0.0..1.0


# ── Context (Stage 0 → Stage 1 seam, I-WIKI-SEAM-1) ─────────────────────────

@dataclass
class GlossaryHint:
    term: str
    page: str
    aliases: list[str]
    type: str   # "idea" | "pattern" | "tool"

@dataclass
class ContextPacket:
    file: Path
    sha256: str
    raw_content: str
    content_chunks: list[str]          # разбивка по заголовкам H1–H3; LLM выбирает нужные
    glossary_hints: list[GlossaryHint]
    related_pages: list[SearchResult]  # со score


# ── Extraction (Stage 1 → Stage 2 seam, I-WIKI-EXTRACT-1) ───────────────────

class ExtractedEntity(BaseModel):
    term: str
    type: Literal["idea", "pattern", "tool"]
    confidence: float   # 0.0..1.0
    in_glossary: bool   # True = known entity; False = discovery candidate

class Relation(BaseModel):
    from_term: str
    to_term: str
    type: str   # "uses" | "extends" | "conflicts_with" | "implements"

class ConflictNote(BaseModel):
    page: str
    note: str

class GlossaryProposal(BaseModel):
    term: str
    suggested_page: str
    type: Literal["idea", "pattern", "tool"]
    reason: str

class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]
    relations: list[Relation]
    conflicts: list[ConflictNote]
    glossary_proposals: list[GlossaryProposal]  # новые сущности, не в glossary (I-WIKI-DISCOVERY-1)


# ── Wiki write (I-WIKI-2 enforced by type) ────────────────────────────────────

RewriteReason = Literal["small_page", "structural_change"]

@dataclass
class WikiDiff:
    page_id: str
    unified_diff: str   # формат difflib.unified_diff
    base_sha256: str    # sha256 страницы перед патчем (optimistic lock)

@dataclass
class RewriteOp:
    page_id: str
    page: Page
    reason: RewriteReason   # обязателен; запрещает случайный full rewrite (I-WIKI-2)

@dataclass
class ApplyResult:
    success: bool
    conflict: bool      # True → STOP (I-WIKI-CONFLICT-1)
    applied_lines: int
```

### Ключевые интерфейсы (I-TECH-1)

```python
class SearchEngine:
    def index(pages: list[Page]) -> None: ...  # вызывается при старте CLI; индекс ephemeral (в памяти)
    def search(query: str, min_score: float = 0.3) -> list[SearchResult]:
        # все страницы выше порога, отсортированные по score desc
        ...

class WikiRepo:
    # Read
    def load_page(id: str) -> Page: ...
    def list_pages(type: PageType) -> list[Page]: ...
    def page_size(id: str) -> int: ...   # байты; используется для I-WIKI-2 small_page check

    # Write — ТОЛЬКО через типизированные методы (I-WIKI-2)
    def apply_diff(diff: WikiDiff) -> ApplyResult:
        # валидирует base_sha256, применяет patch; default path
        ...
    def create_page(id: str, page: Page) -> None:
        # только для новых страниц (page_id NOT EXISTS)
        ...
    def rewrite_page(op: RewriteOp) -> None:
        # full rewrite только при op.reason = "small_page" | "structural_change" (I-WIKI-2)
        ...

# LLMClient — не используется в v1 (Claude Code = агент, вызывается через Skill)
# Оставлен как интерфейсный контракт для возможного v2 SDK-режима (I-TECH-1)
class LLMClient:
    def extract(packet: ContextPacket) -> ExtractionResult: ...
    def synthesize(extraction: ExtractionResult, pages: list[Page]) -> SynthesisOutput: ...

class GitRepo:
    def pending_files() -> list[Path]:
        # uncommitted raw/ files WHERE sha256 NOT IN ingest_log (I-WIKI-PENDING-1)
        ...
    def commit(message: str, files: list[Path]) -> None: ...
    def diff(file: Path) -> str: ...
```

---

## §9 — Pipeline (полная картина)

```
RAW markdown
    ↓
wiki ingest <file> (CLI)
    ↓ [runtime/cache/<sha256>.json: ContextPacket]
/wiki-evolve (Skill — Claude Code как агент)
    Stage 0: wiki ingest --pending --take 1  → один ContextPacket
    Stage 1: Claude Code читает ContextPacket
             → пишет runtime/tmp/extraction.json (ExtractionResult)
             wiki validate-extraction          → pydantic check; exit non-zero → STOP
    Stage 2: Claude Code читает ExtractionResult + существующие страницы
             → пишет runtime/tmp/<page_id>.md (черновики)
             wiki apply-drafts                 → CLI: create / apply_diff / rewrite_page
                                                 conflict=True → STOP (I-WIKI-CONFLICT-1)
    ↓
wiki rebuild (CLI)                             # index.md + graph.json; НЕ synthesis
    ↓
wiki lint (CLI)
    ↓
git commit
    ↓ [ingest_log.jsonl: {file, sha256, ts, status: "ingested"}]
    ↓ [runtime/glossary_pending.yaml: glossary_proposals для review]
wiki/ (SSOT, committed)

Query path:
/wiki-query → read-only + insights + promote_suggestion (с context_snapshot)
    ↓ [query_log.jsonl: включая context_snapshot]
(optional) wiki promote <query_id>
    → читает context_snapshot из query_log (без re-ingest)
    → передаёт готовый ContextPacket в /wiki-evolve

Maintenance:
/wiki-curate (вручную)
    Stage 1: dry-run план → показать пользователю
    [human: wiki curate-apply]
    Stage 2: Claude Code пишет runtime/tmp/ → wiki apply-drafts → git commit
```

---

## §10 — Открытые вопросы (для следующей итерации)

- [x] Формат frontmatter страниц wiki → §4: id, type, version, created, updated, sources
- [x] Схема `glossary.yaml` — нужна ли версионность записей? → Нет; история через git
- [x] Стратегия батчинга в evolve → один файл за вызов; `--pending --take 1`
- [x] Порог для `/wiki-curate` — когда запускать? → Только вручную в v1
- [x] `wiki graph` → отложено в v2; `derived/graph.json` строится через `wiki rebuild`
- [x] Структура `wiki_config.yaml` → только: `domain`, `llm_model`, `SMALL_PAGE_THRESHOLD`

---

## §11 — Вне скоупа v1

- Web-клипер / PDF / видео-источники
- Embedding-based search
- MCP-сервер
- Multi-user / team wiki
- Автоматический cron-запуск (evolve/curate)
