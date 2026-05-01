# Wiki Evolve — Разбор сессии и план доработок

**Дата сессии:** 2026-05-01  
**Обработанный файл:** `LLM_Wiki_Spec_v1.md`  
**Результат:** 15 страниц создано, lint OK, glossary 9 терминов

---

## §1 — Отклонения от протокола

### 1.1 Stage 0: `wiki ingest <file>` вместо `--pending --take 1`

**Что было:** пользователь передал конкретный путь → `wiki ingest /path/to/file.md`  
**По протоколу:** `wiki ingest --pending --take 1` (берёт один pending из очереди)  
**Вывод:** обе формы поддерживаются CLI, но SKILL.md описывает только `--pending --take 1`.  
**Действие:** добавить в SKILL.md оба варианта Stage 0 с пояснением когда какой.

### 1.2 `wiki mark-ingested` без флага `--file`

**Что было:** `wiki mark-ingested <sha256>` — путь файла не передан  
**По протоколу:** `wiki mark-ingested <sha256> --file <path>`  
**Последствие:** в `ingest_log.jsonl` нет пути к исходному файлу — аудит неполный  
**Действие:** зафиксировать в протоколе обязательность `--file`; рассмотреть enforcement в CLI.

### 1.3 Путь `glossary_pending.yaml` — несоответствие протокола и CLI

**Что было в SKILL.md:** "сохранить glossary_proposals в `runtime/glossary_pending.yaml`"  
**Что читает CLI (`wiki sync-glossary`):** `.wiki/config/glossary_pending.yaml`  
**Как решили:** скопировали файл вручную  
**Действие:** исправить SKILL.md → правильный путь `.wiki/config/glossary_pending.yaml`.

### 1.4 Proposals не записываются автоматически

**Что было:** `glossary_proposals` живут в `extraction.json`, но ни один CLI не переносит их в `glossary_pending.yaml`  
**Действие:** либо добавить `wiki save-proposals` (читает extraction.json → пишет glossary_pending.yaml), либо явно описать в SKILL.md что LLM создаёт этот файл вручную из ExtractionResult.

### 1.5 Diff-черновики не работали

**Что было:** написал `.diff.md` черновики с `--- a/...` заголовками → `patch` conflict  
**Причина:** `patch <file> <patchfile>` требует точного unified diff формата из `difflib.unified_diff`, а не git-style `--- a/b/` заголовков  
**Как решили:** переключился на `.rewrite.md` (reason: small_page)  
**Действие:** задокументировать точный рабочий формат `.diff.md` (см. §5)

---

## §2 — Проблемы при работе с протоколом

### 2.1 Frontmatter не попадает в wiki-файлы

**Суть:** `apply.py` стрипит YAML frontmatter из черновика, записывает только body.  
**Результат:** страницы в `wiki/` не имеют frontmatter — нет `id`, `type`, `version`, `sources`.  
**Следствие:** `derived/index.md` показывает пустые теги (нечего парсить).  
**Ссылка на spec §4:** frontmatter должен быть: `id, type, version, created, updated, sources`.  
**Решение:** `create_page` и `rewrite_page` должны добавлять frontmatter автоматически.

### 2.2 Теги из черновиков теряются

**Суть:** черновик имеет `tags: [wiki, pipeline]` в frontmatter — `apply.py` его стрипит.  
**Результат:** теги потеряны, `index.md` пуст в колонке tags.  
**Связано с 2.1** — одна причина, одно исправление.

### 2.3 Orphan `typer` после первого apply-drafts

**Суть:** страница `typer` была создана без входящих ссылок.  
**Причина:** в черновике `skill-cli-architecture` ссылка на `[[typer]]` не была включена изначально.  
**Действие:** правило — каждая entity из ExtractionResult должна иметь ≥1 входящую ссылку в черновиках Stage 2.

### 2.4 Broken link `[[wikilinks]]` в entity-registry

**Суть:** в описании синтаксиса использован `[[wikilinks]]` как литеральный текст — lint воспринял как ссылку.  
**Действие:** в черновиках не использовать `[[...]]` для описания синтаксиса, только для реальных страниц.

