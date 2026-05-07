# Wiki CLI — Руководство пользователя

**Vault:** задаётся через реестр (`wiki use <name>`) или `WIKI_VAULT` env.  
**Переопределить на один вызов:** `WIKI_VAULT=/path/to/vault wiki <cmd>`

---

## Быстрый старт

```bash
# Установить (один раз) — создаёт изолированный venv, symlink в /usr/local/bin/wiki
WIKI_SRC=/root/project/.claude/skills/wiki
python3 -m venv $WIKI_SRC/venv
$WIKI_SRC/venv/bin/pip install -e $WIKI_SRC/scripts/ -q
ln -sf $WIKI_SRC/venv/bin/wiki /usr/local/bin/wiki

# Уже установлено — venv: /root/project/.claude/skills/wiki/venv/
# wiki доступен глобально без активации venv

# После установки — зарегистрировать vault:
wiki register llm-wiki /root/project/obsidian-vault/llm-wiki -d "LLM Wiki"
wiki use llm-wiki

# Проверить что всё работает
wiki --help
```

> **Примечание:** `pip install` напрямую не работает на Debian/Ubuntu с externally-managed Python.
> Venv изолирует зависимости и не требует `--break-system-packages`.

### Инициализация vault (первый запуск)

```bash
# Создать vault (путь обязателен — хардкодированного дефолта нет)
wiki init --vault /path/to/my-vault

# Или задать произвольный путь
wiki init --vault /path/to/my-vault

# С кастомным доменом и моделью
wiki init --domain work --model claude-opus-4-7

# Перезаписать существующий конфиг
wiki init --force
```

`wiki init` создаёт структуру директорий, `wiki_config.yaml`, пустой глоссарий, лог-файлы и инициализирует git-репозиторий. Идемпотентен — повторный запуск без `--force` не перезапишет существующие файлы.

---

## Структура vault

```
obsidian-vault/
├── raw/                        ← сюда кидаем исходные заметки (MD, TXT)
├── wiki/
│   ├── idea/                   ← страницы-идеи
│   ├── pattern/                ← паттерны / рецепты
│   └── tool/                   ← инструменты / технологии
├── derived/
│   ├── index.md                ← авто: таблица всех страниц
│   ├── graph.json              ← авто: граф [[wikilinks]]
│   └── views/
│       ├── by-domain.md        ← авто: группировка по domain
│       ├── by-layer.md         ← авто: группировка по layer
│       └── by-type.md          ← авто: группировка по page_type
├── runtime/
│   ├── cache/                  ← ContextPackets + BM25-индекс
│   └── tmp/                    ← черновики LLM (очищается после apply)
├── templates/
│   ├── idea.md                 ← шаблон страницы idea
│   ├── pattern.md              ← шаблон страницы pattern
│   ├── tool.md                 ← шаблон страницы tool
│   ├── create-draft.md         ← шаблон черновика .create.md
│   └── diff-draft.md           ← шаблон черновика .diff.md
└── .wiki/
    ├── config/
    │   ├── wiki_config.yaml    ← конфигурация vault
    │   ├── glossary.yaml       ← принятые термины
    │   └── glossary_pending.yaml ← предложения на review
    └── state/
        ├── ingest_log.jsonl    ← лог обработанных файлов
        └── query_log.jsonl     ← лог запросов
```

### wiki_config.yaml (полный)

```yaml
domain: personal
llm_model: claude-sonnet-4-6
small_page_threshold: 1000
vault_root: /root/project/obsidian-vault

domains:
  - wiki
  - llm
  - sdd
  - infra
  - general

layers:
  - concept
  - architecture
  - implementation
  - integration
```

`domains` и `layers` используются командой `wiki lint` для валидации frontmatter страниц (I-WIKI-DOMAIN-1, I-WIKI-LAYER-1).

---

## Все команды CLI

### `wiki init` — инициализировать vault

```bash
wiki init --vault /path/to/vault     # путь обязателен
wiki init --domain work              # задать домен (default: personal)
wiki init --force                    # перезаписать существующий конфиг
```

