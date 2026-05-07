# Plan: Wiki Skill — 5 New Commands

## Context

Wiki-evolve pipeline требует лишних вызовов CLI и ручной генерации артефактов (diff, sha256, git add). Задача — добавить 5 команд в `cli.py` и расширить существующую `lint`, плюс обновить `SKILL.md`.

Примечание: lint-баг с `[[...]]` внутри code blocks **уже исправлен** в предыдущей сессии.

### Ключевые решения (проработаны в design review)

- `gen-diff` принимает полный новый контент (`--new-content`), а не `--append`. LLM не пишет unified diff вручную — это источник нестабильности. CLI вычисляет diff сам.
- `gen-diff` удаляет промежуточный `.new.md` после успешной генерации.
- `wiki commit` делает `rebuild → lint → commit` (не просто git wrapper). Без этого коммит может зафиксировать невалидное состояние.
- `check-hub` — не отдельная команда. Hub-проверка влита в `wiki lint` как domain-level WARNING.
- `finalize` не трогается — специфична для ingest-flow, рефакторинг через `wiki commit` добавляет риск без пользы.

---

## Файл реализации

Все новые команды — в **`/root/project/.claude/skills/wiki/scripts/cli.py`**.  
Изменения в SKILL.md — в **`/root/project/.claude/skills/wiki/SKILL.md`**.

---

## 1. `wiki page-info <page_id>`

Заменяет два шага: `wiki show` + `sha256sum`.

```python
@app.command(name="page-info")
def page_info(
    page_id: str = typer.Argument(...),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
```

**Логика:**
- `repo._find_page_path(page_id)` — поиск страницы
- Если не найдена: `exists: false`, exit 0 (не exit 1 — это запрос-инфо, не ошибка)
- Если найдена: читаем байты, считаем `hashlib.sha256`, выводим

**Вывод:**
```
exists  : true
page_id : wiki-curate
path    : wiki/pattern/wiki-curate.md
size    : 1842
sha256  : d4e5f6...
```

---

## 2. `wiki gen-diff <page_id> --new-content <path>`

Заменяет inline `python3 -c "import difflib..."`. LLM пишет полный новый контент страницы — CLI вычисляет diff, sha256 и записывает `.diff.md`.

```python
@app.command(name="gen-diff")
def gen_diff(
    page_id: str = typer.Argument(...),
    new_content: Path = typer.Option(..., "--new-content", help="Path to file with full new page content"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
```

**Логика:**
1. `repo.load_page(page_id)` — читаем текущее содержимое; если не найдена → exit 1
2. Читаем `new_content` файл; если не существует → exit 1
3. Вычисляем `base_sha256 = hashlib.sha256(old_content.encode()).hexdigest()`
4. `difflib.unified_diff(old_lines, new_lines, fromfile=path, tofile=path)` — генерируем diff
5. Если diff пустой → `[SKIP] No changes.`, удаляем `new_content` файл, exit 0
6. Форматируем как WikiDiff markdown:
   ```
   ---
   base_sha256: {hex}
   ---
   --- wiki/pattern/wiki-curate.md
   +++ wiki/pattern/wiki-curate.md
   @@ ...
   ```
7. Пишем в `runtime/tmp/{page_id}.diff.md`, печатаем путь
8. **Удаляем `new_content` файл** — промежуточный артефакт, не нужен после генерации

**LLM workflow (Stage 2, diff-операция):**
```
wiki show <page_id>                                          # читаем текущий контент
# → пишем runtime/tmp/<page_id>.new.md с полным новым контентом
wiki gen-diff <page_id> --new-content runtime/tmp/<page_id>.new.md
# → создаёт runtime/tmp/<page_id>.diff.md, удаляет .new.md
wiki apply-drafts                                            # применяем как обычно
```

Покрывает все типы правок: append, хирургические правки в середине, open-questions (удалить из одной секции + добавить в другую).

---

## 3. `wiki commit -m "message"`

Заменяет хрупкий `cd /vault && git add ... && git commit`. Включает rebuild и lint — нельзя коммитить невалидное состояние.

```python
@app.command(name="commit")
def wiki_commit(
    message: str = typer.Option("wiki: update", "--message", "-m"),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
```

**Логика (cwd=vault_root):**
1. **rebuild**: `rebuild_all(vault_root)` — пересобирает `derived/`
2. **lint**: `run_lint(vault_root, ...)` — если `errors` или `broken_links` непусты → печатаем, exit 1
3. **stage**: добавляем только если существуют:
   - `wiki/`
   - `derived/`
   - `.wiki/state/ingest_log.jsonl`
4. `git diff --cached --quiet` → если ничего нет → `[SKIP] Nothing to commit.`, exit 0
5. `git commit -m message` → `[OK] Committed: {message}`

