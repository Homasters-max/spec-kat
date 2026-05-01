# LLM Knowledge Base

## Summary
Персональная база знаний, построенная на основе собственных markdown-заметок с автоматической организацией через SKILL + CLI архитектуру. LLM вызывается только для смыслового обновления (extract + synthesize); весь детерминированный код выполняется без API вызовов.

## How It Works
1. Raw markdown-файлы помещаются в `raw/` (uncommitted = pending)
2. [[wiki-evolve]] обрабатывает каждый файл: ingest → extract → synthesize → apply
3. Знания организуются в три первичных типа страниц: `idea/`, `pattern/`, `tool/`
4. [[git-as-ssot]] определяет состояние: committed = обработано, uncommitted = pending
5. [[wiki-query]] предоставляет read-only доступ через BM25 поиск без embedding
6. [[wiki-curate]] периодически поддерживает качество базы знаний

## When To Use
- Когда нужно накапливать и переиспользовать знания из собственных заметок
- Когда важна воспроизводимость и аудитируемость обновлений
- Когда предпочтительна минимальная зависимость от LLM (cost, latency)

## Trade-offs
- **+** Детерминированный pipeline, git-история всех изменений
- **+** Нет embedding-инфраструктуры, баз данных, серверов
- **-** BM25 слабее semantic search для размытых запросов
- **-** Один файл за вызов `--take 1` (намеренное ограничение батчинга)

## See Also
- [[wiki-evolve]]
- [[wiki-query]]
- [[wiki-curate]]
- [[skill-cli-architecture]]
- [[git-as-ssot]]
- [[automation-over-llm]]
