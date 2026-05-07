# Plan: SDD Wiki Navigation Slices + Unified Graph Index

## Context

В wiki 102 страницы без систематической навигации по двум разрезам SDD-архитектуры:
- **Горизонтальный:** L0 Core → L1 Execution → L2 Intelligence
- **Вертикальный:** Core / Blueprint / Engine / Intelligence

`sdd-component-inventory` перечисляет 35 блоков, но SDD-слой и SDD-домен нигде не хранятся как структурированные метаданные — только в prose. LLM вынужден искать вслепую.

**Решение:** три взаимосвязанных изменения:
1. Обогатить frontmatter ~40 страниц полями `sdd_layer`/`sdd_domain` + тегами `sdd/l*`
2. Сделать `graph.json` единым SSOT — полная схема узлов, все derived views генерируются из него
3. Создать 9 prose wiki-страниц как навигационные якоря (таблицы — в derived views)

---

## Принятые решения (grill-me)

| Вопрос | Решение |
|--------|---------|
| Хранение метаданных | Frontmatter каждой страницы (`sdd_layer: L1`, `sdd_domain: Core`) |
| Obsidian граф | Теги `sdd/l1`, `sdd/core` в массиве `tags` (иерархия в Obsidian) |
| Единый индекс | `graph.json` — полная схема узлов, SSOT для всех derived |
| Derived views | Генерируются из `graph.json`, не из файлов напрямую |
| Новые views | `by-sdd-layer.md` и `by-sdd-domain.md` |
| Скоуп аннотации | Компоненты из инвентаря + явно связанные концепции; wiki-domain страницы — без `sdd_layer` |
| Null стратегия | `"sdd_layer": null` в graph.json для страниц без координат |
| Lint-валидация | WARNING если страница из `sdd_components` в `wiki_config.yaml` не имеет `sdd_layer` |
| 9 wiki страниц | Все 9, но prose-only (без таблиц — они в derived views) |

---

## Часть 1 — Обогащение `graph.json`

### Новая схема узла

```json
{
  "write-kernel": {
    "links": ["event-sourcing", "eventstore-guard", "projection-registry"],
    "sdd_layer": "L0",
    "sdd_domain": "Core",
    "type": "pattern",
    "domain": "sdd",
    "layer": "architecture",
    "tags": ["write-path", "ssot", "enforcement", "sdd/l0", "sdd/core", "domain/sdd"],
    "updated": "2026-05-06",
    "title": "Write Kernel"
  },
  "wiki-evolve": {
    "links": ["context-packet", "wiki-cli"],
    "sdd_layer": null,
    "sdd_domain": null,
    "type": "pattern",
    "domain": "wiki",
    "layer": "architecture",
    "tags": ["pipeline", "ingestion", "write-path", "domain/wiki"],
    "updated": "2026-05-06",
    "title": "Wiki Evolve"
  }
}
```

### Рефакторинг `rebuild.py`

Один проход по wiki-файлам → строим `graph` (dict) → пишем `graph.json` → генерируем все derived из `graph`:

```
_build_graph(vault_root) → dict[page_id, NodeData]
  ├── reads frontmatter: type, domain, layer, sdd_layer, sdd_domain, tags, updated
  ├── extracts wikilinks → links
  └── returns full NodeData per page

rebuild_all(vault_root):
  graph = _build_graph(vault_root)
  _write_graph_json(derived_dir, graph)       ← SSOT
  _write_index(derived_dir, graph)            ← из graph
  _write_by_domain(views_dir, graph)          ← из graph
  _write_by_layer(views_dir, graph)           ← из graph
  _write_by_type(views_dir, graph)            ← из graph
  _write_by_sdd_layer(views_dir, graph)       ← НОВЫЙ
  _write_by_sdd_domain(views_dir, graph)      ← НОВЫЙ
```

Файл: `.claude/skills/wiki/scripts/rebuild.py`

### Новые derived views

`derived/views/by-sdd-layer.md` — группировка по `sdd_layer` (L0 / L1 / L2 / null-раздел пропускается):
```
## L0 (13)
| id | type | sdd_domain | tags | updated |
...

## L1 (14)
...

## L2 (8)
...
```

`derived/views/by-sdd-domain.md` — группировка по `sdd_domain` (Core / Blueprint / Engine / Intelligence):
```
## Core (L0: 13, L1: 13)
| id | type | sdd_layer | tags | updated |
...
```

---

## Часть 2 — Frontmatter аннотация (~40 страниц)

### Таблица аннотаций (из sdd-component-inventory + sdd-bounded-contexts)

**L0 Core (13 блоков):**

