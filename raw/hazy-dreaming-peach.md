# Plan: Wiki CLI + Skill

## Context

Реализация инструмента персональной базы знаний на основе спецификации `/root/project/obsidian-vault/LLM_Wiki_Spec_v1.md`.
Архитектура: Python CLI (`wiki`) + Claude Code skill (`/wiki-evolve`, `/wiki-query`, `/wiki-curate`).

Ключевые принципы: детерминированный CLI без LLM, LLM вызывается только через skill files, git как SSOT pending-state.

Без SDD протоколов, без существующей кодовой базы — новый пакет.

---

## Package Location

Всё, что относится к wiki, живёт внутри skill-директории — отдельного проекта нет.

```
/root/project/.claude/skills/wiki/
  SKILL.md                    # skill entry point + все 3 session протокола
  scripts/                    # Python CLI — файлы напрямую, без вложенного пакета
    pyproject.toml
    cli.py                    # typer app (entry point)
    types.py                  # все dataclass + pydantic модели
    config.py                 # wiki_config.yaml + glossary.yaml
    state.py                  # ingest_log / query_log I/O
    repo.py                   # WikiRepo (I-WIKI-2)
    search.py                 # SearchEngine (BM25)
    git.py                    # GitRepo (I-WIKI-PENDING-1)
    ingest.py                 # Stage 0→1: raw → ContextPacket (I-WIKI-SEAM-1)
    apply.py                  # apply-drafts + validate-extraction
    rebuild.py                # derived/index.md + derived/graph.json
    lint.py                   # orphan / dupe / broken links
```

`scripts/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "wiki-cli"
version = "0.1.0"
dependencies = ["typer>=0.12", "pydantic>=2", "pyyaml", "rank_bm25>=0.2"]

[project.scripts]
wiki = "cli:app"

[tool.setuptools]
py-modules = ["cli", "types", "config", "state", "repo", "search", "git", "ingest", "apply", "rebuild", "lint"]
```

Install: `pip install -e /root/project/.claude/skills/wiki/scripts/`

---

## Step 1 — Scaffold

**Files создаются в `.claude/skills/wiki/scripts/`:**
- `pyproject.toml` (см. выше)
- `types.py`

`types.py` — все контракты данных:
- `PageType = Literal["idea", "pattern", "tool"]`
- `ContextPacket` (dataclass): `file: Path`, `sha256: str`, `raw_content: str`, `content_chunks: list[str]`, `glossary_hints: list[GlossaryHint]`, `related_pages: list[SearchResult]`
- `GlossaryHint` (dataclass): `term, page, aliases, type`
- `SearchResult` (dataclass): `page_id: str`, `score: float`
- `ExtractionResult` (pydantic BaseModel): `entities: list[ExtractedEntity]`, `relations: list[Relation]`, `conflicts: list[ConflictNote]`, `glossary_proposals: list[GlossaryProposal]`
- `ExtractedEntity, Relation, ConflictNote, GlossaryProposal` (pydantic BaseModel) — см. spec §8
- `WikiDiff` (dataclass): `page_id: str`, `unified_diff: str`, `base_sha256: str`
- `RewriteOp` (dataclass): `page_id: str`, `page_content: str`, `reason: RewriteReason`
- `RewriteReason = Literal["small_page", "structural_change"]`
- `ApplyResult` (dataclass): `success: bool`, `conflict: bool`, `applied_lines: int`
- `IngestLogEntry, QueryLogEntry` (dataclass)

---

## Step 2 — Core Interfaces

**Dependency order:** types.py → config.py → state.py → git.py → repo.py → search.py

**`config.py`:**
- `WikiConfig` (pydantic): `domain, llm_model, small_page_threshold: int, vault_root: Path`
- `load_config(vault_root) -> WikiConfig`
- `load_glossary(vault_root) -> list[dict]`
- `save_glossary_pending(vault_root, proposals)` — единственный writer `glossary_pending.yaml` (I-WIKI-DISCOVERY-1)

**`state.py`:**
- `append_ingest_log(vault_root, entry)` / `read_ingest_log(vault_root) -> list[IngestLogEntry]`
- `append_query_log(vault_root, entry)` / `read_query_log(vault_root) -> list[QueryLogEntry]`
- Файлы: `.wiki/state/ingest_log.jsonl`, `.wiki/state/query_log.jsonl`

