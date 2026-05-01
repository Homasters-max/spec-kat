# Automation Over LLM

## Summary
Ключевой принцип [[llm-knowledge-base]]: максимум автоматизации, минимум LLM. Код делает всё детерминированное (parsing, indexing, search, git, rebuild, validation). LLM вызывается только для смысловых операций (extraction, synthesis) где детерминизм невозможен.

## How It Works
Разделение ответственности:
- **CLI (без LLM):** ingest, BM25 search, pydantic validation, apply-drafts logic, rebuild, lint, git operations
- **LLM:** Stage 1 (extract entities/relations), Stage 2 (synthesize pages), curate (plan changes)
- **Seam-контракты** — [[context-packet]] и [[extraction-result]] — явно ограничивают область LLM-вмешательства

## When To Use
При любом проектировании компонентов системы: если операция детерминирована, она НЕ должна требовать LLM.

## Trade-offs
- **+** Надёжность: детерминированный код не галлюцинирует
- **+** Стоимость: LLM вызывается только там, где нужен
- **-** Требует явного проектирования границ (seams)

## See Also
- [[llm-knowledge-base]]
- [[skill-cli-architecture]]
- [[context-packet]]
