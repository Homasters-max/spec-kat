---
id: pattern/wiki-skill
page_type: pattern
domain: wiki
layer: architecture
tags:
- knowledge-base
- pipeline
- llm
- cli
- domain/wiki
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SKILL.md
---
# Wiki Skill

## Summary
Точка входа в систему управления wiki. Объединяет 5 протоколов: от добавления знаний до управления открытыми вопросами. Каждый протокол — отдельный page в вики с детальным описанием.

## Протоколы

| Протокол | Когда использовать |
|----------|-------------------|
| [[wiki-evolve]] | Добавить новые знания из raw-файла |
| [[wiki-query]] | Задать вопрос по базе знаний (read-only) |
| [[wiki-curate]] | Почистить orphans, broken links, дубли |
| [[wiki-open-questions]] | Управлять P0/P1/P2 вопросами на страницах |
| [[wiki-docgraph]] | Создать/редактировать DocGraph-узел (task/phase/domain) |

## Навигация по системе

**Стандарты оформления:**
- [[wiki-taxonomy]] — система тегов; правила выбора domain/layer/tags
- [[wiki-markup-standard]] — правила разметки для Obsidian и plain Markdown

**Ключевые компоненты pipeline:**
- [[context-packet]] — результат `wiki ingest`; входной пакет для LLM
- [[extraction-result]] — структура `extraction.json`; выходной пакет LLM Stage 1
- [[wiki-session-isolation]] — изоляция `runtime/tmp/` между сессиями

**DocGraph интеграция:**
- [[wiki-docgraph]] — протокол работы с execution-узлами
- [[docgraph-dual-ssot]] — prose в wiki, структура в EventLog
- [[wiki-semantic-extractor]] — читает prose из WikiSnapshot для контекста задач

## When To Use
При старте любой wiki-сессии — выбрать протокол из таблицы выше.

## See Also
- [[wiki-evolve]]
- [[wiki-query]]
- [[wiki-curate]]
