# Diff-First Updates

## Summary
Принцип обновления wiki-страниц: по умолчанию через unified diff (WikiDiff + base_sha256), full rewrite разрешён только при двух условиях: страница мала (`size < SMALL_PAGE_THRESHOLD`) или изменения структурны (`diff_ratio > 0.8`). Решение принимает `wiki apply-drafts` автоматически — не LLM (I-WIKI-2).

## How It Works
- `WikiRepo.save_page()` не существует — архитектурный запрет случайного full rewrite
- `apply_diff(WikiDiff)` — default path; WikiDiff содержит `base_sha256` как optimistic lock
- `rewrite_page(op: RewriteOp)` — требует явного `reason: "small_page" | "structural_change"`
- Conflict при sha256 mismatch → `ApplyResult.conflict=True` → STOP (I-WIKI-CONFLICT-1)

## When To Use
Всегда при обновлении существующих wiki-страниц в [[wiki-evolve]] Stage 2.

## Trade-offs
- **+** Git-история читаема: diff показывает точные изменения, а не полную замену
- **+** Optimistic lock предотвращает затирание concurrent изменений
- **-** LLM должен генерировать корректный unified diff (форматная точность важна)

## See Also
- [[wiki-evolve]]
- [[extraction-result]]
