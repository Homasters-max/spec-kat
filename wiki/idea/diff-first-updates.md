---
id: idea/diff-first-updates
page_type: idea
domain: wiki
layer: concept
tags:
- write-path
- dedup
- maintenance
- git
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/TASKS.md
---
# Diff-First Updates

## Summary
Принцип [[wiki-evolve]]: обновлять существующие страницы через unified diff, а не полной заменой. Full rewrite — только при структурных изменениях или маленьких страницах (< `small_page_threshold` символов). Сохраняет git-историю читаемой.

## How It Works

Stage 2 (LLM) выбирает операцию по правилу:

| Условие | Операция | Файл черновика |
|---------|---------|---------------|
| Страница не существует | `create` | `<id>.create.md` |
| Страница существует, добавление небольшое, размер > 1000 символов | `diff` | `<id>.diff.md` |
| Страница существует, структурное изменение ИЛИ размер ≤ 1000 символов | `rewrite` | `<id>.rewrite.md` |

**Формат diff-черновика** (pure unified diff, I-WIKI-DIFF-1):

```text
---
base_sha256: <sha256 существующей страницы>
---
--- wiki/pattern/page-id.md
+++ wiki/pattern/page-id.md
@@ -22,4 +22,5 @@
 ## See Also
 - [[automation-over-llm]]
+- [[git-as-ssot]]
```

`base_sha256` — защита от применения diff к изменённой версии страницы.

## When To Use
При выборе операции в Stage 2 wiki-evolve. Если добавляется новый раздел или несколько строк в существующий — diff. Если переструктурируется вся страница — rewrite.

## Trade-offs
- LLM сложнее писать корректный unified diff, чем полный rewrite
- Генерацию diff безопаснее делать через `difflib` в Bash, не вручную

## See Also
- [[wiki-evolve]]
- [[wiki-cli]]
- [[git-as-ssot]]
