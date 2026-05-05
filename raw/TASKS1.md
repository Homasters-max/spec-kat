# Wiki Skill — Task Set (доработка)

Статусы: `[ ]` pending · `[x]` done · `[-]` in progress

## `[x]` T-01: apply.py — fix validate_extraction() mkdir

**Файл:** `scripts/apply.py`  
**Строки:** 26-31 (функция `validate_extraction`)

Добавить `tmp_dir.mkdir(parents=True, exist_ok=True)` перед проверкой файла.

```python
def validate_extraction(vault_root: Path) -> ExtractionResult:
    tmp_dir = vault_root / "runtime" / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)          # ← добавить
    extraction_path = tmp_dir / "extraction.json"
    if not extraction_path.exists():
        ...
```

**Проверка:** `rm -rf runtime/tmp && wiki validate-extraction` → должен создать tmp/ и вернуть "[ERROR] extraction.json not found" (не FileNotFoundError).

---

## `[x]` T-02: cli.py — добавить `wiki mark-ingested`

**Файл:** `scripts/cli.py`  
**Позиция:** после `_ingest_one()` (строка 83), перед `@app.command(name="validate-extraction")`

```python
@app.command(name="mark-ingested")
def mark_ingested(
    sha256: str = typer.Argument(..., help="SHA256 of the ingested file"),
    file: str = typer.Option("", "--file", help="Original file path (for log record)"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Record a file as ingested in ingest_log (run after full wiki-evolve cycle)."""
    import datetime
    from models import IngestLogEntry
    from state import append_ingest_log, read_ingest_log

    vault_root = _resolve_vault(vault)
    known = {e.sha256 for e in read_ingest_log(vault_root)}
    if sha256 in known:
        typer.echo(f"[SKIP] {sha256[:8]} already in ingest_log.")
        return

    cache_path = vault_root / "runtime" / "cache" / f"{sha256}.json"
    entry = IngestLogEntry(
        sha256=sha256,
        file=file or sha256,
        ts=datetime.datetime.utcnow().isoformat(),
        packet_path=str(cache_path),
    )
    append_ingest_log(vault_root, entry)
    typer.echo(f"[OK] Marked {sha256[:8]} as ingested.")
```

**Проверка:** `wiki mark-ingested <sha256>` → `wiki log --n 3` показывает тип "ingest".  
Повторный вызов → "[SKIP] ... already in ingest_log".

---

## `[x]` T-03: cli.py — добавить `wiki log-query`

**Файл:** `scripts/cli.py`  
**Позиция:** после `promote` (строка 266), перед `@app.command(name="sync-glossary")`

```python
@app.command(name="log-query")
def log_query(
    query: str = typer.Option(..., "--query", help="The query text to record"),
    snapshot: Optional[Path] = typer.Option(None, "--snapshot", help="Path to JSON file with context_snapshot"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Record a query in query_log and print the generated query_id."""
    import datetime
    import json
    import uuid

    from models import QueryLogEntry
    from state import append_query_log

    vault_root = _resolve_vault(vault)

    context_snapshot: dict = {}
    if snapshot is not None:
        snap_path = snapshot if snapshot.is_absolute() else Path.cwd() / snapshot
        if not snap_path.exists():
            typer.echo(f"Snapshot file not found: {snap_path}", err=True)
            raise typer.Exit(1)
        try:
            context_snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            typer.echo(f"Invalid JSON in snapshot file: {exc}", err=True)
            raise typer.Exit(1)
        if not isinstance(context_snapshot, dict):
            typer.echo("Snapshot file must contain a JSON object (dict).", err=True)
            raise typer.Exit(1)

    query_id = uuid.uuid4().hex[:12]
    ts = datetime.datetime.utcnow().isoformat()
    entry = QueryLogEntry(query_id=query_id, query=query, ts=ts, context_snapshot=context_snapshot)
    append_query_log(vault_root, entry)
    typer.echo(query_id)
```

