---
id: pattern/wiki-session-isolation
page_type: pattern
domain: wiki
layer: architecture
tags:
- automation
- curation
- maintenance
- pipeline
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS2.md
---
# Wiki Session Isolation

## Summary
Механизм предотвращения межсессионного загрязнения `runtime/tmp/` между протоколами [[wiki-evolve]] и [[wiki-curate]]. Каждый протокол использует собственный способ изоляции.

## How It Works

| Сессия | Механизм изоляции |
|--------|------------------|
| `wiki-evolve` | `wiki clean-tmp` перед Stage 1 (явный, I-WIKI-CLEAN-1) |
| `wiki-curate` | scoped apply по frontmatter `curate_plan.md` (структурная) |
| Смешанная | `curate-apply` игнорирует файлы чужих page_id; выводит WARN |

**wiki-evolve isolation:**

```bash
wiki status     # проверить stale-черновики
wiki clean-tmp  # явная очистка перед Stage 1
```

Без `wiki clean-tmp` черновики предыдущей сессии могут быть применены повторно через `wiki apply-drafts`.

**wiki-curate isolation:**

`curate_plan.md` определяет разрешённые `page_id` (frontmatter `operations`). `curate-apply` применяет только совпадающие черновики — лишние файлы игнорируются со WARN.

```yaml
---
operations:
  - {page_id: my-page, op: diff, rationale: "..."}
---
```

## When To Use
- При диагностике неожиданного применения черновиков
- При переходе от одного протокола к другому в одной рабочей директории
- При настройке нового vault: убедиться что `runtime/tmp/` создан и пуст

## Trade-offs
- `wiki-evolve` требует ручного `wiki clean-tmp` — нет автоматической проверки при `ingest`
- `wiki-curate` защищает только page_id из плана; файлы без соответствия в плане не удаляются из tmp автоматически

## See Also
- [[wiki-evolve]]
- [[wiki-curate]]
- [[wiki-cli]]
