# Wiki System — Task List Phase 2

**Источник:** session-review-2026-05-01.md + архитектурный review  
**Приоритет:** A (критично) → B → C → D → E → F → G  
**Статусы:** `[ ]` pending · `[x]` done · `[-]` in progress

---

## §DECISIONS — Закрытые архитектурные вопросы

| Вопрос | Решение | Обоснование |
|--------|---------|-------------|
| `apply_diff` + version | **Да, инкрементировать** version + обновлять `updated` после успешного patch | Каждое изменение страницы должно быть отслежено; version = единственный способ отличить «трогали» от «не трогали» |
| Dataview vs статика (C3–C5) | **Вариант A — статические таблицы** | Не требует плагина; `wiki rebuild` = детерминированный код без зависимостей; соответствует `automation-over-llm` |
| `save-proposals` — дубли | **skip + warn** | Пользователь мог вручную отредактировать существующий proposal — не перезаписывать |
| `wiki delete` — glossary | **Да, удалять запись** из `glossary.yaml` если `page` совпадает с удаляемой страницей | Иначе glossary ссылается на несуществующий файл — нарушение I-GLOSSARY-1 |
| `domain`/`layer` в lint | **Строгий ERROR** (не warn) | Значения определяются в `wiki_config.yaml`; расширение — через редактирование конфига, не обход lint |
| `tags: []` в lint | **WARNING** (не error) | Пустые теги — качество, не корректность |
| `RewriteOp` расширение | **Отдельные параметры метода**, не поля dataclass | `RewriteOp` — write-операция; метаданные (tags, sources, domain, layer) — отдельный аргумент `meta: PageMeta` |

---

## §OBSIDIAN — Стандарт разметки wiki-страниц

### Блоки кода

Всегда с явным языком — никогда голый ` ``` `:

```
```python    # Python код, типы, dataclass
```yaml      # конфиг, frontmatter примеры
```json      # JSON структуры, extraction.json
```bash      # shell команды, CLI вызовы
```sql       # запросы (если появятся)
```toml      # pyproject.toml и аналоги
```text      # вывод команд, plain text примеры
```

### Callouts (Obsidian-специфичные блоки)

Используются **только** в synthesis и index-страницах. В первичных страницах (idea/pattern/tool) — **запрещены** (портят читаемость вне Obsidian):

```markdown
> [!NOTE] Заголовок
> Содержимое заметки

> [!WARNING] Важно
> Нарушение инварианта

> [!TIP] Совет
> Опциональный совет
```

### Wikilinks

```markdown
[[page-id]]              # ссылка на страницу
[[page-id|Алиас]]        # ссылка с отображаемым текстом — НЕ использовать в wiki/
![[page-id]]             # embed — только в derived/synthesis/
```

**Запрет:** `[[page-id]]` никогда не используется как литеральный текст (описание синтаксиса). Для описания синтаксиса использовать `` `[[...]]` `` в backticks.

### Таблицы

Стандартный GFM. Выравнивание — только левое (`:---`), без центрирования:

```markdown
| Колонка 1 | Колонка 2 | Колонка 3 |
|-----------|-----------|-----------|
| значение  | значение  | значение  |
```

### Frontmatter wiki-страниц (итоговый стандарт)

```yaml
---
id: pattern/wiki-evolve
page_type: pattern
domain: wiki
layer: architecture
tags: [pipeline, write-path, ingestion]
version: 1
created: 2026-05-01
updated: 2026-05-01
sources:
  - raw/LLM_Wiki_Spec_v1.md
---
```

**Поля:**

| Поле | Кто задаёт | Значения |
|------|-----------|---------|
| `id` | CLI (auto) | `{page_type}/{page_id}` |
| `page_type` | LLM (черновик) | `idea \| pattern \| tool` |
| `domain` | LLM (черновик) | из `wiki_config.domains` |
| `layer` | LLM (черновик) | из `wiki_config.layers` |
| `tags` | LLM (черновик) | kebab-case, ≤5, из §TAXONOMY |
| `version` | CLI (auto) | integer, начиная с 1 |
| `created` | CLI (auto при create) | ISO date |
| `updated` | CLI (auto при любом write) | ISO date |
| `sources` | LLM (черновик) | список `raw/*.md` файлов |

