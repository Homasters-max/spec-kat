# Wiki System: Full Implementation Plan v2

Сводный план: исходный snappy-munching-alpaca.md + решения grill-me сессии.

---

## Контекст

Исправления расхождений между SKILL.md, cli.py и wiki-страницами. Добавлены новые команды и переработана архитектура curate-flow по итогам архитектурного ревью.

---

## Файл 1: `cli.py`

Все изменения за один проход.

### 1.1 Новая команда `wiki finalize`

**Зачем:** Объединяет post-action шаги evolve в одну команду с корректным порядком.

**Интерфейс:**
```bash
wiki finalize --file <raw/path.md> [--message "wiki: ingest filename"]
```
Sha256 вычисляется автоматически из `--file` (не передаётся явно).

**Порядок (строгий):**
```
[1/4] rebuild_all(vault_root)
[2/4] run_lint(...)
      → exit 1 если errors или broken_links (не коммитим грязное состояние)
[3/4] append_ingest_log(vault_root, sha256, file=raw_file)
      → [SKIP] если sha256 уже в логе (идемпотентность)
[4/4] git diff --cached --quiet
      → если нет staged изменений: echo "[SKIP] Nothing to commit — already up to date." → exit 0
      git add <raw_file> wiki/ derived/ .wiki/state/ingest_log.jsonl
      git commit -m <message>   # дефолт: "wiki: ingest {filename}"
      → если git commit падает: ingest_log записан но не закоммичен;
        retry безопасен (mark-ingested идемпотентен)
```

**Добавить после `save_proposals` в cli.py.**

---

### 1.2 Новая команда `wiki clean-tmp`

**Зачем:** Явная очистка `runtime/tmp/` для устранения cross-session contamination (I-WIKI-CLEAN-1).

```python
@app.command(name="clean-tmp")
def clean_tmp(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
    """Remove all files from runtime/tmp/ (stale drafts, extraction.json)."""
    vault_root = _resolve_vault(vault)
    tmp = vault_root / "runtime" / "tmp"
    removed = [f for f in tmp.glob("*") if f.is_file()]
    for f in removed:
        f.unlink()
    typer.echo(f"[OK] Removed {len(removed)} file(s) from runtime/tmp/")
```

---

### 1.3 `curate_apply()`: полная переработка

**Зачем:** Текущая реализация не пишет черновики (делает только apply+rebuild). SKILL.md это неверно описывал. Теперь черновики пишет LLM в Stage 1; curate-apply только проверяет, применяет (scoped), запускает lint и cleanup.

**Новый `curate_plan.md` формат (YAML frontmatter):**
```yaml
---
operations:
  - {page_id: wiki-evolve,   op: diff,   rationale: "add missing invariant section"}
  - {page_id: stale-concept, op: delete, rationale: "duplicate of automation-over-llm"}
  - {page_id: new-pattern,   op: create, rationale: "extracted from wiki-query"}
---
## Curation Plan

Человекочитаемое описание планируемых изменений.
```

**Новая логика `curate_apply()`:**

