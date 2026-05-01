# Context Packet

## Summary
Типизированный шов Stage 0 → Stage 1 в [[wiki-evolve]] pipeline (I-WIKI-SEAM-1). CLI строит ContextPacket из raw файла и передаёт LLM — прямая передача raw str или dict запрещена. Кэшируется в `runtime/cache/<sha256>.json`.

## How It Works
```python
@dataclass
class ContextPacket:
    file: Path
    sha256: str
    raw_content: str
    content_chunks: list[str]          # разбивка по H1–H3
    glossary_hints: list[GlossaryHint] # известные термины из glossary.yaml
    related_pages: list[SearchResult]  # BM25 top-k, со score
```
CLI наполняет пакет до LLM: парсит frontmatter, разбивает на чанки, делает glossary lookup, BM25 search. LLM видит структурированный контекст, а не raw text.

## When To Use
Всегда как единственный способ передачи данных от CLI к LLM в evolve pipeline. Также формируется при `wiki promote <query_id>` из context_snapshot в query_log.

## Trade-offs
- **+** Явный контракт предотвращает утечку реализации CLI в LLM-stage
- **+** SHA256 позволяет кэшировать ContextPacket и делать dedup
- **-** Overhead на сериализацию/десериализацию при каждом ingest

## See Also
- [[wiki-evolve]]
- [[extraction-result]]
- [[skill-cli-architecture]]