### Шаблон черновика `.create.md`

```markdown
---
page_type: pattern
domain: wiki
layer: architecture
tags: [pipeline, write-path]
sources: ["raw/LLM_Wiki_Spec_v1.md"]
---
# Page Title

## Summary
Одно предложение — суть страницы.

## How It Works
Шаги или механика. Ссылки: [[related-page-id]].

```python
# пример кода если нужен
```

## When To Use
Условия применения.

## Trade-offs
- **+** преимущество
- **-** ограничение

## See Also
- [[related-page-id]]
```

---

## §TAXONOMY — Система тегов

### Принципы
- Kebab-case, английский язык
- Максимум 5 тегов на страницу
- Теги дополняют `domain`/`layer`, не дублируют их

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

## §REBUILD-FORMAT — Формат статических таблиц (Вариант A)

### `derived/index.md`

```markdown
# Wiki Index

_Updated: 2026-05-01 · 15 pages_

| id | type | domain | layer | tags | updated |
|---|---|---|---|---|---|
| automation-over-llm | idea | wiki | concept | automation, ssot | 2026-05-01 |
| context-packet | pattern | wiki | architecture | seam, pipeline, llm | 2026-05-01 |
```

Строки сортируются: по `page_type` (idea → pattern → tool), затем по `id` алфавитно.

### `derived/views/by-domain.md`

```markdown
# Pages by Domain

_Generated: 2026-05-01_

## wiki (12)

| id | type | layer | tags | updated |
|---|---|---|---|---|
| automation-over-llm | idea | concept | automation | 2026-05-01 |

## llm (3)

| id | type | layer | tags | updated |
|---|---|---|---|---|
```

### `derived/views/by-layer.md`

```markdown
# Pages by Layer

_Generated: 2026-05-01_

## concept (4)

| id | type | domain | tags | updated |
|---|---|---|---|---|

## architecture (8)

...
```

### `derived/views/by-type.md`

```markdown
# Pages by Type

_Generated: 2026-05-01_

## idea (4)

| id | domain | layer | tags | updated |
|---|---|---|---|---|

## pattern (8)

...

## tool (3)

...
```

**Правила rebuild:**
- Если frontmatter отсутствует → страница попадает в таблицу с `domain=?`, `layer=?`, `tags=[]`
- `derived/views/` создаётся автоматически если не существует
- `derived/synthesis/` — rebuild **не трогает** (I-WIKI-1)

---

## Блок A — Критические исправления (models.py / repo.py / apply.py)

**Порядок выполнения строгий: A0 → A1 → A2 → A3 → A4 → A5 → A6 → A7**

- [x] **A0** `models.py`: добавить `PageMeta` dataclass:
  ```python
  @dataclass
  class PageMeta:
      tags: list[str] = field(default_factory=list)
      sources: list[str] = field(default_factory=list)
      domain: str = ""
      layer: str = ""
  ```
  `RewriteOp` НЕ расширяется — `PageMeta` передаётся как отдельный аргумент методов repo.

- [x] **A1** `repo.py`: добавить `_prepend_frontmatter(page_id, page_type, meta, version, created, updated) -> str`:
  ```python
  def _prepend_frontmatter(self, page_id, page_type, meta, version=1, created=None, updated=None):
      from datetime import date
      today = date.today().isoformat()
      fm = {
          "id": f"{page_type}/{page_id}",
          "page_type": page_type,
          "domain": meta.domain,
          "layer": meta.layer,
          "tags": meta.tags,
          "version": version,
          "created": created or today,
          "updated": updated or today,
          "sources": meta.sources,
      }
      return f"---\n{yaml.dump(fm, allow_unicode=True, sort_keys=False)}---\n"
  ```

- [x] **A2** `repo.py`: перенести `_parse_frontmatter` из `apply.py` → метод `WikiRepo._parse_frontmatter` (A4 зависит от A2)