Создаёт структуру директорий, `wiki_config.yaml`, пустой глоссарий, лог-файлы, инициализирует git. Идемпотентен — безопасно запускать повторно.

---

### Frontmatter wiki-страниц

Каждая страница в `wiki/` ДОЛЖНА иметь YAML frontmatter (I-WIKI-FM-1). CLI проставляет системные поля автоматически, LLM заполняет смысловые в черновике:

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

| Поле | Кто задаёт | Значения |
|------|-----------|---------|
| `id` | CLI (auto) | `{page_type}/{page_id}` |
| `page_type` | LLM (черновик) | `idea \| pattern \| tool` |
| `domain` | LLM (черновик) | из `wiki_config.domains` |
| `layer` | LLM (черновик) | из `wiki_config.layers` |
| `tags` | LLM (черновик) | kebab-case, ≤5 штук |
| `version` | CLI (auto) | integer, начиная с 1; инкрементируется при каждом write |
| `created` | CLI (auto при create) | ISO date |
| `updated` | CLI (auto при любом write) | ISO date |
| `sources` | LLM (черновик) | список `raw/*.md` файлов-источников |

**Допустимые значения domain** (из `wiki_config.domains`): `wiki`, `llm`, `sdd`, `infra`, `general`

**Допустимые значения layer** (из `wiki_config.layers`): `concept`, `architecture`, `implementation`, `integration`

---

### `wiki ingest` — загрузить сырой файл

```bash
# Показать необработанные файлы из raw/
wiki ingest --pending

# Обработать один файл (создаёт ContextPacket в runtime/cache/)
wiki ingest raw/my-notes.md

# Взять N первых pending-файлов и обработать
wiki ingest --pending --take 3
```

Файл считается обработанным, если его sha256 уже есть в `ingest_log`. Повторный запуск выводит `[SKIP]`.

---

### `wiki search` — поиск по wiki-страницам (BM25)

```bash
wiki search "retrieval augmented generation"
wiki search "docker deployment" --top-k 5
```

Ищет по всем `wiki/**/*.md`. Возвращает ranked list с ID страниц.

---

### `wiki show` — просмотр страниц

```bash
# Показать все идеи
wiki show idea

# Показать все паттерны
wiki show pattern

# Показать конкретную страницу по ID
wiki show rag-pipeline
```

---

### `wiki rebuild` — пересобрать derived/

```bash
wiki rebuild
```

Пересоздаёт статические таблицы и `derived/graph.json`. Запускать после любого изменения wiki-страниц.

Генерируемые файлы:

| Файл | Содержимое |
|------|-----------|
| `derived/index.md` | Все страницы: id, type, domain, layer, tags, updated |
| `derived/views/by-domain.md` | Группировка по domain |
| `derived/views/by-layer.md` | Группировка по layer |
| `derived/views/by-type.md` | Группировка по page_type |
| `derived/graph.json` | Граф wikilinks |

Страницы без frontmatter попадают в таблицы с `domain=?`, `layer=?`. `derived/synthesis/` rebuild не трогает.

---

### `wiki lint` — проверка целостности

```bash
wiki lint          # exit 0 = OK, exit 1 = есть проблемы
```

Проверяет:
- **Orphans** — страницы без входящих ссылок
- **Broken links** — `[[ссылки]]` на несуществующие страницы
- **Duplicates** — пары страниц с similarity > 85%
- **Frontmatter** — наличие, валидность domain/layer, непустые tags:

| Проверка | Уровень | Условие |
|----------|---------|---------|
| Нет frontmatter | WARNING | страница без `---` блока |
| Неверный `domain` | ERROR | не в `wiki_config.domains` (I-WIKI-DOMAIN-1) |
| Неверный `layer` | ERROR | не в `wiki_config.layers` (I-WIKI-LAYER-1) |
| Пустые `tags: []` | WARNING | теги — качество, не корректность |