```python
# 1. Прочитать и распарсить план
plan_text = plan_path.read_text(encoding="utf-8")
fm, body = WikiRepo._parse_frontmatter(plan_text)   # переиспользуем существующий парсер
plan_ops = fm.get("operations", [])
if not plan_ops:
    typer.echo("[ERROR] curate_plan.md has no operations in frontmatter.", err=True)
    raise typer.Exit(1)

typer.echo("=== Curate Plan ===")
typer.echo(plan_text)
typer.echo("===================\n")

# 2. Pre-flight: проверить наличие всех требуемых черновиков
missing = [
    f"{op['page_id']}.{op['op']}.md"
    for op in plan_ops
    if op["op"] != "delete"
    and not (tmp_dir / f"{op['page_id']}.{op['op']}.md").exists()
]
if missing:
    typer.echo("[ERROR] Missing draft files:\n" + "\n".join(f"  {m}" for m in missing), err=True)
    raise typer.Exit(1)

# 3. Предупредить о лишних файлах (не блокируем — scoped apply их проигнорирует)
allowed = {f"{op['page_id']}.{op['op']}.md" for op in plan_ops if op["op"] != "delete"}
extra = [f.name for f in tmp_dir.glob("*.md") if f.name not in allowed and f.name != "curate_plan.md"]
if extra:
    typer.echo("[WARN] Unexpected draft files (will be ignored, run 'wiki clean-tmp' to remove):")
    for e in extra:
        typer.echo(f"  {e}")

# 4. Scoped apply (только page_id из плана)
# Примечание: apply_drafts применяет ВСЕ файлы в tmp/.
# Для scoped apply: временно переместить не-allowed файлы или фильтровать через allowed set.
# Реализация: передать allowed_ids в apply_drafts (расширить сигнатуру) либо
# применять операции вручную в цикле по plan_ops.
repo = WikiRepo(vault_root)
results = _apply(vault_root, repo, allowed_ids={op["page_id"] for op in plan_ops if op["op"] != "delete"})
ok = sum(1 for r in results if r.success)
typer.echo(f"[APPLY] {ok}/{len(results)} drafts applied.")

# 5. Вывести инструкции для pending deletes
delete_ops = [op for op in plan_ops if op["op"] == "delete"]
if delete_ops:
    typer.echo("\n[DELETE PENDING] Run manually:")
    for op in delete_ops:
        typer.echo(f"  wiki delete {op['page_id']} --confirm")

# 6. Rebuild
rebuild_all(vault_root)
typer.echo("[REBUILD] derived/ updated.")

# 7. Lint (дифференцированный)
from config import load_config
from lint import run_lint
cfg = load_config(vault_root)
report = run_lint(vault_root, domains=cfg.domains or None, layers=cfg.layers or None)

has_fm_errors = bool(report["errors"])
has_broken    = bool(report["broken_links"])
has_orphans   = len(report["orphans"])

if has_fm_errors:
    typer.echo("[ERROR] Frontmatter errors — fix before git commit:", err=True)
    for e in report["errors"]:
        typer.echo(f"  {e['page_id']}: {e['message']}", err=True)
    raise typer.Exit(1)   # НЕ удаляем curate_plan.md — нужен для диагностики

if has_broken:
    typer.echo(f"[WARN] {len(report['broken_links'])} broken link(s) — expected if 'delete' ops pending.")
    typer.echo("       Run 'wiki delete <page_id> --confirm' for each, then 'wiki lint'.")
elif has_orphans:
    typer.echo(f"[WARN] {has_orphans} orphan(s) — run 'wiki lint' for details.")
else:
    typer.echo("[OK] Lint passed.")

# 8. Cleanup curate_plan.md после успеха (если lint прошёл без FM errors)
plan_path.unlink(missing_ok=True)
typer.echo("[CLEAN] curate_plan.md removed.")
```

**Важно: расширить сигнатуру `apply_drafts()` в apply.py:**
```python
def apply_drafts(vault_root: Path, repo: WikiRepo, allowed_ids: set[str] | None = None) -> list[ApplyResult]:
    # Фильтровать draft_files: если allowed_ids задан, включать только matching page_id
    if allowed_ids is not None:
        draft_files = [(pid, op, path) for pid, op, path in draft_files if pid in allowed_ids]
```

---

### 1.4 `curate_apply()`: pre-check на наличие черновиков (упрощённый из плана п.7)

Уже включён в 1.3 как шаг 2 (pre-flight missing check). Отдельно реализовывать не нужно.

---

### 1.5 `init_vault()`: добавить `--domains` и `--layers`

**Зачем:** Без них новые vaults создаются без `domains`/`layers` в конфиге → lint молча пропускает domain/layer validation.

```python
domains: str = typer.Option("personal,general", "--domains",
    help="Comma-separated allowed domains (e.g. 'wiki,llm,sdd')"),
layers: str = typer.Option("concept,architecture,implementation", "--layers",
    help="Comma-separated allowed layers"),
```

В конфиг добавить:
```python
"domains": [d.strip() for d in domains.split(",") if d.strip()],
"layers":  [l.strip() for l in layers.split(",")  if l.strip()],
```

`--domain` (singular) оставить как есть — обязательное поле `WikiConfig.domain: str`.

---

### 1.6 `status()`: добавить lint-summary

