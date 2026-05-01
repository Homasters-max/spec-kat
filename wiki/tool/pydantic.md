# Pydantic

## Summary
Python-библиотека для валидации данных через аннотации типов. В [[llm-knowledge-base]] используется как enforcement layer для LLM-шовных типов (I-WIKI-EXTRACT-1): невалидный LLM output отклоняется до применения к SSOT.

## How It Works
- `ExtractionResult`, `ExtractedEntity`, `Relation`, `ConflictNote`, `GlossaryProposal` — pydantic `BaseModel`
- `wiki validate-extraction` читает `runtime/tmp/extraction.json` и вызывает `model_validate(data)`
- Exit non-zero при любой ошибке валидации → STOP (I-WIKI-EXTRACT-1)
- Pydantic гарантирует типы полей, Literal constraints (`type: "idea" | "pattern" | "tool"`), required fields

## When To Use
Для всех шов-типов между CLI и LLM (I-WIKI-SEAM-1, I-WIKI-EXTRACT-1). Не используется для внутренних dataclass-типов, не проходящих через LLM.

## Trade-offs
- **+** Чёткие сообщения об ошибках при LLM format failures
- **+** Нет отдельной schema validation библиотеки — типы Python = схема
- **-** Overhead на создание Pydantic объектов (незначительный)

## See Also
- [[extraction-result]]
- [[skill-cli-architecture]]
