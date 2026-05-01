# Wiki CLI + Skill — Task List

Исходный план(для справки): /root/.claude/plans/hazy-dreaming-peach.md

Детальный список задач для разработки. Порядок строгий: каждый блок зависит от предыдущих.  
Статусы: `[ ]` pending · `[x]` done · `[-]` in progress

---

## Блок 1 — Scaffold

**Цель:** создать структуру директорий и базовые контракты данных.

- [x] **1.1** Создать директорию `.claude/skills/wiki/scripts/`
- [x] **1.2** Создать `scripts/pyproject.toml`:
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
  py-modules = ["cli", "models", "config", "state", "repo", "search", "git", "ingest", "apply", "rebuild", "lint"]
  ```
- [x] **1.3** Создать `scripts/models.py` со всеми контрактами данных:  
  > **Примечание:** файл назван `models.py` вместо `types.py` — `types` конфликтует со stdlib Python и не может быть корректно импортирован даже после `pip install -e .`. Во всех модулях использовать `from models import ...`.
  - `PageType = Literal["idea", "pattern", "tool"]`
  - `GlossaryHint` (dataclass): `term: str`, `page: str`, `aliases: list[str]`, `type: str`
  - `SearchResult` (dataclass): `page_id: str`, `score: float`
  - `ContextPacket` (dataclass): `file: Path`, `sha256: str`, `raw_content: str`, `content_chunks: list[str]`, `glossary_hints: list[GlossaryHint]`, `related_pages: list[SearchResult]`
  - `ExtractedEntity` (pydantic BaseModel): поля по spec §8
  - `Relation` (pydantic BaseModel): поля по spec §8
  - `ConflictNote` (pydantic BaseModel): поля по spec §8
  - `GlossaryProposal` (pydantic BaseModel): поля по spec §8
  - `ExtractionResult` (pydantic BaseModel): `entities`, `relations`, `conflicts`, `glossary_proposals`
  - `WikiDiff` (dataclass): `page_id: str`, `unified_diff: str`, `base_sha256: str`
  - `RewriteReason = Literal["small_page", "structural_change"]`
  - `RewriteOp` (dataclass): `page_id: str`, `page_content: str`, `reason: RewriteReason`
  - `ApplyResult` (dataclass): `success: bool`, `conflict: bool`, `applied_lines: int`
  - `IngestLogEntry` (dataclass): `sha256: str`, `file: str`, `ts: str`, `packet_path: str`
  - `QueryLogEntry` (dataclass): `query_id: str`, `query: str`, `ts: str`, `context_snapshot: dict`

---

## Блок 2 — config.py

**Зависимости:** types.py  
**Цель:** загрузка конфигурации vault'а, чтение/запись glossary.

- [x] **2.1** Создать `scripts/config.py`:
  - `WikiConfig` (pydantic BaseModel): `domain: str`, `llm_model: str`, `small_page_threshold: int`, `vault_root: Path`
  - `load_config(vault_root: Path) -> WikiConfig` — читает `.wiki/config/wiki_config.yaml`
  - `load_glossary(vault_root: Path) -> list[dict]` — читает `.wiki/config/glossary.yaml`
  - `save_glossary_pending(vault_root: Path, proposals: list[GlossaryProposal])` — единственный writer `glossary_pending.yaml` (I-WIKI-DISCOVERY-1)
- [x] **2.2** Убедиться, что `save_glossary_pending` не трогает `glossary.yaml` напрямую — только `glossary_pending.yaml`

---

## Блок 3 — state.py

**Зависимости:** types.py  
**Цель:** персистентные логи операций.

- [x] **3.1** Создать `scripts/state.py`:
  - `append_ingest_log(vault_root: Path, entry: IngestLogEntry)` — дописывает в `.wiki/state/ingest_log.jsonl`
  - `read_ingest_log(vault_root: Path) -> list[IngestLogEntry]` — читает весь файл
  - `append_query_log(vault_root: Path, entry: QueryLogEntry)` — дописывает в `.wiki/state/query_log.jsonl`
  - `read_query_log(vault_root: Path) -> list[QueryLogEntry]` — читает весь файл
- [x] **3.2** Формат каждой строки — JSON, одна запись на строку (jsonlines)

---

## Блок 4 — git.py

**Зависимости:** types.py, state.py  
**Цель:** обнаружение необработанных файлов через git + коммит.

- [x] **4.1** Создать `scripts/git.py` с классом `GitRepo(vault_root: Path)`:
  - `pending_raw_files() -> list[Path]`:
    - uncommitted файлы в `raw/` (git status: untracked + modified)
    - исключить те, чей sha256 уже есть в `ingest_log` (I-WIKI-PENDING-1)
  - `commit(message: str, files: list[Path])` — `git add <files>` + `git commit -m message`
- [x] **4.2** sha256 вычислять через `hashlib.sha256` от содержимого файла

---

## Блок 5 — repo.py

**Зависимости:** types.py  
**Цель:** все операции изменения страниц wiki — только через WikiRepo.

- [x] **5.1** Создать `scripts/repo.py` с классом `WikiRepo(vault_root: Path)`:
  - `load_page(page_id: str) -> str | None` — читает `wiki/<type>/<page_id>.md`, ищет по всем типам
  - `list_pages(type: PageType | None = None) -> list[str]` — перечисляет page_id из `wiki/`
  - `page_size(page_id: str) -> int` — количество символов страницы
  - `create_page(page_id: str, page_type: PageType, content: str) -> ApplyResult` — создаёт файл; ошибка если уже существует
  - `apply_diff(diff: WikiDiff) -> ApplyResult` — патчит файл через `difflib.restore` или `patch`; `conflict=True` если патч не применился
  - `rewrite_page(op: RewriteOp) -> ApplyResult` — полная замена содержимого файла
- [x] **5.2** Убедиться, что метода `save_page()` нет нигде (I-WIKI-2)
- [x] **5.3** `page_id` не содержит точек — валидировать на входе в create_page

---

## Блок 6 — search.py

**Зависимости:** types.py  
**Цель:** BM25-поиск по всем страницам wiki.

- [x] **6.1** Создать `scripts/search.py` с классом `SearchEngine(vault_root: Path)`:
  - `build_index()`:
    - читает все `wiki/**/*.md`
    - токенизирует (split по пробелам + lower)
    - строит `BM25Okapi` из `rank_bm25`
    - кэширует корпус в `runtime/cache/bm25_corpus.json` с сохранением mtime файлов
    - при следующем вызове проверяет mtime — перестраивает только если изменилось
  - `search(query: str, top_k: int = 10) -> list[SearchResult]`
- [x] **6.2** `build_index()` вызывать лениво перед первым `search()`

---

## Блок 7 — ingest.py + CLI `wiki ingest`

**Зависимости:** types.py, config.py, state.py, search.py  
**Цель:** Stage 0→1 пайплайна — создание ContextPacket из raw-файла.

- [x] **7.1** Создать `scripts/ingest.py`:
  - `make_context_packet(source_path: Path, vault_root: Path) -> ContextPacket` (I-WIKI-SEAM-1):
    - парсит YAML frontmatter
    - извлекает H1-H3 заголовки
    - разбивает на chunks (по заголовкам или фиксированный размер)
    - извлекает `[[wikilinks]]`
    - делает glossary lookup через `load_glossary()`
    - делает BM25 `search()` для related_pages
    - вычисляет sha256 содержимого
  - `cache_context_packet(vault_root: Path, packet: ContextPacket) -> Path` — сериализует в `runtime/cache/<sha256>.json`, возвращает путь
  - `load_context_packet(vault_root: Path, sha256: str) -> ContextPacket` — десериализует из кэша
- [x] **7.2** В `cli.py` добавить команду `wiki ingest`:
  - `wiki ingest <file>` → `make_context_packet` → `cache_context_packet` → печатает summary (sha256, chunks, related)
  - `wiki ingest --pending` → dry-run: печатает список pending файлов (без обработки)
  - `wiki ingest --pending --take N` → берёт N файлов → обрабатывает каждый → кэширует
  - Файлы с sha256 уже в ingest_log → пропускает с `[SKIP] <file>`
  - **НЕ** пишет в ingest_log (это делает post-action в wiki-evolve skill)

---

## Блок 8 — apply.py + CLI apply-команды

**Зависимости:** types.py, repo.py  
**Цель:** Stage 2 пайплайна — применение LLM-черновиков к wiki.

- [x] **8.1** Создать `scripts/apply.py`:
  - `validate_extraction(vault_root: Path) -> ExtractionResult` (I-WIKI-EXTRACT-1):
    - читает `runtime/tmp/extraction.json`
    - вызывает `ExtractionResult.model_validate(data)`
    - при ошибке валидации: печатает детали + `sys.exit(1)`
  - `apply_drafts(vault_root: Path, repo: WikiRepo) -> list[ApplyResult]`:
    1. Сканирует `runtime/tmp/` по шаблону `<page_id>.[create|diff|rewrite].md`
    2. `*.create.md` → `repo.create_page()`
    3. `*.diff.md` → `repo.apply_diff()` (парсит WikiDiff из файла)
    4. `*.rewrite.md` → `repo.rewrite_page()` (парсит RewriteOp, `reason` из YAML frontmatter)
    5. При `ApplyResult.conflict=True` → `sys.exit(1)` немедленно (I-WIKI-CONFLICT-1)
    6. После успешного завершения всех операций — очищает `runtime/tmp/`
- [x] **8.2** Конвенция имён draft-файлов: `page_id` не содержит точек
- [x] **8.3** В `cli.py` добавить:
  - `wiki validate-extraction` → exit 0/1
  - `wiki apply-drafts` → exit 1 при conflict

---

## Блок 9 — rebuild.py + lint.py + CLI

**Зависимости:** types.py, repo.py  
**Цель:** поддержание derived-артефактов и проверка целостности wiki.

- [x] **9.1** Создать `scripts/rebuild.py`:
  - `rebuild_all(vault_root: Path)`:
    - читает frontmatter всех `wiki/**/*.md`
    - генерирует `derived/index.md` — таблица всех страниц (id, type, title, tags)
    - генерирует `derived/graph.json` — граф `[[wikilinks]]` между страницами
    - **не трогает** `derived/synthesis/` (LLM-only зона)
- [x] **9.2** Создать `scripts/lint.py`:
  - `find_orphans(vault_root: Path) -> list[str]` — страницы без входящих ссылок
  - `find_broken_links(vault_root: Path) -> list[tuple[str, str]]` — `[[ссылки]]` на несуществующие страницы
  - `find_duplicates(vault_root: Path) -> list[tuple[str, str]]` — пары страниц с `difflib.SequenceMatcher > 0.85`
  - `run_lint(vault_root: Path) -> dict` — агрегирует все три проверки
- [x] **9.3** В `cli.py` добавить:
  - `wiki rebuild` — запускает `rebuild_all()`
  - `wiki lint` — запускает `run_lint()`, exit 1 если есть проблемы

---

## Блок 10 — cli.py (оставшиеся команды)

**Зависимости:** все предыдущие модули  
**Цель:** полный CLI-интерфейс пользователя.

- [x] **10.1** `wiki search <query>` — `SearchEngine.build_index()` → `search(query)` → numbered ranked list
- [x] **10.2** `wiki show <id|type>`:
  - если аргумент — PageType (`idea`/`pattern`/`tool`) → `repo.list_pages(type)`
  - иначе → `repo.load_page(id)` → вывести содержимое
- [x] **10.3** `wiki log` — последние 20 записей из ingest_log + query_log, объединить по ts desc
- [x] **10.4** `wiki promote <query_id>`:
  - читает `context_snapshot` из query_log по `query_id`
  - конвертирует в `ContextPacket`
  - кэширует через `cache_context_packet()` (I-WIKI-SEAM-1)
- [x] **10.5** `wiki sync-glossary` — интерактивный review `glossary_pending.yaml`:
  - показывает каждый proposal пользователю
  - y/n/edit — принятые записи добавляет в `glossary.yaml`
  - очищает `glossary_pending.yaml` (I-WIKI-DISCOVERY-1)
- [x] **10.6** `wiki curate-apply`:
  - читает `runtime/tmp/curate_plan.md`
  - пишет черновики `runtime/tmp/<page_id>.[op].md`
  - вызывает `apply_drafts()`
- [x] **10.7** `wiki evolve` — печатает: `"Run /wiki skill in Claude Code and choose wiki-evolve"`

---

## Блок 11 — SKILL.md

**Зависимости:** все блоки 1–10  
**Цель:** skill entry point с тремя embedded протоколами для Claude Code.

- [x] **11.1** Создать `.claude/skills/wiki/SKILL.md` с YAML frontmatter:
  ```yaml
  ---
  name: wiki
  description: Personal knowledge base management — evolve, query, or curate wiki pages.
    Use when user wants to add knowledge, answer questions from the wiki, or curate pages.
  ---
  ```
- [x] **11.2** Секция **wiki-evolve protocol**:
  ```
  Stage 0: wiki ingest --pending --take 1  → ContextPacket path
  Stage 1 (LLM): Read ContextPacket → write runtime/tmp/extraction.json (ExtractionResult schema)
                 → user runs: wiki validate-extraction  (exit non-zero → STOP)
  Stage 2 (LLM): Read ExtractionResult + existing pages
                 → write runtime/tmp/<page_id>.[create|diff|rewrite].md
                 → user runs: wiki apply-drafts  (conflict → STOP)
  Post-action:   wiki rebuild → wiki lint → git commit → wiki sync-glossary
  ```
- [x] **11.3** Секция **wiki-query protocol**:
  ```
  Stage 0: wiki search <terms>  → top_k results
           wiki show <ids>      → page contents
  Stage 1 (LLM): synthesize answer + citations + insights + promote_suggestion
  Post-action: user appends to query_log via wiki promote <query_id>
  READ-ONLY (I-WIKI-QUERY-1)
  ```
- [x] **11.4** Секция **wiki-curate protocol**:
  ```
  Stage 0: wiki lint → wiki search <terms> → query_log.jsonl
  Stage 1 (LLM, dry-run): write runtime/tmp/curate_plan.md → show user [HUMAN GATE]
  [human: wiki curate-apply]
  Stage 2 (LLM): write runtime/tmp/<page_id>.[op].md → wiki apply-drafts → wiki rebuild
  git commit  ← пользователь вручную
  ```

---

## Блок 12 — Smoke Test

**Цель:** убедиться, что весь стек работает end-to-end.

- [x] **12.1** Установить пакет: `pip install -e /root/project/.claude/skills/wiki/scripts/`
- [x] **12.2** Подготовить testwiki:
  ```bash
  mkdir -p /tmp/testwiki/{raw,wiki/{idea,pattern,tool},derived,runtime/{cache,tmp},.wiki/{config,state}}
  printf "domain: test\nllm_model: claude-sonnet-4-6\nsmall_page_threshold: 1000\nvault_root: /tmp/testwiki" \
    > /tmp/testwiki/.wiki/config/wiki_config.yaml
  echo "[]" > /tmp/testwiki/.wiki/config/glossary.yaml
  touch /tmp/testwiki/.wiki/state/ingest_log.jsonl
  cd /tmp/testwiki && git init
  printf "# Test note\nRAG is a retrieval technique." > raw/test1.md
  ```
- [x] **12.3** Проверить `wiki ingest --pending` — показывает `test1.md`
- [x] **12.4** Проверить `wiki ingest raw/test1.md` — создаёт `runtime/cache/<sha256>.json`
- [x] **12.5** Проверить `wiki search "retrieval"` — находит test1.md
- [x] **12.6** Проверить `wiki rebuild` — создаёт `derived/index.md` + `derived/graph.json`
- [x] **12.7** Проверить `wiki lint` — no errors
- [x] **12.8** Mock validate-extraction:
  ```bash
  echo '{"entities":[],"relations":[],"conflicts":[],"glossary_proposals":[]}' \
    > runtime/tmp/extraction.json
  wiki validate-extraction  # exit 0
  ```

---

## Инварианты (справочно)

| Инвариант | Где соблюдается |
|-----------|-----------------|
| I-WIKI-1 | `types.py`: `PageType`, структура директорий |
| I-WIKI-2 | `repo.py`: нет метода `save_page()` |
| I-WIKI-SEAM-1 | `ingest.py`: `make_context_packet` — единственный конструктор `ContextPacket` |
| I-WIKI-EXTRACT-1 | `apply.py`: `validate_extraction` → pydantic + `sys.exit(1)` |
| I-WIKI-CONFLICT-1 | `apply.py`: `apply_drafts` → стоп на первом конфликте |
| I-WIKI-DISCOVERY-1 | `config.py`: `save_glossary_pending`; `sync-glossary` — единственный writer `glossary.yaml` |
| I-WIKI-PENDING-1 | `git.py`: `pending_raw_files` = uncommitted raw/ WHERE sha256 NOT IN ingest_log |
| I-WIKI-QUALITY-1 | `SKILL.md`: `/wiki-curate` протокол |
| I-WIKI-QUERY-1 | `SKILL.md`: wiki-query = read-only |