---

## §3 — Шаблон YAML frontmatter для wiki-страниц

### Проблема
Сейчас wiki-файлы не имеют frontmatter. Spec §4 его требует. `apply.py` стрипит frontmatter из черновика.

### Решение: CLI добавляет frontmatter автоматически

`create_page` и `rewrite_page` в `repo.py` оборачивают content:

```python
def _prepend_frontmatter(page_id, page_type, content, sources=None, version=1):
    from datetime import date
    today = date.today().isoformat()
    fm = {
        "id": f"{page_type}/{page_id}",
        "page_type": page_type,
        "version": version,
        "created": today,   # только при create; rewrite сохраняет оригинал
        "updated": today,
        "sources": sources or [],
    }
    return f"---\n{yaml.dump(fm, allow_unicode=True)}---\n{content}"
```

### Шаблон черновика для LLM (`.create.md`)

```markdown
---
page_type: pattern
tags: [tag1, tag2, tag3]
sources: ["raw/filename.md"]
---
# Page Title

## Summary
Одно предложение — суть страницы.

## How It Works
Шаги или механика, с [[wikilinks]] на связанные страницы.

## When To Use
Условия применения.

## Trade-offs
- **+** преимущество
- **-** ограничение

## See Also
- [[related-page-id]]
```

### Поля frontmatter черновика
| Поле | Кто задаёт | Назначение |
|------|-----------|------------|
| `page_type` | LLM | определяет директорию wiki/type/ |
| `tags` | LLM | теги (см. §4) |
| `sources` | LLM | какой raw-файл является источником |
| `base_sha256` | LLM | только для `.diff.md` — optimistic lock |
| `reason` | LLM | только для `.rewrite.md` |

### Поля, добавляемые CLI автоматически
`id`, `version`, `created`, `updated` — из repo.py при записи в wiki/

---

## §4 — Система тегов

### Принципы
- Kebab-case, английский язык
- Максимум 5 тегов на страницу
- Теги дополняют тип (idea/pattern/tool), не заменяют его

### Таксономия

#### По домену
| Тег | Применение |
|-----|-----------|
| `wiki` | система wiki самой по себе |
| `llm` | взаимодействие с LLM |
| `knowledge-base` | хранение и организация знаний |
| `pipeline` | последовательность обработки данных |
| `cli` | command-line инструменты |
| `search` | механизмы поиска |
| `git` | git workflow |
| `markdown` | работа с markdown |

#### По архитектурному слою
| Тег | Применение |
|-----|-----------|
| `seam` | граница между компонентами |
| `ssot` | Single Source of Truth |
| `automation` | детерминированный код без LLM |
| `validation` | проверка данных, схем |
| `write-path` | пути записи в SSOT |
| `read-only` | readonly операции |

#### По жизненному циклу знаний
| Тег | Применение |
|-----|-----------|
| `ingestion` | ввод новых знаний |
| `extraction` | извлечение сущностей |
| `maintenance` | поддержка качества |
| `curation` | редактирование |
| `dedup` | дедупликация |

### Примеры применения (ретроспективно для текущих страниц)
```
llm-knowledge-base:    [knowledge-base, markdown, pipeline, git]
wiki-evolve:           [wiki, pipeline, write-path, ingestion]
wiki-query:            [wiki, read-only, search]
wiki-curate:           [wiki, maintenance, curation]
context-packet:        [seam, pipeline, llm]
extraction-result:     [seam, llm, validation]
skill-cli-architecture:[cli, automation, seam]
git-as-ssot:           [git, ssot, automation]
diff-first-updates:    [wiki, write-path, validation]
entity-registry:       [wiki, dedup, ssot]
```

---

## §5 — Стратегия слияний при повторном ingest

### Контекст
`/root/project/obsidian-vault/raw/hazy-dreaming-peach.md` — plan document с деталями реализации CLI (структура пакета, pyproject.toml, модули). При ingest пересечётся с существующими страницами.

### Типы ситуаций

