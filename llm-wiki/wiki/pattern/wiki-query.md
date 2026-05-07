---
id: pattern/wiki-query
page_type: pattern
domain: wiki
layer: architecture
tags:
- read-only
- search
- llm
- knowledge-base
- domain/wiki
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS.md
---
# Wiki Query

## Summary
Read-only протокол [[wiki-cli]] для ответа на вопросы из базы знаний. LLM синтезирует ответ из найденных страниц. Никаких изменений wiki не производится (I-WIKI-QUERY-1).

## How It Works

**Stage 0 (CLI):**

```bash
wiki search <terms>      # BM25-поиск, возвращает ranked list page_id + scores
wiki show <page_id>      # полное содержимое страницы
```

**Stage 1 (LLM):**
Синтезирует ответ из прочитанных страниц. Вывод содержит:
- `answer` — прямой ответ на вопрос
- `citations` — список использованных page_id
- `insights` — новые связи или пробелы, замеченные при синтезе
- `promote_suggestion` — сигнал о ценном знании для будущего wiki-evolve

**Post-action (опционально):**

```bash
QID=$(wiki log-query --query "<вопрос>")
wiki promote $QID    # сохранить контекст для будущего wiki-evolve
```

## When To Use
Когда нужно найти информацию в wiki или синтезировать ответ из нескольких страниц.

## Trade-offs
- Качество ответа ограничено тем, что уже есть в wiki
- BM25-поиск не понимает семантику — запросы должны содержать ключевые слова из страниц

## See Also
- [[wiki-cli]]
- [[wiki-evolve]]
- [[wiki-curate]]