В конец функции `status`:
```python
try:
    from config import load_config
    from lint import run_lint
    cfg = load_config(vault_root)
    report = run_lint(vault_root, domains=getattr(cfg, "domains", None) or None,
                                   layers=getattr(cfg, "layers", None) or None)
    n_orphans = len(report["orphans"])
    n_broken  = len(report["broken_links"])
    n_errors  = len(report["errors"])
    health = "OK" if not (n_broken or n_errors) else "ISSUES"
    typer.echo(f"Wiki health       : {health}  (orphans={n_orphans}, broken={n_broken}, errors={n_errors})")
except Exception:
    typer.echo("Wiki health       : (lint unavailable)")
```

---

## Файл 2: `.gitignore` (в vault root)

Добавить (или создать):
```
.wiki/state/query_log.jsonl
.wiki/config/glossary_pending.yaml
runtime/cache/
```

**Обоснование:**
- `query_log.jsonl` — эфемерное state, lifecycle отличен от ingest
- `glossary_pending.yaml` — временный буфер до `wiki sync-glossary`
- `ingest_log.jsonl` — в git (коммитится через `wiki finalize`)

---

## Файл 3: `SKILL.md`

### 3.1 wiki-evolve protocol — полный новый текст

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
  Analyse content_chunks, glossary_hints, related_pages.

  IMPORTANT: ensure runtime/tmp/ exists before writing:
    mkdir -p <vault>/runtime/tmp/

  Write runtime/tmp/extraction.json conforming to ExtractionResult schema.

  → user runs: wiki validate-extraction
    exit non-zero → STOP, fix extraction.json and retry

  → user runs: wiki save-proposals   ← только если glossary_proposals > 0 (I-WIKI-SEQ-1)

Stage 2 (LLM):
  Read ExtractionResult from runtime/tmp/extraction.json.
  For each entity choose operation: create / diff / rewrite
  Write draft files to runtime/tmp/.

  → user runs: wiki apply-drafts
    conflict → STOP, resolve manually then retry

Post-action (CLI):
  wiki finalize --file <raw/path.md>   ← выполняет: rebuild → lint → mark-ingested → git commit
  wiki sync-glossary                   ← интерактивный, пользователь вручную
                                          (.wiki/config/glossary_pending.yaml)
```

### 3.2 wiki-curate protocol — полный новый текст

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

### 3.3 §INVARIANTS — добавить две строки

```
I-WIKI-CONFLICT-1  apply-drafts завершается exit 1 на первом конфликте (SHA256 mismatch или
                   страница не найдена); применённые черновики НЕ откатываются; пользователь
                   разрешает конфликт вручную и перезапускает apply-drafts
I-WIKI-QUERY-1     wiki-query НЕ ДОЛЖЕН писать в wiki/ или .wiki/config/; разрешены только
                   log-query и promote (оба пишут в .wiki/state/)
```

### 3.4 I-WIKI-SEQ-1 — обновить

```
# Было:
I-WIKI-SEQ-1  ingest → extraction → validate → drafts → apply → rebuild → lint → commit → mark-ingested → [save-proposals] → [sync-glossary]