- [x] **A3** `repo.py`: `create_page(page_id, page_type, content, meta: PageMeta)`:
  - вызывать `_prepend_frontmatter(page_id, page_type, meta, version=1)`
  - записывать `frontmatter + content`

- [x] **A4** `repo.py`: `rewrite_page(op: RewriteOp, meta: PageMeta)`:
  - читать существующий файл через `_parse_frontmatter`
  - извлечь `created` из существующего frontmatter (сохранить)
  - инкрементировать `version + 1`
  - вызывать `_prepend_frontmatter(... version=old+1, created=old_created)`
  - записывать `new_frontmatter + op.page_content`

- [x] **A5** `repo.py`: `apply_diff(diff: WikiDiff)` — после успешного `patch`:
  - читать файл, парсить frontmatter через `_parse_frontmatter`
  - инкрементировать `version + 1`, обновить `updated = today`
  - перезаписать файл с обновлённым frontmatter + body
  - метаданные (tags, domain, layer) **не меняются** (diff не несёт мета)

- [x] **A6** `apply.py`: при `op == "create"` — извлечь из frontmatter черновика `tags, sources, domain, layer` → собрать `PageMeta` → передать в `repo.create_page(..., meta=meta)`

- [x] **A7** `apply.py`: при `op == "rewrite"` — извлечь `PageMeta` из frontмatter черновика → передать в `repo.rewrite_page(op, meta=meta)`

---

## Блок B — Новые команды CLI (cli.py)

- [x] **B1** Добавить команду `wiki save-proposals`:
  - читает `runtime/tmp/extraction.json` → берёт `glossary_proposals`
  - читает `.wiki/config/glossary_pending.yaml` (если существует)
  - merge: если `term` уже есть → `[SKIP] term (already pending)` + warn
  - дозаписывает новые proposals в yaml
  - выводит: `[OK] N added, M skipped`

- [x] **B2** `wiki mark-ingested`: сделать `--file` обязательным:
  - `file: str = typer.Option(..., "--file", help="Original file path")` (убрать `""` default)
  - если пустой → `exit 1` с сообщением

- [x] **B3** Добавить команду `wiki delete <page_id> [--confirm]`:
  
  **Без `--confirm` (dry-run):**
  - показать содержимое страницы (первые 10 строк)
  - найти все страницы с `[[page_id]]` → показать список
  - найти запись в `glossary.yaml` → показать если есть
  - вывести: `Run with --confirm to proceed`
  
  **С `--confirm`:**
  1. Найти все `wiki/**/*.md` с `[[page_id]]`
  2. В каждом: удалить строки `- [[page_id]]` (See Also блок); заменить inline `[[page_id]]` на `page_id` (exact match regex: `\[\[page_id\]\]`)
  3. Если `page_id` есть в `glossary.yaml` как `page` → удалить запись
  4. Удалить файл страницы
  5. Вызвать `rebuild_all()`
  6. Вывести summary: `Deleted page_id. Updated N pages. Glossary: removed/kept.`

---

## Блок C — Rebuild (rebuild.py)

- [x] **C1** `rebuild.py`: парсить YAML frontmatter каждого `wiki/**/*.md` при сборке таблиц:
  ```python
  def _read_page_meta(path: Path) -> dict:
      text = path.read_text(encoding="utf-8")
      if text.startswith("---"):
          end = text.find("\n---", 3)
          if end != -1:
              return yaml.safe_load(text[3:end].strip()) or {}
      return {}  # страница без frontmatter → пустой dict
  ```

- [x] **C2** `rebuild.py`: обновить `derived/index.md` по формату из §REBUILD-FORMAT:
  - колонки: `id | type | domain | layer | tags | updated`
  - сортировка: по type (idea→pattern→tool), затем по id
  - страницы без frontmatter → `domain=?`, `layer=?`, `tags=`

- [x] **C3** `rebuild.py`: создавать `derived/views/` если не существует

- [x] **C4** `rebuild.py`: генерировать `derived/views/by-domain.md` (статическая таблица, §REBUILD-FORMAT)

- [x] **C5** `rebuild.py`: генерировать `derived/views/by-layer.md` (статическая таблица)

- [x] **C6** `rebuild.py`: генерировать `derived/views/by-type.md` (статическая таблица)