Обязателен exit 0 до `git commit` (I-WIKI-LINT-1).

---

### `wiki validate-extraction` — проверить extraction.json

```bash
wiki validate-extraction    # exit 0 = валидный, exit 1 = ошибка схемы
```

Проверяет `runtime/tmp/extraction.json` по схеме `ExtractionResult`. Запускать после того как LLM записал extraction.json.

---

### `wiki apply-drafts` — применить черновики LLM

```bash
wiki apply-drafts    # exit 0 = OK, exit 1 = конфликт
```

Сканирует `runtime/tmp/` и применяет файлы по маске `<page_id>.[create|diff|rewrite].md`:
- `.create.md` → создать новую страницу
- `.diff.md` → применить unified diff к существующей странице
- `.rewrite.md` → полная замена страницы

При конфликте останавливается немедленно (не откатывает уже применённые).

---

### `wiki save-proposals` — сохранить предложения глоссария

```bash
wiki save-proposals
```

Читает `glossary_proposals` из `runtime/tmp/extraction.json` и дозаписывает новые записи в `.wiki/config/glossary_pending.yaml`.

- Если `term` уже есть в pending → `[SKIP] term (already pending)` + предупреждение (не перезаписывает — пользователь мог редактировать вручную)
- Выводит: `[OK] N added, M skipped`

Запускать **только если `glossary_proposals > 0`** (I-WIKI-SEQ-1), после `git commit`.

---

### `wiki delete` — удалить страницу

```bash
# Dry-run: показать что будет удалено
wiki delete <page_id>

# Применить удаление
wiki delete <page_id> --confirm
```

**Без `--confirm` (dry-run):**
- Показывает первые 10 строк страницы
- Находит все страницы с `[[page_id]]` и показывает список
- Показывает запись в `glossary.yaml` если есть
- Выводит: `Run with --confirm to proceed`

**С `--confirm`:**
1. Находит все `wiki/**/*.md` с `[[page_id]]`
2. В каждом удаляет строки `- [[page_id]]` (See Also блок) и заменяет inline `[[page_id]]` на `page_id`
3. Если `page_id` есть в `glossary.yaml` как `page` → удаляет запись
4. Удаляет файл страницы
5. Вызывает `wiki rebuild`
6. Выводит: `Deleted page_id. Updated N pages. Glossary: removed/kept.`

После `--confirm` обязательно запустить `wiki lint` (I-WIKI-DELETE-1).

---

### `wiki log` — история операций

```bash
wiki log           # последние 20 записей
wiki log --n 50    # последние 50
```

Объединяет ingest_log и query_log, сортирует по времени (новые вверху).

---

### `wiki mark-ingested` — пометить файл как обработанный

```bash
wiki mark-ingested <sha256>
wiki mark-ingested <sha256> --file raw/my-notes.md
```

Записывает sha256 в `ingest_log.jsonl`. Запускать как **последний шаг** после `git commit` в pipeline wiki-evolve. Только после этого файл перестаёт появляться в `wiki ingest --pending`.

SHA256 печатается командой `wiki ingest` в строке `sha256 : ...`.

---

### `wiki promote` — продвинуть query в ContextPacket

```bash
wiki promote <query_id>
```

Берёт `context_snapshot` из query_log по ID и кэширует как ContextPacket для последующей обработки через `wiki-evolve`.

---

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

---

### `wiki status` — состояние pipeline

```bash
wiki status
```

Показывает:
- Количество необработанных файлов в `raw/`
- Наличие `runtime/tmp/extraction.json`
- Черновики в `runtime/tmp/`
- Количество записей в ingest_log и query_log

---

### `wiki sync-glossary` — интерактивный review глоссария

```bash
wiki sync-glossary
```

Показывает каждое предложение из `glossary_pending.yaml`. Команды: `y` — принять, `n` — пропустить, `e` — принять с правкой термина. Принятые записи добавляются в `glossary.yaml`, pending очищается.

---

### `wiki curate-apply` — применить план курации

```bash
wiki curate-apply
```