**`git.py` — `GitRepo`:**
- `pending_raw_files() -> list[Path]` — uncommitted raw/ WHERE sha256 NOT IN ingest_log (I-WIKI-PENDING-1)
- `commit(message: str, files: list[Path])`

**`repo.py` — `WikiRepo`:**
- `load_page(id) -> str | None`
- `list_pages(type=None) -> list[str]`
- `page_size(id) -> int`
- `create_page(id, page_type, content) -> ApplyResult`
- `apply_diff(diff: WikiDiff) -> ApplyResult` — uses difflib; sets `conflict=True` if patch fails
- `rewrite_page(op: RewriteOp) -> ApplyResult`
- **NO `save_page()`** — I-WIKI-2

**`search.py` — `SearchEngine`:**
- `build_index()` — читает wiki/**/*.md, tokenизирует, строит `BM25Okapi` в памяти
- `search(query, top_k=10) -> list[SearchResult]`
- Кэш корпуса: `runtime/cache/bm25_corpus.json` с mtime-инвалидацией

---

## Step 3 — Ingest Pipeline

**`ingest.py`:**
- `make_context_packet(source_path) -> ContextPacket` — парсит frontmatter, H1-H3 заголовки, chunks, wikilinks, glossary lookup, BM25 — единственное место создания ContextPacket (I-WIKI-SEAM-1)
- `cache_context_packet(vault_root, packet) -> Path` — `runtime/cache/<sha256>.json`
- `load_context_packet(vault_root, sha256) -> ContextPacket`

**CLI `wiki ingest`:**
```
wiki ingest <file>            → make_context_packet → cache → print summary
wiki ingest --pending         → dry-run: список файлов
wiki ingest --pending --take N → N файлов → ContextPacket в cache
```
- Пропускает файлы с sha256 уже в ingest_log (`[SKIP]`)
- НЕ пишет в ingest_log (это делает post-action в wiki-evolve skill)

---

## Step 4 — Apply Pipeline

**`apply.py`:**
- `validate_extraction(vault_root) -> ExtractionResult` — читает `runtime/tmp/extraction.json`, вызывает `ExtractionResult.model_validate()`; при ошибке: print + `sys.exit(1)` (I-WIKI-EXTRACT-1)
- `apply_drafts(vault_root, repo) -> list[ApplyResult]`:
  1. Сканирует `runtime/tmp/*.md` по имени файла: `<page_id>.create.md`, `<page_id>.diff.md`, `<page_id>.rewrite.md`
  2. Роутит в `repo.create_page / apply_diff / rewrite_page`
  3. Если `ApplyResult.conflict=True` → STOP (I-WIKI-CONFLICT-1), exit 1
  4. После завершения очищает `runtime/tmp/`

**CLI:**
- `wiki validate-extraction` → exit 0/1
- `wiki apply-drafts` → exit 1 при conflict

Draft filename convention: `<page_id>` не содержит точек. YAML frontmatter в draft файле содержит `reason:` для rewrite-операций.

---

## Step 5 — Rebuild + Lint

**`rebuild.py`:**
- `rebuild_all(vault_root)` → `derived/index.md` (из frontmatter всех страниц) + `derived/graph.json` (из [[wikilinks]])
- НЕ трогает `derived/synthesis/` (LLM-only)

**`lint.py`:**
- `find_orphans(vault_root) -> list[str]`
- `find_broken_links(vault_root) -> list[tuple[str, str]]`
- `find_duplicates(vault_root) -> list[tuple[str, str]]` — `difflib.SequenceMatcher > 0.85`
- `run_lint(vault_root) -> dict` — агрегирует

**CLI:** `wiki rebuild`, `wiki lint` (exit 1 если есть проблемы)

---

## Step 6 — Remaining CLI

| Command | Logic |
|---------|-------|
| `wiki search <query>` | `SearchEngine.build_index()` → `search(query)` → ranked list |
| `wiki show <id\|type>` | если PageType → `list_pages`; иначе `load_page` |
| `wiki log` | последние 20 записей из ingest_log + query_log |
| `wiki promote <query_id>` | читает context_snapshot из query_log → `ContextPacket` → cache (I-WIKI-SEAM-1) |
| `wiki sync-glossary` | интерактивный review glossary_pending.yaml → glossary.yaml (I-WIKI-DISCOVERY-1) |
| `wiki curate-apply` | читает `runtime/tmp/curate_plan.md` → пишет черновики → `apply_drafts` |
| `wiki evolve` | print инструкции: "Run /wiki skill and choose wiki-evolve" |