Не трогает source file и `query_log.jsonl` никогда.

**Использование:** wiki-curate, wiki-docgraph, wiki-open-questions flows — везде где `finalize` не подходит (нет raw-файла для mark-ingested).

---

## 4. `wiki exists <id1> <id2> ...`

Batch-проверка перед Stage 2 вместо N последовательных `wiki show`.

```python
@app.command(name="exists")
def exists_cmd(
    page_ids: list[str] = typer.Argument(...),
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
```

**Логика:** для каждого id → `repo._find_page_path(id)`, собираем таблицу.

**Вывод:**
```
page_id                        exists   size
--------------------------------------------------
wiki-curate                    true     1842
wiki-open-questions            false       —
wiki-evolve-protocol           true     3107
```

---

## 5. `wiki lint --errors-only` / `--json` / hub warning

Расширение существующей команды `lint` (строки 203-257 cli.py).

```python
# Добавить параметры в существующую def lint():
errors_only: bool = typer.Option(False, "--errors-only", help="Print only errors and broken links"),
json_output: bool = typer.Option(False, "--json", help="Output full report as JSON"),
```

**`--json`:** `import json; typer.echo(json.dumps(report, indent=2))` — вывод всего report dict и выход.

**`--errors-only`:** выводит только `errors` + `broken_links`, пропускает orphans/warnings/duplicates.  
Exit code: 0 если `errors` и `broken_links` пусты, иначе 1.

**Hub warning (вместо отдельной `check-hub` команды):**  
Добавить в `run_lint()` в `lint.py` domain-level проверку: для каждого домена из конфига — если страниц ≥ 3 и ни одна не содержит тег `role/hub` → добавить в `report["warnings"]`:
```
{"page_id": "<domain>", "message": "No hub page for domain '<domain>'. Add tag 'role/hub' to the overview page."}
```
Выводится в стандартном блоке warnings, не блокирует exit code.

---

## Порядок реализации

1. `page-info` — простой, никаких зависимостей
2. `exists` — простой, никаких зависимостей
3. `lint --errors-only/--json` + hub warning — редактирование существующей функции, тестируем отдельно
4. `gen-diff --new-content` — требует `difflib` + корректное удаление `.new.md`
5. `commit` — rebuild → lint → git; зависит от корректной работы lint (п.3)

Все изменения — в `cli.py` и `lint.py`. Нет изменений в других модулях.

---

## SKILL.md

**Обновить Stage 2 (diff-операция):**
- Убрать: `.diff.md FORMAT` блок с `sha256sum` и `python3 -c "import difflib..."` из `§FORMATS`
- Добавить: новый workflow через `wiki gen-diff --new-content` (см. раздел 2 выше)
- `§FORMATS` оставляет только `.create.md` и `.rewrite.md` — то что LLM пишет сам

**Обновить Stage 2 (operation selection):**
- `wiki exists <id1> <id2> ...` вместо последовательных `wiki show` для проверки существования

**Обновить post-action в wiki-curate и wiki-open-questions:**
- Заменить `git add wiki/ derived/ && git commit -m "..."` на `wiki commit -m "..."`

**Добавить в секцию команд:**
- `wiki page-info <page_id>` с примером вывода
- `wiki gen-diff <page_id> --new-content <path>` с LLM workflow
- `wiki commit -m "msg"` с указанием: делает rebuild → lint → commit
- `wiki exists <id1> <id2>` с примером таблицы
- `wiki lint --errors-only` / `wiki lint --json`

---

## Верификация

1. `wiki page-info existing-page` → строки `exists: true`, `sha256: ...`
2. `wiki page-info nonexistent` → `exists: false`, exit 0
3. `wiki gen-diff existing-page --new-content /tmp/new.md` → файл `runtime/tmp/existing-page.diff.md` с `base_sha256`; `/tmp/new.md` удалён
4. `wiki gen-diff existing-page --new-content /tmp/identical.md` (контент не изменился) → `[SKIP] No changes.`, файл удалён, exit 0
5. `wiki commit -m "test"` при наличии изменений → rebuild + lint pass + commit; не стейджит `query_log.jsonl`
6. `wiki commit -m "test"` при lint errors → exit 1, commit не выполнен
7. `wiki exists page1 nonexistent page2` → таблица с правильными exists/size
8. `wiki lint --json` → валидный JSON с полями `errors`, `broken_links`, `orphans`, `warnings`, `duplicates`
9. `wiki lint --errors-only` → только errors + broken, без orphans/warnings/duplicates
10. `wiki lint` при домене с ≥3 страницами без `role/hub` → WARNING в выводе