---

## Блок D — Lint (lint.py)

- [x] **D1** `lint.py`: страница без frontmatter → `WARNING: no frontmatter` (не error; совместимость со старыми страницами)

- [x] **D2** `lint.py`: `domain` не в `wiki_config.domains` → `ERROR: invalid domain`

- [x] **D3** `lint.py`: `layer` не в `wiki_config.layers` → `ERROR: invalid layer`

- [x] **D4** `lint.py`: `tags: []` (пустой список) → `WARNING: empty tags`

---

## Блок E — Конфигурация

- [x] **E1** `wiki_config.yaml`: добавить поля `domains` и `layers`:

  ```yaml
  domain: personal
  llm_model: claude-sonnet-4-6
  small_page_threshold: 1000
  vault_root: /root/project/obsidian-vault

  domains:
    - wiki       # система wiki самой по себе
    - llm        # LLM, промпты, агенты
    - sdd        # SDD процесс и инструменты
    - infra      # инфраструктура, DevOps
    - general    # общие концепции без домена

  layers:
    - concept        # абстрактная идея, принцип
    - architecture   # паттерн, структурное решение
    - implementation # конкретный код, инструмент
    - integration    # связь компонентов, workflow
  ```

- [x] **E2** `config.py`: добавить чтение `domains` и `layers` из `wiki_config.yaml` → передавать в lint

---

## Блок F — Протокол и документация (SKILL.md)

