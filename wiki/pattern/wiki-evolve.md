# Wiki Evolve

## Summary
Write-path workflow для обновления wiki из raw markdown-файлов. Трёхстадийный pipeline: Stage 0 (CLI ingest) → Stage 1 (LLM extract) → Stage 2 (LLM synthesize + apply). Единственный легальный способ записи в wiki SSOT.

## How It Works
1. **Stage 0** — `wiki ingest --pending --take 1`: CLI строит [[context-packet]] из raw файла (BM25, glossary lookup) без LLM
2. **Stage 1** — LLM читает ContextPacket, пишет [[extraction-result]] в `runtime/tmp/extraction.json`; `wiki validate-extraction` → pydantic check (I-WIKI-EXTRACT-1)
3. **Stage 2** — LLM читает ExtractionResult + существующие страницы, пишет черновики в `runtime/tmp/<page_id>.[op].md`; `wiki apply-drafts` → [[diff-first-updates]] (create/diff/rewrite)
4. **Post-actions** — `wiki rebuild`, `wiki lint`, `git commit`, `wiki sync-glossary`

## When To Use
- При появлении нового raw markdown-файла в `raw/`
- После `wiki promote <query_id>` для записи инсайтов из query в wiki

## Trade-offs
- **+** Каждое изменение атомарно и аудитируемо через git
- **+** [[automation-over-llm]]: Stage 0 и Post-actions без LLM
- **-** Один файл за вызов (намеренно: простота > скорость)
- **-** Конфликты разрешаются вручную (I-WIKI-CONFLICT-1, запрет auto-retry)

## See Also
- [[context-packet]]
- [[extraction-result]]
- [[diff-first-updates]]
- [[llm-knowledge-base]]
- [[entity-registry]]
