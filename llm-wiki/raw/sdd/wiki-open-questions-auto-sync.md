# Plan: Auto-sync derived/open-questions.md

## Проблема

`derived/open-questions.md` — навигационный индекс всех открытых архитектурных вопросов по базе знаний. Сейчас он обновляется вручную через wiki-curate. Агент, добавивший вопрос в страницу wiki, не синхронизирует индекс автоматически — файл стареет.

## Решение

Добавить команду `wiki rebuild-open-questions` в CLI и вызывать её автоматически из `apply-drafts`, если затронуты `## Open Questions` блоки.

### Команда `wiki rebuild-open-questions`

Сканирует все страницы `wiki/**/*.md`, извлекает блоки `## Open Questions`, группирует по приоритету (P0/P1/P2/P3), пересобирает `derived/open-questions.md`.

```python
@app.command(name="rebuild-open-questions")
def rebuild_open_questions(
    vault: Path = typer.Option(_DEFAULT_VAULT, "--vault", envvar="WIKI_VAULT"),
) -> None:
```

**Логика:**
1. Glob `wiki/**/*.md` — все страницы
2. Для каждой страницы: найти секцию `## Open Questions`, извлечь строки `- [ ] (P0|P1|P2|P3) ...`
3. Сгруппировать по приоритету → по page_id
4. Перезаписать `derived/open-questions.md` (rebuild, не diff — derived файл)
5. Вывод: `[OK] open-questions.md: {p0} P0, {p1} P1, {p2} P2, {p3} P3`

### Интеграция в `apply-drafts`

После применения каждого черновика — проверить, содержит ли diff строки `## Open Questions` или `- [ ]`. Если да → вызвать `rebuild_open_questions()` в конце. Не вызывать если OQ-блоки не затронуты (избежать лишних мутаций derived/).

**Детекция:** простой `"Open Questions" in diff_content or "- [ ]" in diff_content`.

### Трейдофф

- **Детектировать изменение OQ-блока** → коммит только при реальном изменении, но сложнее
- **Всегда пересобирать** → проще, но каждый `apply-drafts` мутирует derived/

Выбор: детекция через проверку diff-контента — дёшево, достаточно надёжно.

## Порядок реализации

1. `rebuild-open-questions` как standalone команда — можно вызывать вручную
2. Интеграция в `apply-drafts` — автовызов при наличии OQ-изменений
3. Обновить SKILL.md: убрать упоминание ручного обновления derived/open-questions.md через wiki-curate

## Верификация

1. `wiki rebuild-open-questions` → пересобирает derived/open-questions.md, exit 0
2. `apply-drafts` с diff содержащим `- [ ]` → автоматически вызывает rebuild
3. `apply-drafts` без OQ-изменений → derived/open-questions.md не трогается
4. После `apply-drafts` + autorebuild → `wiki lint` exit 0
