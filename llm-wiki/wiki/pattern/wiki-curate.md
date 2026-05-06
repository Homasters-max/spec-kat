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
- domain/wiki
version: 3
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/TASKS.md
---
# Wiki Curate

## Summary
Протокол [[wiki-cli]] для поддержания качества базы знаний: устранение orphans, битых ссылок, дублирующихся страниц. Включает human gate перед применением изменений.

## How It Works

**Stage 0 (CLI):**

```bash
wiki lint             # orphans, broken links, duplicates, frontmatter
wiki search <terms>   # найти связанные страницы
wiki log --n 50       # контекст прошлых запросов (опционально)
```

**Stage 1 (LLM):**
- Анализирует вывод lint + содержимое страниц
- Пишет `runtime/tmp/curate_plan.md` с YAML frontmatter:

```yaml
---
operations:
  - {page_id: <id>, op: create|diff|rewrite|delete, rationale: "..."}
---
## Curation Plan
Human-readable description.
```

- Пишет черновики для всех non-delete операций в `runtime/tmp/`

**[HUMAN GATE]** — пользователь проверяет реальные черновики:

```bash
wiki status                  # список draft files + wiki health
cat runtime/tmp/*.diff.md    # конкретные изменения
wiki curate-apply            # → scoped apply + rebuild + lint + cleanup
```

**Post-action:**

```bash
wiki delete <page_id> --confirm   # для каждого op: delete из плана
git add wiki/ derived/ && git commit -m "wiki: curate ..."
wiki lint                          # финальная проверка
```

## When To Use
- После накопления большого числа страниц
- При обнаружении `wiki lint` exit 1
- Когда есть подозрение на дублирование знаний

## Trade-offs
- Требует human gate — нельзя автоматизировать полностью
- Конфликт при `apply-drafts` требует ручного разрешения (I-WIKI-CONFLICT-1)
- `curate-apply` не коммитит автоматически: LLM пишет черновики, CLI применяет, пользователь коммитит
- `curate-apply` lint: exit 1 на FM errors; WARN на broken_links (ожидаемо при pending deletes); WARN на orphans
- pre-flight: exit 1 если отсутствуют черновики для non-delete операций
- Лишние файлы в `runtime/tmp/` игнорируются scoped apply; `wiki clean-tmp` для очистки

## See Also
- [[wiki-cli]]
- [[wiki-evolve]]
- [[wiki-query]]