Читает `runtime/tmp/curate_plan.md`, применяет черновики через `apply-drafts`, пересобирает derived/. Вызывается после того как пользователь одобрил план.

---

### `wiki templates` — список шаблонов

```bash
wiki templates
```

Показывает доступные шаблоны страниц и черновиков с путями:

```text
→ idea      : templates/idea.md
→ pattern   : templates/pattern.md
→ tool      : templates/tool.md
→ drafts    : templates/create-draft.md, templates/diff-draft.md
```

---

### `wiki evolve` — запустить wiki-evolve в Claude Code

```bash
wiki evolve
wiki evolve --vault /path/to/vault
```

Запускает wiki-evolve skill в Claude Code (аналог `/wiki` → wiki-evolve в чате). Используется для автоматизации pipeline через CLI без ручного запуска skill.

---

## Работа с Claude Code

Запустить skill: напишите в чате `/wiki` или опишите задачу (Claude сам определит нужный протокол).

### Сценарий 1: добавить новые знания (wiki-evolve)

1. Положите заметку в `raw/` (markdown, txt)
2. Запустите `/wiki` → выберите **wiki-evolve**
3. Claude: Stage 0 — `wiki ingest --pending --take 1`
4. Claude (LLM): читает ContextPacket, пишет `runtime/tmp/extraction.json`
5. Вы: `wiki validate-extraction` — убедитесь что exit 0
6. Claude (LLM): пишет черновики страниц в `runtime/tmp/`
7. Вы: `wiki apply-drafts` → `wiki rebuild` → `wiki lint` → `git commit`
8. Вы: `wiki mark-ingested <sha256>` — пометить файл как обработанный
9. Claude: `wiki sync-glossary` — опциональный review новых терминов

### Сценарий 2: задать вопрос (wiki-query)

1. Запустите `/wiki` → опишите вопрос
2. Claude: `wiki search <terms>` + `wiki show <ids>` — READ-ONLY
3. Claude (LLM): синтезирует ответ с цитатами
4. Опционально: `wiki log-query --query "<вопрос>" [--snapshot ctx.json]` → получить `query_id`
5. Опционально: `wiki promote <query_id>` — сохранить контекст для wiki-evolve

### Сценарий 3: навести порядок (wiki-curate)

1. Запустите `/wiki` → выберите **wiki-curate**
2. Claude: `wiki lint` + `wiki search`
3. Claude (LLM): пишет `runtime/tmp/curate_plan.md` — **вы читаете и одобряете**
4. Вы: `wiki curate-apply`
5. Вы: `git commit` вручную после проверки изменений

---

## Инициализация нового vault

```bash
VAULT=/path/to/my-vault

mkdir -p $VAULT/{raw,wiki/{idea,pattern,tool},derived,runtime/{cache,tmp},.wiki/{config,state}}

cat > $VAULT/.wiki/config/wiki_config.yaml << EOF
domain: personal
llm_model: claude-sonnet-4-6
small_page_threshold: 1000
vault_root: $VAULT
EOF

echo "[]" > $VAULT/.wiki/config/glossary.yaml
touch $VAULT/.wiki/state/ingest_log.jsonl
touch $VAULT/.wiki/state/query_log.jsonl

cd $VAULT && git init

# Зарегистрировать и активировать
wiki register my-vault $VAULT -d "My knowledge base"
wiki use my-vault
```

---

## Несколько проектов (multi-vault)

Wiki поддерживает несколько изолированных vault'ов — для разных проектов, команд или контекстов. Каждый vault полностью независим: свои страницы, glossary, ingest_log, `domains`/`layers`.

### Реестр vault'ов

Глобальный реестр хранится в `~/.wiki/vaults.yaml`. Активный vault — в `~/.wiki/active`.

**Логика разрешения vault (приоритет по убыванию):**

1. `WIKI_VAULT` env — явный override на один вызов
2. `~/.wiki/active` → lookup в `~/.wiki/vaults.yaml`
3. Ошибка: `No active vault. Run: wiki use <name>  or  export WIKI_VAULT=/path/to/vault`

