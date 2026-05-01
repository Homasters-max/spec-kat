# Wiki Curate

## Summary
Maintenance workflow для контроля качества wiki (I-WIKI-QUALITY-1). Находит orphan-страницы, дубли, broken links, semantic conflicts. Все изменения применяются только после явного подтверждения пользователя — human gate обязателен.

## How It Works
1. **Stage 0** — `wiki lint` → orphans, broken links, дубли; `wiki search <terms>` → кластеры похожих страниц; `query_log.jsonl` → частые вопросы = слабые места
2. **Stage 1** (dry-run) — LLM формирует `runtime/tmp/curate_plan.md` с планом операций (merge, упрощение, удаление, реорганизация связей); показывает пользователю
3. **[HUMAN GATE]** — `wiki curate-apply` запускается только после явного подтверждения
4. **Stage 2** — LLM пишет черновики в `runtime/tmp/<page_id>.[op].md`; `wiki apply-drafts` → `wiki rebuild`; пользователь делает `git commit` после review

## When To Use
- Периодически (только вручную в v1)
- При обнаружении растущего числа orphan-страниц через `wiki lint`
- При частых не-ответных запросах через `wiki-query` (сигнал слабых мест)

## Trade-offs
- **+** Human gate предотвращает автоматическое удаление нужных знаний
- **-** Требует ручного запуска — нет cron в v1

## See Also
- [[llm-knowledge-base]]
- [[wiki-evolve]]
- [[diff-first-updates]]
