# Wiki CLI — Руководство пользователя

**Vault по умолчанию:** `/root/project/obsidian-vault/`  
**Переопределить:** `export WIKI_VAULT=/path/to/vault` или `--vault /path`

---
cd /root/project/.claude/skills/wiki && source venv/bin/activate && wiki ingest /root/project/obsidian-vault/raw/hazy-dreaming-peach.md 2>&1

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

# Проверить что всё работает
wiki --help
```

> **Примечание:** `pip install` напрямую не работает на Debian/Ubuntu с externally-managed Python.
> Venv изолирует зависимости и не требует `--break-system-packages`.

### Инициализация vault (первый запуск)

```bash
# Создать vault в папке по умолчанию (/root/project/obsidian-vault)
wiki init

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
│   └── graph.json              ← авто: граф [[wikilinks]]
├── runtime/
│   ├── cache/                  ← ContextPackets + BM25-индекс
│   └── tmp/                    ← черновики LLM (очищается после apply)
└── .wiki/
    ├── config/
    │   ├── wiki_config.yaml    ← конфигурация vault
    │   ├── glossary.yaml       ← принятые термины
    │   └── glossary_pending.yaml ← предложения на review
    └── state/
        ├── ingest_log.jsonl    ← лог обработанных файлов
        └── query_log.jsonl     ← лог запросов
```

### wiki_config.yaml (минимальный)

```yaml
domain: personal
llm_model: claude-sonnet-4-6
small_page_threshold: 1000
vault_root: /root/project/obsidian-vault
```

---

## Все команды CLI

### `wiki init` — инициализировать vault

```bash
wiki init                            # vault в /root/project/obsidian-vault
wiki init --vault /path/to/vault     # произвольный путь
wiki init --domain work              # задать домен (default: personal)
wiki init --force                    # перезаписать существующий конфиг
```

Создаёт структуру директорий, `wiki_config.yaml`, пустой глоссарий, лог-файлы, инициализирует git. Идемпотентен — безопасно запускать повторно.

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

Пересоздаёт `derived/index.md` (таблица всех страниц) и `derived/graph.json` (граф ссылок). Запускать после любого изменения wiki-страниц.

---

### `wiki lint` — проверка целостности

```bash
wiki lint          # exit 0 = OK, exit 1 = есть проблемы
```

Проверяет:
- **Orphans** — страницы без входящих ссылок
- **Broken links** — `[[ссылки]]` на несуществующие страницы
- **Duplicates** — пары страниц с similarity > 85%

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
VAULT=/root/project/obsidian-vault

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
```

---

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|------------|-------------|------------|
| `WIKI_VAULT` | `/root/project/obsidian-vault` | Путь к vault (глобальный override) |

```bash
# Временно использовать другой vault
WIKI_VAULT=/tmp/other-wiki wiki search "test"

# Постоянно задать в shell profile
echo 'export WIKI_VAULT=/root/project/obsidian-vault' >> ~/.bashrc
```

---

## Типичные ошибки

| Симптом | Причина | Решение |
|---------|---------|---------|
| `wiki_config.yaml not found` | vault не инициализирован | создать `.wiki/config/wiki_config.yaml` |
| `[SKIP] file.md` при ingest | sha256 уже в ingest_log | файл уже обработан ранее |
| `wiki apply-drafts` exit 1 | конфликт при патче | вручную отредактировать страницу, запустить снова |
| `wiki lint` exit 1 — orphan | страница без входящих ссылок | добавить `[[page_id]]` в связанную страницу |
| `wiki search` — No results | wiki/ пуст или индекс устарел | удалить `runtime/cache/bm25_corpus.json`, повторить |
| `validate-extraction` exit 1 | невалидный JSON или схема | LLM должен переписать extraction.json |
| `wiki promote` exit 1 — "context_snapshot is empty" | log-query вызван без --snapshot | повторить с --snapshot |
| `wiki promote` exit 1 — "query_id not found" | неверный query_id | проверить `wiki log --n 50` |
