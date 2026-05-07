---
id: idea/wiki-taxonomy
page_type: idea
domain: wiki
layer: architecture
tags:
- knowledge-base
- maintenance
- markdown
- llm
- domain/wiki
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SKILL.md
---
# Wiki Taxonomy

## Summary
Система тегов для wiki-страниц. Теги дополняют поля `domain` и `layer`, не дублируют их. Каждая страница: ≤5 семантических тегов + 1 обязательный `domain/<domain>` тег (Obsidian-фильтр).

## How It Works

**Domain-тег (обязательный):** `domain/<domain>` (например `domain/sdd`, `domain/wiki`). Не входит в лимит 5. В Obsidian отображается как иерархический тег `domain > sdd`.

**По домену применения:**

| Тег | Применение |
|-----|-----------|
| `knowledge-base` | хранение и организация знаний |
| `pipeline` | последовательность обработки данных |
| `cli` | command-line инструменты |
| `search` | механизмы поиска |
| `git` | git workflow |
| `markdown` | работа с markdown |
| `llm` | взаимодействие с LLM |

**По архитектурному слою:**

| Тег | Применение |
|-----|-----------|
| `seam` | граница между компонентами |
| `ssot` | Single Source of Truth паттерны |
| `automation` | детерминированный код без LLM |
| `validation` | проверка данных, схем |
| `write-path` | пути записи в SSOT |
| `read-only` | readonly операции |
| `dedup` | дедупликация |

**По жизненному циклу знаний:**

| Тег | Применение |
|-----|-----------|
| `ingestion` | ввод новых знаний |
| `extraction` | извлечение сущностей |
| `maintenance` | поддержка качества |
| `curation` | редактирование |
| `open-questions` | страницы с нерешёнными вопросами |

**По технологии:**

| Тег | Применение |
|-----|-----------|
| `python` | Python-специфичные концепции |
| `pydantic` | использует pydantic |
| `bm25` | алгоритмы ранжирования |
| `yaml` | конфигурация YAML |

## When To Use
При создании или обновлении любой wiki-страницы — выбрать теги из таксономии.

## Trade-offs
- Теги — kebab-case, английский; нарушение → lint warning
- Максимум 5 семантических тегов: избыток тегов снижает фильтрацию в Obsidian
- `domain/<domain>` обязателен на каждой странице (I-WIKI-FM-1)

## See Also
- [[wiki-markup-standard]]
- [[wiki-evolve]]
