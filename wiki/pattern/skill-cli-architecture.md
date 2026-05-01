# Skill + CLI Architecture

## Summary
Архитектурный паттерн, где детерминированная логика реализована в CLI (без LLM), а смысловая обработка делегирована LLM через skill-файлы (session protocols). Разработан по образцу SDD и применяется в LLM Wiki.

## How It Works
- **CLI** — выполняет всё детерминированное: парсинг, индексирование, валидация, git операции, rebuild. Никаких API вызовов.
- **Skill** — markdown-файл с протоколом сессии для LLM (Claude Code). Описывает stages, seams, invariants.
- **Seam** — явный типизированный контракт между CLI и LLM (например, [[context-packet]], [[extraction-result]]). Прямая передача raw str запрещена.
- **Инварианты** — машиночитаемые правила, enforcement через CLI (pydantic валидация, conflict detection).

## When To Use
- Когда операция частично детерминирована (parsing, search) и частично требует понимания (extraction, synthesis)
- Когда важна аудитируемость каждого шага
- Когда нужно минимизировать LLM вызовы (cost)

## Trade-offs
- **+** Детерминированные части надёжны, быстры и тестируемы
- **+** LLM вызывается только там, где необходимо
- **-** Требует явного проектирования seam-контрактов

## See Also
- [[llm-knowledge-base]]
- [[automation-over-llm]]
- [[context-packet]]
- [[extraction-result]]
- [[typer]]