**Проверка:**  
```bash
QID=$(wiki log-query --query "test query")
echo $QID                    # 12-char hex
wiki log --n 3               # тип "query"
wiki promote $QID            # exit 1: "context_snapshot is empty" — ожидаемо

echo '{"k": "v"}' > /tmp/ctx.json
QID2=$(wiki log-query --query "q2" --snapshot /tmp/ctx.json)
wiki promote $QID2           # [OK] Promoted query ...
```

---

## `[x]` T-04: cli.py — добавить `wiki status`

**Файл:** `scripts/cli.py`  
**Позиция:** после `log_query` (после T-03), перед `@app.command(name="sync-glossary")`

```python
@app.command()
def status(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Show current wiki pipeline state: pending files, tmp drafts, logs."""
    from git import GitRepo
    from state import read_ingest_log, read_query_log

    vault_root = _resolve_vault(vault)

    # Pending raw files
    try:
        repo = GitRepo(vault_root)
        pending = repo.pending_raw_files()
    except Exception:
        pending = []
    typer.echo(f"Pending raw files : {len(pending)}")
    for f in pending[:5]:
        typer.echo(f"  {f.relative_to(vault_root)}")
    if len(pending) > 5:
        typer.echo(f"  ... and {len(pending) - 5} more")

    # runtime/tmp/ contents
    tmp_dir = vault_root / "runtime" / "tmp"
    extraction = tmp_dir / "extraction.json"
    typer.echo(f"extraction.json   : {'EXISTS' if extraction.exists() else 'missing'}")
    drafts = (
        list(tmp_dir.glob("*.create.md"))
        + list(tmp_dir.glob("*.diff.md"))
        + list(tmp_dir.glob("*.rewrite.md"))
    )
    typer.echo(f"Draft files (tmp) : {len(drafts)}")
    for d in drafts[:5]:
        typer.echo(f"  {d.name}")

    # Log summary
    ingest_entries = read_ingest_log(vault_root)
    query_entries = read_query_log(vault_root)
    typer.echo(f"Ingest log entries: {len(ingest_entries)}")
    typer.echo(f"Query log entries  : {len(query_entries)}")
    if ingest_entries:
        last = ingest_entries[-1]
        typer.echo(f"  Last ingest: {last.ts[:19]}  {last.file}")
```

**Проверка:** `wiki status` — без ошибок, выводит все поля.

---

## `[x]` T-05: SKILL.md — расширить Stage 1 wiki-evolve

**Файл:** `SKILL.md`  
**Строки:** 28-40 (блок Stage 1)

Заменить весь блок Stage 1 на расширенный вариант с примером extraction.json, правилами page_id, type guide и порогом уверенности:

```
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
```

---

## `[x]` T-06: SKILL.md — расширить Stage 2 wiki-evolve

**Файл:** `SKILL.md`  
**Строки:** 42-52 (блок Stage 2)

Заменить блок Stage 2 на расширенный вариант с критериями выбора операции, шаблоном страницы (`page_type:` не `type:`!), форматами diff/rewrite и правилом wikilinks:

```
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
    tags: [rag, retrieval, llm]
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
    ---
    reason: structural_change    # or: small_page
    ---
    <full new page content — same structure as .create.md body>

  WIKILINKS: [[page_id]] — no spaces, no extension.
  Each entity in ExtractionResult should appear in at least one wikilink.

  → user runs: wiki apply-drafts
    conflict → STOP, resolve manually then retry
```

---

## `[x]` T-07: SKILL.md — обновить Post-action wiki-evolve

**Файл:** `SKILL.md`  
**Строки:** 54-58 (блок Post-action)

Добавить `wiki mark-ingested <sha256>` последним шагом:

```
Post-action (CLI, run in order):
  wiki rebuild                        ← regenerate derived/index.md + graph.json
  wiki lint                           ← exit 1 if broken links / orphans / duplicates
  git commit                          ← commit raw file + wiki pages together
  wiki sync-glossary                  ← interactive review of glossary_pending.yaml
  wiki mark-ingested <sha256>         ← mark file done; sha256 printed by wiki ingest
```

