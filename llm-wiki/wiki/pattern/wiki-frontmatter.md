---
id: pattern/wiki-frontmatter
page_type: pattern
domain: wiki
layer: architecture
tags:
- validation
- ssot
- markdown
- yaml
version: 2
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/task-list-phase2.md
---
# Wiki Frontmatter

## Summary
Обязательный YAML-блок в начале каждой wiki-страницы, определяющий метаданные для lint, rebuild и поиска. Стандарт зафиксирован в I-WIKI-FM-1 и управляется CLI автоматически при `create`, `apply_diff`, `rewrite_page`.

## How It Works
Каждый файл `wiki/**/*.md` начинается с YAML frontmatter:

```yaml
---
id: pattern/wiki-evolve
page_type: pattern
domain: wiki
layer: architecture
tags: [pipeline, write-path, ingestion]
version: 1
created: 2026-05-01
updated: 2026-05-01
sources:
  - raw/LLM_Wiki_Spec_v1.md
---
```

Поля и ответственность:

| Поле | Кто задаёт | Значения |
|------|-----------|---------|
| `id` | CLI (auto) | `{page_type}/{page_id}` |
| `page_type` | LLM (черновик) | `idea \| pattern \| tool` |
| `domain` | LLM (черновик) | из `wiki_config.domains` |
| `layer` | LLM (черновик) | из `wiki_config.layers` |
| `tags` | LLM (черновик) | kebab-case, ≤5 |
| `version` | CLI (auto) | integer от 1, инкремент при каждом write |
| `created` | CLI (auto при create) | ISO date, неизменно после создания |
| `updated` | CLI (auto при любом write) | ISO date |
| `sources` | LLM (черновик) | список `raw/*.md` файлов |

**Допустимые значения `domain`** (из `wiki_config.domains`): `wiki`, `llm`, `sdd`, `infra`, `general`

**Допустимые значения `layer`** (из `wiki_config.layers`): `concept`, `architecture`, `implementation`, `integration`

`domain` и `layer` проверяются lint против `wiki_config.domains` / `wiki_config.layers` (I-WIKI-DOMAIN-1, I-WIKI-LAYER-1). Отсутствие frontmatter = `WARNING` (не error). Пустые `tags: []` = `WARNING`.

В черновиках LLM задаёт `page_type`, `domain`, `layer`, `tags`, `sources`. CLI перезаписывает `id`, `version`, `created`, `updated` при применении через [[wiki-cli]].

## When To Use
- При создании любой wiki-страницы (frontmatter обязателен, I-WIKI-FM-1).
- При написании `.create.md` черновика: включить frontmatter с полями LLM-ответственности.
- При проверке страницы: `wiki lint` валидирует frontmatter автоматически.

## Trade-offs
- `id` содержит `page_type` как префикс (`pattern/page-id`) — это SSOT типа страницы.
- `version` инкрементируется даже при `apply_diff` (patch без замены мета).
- `domain`/`layer` в черновиках LLM — ошибки lint останавливают pipeline (I-WIKI-LINT-1).

## See Also
- [[wiki-cli]]
- [[wiki-evolve]]
- [[page-meta]]
- [[ingest-log]]