| page_id | sdd_layer | sdd_domain | новые теги |
|---------|-----------|------------|-----------|
| event-sourcing | L0 | Core | sdd/l0, sdd/core |
| reducer | L0 | Core | sdd/l0, sdd/core |
| write-kernel | L0 | Core | sdd/l0, sdd/core |
| command-bus | L0 | Core | sdd/l0, sdd/core |
| command-context | L0 | Core | sdd/l0, sdd/core |
| eventstore-guard | L0 | Core | sdd/l0, sdd/core |
| projection-registry | L0 | Core | sdd/l0, sdd/core |
| upcaster-registry | L0 | Core | sdd/l0, sdd/core |
| error-event | L0 | Core | sdd/l0, sdd/core |
| global-laws | L0 | Core | sdd/l0, sdd/core |
| command-spec | L0 | Core | sdd/l0, sdd/core |
| optimistic-concurrency-control | L0 | Core | sdd/l0, sdd/core |
| cqrs-boundary | L0 | Core | sdd/l0, sdd/core |

**L1 Core (13 блоков):**

| page_id | sdd_layer | sdd_domain | новые теги |
|---------|-----------|------------|-----------|
| execution-guard | L1 | Core | sdd/l1, sdd/core |
| scope-guard | L1 | Core | sdd/l1, sdd/core |
| trace-store | L1 | Core | sdd/l1, sdd/core |
| error-classifier | L1 | Core | sdd/l1, sdd/core |
| session-orchestrator | L1 | Core | sdd/l1, sdd/core |
| context-kernel | L1 | Core | sdd/l1, sdd/core |
| input-port | L1 | Core | sdd/l1, sdd/core |
| agent-handle | L1 | Core | sdd/l1, sdd/core |
| sandbox-manager | L1 | Core | sdd/l1, sdd/core |
| idempotency-middleware | L1 | Core | sdd/l1, sdd/core |
| idempotency-projection | L1 | Core | sdd/l1, sdd/core |
| memory-layer | L1 | Core | sdd/l1, sdd/core |
| middleware-pipeline | L1 | Core | sdd/l1, sdd/core |

**L1 Blueprint (1 блок) + L1 Engine:**

| page_id | sdd_layer | sdd_domain | новые теги |
|---------|-----------|------------|-----------|
| policy-kernel | L1 | Blueprint | sdd/l1, sdd/blueprint |
| agent-loop | L1 | Engine | sdd/l1, sdd/engine |

**L2 Blueprint (4 блока):**

| page_id | sdd_layer | sdd_domain | новые теги |
|---------|-----------|------------|-----------|
| spec-manager | L2 | Blueprint | sdd/l2, sdd/blueprint |
| plan-manager | L2 | Blueprint | sdd/l2, sdd/blueprint |
| phase-orchestrator | L2 | Blueprint | sdd/l2, sdd/blueprint |
| constitution-parser | L2 | Blueprint | sdd/l2, sdd/blueprint |

**L2 Intelligence (4 блока):**

| page_id | sdd_layer | sdd_domain | новые теги |
|---------|-----------|------------|-----------|
| audit-engine | L2 | Intelligence | sdd/l2, sdd/intelligence |
| meta-optimization | L2 | Intelligence | sdd/l2, sdd/intelligence |
| scenario-gen | L2 | Intelligence | sdd/l2, sdd/intelligence |
| embedding-projection | L2 | Intelligence | sdd/l2, sdd/intelligence |

**Концепции-якоря (явно связанные с архитектурой):**

| page_id | sdd_layer | sdd_domain | новые теги |
|---------|-----------|------------|-----------|
| l1-l2-isolation | L1 | Core | sdd/l1, sdd/core |
| sdd-actor-model | L1 | Core | sdd/l1, sdd/core |
| observability-events | L0 | Core | sdd/l0, sdd/core |
| replay-engine | L0 | Core | sdd/l0, sdd/core |

---

## Часть 3 — `wiki_config.yaml` + lint

### Добавить в `wiki_config.yaml`

```yaml
sdd_components:
  - event-sourcing
  - reducer
  - write-kernel
  # ... полный список из таблицы выше
```

### Расширить `lint.py`

Новая проверка `check_sdd_annotations(vault_root, pages)`:
- Читает `sdd_components` из `wiki_config.yaml`
- Для каждого page_id из списка: проверяет наличие `sdd_layer` и `sdd_domain` в frontmatter
- WARNING (не ERROR) если отсутствует

Файл: `.claude/skills/wiki/scripts/lint.py`

---

## Часть 4 — 9 prose wiki-страниц

Все страницы — `idea` тип, `layer: architecture`, `domain: sdd`. Без таблиц компонентов (они в derived). Prose: назначение, границы, ключевые инварианты, антипаттерны.

### Новые теги для навигационных страниц

| page_id | sdd_layer | sdd_domain | теги |
|---------|-----------|------------|------|
| sdd-horizontal-slice | null | null | bounded-contexts, navigation, domain/sdd |
| sdd-vertical-slice | null | null | bounded-contexts, navigation, domain/sdd |
| sdd-layer-l0 | null | null | sdd/l0, enforcement, ssot, domain/sdd |
| sdd-layer-l1 | null | null | sdd/l1, pipeline, automation, domain/sdd |
| sdd-layer-l2 | null | null | sdd/l2, validation, automation, domain/sdd |
| sdd-domain-core | null | null | sdd/core, ssot, write-path, domain/sdd |
| sdd-domain-blueprint | null | null | sdd/blueprint, pipeline, domain/sdd |
| sdd-domain-engine | null | null | sdd/engine, pipeline, llm, domain/sdd |
| sdd-domain-intelligence | null | null | sdd/intelligence, validation, domain/sdd |

