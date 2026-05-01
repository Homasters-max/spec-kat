# Entity Registry

## Summary
Canonical mapping известных сущностей wiki (I-GLOSSARY-1). Хранится в `.wiki/config/glossary.yaml`. Одна сущность = одна canonical page, все алиасы ведут туда. CLI использует реестр для автолинковки и нормализации при ingest.

## How It Works
```yaml
- term: "RAG"
  page: "pattern/rag.md"
  aliases: ["retrieval augmented generation"]
  type: "pattern"
```
CLI при ingest делает lookup: заменяет упоминания терминов и алиасов на wikilinks, предлагает тип сущности как hint для LLM. Новые сущности не попадают в реестр напрямую — только через [[glossary-discovery]] → `wiki sync-glossary`.

## When To Use
Реестр читается при каждом `wiki ingest`. Обновляется только через `wiki sync-glossary` (интерактивный review proposals из [[extraction-result]]).

## Trade-offs
- **+** Нет дублирующих сущностей — нормализация на входе (I-WIKI-3)
- **+** Glossary не блокирует ingest: новые сущности обнаруживаются в extraction, sync — post-action
- **-** Ручной sync-glossary требует внимания пользователя

## See Also
- [[glossary-discovery]]
- [[extraction-result]]
- [[wiki-evolve]]