# Стало:
I-WIKI-SEQ-1  ingest → extraction → validate → [save-proposals если proposals>0] → drafts → apply-drafts → finalize(rebuild→lint→mark-ingested→commit) → [sync-glossary]
```

---

## Файл 4: `wiki-evolve.md`

**Путь:** `obsidian-vault/llm-wiki/wiki/pattern/wiki-evolve.md`

Изменения:
- Step 0: добавить `wiki status` + `wiki clean-tmp` перед Stage 0
- Stage 1: добавить `wiki save-proposals` после `wiki validate-extraction`
- Post-action: заменить `rebuild + lint + git commit + mark-ingested + save-proposals` на `wiki finalize --file <path>` (shortcut)
- Обновить `version` и `updated`

---

## Файл 5: `wiki-curate.md`

**Путь:** `obsidian-vault/llm-wiki/wiki/pattern/wiki-curate.md`

Изменения:
- Stage 0: `cat .wiki/state/query_log.jsonl` → `wiki log --n 50`
- Stage 1: LLM пишет `curate_plan.md` (YAML frontmatter) + черновики в одном шаге
- Убрать Stage 1.5 (слияние с Stage 1)
- Один HUMAN GATE: перед `wiki curate-apply`, на основе просмотра реальных черновиков
- Stage 2: исправить описание `curate-apply` (не пишет черновики; выполняет pre-flight, scoped apply, lint, cleanup)
- Обновить `version` и `updated`

---

## Файл 6: `wiki-cli.md`

**Путь:** `obsidian-vault/llm-wiki/wiki/tool/wiki-cli.md`

Изменения:
- `wiki evolve`: "подсказка-указатель; выводит инструкцию запустить /wiki skill; НЕ автоматизирует pipeline"
- Добавить: `wiki finalize --file <path> — post-action shortcut: rebuild → lint → mark-ingested → git commit`
- Добавить: `wiki clean-tmp — удаляет все файлы из runtime/tmp/ (stale drafts, extraction.json)`
- Обновить: `wiki curate-apply` — "проверяет наличие черновиков (pre-flight), scoped apply по curate_plan.md frontmatter, дифференцированный lint"
- Обновить: `wiki init` — добавить `--domains` и `--layers`
- Обновить `version` и `updated`

---

## Порядок выполнения

1. **`apply.py`** — расширить `apply_drafts(allowed_ids=None)`
2. **`cli.py`** — всё за один проход: finalize, clean-tmp, curate-apply (новая логика), init (--domains/--layers), status (lint summary)
3. **`.gitignore`** — добавить исключения
4. **`SKILL.md`** — wiki-evolve + wiki-curate + §INVARIANTS + I-WIKI-SEQ-1
5. **`wiki-evolve.md`** — обновление страницы
6. **`wiki-curate.md`** — обновление страницы
7. **`wiki-cli.md`** — обновление страницы
8. **Верификация** — (см. ниже)

---

## Исправления (post-implementation)

### Bugfix: конфликт переменной `name` в `init_vault()`

**Файл:** `cli.py`, функция `init_vault()`

**Проблема:** Loop-переменная `for name in ("ingest_log.jsonl", "query_log.jsonl"):`
затирала параметр функции `name: Optional[str]` (флаг `--name`). После цикла
`name == "query_log.jsonl"` вместо значения, переданного пользователем, поэтому
vault регистрировался под именем `"query_log.jsonl"` независимо от `--name`.

**Исправление:** переименовать loop-переменную в `log_name`.

```python
# было:
for name in ("ingest_log.jsonl", "query_log.jsonl"):
    p = vault_root / ".wiki" / "state" / name

# стало:
for log_name in ("ingest_log.jsonl", "query_log.jsonl"):
    p = vault_root / ".wiki" / "state" / log_name
```

---

## Верификация

```bash
cd /root/project/obsidian-vault/llm-wiki

# 1. SKILL.md корректно содержит новые инварианты
grep -n "I-WIKI-CONFLICT-1\|I-WIKI-QUERY-1\|I-WIKI-SEQ-1\|I-WIKI-CLEAN-1" \
  /root/project/.claude/skills/wiki/SKILL.md

# 2. Новые CLI-команды
wiki --help           # должны быть: finalize, clean-tmp
wiki finalize --help  # --file обязателен, нет позиционного sha256
wiki clean-tmp --help

# 3. curate-apply без черновиков → [ERROR]
wiki curate-apply     # должна выдать [ERROR] curate_plan.md has no operations (или not found)

# 4. init с новыми флагами
wiki init --vault /tmp/test-vault --name test-vault \
  --domains "wiki,llm" --layers "concept,architecture" --force
grep -E "domains|layers" /tmp/test-vault/.wiki/config/wiki_config.yaml

# 5. Lint на vault после обновления wiki-страниц
wiki rebuild && wiki lint   # exit 0 обязателен
```

---

## Схема изоляции сессий (итог)

| Сессия | Механизм изоляции |
|--------|------------------|
| wiki-evolve | `wiki clean-tmp` перед Stage 1 (явный, I-WIKI-CLEAN-1) |
| wiki-curate | scoped apply по frontmatter `curate_plan.md` (структурная) |
| Смешанная | curate-apply игнорирует файлы чужих page_id; WARN предупреждает |

## Git-стратегия state-файлов

| Файл | Git |
|------|-----|
| `ingest_log.jsonl` | в git (коммитится через `wiki finalize`) |
| `query_log.jsonl` | в `.gitignore` (эфемерное state) |
| `glossary_pending.yaml` | в `.gitignore` (временный буфер) |
| `runtime/cache/` | в `.gitignore` (автогенерат) |
