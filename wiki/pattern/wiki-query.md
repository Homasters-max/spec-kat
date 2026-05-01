# Wiki Query

## Summary
Read-only workflow для получения ответов из wiki (I-WIKI-QUERY-1). Никогда не пишет в SSOT напрямую. Может предлагать `promote_suggestion` — сигнал для создания ContextPacket из инсайта и последующего [[wiki-evolve]].

## How It Works
1. **Stage 0** — `wiki search <terms>` → BM25 ranked list; `wiki show <page_id>` → контент страниц
2. **Stage 1** — LLM синтезирует ответ из загруженных страниц; формирует структурированный output:
   - `answer` — прямой ответ на вопрос
   - `citations` — список использованных page_id
   - `insights` — gaps, conflicts, synthesis (тип + заметка + страницы)
   - `promote_suggestion` — optional сигнал для записи инсайта в wiki
3. **Post-action** — `wiki log-query` записывает в `query_log.jsonl`; при `promote_suggestion != null` → `wiki promote <query_id>` → [[wiki-evolve]]

## When To Use
- Для ответа на вопрос с использованием накопленных знаний
- Для обнаружения пробелов и конфликтов в wiki

## Trade-offs
- **+** Read-only — zero risk записи мусора в SSOT
- **-** BM25 не понимает семантику; для размытых запросов нужны точные термины

## See Also
- [[llm-knowledge-base]]
- [[bm25-search]]
- [[wiki-evolve]]
