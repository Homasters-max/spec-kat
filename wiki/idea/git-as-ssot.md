# Git as SSOT

## Summary
Git используется как единственный источник истины состояния [[llm-knowledge-base]]. Uncommitted файлы = pending (ожидают evolve). Committed файлы = обработаны. История знаний = git log. Никакой отдельной базы данных состояния не нужно.

## How It Works
- `raw/` uncommitted → pending для [[wiki-evolve]] (I-WIKI-PENDING-1)
- `wiki/` + `derived/` committed → обработанные знания (SSOT)
- `ingest_log.jsonl` — только audit trail "ingested" (dedup-фильтр, не источник состояния)
- `GitRepo.pending_files()` = uncommitted `raw/` WHERE sha256 NOT IN ingest_log
- Эволюция знаний полностью читаема через `git log` и `git diff`

## When To Use
Везде в [[llm-knowledge-base]]: состояние pipeline определяется git-статусом, не отдельным state store.

## Trade-offs
- **+** Бесплатная история, branching, rollback через git
- **+** Нет отдельной БД — меньше инфраструктуры
- **-** Pending detection через git + ingest_log = две проверки (небольшой overhead)

## See Also
- [[llm-knowledge-base]]
- [[wiki-evolve]]
