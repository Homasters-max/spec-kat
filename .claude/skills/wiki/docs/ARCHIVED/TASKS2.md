# Wiki System — Task List (Phase 2)

**Источник:** session-review-2026-05-01.md + plan upgrade  
**Приоритет:** критично → важно → улучшение

---

## Блок A — Критические исправления (repo.py / apply.py)

- [ ] **A1** `repo.py`: добавить `_prepend_frontmatter(page_id, page_type, tags, sources, domain, layer, version, created)` → возвращает полный текст с YAML frontmatter
- [ ] **A2** `repo.py`: `create_page(...)` — добавить параметры `tags, sources, domain, layer`; вызывать `_prepend_frontmatter` перед записью файла
- [ ] **A3** `repo.py`: `rewrite_page(...)` — читать существующий frontmatter, сохранять `created`, инкрементировать `version`, обновлять `updated`; вызывать `_prepend_frontmatter` перед записью
- [ ] **A4** `repo.py`: вынести `_parse_frontmatter` из `apply.py` в `repo.py` (единственный источник истины)
- [ ] **A5** `apply.py`: при `op == "create"` передавать в `repo.create_page` поля `tags, sources, domain, layer` из frontmatter черновика
- [ ] **A6** `apply.py`: при `op == "rewrite"` передавать `tags, sources, domain, layer` в `repo.rewrite_page`

---

## Блок B — Новые команды CLI (cli.py)

- [ ] **B1** Добавить команду `wiki save-proposals`:  
  читает `runtime/tmp/extraction.json` → берёт `glossary_proposals` → дозаписывает в `.wiki/config/glossary_pending.yaml` (merge, не перезаписывает)
- [ ] **B2** `wiki mark-ingested`: сделать `--file` обязательным (`typer.Option(..., "--file")`); выдавать `exit 1` если пустой
- [ ] **B3** Добавить команду `wiki delete <page_id> [--confirm]`:
  - без `--confirm`: dry-run — показать страницу и все входящие ссылки
  - с `--confirm`:
    1. удалить строки `- [[page_id]]` из всех wiki-страниц
    2. заменить inline `[[page_id]]` на plain text `page_id`
    3. удалить файл страницы
    4. запустить `rebuild_all()` автоматически
  - не трогать `derived/`, `runtime/`, `.wiki/` — rebuild пересоберёт

---

## Блок C — Rebuild + Dataview (rebuild.py)

- [ ] **C1** `rebuild.py`: парсить YAML frontmatter каждого `wiki/**/*.md` при сборке `index.md`; добавить колонки `domain`, `layer`, `tags`, `updated`
- [ ] **C2** `rebuild.py`: создавать директорию `derived/views/` если не существует
- [ ] **C3** `rebuild.py`: генерировать `derived/views/by-domain.md` с Dataview-запросом (TABLE по domain)
- [ ] **C4** `rebuild.py`: генерировать `derived/views/by-layer.md` с Dataview-запросом (TABLE по layer)
- [ ] **C5** `rebuild.py`: генерировать `derived/views/by-type.md` с Dataview-запросом (TABLE по page_type)

---

## Блок D — Lint (lint.py)

- [ ] **D1** `lint.py`: страница без frontmatter → WARNING (не error; ретро-миграции нет)
- [ ] **D2** `lint.py`: `domain` не в `config.domains` → ERROR
- [ ] **D3** `lint.py`: `layer` не в `config.layers` → ERROR

---

## Блок E — Конфигурация

- [ ] **E1** `wiki_config.yaml` (шаблон в `cli.py::init_vault`): добавить поля `domains: [llm, wiki, sdd, infra]` и `layers: [concept, architecture, implementation, integration]`

---

## Блок F — Протокол и документация (SKILL.md / guide.md)

- [ ] **F1** `SKILL.md`: добавить раздел `§INVARIANTS` с правилами I-WIKI-FM-1 … I-WIKI-DELETE-1 (см. план)
- [ ] **F2** `SKILL.md`: Stage 0 — задокументировать обе формы ingest (`--pending --take 1` и `<path>`)
- [ ] **F3** `SKILL.md`: исправить путь glossary → `.wiki/config/glossary_pending.yaml`
- [ ] **F4** `SKILL.md`: `mark-ingested` — добавить обязательный `--file <path>`
- [ ] **F5** `SKILL.md`: добавить раздел `§FORMATS` с рабочим форматом `.diff.md` (pure unified diff, не git-style)
- [ ] **F6** `SKILL.md`: правило — каждая entity ДОЛЖНА иметь ≥1 входящую `[[wikilink]]` (I-WIKI-LINK-1)
- [ ] **F7** `SKILL.md`: Post-action — добавить `wiki save-proposals` и `wiki delete`
- [ ] **F8** `SKILL.md`: добавить раздел `§TAXONOMY` (page_type / domain / layer / tags)
- [ ] **F9** `SKILL.md`: обновить шаблон `.create.md` — добавить поля `domain`, `layer`
- [ ] **F10** `guide.md`: обновить — новые команды (`save-proposals`, `delete`), frontmatter, domain/layer, Dataview views

---

## Инварианты (нарушать нельзя)

```
I-WIKI-FM-1     Каждый wiki-файл ДОЛЖЕН иметь YAML frontmatter: id, page_type, version, created, updated, sources, tags
I-WIKI-INGEST-1 mark-ingested ДОЛЖЕН вызываться с --file <path>; без него → exit 1
I-WIKI-EXTRACT-1 validate-extraction ДОЛЖЕН выдать exit 0 до начала Stage 2
I-WIKI-LINK-1   Каждая entity из ExtractionResult → ≥1 [[wikilink]] в черновиках
I-WIKI-DIFF-1   .diff.md — pure unified diff (difflib); ЗАПРЕЩЕНЫ git-style "--- a/..."
I-WIKI-LINT-1   wiki lint exit 0 до git commit
I-WIKI-GLOSSARY-1 glossary_pending.yaml → ВСЕГДА .wiki/config/glossary_pending.yaml
I-WIKI-SEQ-1    Порядок wiki-evolve СТРОГИЙ: ingest → extraction → validate → [save-proposals] → drafts → apply-drafts → rebuild → lint → commit → mark-ingested → [sync-glossary]
I-WIKI-CLEAN-1  runtime/tmp/ пуст в начале новой wiki-evolve сессии
I-WIKI-DOMAIN-1 domain в frontmatter ∈ wiki_config.domains (lint проверяет)
I-WIKI-LAYER-1  layer в frontmatter ∈ wiki_config.layers (lint проверяет)
I-WIKI-DELETE-1 wiki delete --confirm: удаляет входящие ссылки автоматически + rebuild; wiki lint после → 0 broken links на удалённую страницу
```