Хардкодированного fallback нет — vault всегда нужно сконфигурировать явно.

### `wiki register` — зарегистрировать vault

```bash
wiki register llm-wiki /root/project/obsidian-vault/llm-wiki -d "LLM Wiki knowledge base"
wiki register work     /home/user/work-wiki                  -d "Work project notes"
wiki register sdd      /root/project/sdd-wiki
```

Записывает vault в `~/.wiki/vaults.yaml`. Повторный вызов с тем же именем обновляет путь.

### `wiki vaults` — список vault'ов

```bash
wiki vaults
```

Выводит все зарегистрированные vault'ы. Активный помечен `▶`:

```text
  ▶ llm-wiki             /root/project/obsidian-vault/llm-wiki  # LLM Wiki knowledge base
    work                 /home/user/work-wiki                    # Work project notes
    sdd                  /root/project/sdd-wiki
```

### `wiki use` — переключить активный vault

```bash
wiki use work
# [OK] Active vault → work  (/home/user/work-wiki)
```

После этого все команды (`wiki ingest`, `wiki search`, `wiki lint` и т.д.) работают с vault `work` — без `--vault` флага.

### `wiki init --name` — создать и зарегистрировать

```bash
wiki init --vault /home/user/new-project --name new-project --domain llm
```

Создаёт структуру vault и сразу регистрирует его в реестре.

### Типичный workflow с несколькими проектами

```bash
# Первоначальная настройка
wiki register llm-wiki /root/project/obsidian-vault/llm-wiki -d "LLM Wiki"
wiki register work     /home/user/work-wiki                  -d "Work notes"

# Работа с llm-wiki
wiki use llm-wiki
wiki ingest --pending --take 1
wiki search "rag pipeline"

# Переключиться на work
wiki use work
wiki ingest raw/standup-notes.md
wiki lint

# Временно обратиться к другому vault без переключения
WIKI_VAULT=/root/project/obsidian-vault/llm-wiki wiki search "context packet"
```

---

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|------------|-------------|------------|
| `WIKI_VAULT` | активный vault из `~/.wiki/active` | Явный путь к vault (override реестра) |

```bash
# Временно использовать конкретный vault (не меняет ~/.wiki/active)
WIKI_VAULT=/tmp/other-wiki wiki search "test"

# Постоянно задать конкретный vault в shell profile (отключает реестр)
echo 'export WIKI_VAULT=/root/project/obsidian-vault/llm-wiki' >> ~/.bashrc
```

---

## Типичные ошибки

| Симптом | Причина | Решение |
|---------|---------|---------|
| `No active vault` | vault не выбран | `wiki use <name>` или `export WIKI_VAULT=/path` |
| `wiki_config.yaml not found` | vault не инициализирован | создать `.wiki/config/wiki_config.yaml` |
| `[SKIP] file.md` при ingest | sha256 уже в ingest_log | файл уже обработан ранее |
| `wiki apply-drafts` exit 1 | конфликт при патче | вручную отредактировать страницу, запустить снова |
| `wiki lint` exit 1 — orphan | страница без входящих ссылок | добавить `[[page_id]]` в связанную страницу |
| `wiki search` — No results | wiki/ пуст или индекс устарел | удалить `runtime/cache/bm25_corpus.json`, повторить |
| `validate-extraction` exit 1 | невалидный JSON или схема | LLM должен переписать extraction.json |
| `wiki promote` exit 1 — "context_snapshot is empty" | log-query вызван без --snapshot | повторить с --snapshot |
| `wiki promote` exit 1 — "query_id not found" | неверный query_id | проверить `wiki log --n 50` |
| `wiki use` exit 1 — "not found" | имя не в реестре | `wiki vaults` → проверить список, `wiki register` если нужно |
| команда работает не с тем vault | `WIKI_VAULT` env перекрывает реестр | `unset WIKI_VAULT` или `wiki use <name>` |