- [ ] **F1** `SKILL.md`: добавить раздел `§INVARIANTS`:
  ```
  I-WIKI-FM-1       Каждый wiki-файл ДОЛЖЕН иметь YAML frontmatter: id, page_type, domain, layer, tags, version, created, updated, sources
  I-WIKI-INGEST-1   mark-ingested ДОЛЖЕН вызываться с --file <path>; без него → exit 1
  I-WIKI-LINK-1     Каждая entity из ExtractionResult → ≥1 [[wikilink]] в черновиках Stage 2
  I-WIKI-DIFF-1     .diff.md — pure unified diff (difflib); ЗАПРЕЩЕНЫ git-style "--- a/..."
  I-WIKI-LINT-1     wiki lint exit 0 до git commit
  I-WIKI-GLOSSARY-1 glossary_pending.yaml → ВСЕГДА .wiki/config/glossary_pending.yaml
  I-WIKI-SEQ-1      Порядок СТРОГИЙ: ingest → extraction → validate → [save-proposals если proposals>0] → drafts → apply-drafts → rebuild → lint → commit → mark-ingested --file → [sync-glossary]
  I-WIKI-CLEAN-1    runtime/tmp/ пуст в начале новой wiki-evolve сессии (проверять перед Stage 1)
  I-WIKI-DOMAIN-1   domain ∈ wiki_config.domains — lint ERROR
  I-WIKI-LAYER-1    layer ∈ wiki_config.layers — lint ERROR
  I-WIKI-DELETE-1   wiki delete --confirm: удаляет входящие ссылки + glossary entry + rebuild; lint после → 0 broken links
  I-WIKI-MARKUP-1   Callouts (>[!NOTE]) — только в derived/synthesis/; запрещены в wiki/idea|pattern|tool/
  I-WIKI-MARKUP-2   Блоки кода ВСЕГДА с языком: ```python, ```yaml, ```json, ```bash; голый ``` запрещён
  I-WIKI-MARKUP-3   [[wikilink]] используется только для реальных страниц; для описания синтаксиса — `[[...]]` в backticks
  ```

- [ ] **F2** `SKILL.md` Stage 0: документировать обе формы:
  ```
  wiki ingest --pending --take 1   # из очереди pending (стандартный путь)
  wiki ingest <path>               # конкретный файл (когда пользователь передаёт путь явно)
  ```

- [ ] **F3** `SKILL.md` Post-action: исправить путь `runtime/glossary_pending.yaml` → `.wiki/config/glossary_pending.yaml`

- [ ] **F4** `SKILL.md` Post-action: обновить последовательность:
  ```
  wiki rebuild
  wiki lint                        ← exit 0 обязателен (I-WIKI-LINT-1)
  git commit <raw_file> <wiki/**>
  wiki mark-ingested <sha256> --file <path>   ← --file обязателен (I-WIKI-INGEST-1)
  wiki save-proposals              ← только если glossary_proposals > 0 (I-WIKI-SEQ-1)
  wiki sync-glossary               ← интерактивный, пользователь запускает вручную
  ```

- [ ] **F5** `SKILL.md` добавить раздел `§FORMATS`:
  
  **Рабочий формат `.diff.md`** (pure unified diff, I-WIKI-DIFF-1):
  ```
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

- [ ] **F6** `SKILL.md` добавить раздел `§TAXONOMY` (ссылка на систему тегов + таблицы из §TAXONOMY выше)

- [ ] **F7** `SKILL.md` обновить шаблон `.create.md` — добавить поля `domain`, `layer` (см. §OBSIDIAN)

- [ ] **F8** `SKILL.md` добавить раздел `§OBSIDIAN` (стандарт разметки из §OBSIDIAN выше)

- [ ] **F9** `guide.md`: добавить секции для новых команд (`save-proposals`, `delete`), frontmatter, domain/layer, таблицы views

---

## Инварианты (финальный список)

```
I-WIKI-FM-1       Каждый wiki-файл ДОЛЖЕН иметь YAML frontmatter: id, page_type, domain, layer, tags, version, created, updated, sources
I-WIKI-INGEST-1   mark-ingested ДОЛЖЕН вызываться с --file <path>; без него → exit 1
I-WIKI-EXTRACT-1  validate-extraction ДОЛЖЕН выдать exit 0 до начала Stage 2
I-WIKI-LINK-1     Каждая entity из ExtractionResult → ≥1 [[wikilink]] в черновиках Stage 2
I-WIKI-DIFF-1     .diff.md — pure unified diff (difflib); ЗАПРЕЩЕНЫ git-style "--- a/..."
I-WIKI-LINT-1     wiki lint exit 0 до git commit
I-WIKI-GLOSSARY-1 glossary_pending.yaml → ВСЕГДА .wiki/config/glossary_pending.yaml
I-WIKI-SEQ-1      Порядок СТРОГИЙ: ingest → extraction → validate → [save-proposals если proposals>0] → drafts → apply-drafts → rebuild → lint → commit → mark-ingested --file → [sync-glossary]
I-WIKI-CLEAN-1    runtime/tmp/ пуст в начале новой wiki-evolve сессии
I-WIKI-DOMAIN-1   domain ∈ wiki_config.domains — lint ERROR
I-WIKI-LAYER-1    layer ∈ wiki_config.layers — lint ERROR
I-WIKI-DELETE-1   wiki delete --confirm: удаляет входящие ссылки + glossary entry + rebuild; lint после → 0 broken links
I-WIKI-MARKUP-1   Callouts (>[!NOTE]) — только в derived/synthesis/; запрещены в wiki/idea|pattern|tool/
I-WIKI-MARKUP-2   Блоки кода ВСЕГДА с языком: ```python, ```yaml, ```json, ```bash; голый ``` запрещён
I-WIKI-MARKUP-3   [[wikilink]] используется только для реальных страниц; для описания синтаксиса — `[[...]]` в backticks
```

---

## Блок G — Шаблоны страниц (templates/)

Шаблоны хранятся в `obsidian-vault/templates/` — Obsidian может использовать их через плагин Templater или вручную. Дополнительно используются LLM как образцы при написании черновиков.

- [ ] **G1** Создать `templates/idea.md` — шаблон для страниц типа `idea`:

  ```markdown
  ---
  page_type: idea
  domain: {{domain}}
  layer: concept
  tags: []
  sources: []
  ---
  # {{Title}}

  ## Summary
  Одно предложение — суть идеи или принципа.

  ## Описание
  Развёрнутое объяснение. Почему это важно, откуда возникает.

  ## Когда применять
  Условия, при которых этот принцип релевантен.

  ## Антипаттерн
  Что происходит при нарушении этой идеи.

  ## See Also
  - [[related-page-id]]
  ```

- [ ] **G2** Создать `templates/pattern.md` — шаблон для страниц типа `pattern`:

  ```markdown
  ---
  page_type: pattern
  domain: {{domain}}
  layer: architecture
  tags: []
  sources: []
  ---
  # {{Title}}

  ## Summary
  Одно предложение — что это за паттерн и зачем.

  ## How It Works
  Шаги или механика. Ссылки на компоненты: [[component-page]].

  ```python
  # пример кода если применимо
  ```

  ## When To Use
  Условия применения паттерна.

  ## Trade-offs
  - **+** преимущество
  - **-** ограничение

  ## See Also
  - [[related-page-id]]
  ```

- [ ] **G3** Создать `templates/tool.md` — шаблон для страниц типа `tool`:

  ```markdown
  ---
  page_type: tool
  domain: {{domain}}
  layer: implementation
  tags: []
  sources: []
  ---
  # {{Title}}

  ## Summary
  Что это за инструмент и его основное назначение в данном контексте.

  ## How It Works
  Ключевые API / команды / механика, используемые в проекте.

  ```bash
  # пример команды или использования
  ```

  ## When To Use
  Когда выбирать этот инструмент, а не альтернативы.

  ## Trade-offs
  - **+** преимущество
  - **-** ограничение / зависимость

  ## See Also
  - [[related-page-id]]
  ```

- [ ] **G4** Создать `templates/create-draft.md` — шаблон черновика `.create.md` для LLM Stage 2.  
  Это образец, который LLM копирует и заполняет при написании `runtime/tmp/<page_id>.create.md`:

  ```markdown
  ---
  page_type: pattern
  domain: wiki
  layer: architecture
  tags: [pipeline, write-path]
  sources: ["raw/filename.md"]
  ---
  # Page Title

  ## Summary
  ...

  ## How It Works
  ...

  ## When To Use
  ...

  ## Trade-offs
  - **+** ...
  - **-** ...

  ## See Also
  - [[related-page-id]]
  ```

- [ ] **G5** Создать `templates/diff-draft.md` — шаблон черновика `.diff.md` для LLM Stage 2:

  ```markdown
  ---
  base_sha256: <sha256sum wiki/type/page-id.md | awk '{print $1}'>
  ---
  --- wiki/pattern/page-id.md
  +++ wiki/pattern/page-id.md
  @@ -N,M +N,M @@
   context line (пробел в начале обязателен)
  -удалённая строка
  +добавленная строка
   context line
  ```

  **Правила:**
  - Контекстные строки (без `+`/`-`) должны совпадать с файлом **побайтно**
  - Генерировать через `difflib.unified_diff`, не вручную
  - `base_sha256` = текущий sha256 файла до патча

- [ ] **G6** `cli.py`: добавить команду `wiki templates` — показывает список шаблонов и их расположение:
  ```
  wiki templates
  → idea      : templates/idea.md
  → pattern   : templates/pattern.md
  → tool      : templates/tool.md
  → drafts    : templates/create-draft.md, templates/diff-draft.md
  ```

---

## Зависимости между блоками

```
E1, E2  →  D2, D3        (lint читает config.domains/layers)
A0      →  A1, A2        (PageMeta нужен для repo методов)
A2      →  A6, A7        (_parse_frontmatter в repo.py)
A1,A2   →  A3, A4, A5   (методы repo зависят от _prepend_frontmatter)
A3,A4   →  A6, A7        (apply.py передаёт meta в repo)
A,B,C,D,E → F            (документация пишется последней)
F5      →  G5            (формат diff-draft берётся из §FORMATS)
G1-G5   →  G6            (wiki templates команда после создания файлов)
```

## Следующий ingest после Phase 2

После реализации всех блоков:
1. Обработать `raw/hazy-dreaming-peach.md` с merge-стратегией (Stage 2 с `wiki show` перед каждым черновиком)
2. Ожидаемые операции: `diff` для llm-knowledge-base / wiki-evolve / skill-cli-architecture; `create` для новых модулей
3. Ожидаемые entity из этого файла: `ingest-module`, `rebuild-module`, `wiki-config-schema` — уточнить при extraction
