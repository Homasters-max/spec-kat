# BM25 Search

## Summary
Классический алгоритм ранжирования документов (Best Match 25) без embedding-инфраструктуры. В [[llm-knowledge-base]] реализован через `rank_bm25` как `SearchEngine` интерфейс с ephemeral in-memory индексом.

## How It Works
- `SearchEngine.index(pages)` — строит индекс при старте CLI (в памяти, не персистентный)
- `SearchEngine.search(query, min_score=0.3)` → `list[SearchResult]` sorted by score desc
- `score: float` — normalized BM25 score 0.0..1.0
- В [[wiki-query]]: `wiki search <terms>` → ranked page list для LLM Stage 1
- В [[wiki-evolve]]: при ingest находит related pages для [[context-packet]]

## When To Use
Для поиска по wiki без LLM (I-WIKI-QUERY-1 не нарушается). Эффективен при точных терминах; для размытых запросов требует подбора правильных ключевых слов.

## Trade-offs
- **+** Нет векторной БД, embedding вызовов, инфраструктуры
- **+** Детерминированный результат при одинаковом запросе
- **-** Не понимает семантики: "персональная база знаний" ≠ "knowledge management"

## See Also
- [[llm-knowledge-base]]
- [[wiki-query]]