`sdd-horizontal-slice` содержит алгоритм SDDNAV-1 (5 шагов навигации для LLM) + ссылки на `derived/views/by-sdd-layer.md`.

---

## Часть 5 — SKILL.md: правило классификации sdd_layer/sdd_domain

Добавить в раздел wiki-evolve **Stage 2** рядом с описанием `.create.md` формата:

```
SDD CLASSIFICATION RULE (применять когда domain: sdd):

  sdd_layer:
    L0 — определяет физику системы: EventLog, WriteKernel, Guards, CommandBus,
         ProjectionRegistry и их прямые зависимости. Полностью детерминирован,
         нет зависимости от L1/L2.
    L1 — исполняет задачи детерминированно через L0-примитивы. Ephemeral,
         replay-safe, session-scoped.
    L2 — анализирует, предлагает, оптимизирует. Eventual consistency.
         НИКОГДА не мутирует state напрямую.
    null — концепция/паттерн без чёткой привязки к слою

  sdd_domain:
    Core        — владеет инфраструктурой (EventLog, write path, projections)
    Blueprint   — владеет проектной моделью (specs, plans, phases, policy)
    Engine      — владеет runtime исполнения (AgentLoop, execution)
    Intelligence — владеет анализом (metrics, proposals, audit)
    null        — страница не является SDD-компонентом

  Если неоднозначно → [[sdd-component-inventory]] как авторитетный источник
  Если компонент вне SDD-системы → sdd_layer: null, sdd_domain: null
```

Также обновить `.create.md` FORMAT в SKILL.md — добавить поля:

```yaml
---
page_type: pattern
domain: sdd
layer: architecture
sdd_layer: L1          # L0 | L1 | L2 | null
sdd_domain: Core       # Core | Blueprint | Engine | Intelligence | null
tags: [pipeline, enforcement, sdd/l1, sdd/core, domain/sdd]
sources: ["raw/filename.md"]
---
```

Файл: `.claude/skills/wiki/SKILL.md`

---

## Порядок реализации

```
Step 1: Рефакторинг rebuild.py
  - Новая схема NodeData
  - Один проход _build_graph()
  - Все derived из graph
  - Новые _write_by_sdd_layer() и _write_by_sdd_domain()
  - wiki rebuild → проверить что старые views не сломались

Step 2: Обогащение frontmatter (~40 страниц)
  - Добавить sdd_layer, sdd_domain в frontmatter
  - Добавить sdd/l*, sdd/* в tags
  - wiki rebuild → проверить by-sdd-layer.md и by-sdd-domain.md

Step 3: wiki_config.yaml + lint.py
  - Добавить sdd_components список
  - Добавить check_sdd_annotations() в lint.py
  - wiki lint → должны быть только WARNINGs для пропущенных

Step 4: SKILL.md
  - Добавить SDD CLASSIFICATION RULE в wiki-evolve Stage 2
  - Обновить .create.md FORMAT (добавить sdd_layer, sdd_domain)

Step 5: 9 новых wiki-страниц
  - Создать .create.md в runtime/tmp/
  - wiki apply-drafts
  - wiki commit

Step 6: Верификация
```

---

## Критические файлы

**Изменяются:**
- `.claude/skills/wiki/scripts/rebuild.py` — рефакторинг + новые views
- `.claude/skills/wiki/scripts/lint.py` — check_sdd_annotations()
- `.claude/skills/wiki/scripts/models.py` — NodeData dataclass (опционально)
- `obsidian-vault/llm-wiki/.wiki/config/wiki_config.yaml` — sdd_components list
- `.claude/skills/wiki/SKILL.md` — classification rule + обновлённый .create.md FORMAT
- ~40 frontmatter файлов в `wiki/idea/` и `wiki/pattern/`

**Создаются:**
- `derived/views/by-sdd-layer.md`
- `derived/views/by-sdd-domain.md`
- 9 новых `wiki/idea/sdd-*.md`

---

## Верификация

```bash
# 1. Структура graph.json — все узлы имеют sdd_layer поле
python3 -c "import json; g=json.load(open('derived/graph.json')); assert all('sdd_layer' in v for v in g.values())"

# 2. Новые views существуют
ls derived/views/by-sdd-layer.md derived/views/by-sdd-domain.md

# 3. L0 компоненты корректно сгруппированы
grep -A3 "## L0" derived/views/by-sdd-layer.md

# 4. Lint чистый (только WARNING, нет ERROR)
wiki lint

# 5. Obsidian: тег sdd/l0 виден в Tag Pane → фильтр показывает L0 компоненты
# 6. LLM тест: wiki show sdd-horizontal-slice → SDDNAV-1 алгоритм доступен
# 7. 9 новых страниц существуют
wiki exists sdd-horizontal-slice sdd-vertical-slice sdd-layer-l0 sdd-layer-l1 sdd-layer-l2 \
  sdd-domain-core sdd-domain-blueprint sdd-domain-engine sdd-domain-intelligence
```