---

## `[x]` T-08: SKILL.md — исправить wiki-query post-action

**Файл:** `SKILL.md`  
**Строки:** 81-83 (Post-action блок wiki-query)

Заменить broken "promote → saves to query_log" на корректный двухшаговый flow:

```
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

## `[x]` T-09: guide.md — добавить разделы новых команд

**Файл:** `docs/guide.md`

### 9a. Вставить `### wiki mark-ingested` после `### wiki log` (~строка 198):

```markdown
### `wiki mark-ingested` — пометить файл как обработанный

```bash
wiki mark-ingested <sha256>
wiki mark-ingested <sha256> --file raw/my-notes.md
```

Записывает sha256 в `ingest_log.jsonl`. Запускать как **последний шаг** после `git commit` в pipeline wiki-evolve. Только после этого файл перестаёт появляться в `wiki ingest --pending`.

SHA256 печатается командой `wiki ingest` в строке `sha256 : ...`.
```

### 9b. Вставить `### wiki log-query` после `### wiki promote`:

```markdown
### `wiki log-query` — записать запрос в query_log

```bash
wiki log-query --query "что такое RAG pipeline?"
wiki log-query --query "что такое RAG pipeline?" --snapshot /tmp/context.json
```

Выводит сгенерированный `query_id` в stdout. Использовать перед `wiki promote`:

```bash
QID=$(wiki log-query --query "что такое RAG pipeline?")
wiki promote $QID
```

`--snapshot` — путь к JSON-файлу с объектом контекста (`{}`-формат). Если не указан, `context_snapshot = {}` и `wiki promote` вернёт ошибку "context_snapshot is empty".
```

### 9c. Вставить `### wiki status` после `### wiki log-query`:

```markdown
### `wiki status` — состояние pipeline

```bash
wiki status
```

Показывает:
- Количество необработанных файлов в `raw/`
- Наличие `runtime/tmp/extraction.json`
- Черновики в `runtime/tmp/`
- Количество записей в ingest_log и query_log
```

### 9d. Обновить Сценарий 1 (добавить mark-ingested):

В шаге 7 добавить: `wiki mark-ingested <sha256>` — последним, после `git commit`.

### 9e. Обновить Сценарий 2 (wiki-query):

Заменить шаг 4:
```
4. Опционально: `wiki log-query --query "<вопрос>" [--snapshot ctx.json]` → получить `query_id`
5. Опционально: `wiki promote <query_id>` — сохранить контекст для wiki-evolve
```

### 9f. Добавить в таблицу ошибок:

| Симптом | Причина | Решение |
|---------|---------|---------|
| `wiki promote` exit 1 — "context_snapshot is empty" | log-query вызван без --snapshot | повторить с --snapshot |
| `wiki promote` exit 1 — "query_id not found" | неверный query_id | проверить `wiki log --n 50` |

---

## `[ ]` T-10: Инициализировать vault (если не сделано)

**Проверить:**
```bash
ls /root/project/obsidian-vault/.wiki/config/wiki_config.yaml 2>/dev/null \
  && echo "vault OK" || wiki init
```

---

## Порядок выполнения

```
T-01  apply.py mkdir fix      (независимая, начать первой)
T-02  mark-ingested command   (независимая)
T-03  log-query command       (независимая)
T-04  status command          (независимая)
T-05  SKILL.md Stage 1        (независимая)
T-06  SKILL.md Stage 2        (независимая)
T-07  SKILL.md post-action    (зависит от T-02: знать синтаксис mark-ingested)
T-08  SKILL.md wiki-query     (зависит от T-03: знать синтаксис log-query)
T-09  guide.md                (зависит от T-02, T-03, T-04)
T-10  wiki init               (первый шаг если vault не инициализирован)
```

T-01..T-04 можно выполнять параллельно. T-05..T-06 можно выполнять параллельно. T-07..T-09 после T-02..T-04.
