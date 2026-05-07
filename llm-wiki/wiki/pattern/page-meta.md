---
id: pattern/page-meta
page_type: pattern
domain: wiki
layer: implementation
tags:
- python
- pydantic
- write-path
- validation
- domain/wiki
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/task-list-phase2.md
---
# PageMeta

## Summary
Dataclass для передачи метаданных страницы (`tags`, `sources`, `domain`, `layer`) в методы [[wiki-cli]] `repo.py`, отделяя write-операцию от метаданных согласно архитектурному решению Phase 2.

## How It Works

```python
@dataclass
class PageMeta:
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    domain: str = ""
    layer: str = ""
```

`PageMeta` не является полем `RewriteOp` — передаётся как отдельный аргумент методов `repo.py`:

```python
repo.create_page(page_id, page_type, content, meta=meta)
repo.rewrite_page(op, meta=meta)
```

`apply.py` собирает `PageMeta` из frontmatter черновика (`.create.md` или `.rewrite.md`):
1. Читает `page_type`, `domain`, `layer`, `tags`, `sources` из YAML frontmatter черновика.
2. Собирает `PageMeta(tags=..., sources=..., domain=..., layer=...)`.
3. Передаёт в соответствующий метод `repo.py`.

`apply_diff` (`A5`) не принимает `PageMeta` — diff не несёт метаданных; `domain`, `layer`, `tags` не меняются при patch.

## When To Use
- При реализации `repo.create_page` и `repo.rewrite_page` — всегда принимать `meta: PageMeta`.
- При написании `apply.py` — всегда извлекать `PageMeta` из frontmatter черновика перед вызовом repo.
- При `apply_diff` — `PageMeta` не нужен.

## Trade-offs
- **+** `RewriteOp` остаётся чистой write-операцией, метаданные не смешиваются с контентом.
- **-** `apply.py` обязан извлекать `PageMeta` из каждого черновика — дополнительный parsing шаг.
- Метаданные `domain`/`layer` проверяются lint, но не валидируются в `PageMeta` на уровне dataclass.

## See Also
- [[wiki-cli]]
- [[wiki-frontmatter]]
- [[wiki-evolve]]
