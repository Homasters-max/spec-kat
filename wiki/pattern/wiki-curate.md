---
id: pattern/wiki-curate
page_type: pattern
domain: wiki
layer: architecture
tags:
- curation
- maintenance
- pipeline
- llm
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS.md
---
# Wiki Curate

## Summary
Протокол [[wiki-cli]] для поддержания качества базы знаний: устранение orphans, битых ссылок, дублирующихся страниц. Включает human gate перед применением изменений.

## How It Works

**Stage 0 (CLI):**

```bash
wiki lint                             # orphans, broken links, duplicates, frontmatter
wiki search <terms>                   # найти связанные страницы
cat .wiki/state/query_log.jsonl       # контекст прошлых запросов (опционально)
```

**Stage 1 (LLM, dry-run):**
- Анализирует вывод lint + содержимое страниц
- Пишет `runtime/tmp/curate_plan.md` — список операций с обоснованием
- Показывает план пользователю

**[HUMAN GATE]** — пользователь одобряет план:

```bash
wiki curate-apply
```

**Stage 2 (LLM, после curate-apply):**
- `curate-apply` читает `curate_plan.md`, пишет черновики, вызывает `apply_drafts`
- `wiki rebuild`

```bash
git commit   # пользователь вручную после проверки
```

## When To Use
- После накопления большого числа страниц
- При обнаружении `wiki lint` exit 1
- Когда есть подозрение на дублирование знаний

## Trade-offs
- Требует human gate — нельзя автоматизировать полностью
- Конфликт при `apply-drafts` требует ручного разрешения (I-WIKI-CONFLICT-1)

## See Also
- [[wiki-cli]]
- [[wiki-evolve]]
- [[wiki-query]]
