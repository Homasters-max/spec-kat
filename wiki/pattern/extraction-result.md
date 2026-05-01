# Extraction Result

## Summary
Типизированный шов Stage 1 → Stage 2 в [[wiki-evolve]] pipeline (I-WIKI-EXTRACT-1). LLM пишет `runtime/tmp/extraction.json`, CLI валидирует через [[pydantic]] перед Stage 2. Невалидный JSON → STOP, без молчаливого fallback.

## How It Works
```python
class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity]        # term, type, confidence ≥ 0.7, in_glossary
    relations: list[Relation]              # from_term → to_term, type
    conflicts: list[ConflictNote]          # page + note
    glossary_proposals: list[GlossaryProposal]  # новые сущности для sync (I-WIKI-DISCOVERY-1)
```
LLM извлекает сущности и связи из [[context-packet]]. Не пишет markdown (I-WIKI-4). Proposals не попадают в glossary.yaml напрямую — только через `wiki sync-glossary` post-action.

## When To Use
Как единственный способ передачи результатов LLM extraction к Stage 2 synthesis. `wiki validate-extraction` должен выдать exit 0 перед переходом к Stage 2.

## Trade-offs
- **+** Pydantic-валидация отсекает галлюцинации на шве до применения к SSOT
- **+** [[glossary-discovery]] через proposals вместо прямой записи — предотвращает bottleneck
- **-** LLM должен строго следовать JSON-схеме; форматные ошибки требуют retry

## See Also
- [[context-packet]]
- [[wiki-evolve]]
- [[entity-registry]]
- [[pydantic]]
- [[glossary-discovery]]