---

## Step 7 — Skill File

**File:** `/root/project/.claude/skills/wiki/SKILL.md`

```yaml
---
name: wiki
description: Personal knowledge base management — evolve, query, or curate wiki pages.
  Use when user wants to add knowledge, answer questions from the wiki, or curate pages.
---
```

Тело содержит три секции-протокола:

### wiki-evolve protocol (embedded):
```
Stage 0: wiki ingest --pending --take 1  → ContextPacket path
Stage 1 (LLM): Read ContextPacket → write runtime/tmp/extraction.json (ExtractionResult schema)
               → user runs: wiki validate-extraction  (exit non-zero → STOP)
Stage 2 (LLM): Read ExtractionResult + existing pages
               → write runtime/tmp/<page_id>.[create|diff|rewrite].md
               → user runs: wiki apply-drafts  (conflict → STOP)
Post-action: wiki rebuild → wiki lint → git commit
             → save glossary_proposals: wiki sync-glossary
```

### wiki-query protocol (embedded):
```
Stage 0: wiki search <terms>  → top_k results
         wiki show <ids>      → page contents
Stage 1 (LLM): synthesize answer + citations + insights + promote_suggestion
Post-action: user appends to query_log.jsonl via wiki promote <query_id>
READ-ONLY (I-WIKI-QUERY-1)
```

### wiki-curate protocol (embedded):
```
Stage 0: wiki lint → wiki search <terms> → query_log.jsonl
Stage 1 (LLM, dry-run): write runtime/tmp/curate_plan.md → show user [HUMAN GATE]
[human: wiki curate-apply]
Stage 2 (LLM): write runtime/tmp/<page_id>.[op].md → wiki apply-drafts → wiki rebuild
git commit  ← пользователь вручную
```

---

## Invariants Enforcement Map

| Invariant | Enforced In |
|-----------|------------|
| I-WIKI-1 | types.py: `PageType`, directory structure |
| I-WIKI-2 | repo.py: no `save_page()` |
| I-WIKI-SEAM-1 | ingest.py: `make_context_packet` — единственный constructor |
| I-WIKI-EXTRACT-1 | apply.py: `validate_extraction` → pydantic + sys.exit(1) |
| I-WIKI-CONFLICT-1 | apply.py: `apply_drafts` → stop on first conflict |
| I-WIKI-DISCOVERY-1 | config.py: `save_glossary_pending`; `sync-glossary` — единственный writer glossary.yaml |
| I-WIKI-PENDING-1 | git.py: `pending_raw_files` = uncommitted raw/ WHERE sha256 NOT IN ingest_log |
| I-WIKI-QUALITY-1 | SKILL.md: `/wiki-curate` protocol |
| I-WIKI-QUERY-1 | SKILL.md: wiki-query = read-only |

---

## Verification

```bash
# Установка (из корня проекта)
pip install -e /root/project/.claude/skills/wiki/scripts/

# Smoke test
mkdir -p /tmp/testwiki/{raw,wiki/{idea,pattern,tool},derived,runtime/{cache,tmp},.wiki/{config,state}}
printf "domain: test\nllm_model: claude-sonnet-4-6\nsmall_page_threshold: 1000\nvault_root: /tmp/testwiki" \
  > /tmp/testwiki/.wiki/config/wiki_config.yaml
echo "[]" > /tmp/testwiki/.wiki/config/glossary.yaml
touch /tmp/testwiki/.wiki/state/ingest_log.jsonl

cd /tmp/testwiki && git init
printf "# Test note\nRAG is a retrieval technique." > raw/test1.md

wiki ingest --pending          # показывает test1.md
wiki ingest raw/test1.md       # создаёт runtime/cache/<sha256>.json
wiki search "retrieval"        # BM25 search
wiki rebuild                   # derived/index.md + derived/graph.json
wiki lint                      # no errors

# validate-extraction (mock)
echo '{"entities":[],"relations":[],"conflicts":[],"glossary_proposals":[]}' \
  > runtime/tmp/extraction.json
wiki validate-extraction       # exit 0

# Skill: /wiki в Claude Code → выбрать session type
```
