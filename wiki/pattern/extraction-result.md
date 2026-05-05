---
id: pattern/extraction-result
page_type: pattern
domain: wiki
layer: architecture
tags:
- seam
- pipeline
- extraction
- pydantic
- validation
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS.md
---
# Extraction Result

## Summary
Архитектурный шов между Stage 1 (LLM extraction) и Stage 2 (apply drafts) в протоколе [[wiki-evolve]]. Pydantic-валидируемый JSON-файл `runtime/tmp/extraction.json`. LLM пишет его в Stage 1, CLI проверяет схему через `wiki validate-extraction` (I-WIKI-EXTRACT-1).

## How It Works

Структура (pydantic `ExtractionResult`):

```python
class ExtractionResult(BaseModel):
    entities:            list[ExtractedEntity]
    relations:           list[Relation]
    conflicts:           list[ConflictNote]
    glossary_proposals:  list[GlossaryProposal]
```

Вложенные типы:

```python
class ExtractedEntity(BaseModel):
    term:         str        # kebab-case page_id
    type:         str        # "idea" | "pattern" | "tool"
    confidence:   float      # 0.0–1.0; включать только ≥ 0.7
    in_glossary:  bool       # True если term в glossary_hints ContextPacket

class Relation(BaseModel):
    from_term:  str
    to_term:    str
    type:       str          # "uses" | "implements" | "extends" | "replaces"

class GlossaryProposal(BaseModel):
    term:           str
    suggested_page: str      # page_id куда ведёт термин
    type:           str
    reason:         str
```

**Валидация:**

```bash
wiki validate-extraction   # exit 0 = OK, exit 1 = schema error
```

## When To Use
Stage 1 (LLM): после чтения [[context-packet]] — написать `extraction.json`.
Stage 2 (LLM): после `validate-extraction` exit 0 — читать для создания черновиков страниц.

## Trade-offs
- LLM должен следовать kebab-case для `term` — ошибки именования ломают `apply-drafts`
- confidence < 0.7 включать не нужно — засоряет базу слабыми сущностями

## See Also
- [[wiki-evolve]]
- [[context-packet]]
- [[wiki-cli]]
