---
id: pattern/wiki-semantic-extractor
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- search
- llm
- read-only
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/Wiki Skill DocGraph Integration Plan.md
---
# WikiSemanticExtractor

Компонент чтения семантического контекста DocGraph-узлов для [[graph-query-engine]]. Заменяет устаревший `SpecExtractor` (Q6, I-QE-ADAPTER-1). Читает prose исключительно через `WikiSnapshot` — никогда напрямую из файловой системы.

## How It Works

**Навигация (три уровня prose = один контекстный пакет):**

```text
task → part_of → phase → part_of → domain
  P1              P2                P3
```

**Приоритеты контента:**

| Приоритет | Источник                       |
|-----------|--------------------------------|
| P1        | task prose (Summary, Criteria, Notes) |
| P2        | phase prose                    |
| P3        | domain prose                   |
| P4        | code context                   |
| P5        | affects-рёбра (только при наличии бюджета) |

Если `budget_exceeded` → affects-рёбра (P5) пропускаются (Q14).

**Интерфейс:**

```python
class WikiSemanticExtractor:
    def extract(self, node_id: str, snapshot: WikiSnapshot) -> SemanticContext: ...
```

**SSOT разделение:**
- Wiki (через WikiSnapshot) → семантика (prose, intent, domain rules)
- EventLog → структура (status, deps, blocked_by)

`WikiSemanticExtractor` MUST NOT читать структурные данные из Wiki (I-GRAPH-SSOT-2).

## When To Use

Вызывается [[graph-query-engine]] при построении контекстного пакета. Input всегда приходит через [[wiki-snapshot-loader]] — никогда путём прямого чтения `/wiki/vN/`.

## Trade-offs

- Строгое разделение: semantic extractor = prose only, не статус задач. Избегает смешения SSOT (I-GRAPH-SSOT-2).
- Навигация по трём уровням (task→phase→domain) даёт богатый контекст, но увеличивает размер пакета при глубокой иерархии.

## See Also

- [[wiki-snapshot-loader]]
- [[graph-query-engine]]
- [[context-kernel]]
- [[doc-graph-node]]
- [[docgraph-dual-ssot]]
