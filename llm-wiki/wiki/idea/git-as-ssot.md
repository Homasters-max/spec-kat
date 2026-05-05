---
id: idea/git-as-ssot
page_type: idea
domain: wiki
layer: concept
tags:
- git
- ssot
- knowledge-base
- ingestion
- domain/wiki
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS.md
---
# Git as SSOT

## Summary
Принцип [[wiki-cli]]: git — единственный источник истины о состоянии базы знаний. Uncommitted файлы в `raw/` = необработанные знания. Committed = включённые в систему. История изменений страниц = git log.

## How It Works

`git.py::GitRepo.pending_raw_files()` определяет что ещё не обработано:

```python
pending = uncommitted_files_in_raw()
         - files_whose_sha256_in_ingest_log()
```

**Поток:**
1. Пользователь кладёт файл в `raw/` — он появляется в `git status` (untracked/modified)
2. `wiki ingest --pending` находит его через `git status`
3. После полного wiki-evolve цикла — `git commit raw/file.md wiki/**`
4. `wiki mark-ingested <sha256> --file <path>` — файл больше не pending

**Почему git, не filesystem:**
- Uncommitted = явный сигнал "ещё не обработано"
- Commit = атомарная операция "raw + wiki страницы вместе"
- История правок страниц хранится в git log


## State File Git Strategy

Не все файлы wiki-системы должны быть в git:

| Файл | Git | Причина |
|------|-----|---------|
| `ingest_log.jsonl` | tracked | SSOT: что уже обработано |
| `query_log.jsonl` | .gitignore | Эфемерный state, lifecycle отличен от ingest |
| `glossary_pending.yaml` | .gitignore | Временный буфер до `wiki sync-glossary` |
| `runtime/cache/` | .gitignore | Автогенерируемые ContextPackets |

## Trade-offs
- Vault должен быть git-репозиторием (или вложен в него)
- `git status` медленнее чем filesystem scan на больших репозиториях

## See Also
- [[wiki-cli]]
- [[wiki-evolve]]
- [[automation-over-llm]]