| Тип | Описание | Операция |
|-----|----------|----------|
| A | Новая информация, дополняет страницу | `diff` |
| B | Другой угол зрения на ту же концепцию | `diff` (новая секция) |
| C | Противоречие с существующей страницей | `diff` или `rewrite` + ConflictNote |
| D | Детали реализации (код, модули) | `diff` → секция `## Implementation Notes` |
| E | Полностью новая сущность | `create` |

### Алгоритм Stage 2 при merge

```
для каждой entity из ExtractionResult:
  1. wiki show <page_id>
     → если "not found": операция CREATE
     → если существует: перейти к 2
  2. Прочитать текущий контент страницы
  3. Оценить delta: что нового в источнике vs страница?
     → delta < 5 строк: diff
     → структурное изменение: rewrite (reason: structural_change)
     → страница < SMALL_PAGE_THRESHOLD: rewrite (reason: small_page)
  4. Для diff: получить base_sha256:
     sha256sum wiki/<type>/<id>.md | awk '{print $1}'
```

### Рабочий формат `.diff.md`

**Проблема:** `patch <file> <patchfile>` требует стандартный unified diff без git-путей.

**Безопасный способ — генерировать через Python:**
```bash
python3 -c "
import difflib, sys
page = 'wiki/pattern/llm-knowledge-base.md'
old = open(page).readlines()
new = old[:]
new.append('- [[new-link]]\n')
print(''.join(difflib.unified_diff(old, new, fromfile=page, tofile=page)))
" > /tmp/check.patch
patch wiki/pattern/llm-knowledge-base.md /tmp/check.patch  # тест
```

**Формат файла черновика:**
```markdown
---
base_sha256: <sha256sum wiki/type/page-id.md | awk '{print $1}'>
---
--- wiki/pattern/page-id.md
+++ wiki/pattern/page-id.md
@@ -25,3 +25,4 @@
 ## See Also
 - [[existing-link]]
+- [[new-link]]
```

**Ключевое правило:** строки контекста (без `+`/`-`) должны точно совпадать с файлом, включая пробелы и кодировку.

### Ожидаемые сущности из `hazy-dreaming-peach.md`

| Entity | Тип операции | Обоснование |
|--------|-------------|-------------|
| `llm-knowledge-base` | diff | добавить tech stack / pyproject.toml |
| `wiki-evolve` | diff | детали Stage 0-2 с кодом |
| `skill-cli-architecture` | diff | структура пакета (модули) |
| `ingest` (модуль) | create | новая сущность — tool |
| `rebuild` (модуль) | create | новая сущность — tool |
| `wiki-config` | create | wiki_config.yaml — новая сущность |

---

## §6 — Чеклист изменений

### SKILL.md
- [ ] Stage 0: добавить `wiki ingest <file>` как альтернативу `--pending --take 1`
- [ ] Post-action: исправить путь → `.wiki/config/glossary_pending.yaml`
- [ ] Post-action: `wiki mark-ingested <sha256> --file <path>` — добавить `--file`
- [ ] Добавить рабочий пример `.diff.md` (из §5)
- [ ] Правило: каждая entity ДОЛЖНА иметь ≥1 входящую ссылку

### CLI (repo.py / apply.py)
- [ ] `create_page` — автодобавление frontmatter (id, page_type, version, created, updated, sources)
- [ ] `rewrite_page` — обновление frontmatter (version+1, updated; created сохранить)
- [ ] `apply.py` → передавать `tags` и `sources` из frontmatter черновика в create/rewrite
- [ ] `rebuild.py` → парсить frontmatter wiki-файлов для index.md (tags, updated, sources)

### Новая команда: `wiki save-proposals`
```
wiki save-proposals   # extraction.json → .wiki/config/glossary_pending.yaml
```

### Приоритет
1. **Критично:** frontmatter в wiki-файлах (§3) + правильный путь glossary_pending (§1.3)
2. **Важно:** система тегов (§4) + `wiki save-proposals` (§1.4)
3. **Следующий ingest:** `hazy-dreaming-peach.md` с merge-стратегией из §5
