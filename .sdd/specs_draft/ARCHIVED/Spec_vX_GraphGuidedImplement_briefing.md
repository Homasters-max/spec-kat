# Briefing: Graph-Guided Implement Protocol
<!-- Документ для передачи контекста в сессию DRAFT_SPEC v55 -->
<!-- Статус: черновик идей — НЕ APPROVED SPEC -->
<!-- Обновлён: 2026-04-30 (системный архитектурный анализ) -->

**Дата:** 2026-04-30
**Контекст:** после завершения Phase 54 (Real System Validation)
**Целевая сессия:** DRAFT_SPEC v55 → PLAN Phase 55 → DECOMPOSE
**Следующая фаза после tested_by:** DRAFT_SPEC v56 → Phase 56 (Graph-First)

---

## 1. Проблема: почему grep — архитектурный анти-паттерн в SDD

Текущий `implement.md` позволяет LLM читать Task Inputs как список файлов
и неявно предполагает навигацию через grep/прямое чтение. Это нарушает:

| Нарушение | Следствие |
|-----------|-----------|
| Обход Event Sourcing | контекст строится не из детерминированного источника |
| Нет семантики зависимостей | LLM не видит, кто зависит от изменяемого файла |
| Произвольный scope | LLM "гуляет" по коду вне Task Inputs (или слепнет без него) |
| Нет контроля | нельзя аудировать, почему прочитан конкретный файл |

**Правильная формулировка:** "Ты не заменяешь grep на граф. Ты запрещаешь навигацию вне графа."

---

## 2. Текущее состояние графа (факты на 2026-04-30)

```
NODES: COMMAND(15), EVENT(20), FILE(141), GUARD(5), INVARIANT(38), REDUCER(1), TERM(13)
TOTAL: 233 nodes

EDGES: imports(455), implements(24), emits(7), guards(8), means(7)
TOTAL: 501 edges

ОТСУТСТВУЮТ:
  - tested_by edges: 0       ← критично для Phase 56
  - calls edges: 0           ← нет связей между функциями
  - CLASS/FUNCTION nodes: 0  ← граф FILE-level, не symbol-level
```

**Критическое наблюдение:** imports составляют 455/501 = 91% всех рёбер.
При traversal без фильтрации — это шум. `sdd explain` весовой (imports=0.60 vs implements=0.85)
но traversal по умолчанию должен использовать только `implements, guards, emits`.

**Вывод:** граф сейчас знает "какой файл реализует какую команду" и "кто что импортирует".
Он НЕ знает "кто вызывает функцию X" и "какой тест покрывает компонент Y".

Это означает: **полный Graph-First сейчас преждевременен** — система ослепнет.
Правильно: Graph-Guided (Phase 55) → Graph-First (Phase 56 после tested_by).

---

## 3. Архитектура решения: два шага

### Phase 55 — Graph-Guided Implement (реалистично сейчас)

**Принцип:** граф = обязательный навигатор, файлы = materialization layer.

```
БЫЛО:  Task Inputs → читать всё подряд → grep для поиска зависимостей
СТАЛО: anchor_nodes → graph traversal → читать только graph-reachable файлы
```

**Новый STEP 4.5 в `implement.md` (MANDATORY, вставляется между STEP 4 и STEP 5):**

```bash
# STEP 4.5 — Graph Discovery (обязателен, SEM-13: sequential)
sdd resolve "<task semantic keywords>"          # найти релевантные узлы
sdd explain <anchor_node_id>                   # зависимости anchor-узла
sdd trace FILE:<file_to_modify>                # кто зависит от изменяемого файла
```

**Правило чтения:** файл может быть прочитан ТОЛЬКО если:
- (a) появился в выводе любой из команд resolve/explain/trace текущей сессии, ИЛИ
- (b) явно в Task Inputs И `sdd explain FILE:X` вернул 0 edges → fallback разрешён + логируется

**Новый инвариант:**
```
I-IMPLEMENT-GRAPH-1:
  LLM MUST NOT read any src/ file unless it is either:
  (a) reachable via graph traversal from task anchor nodes (appeared in
      resolve/explain/trace output during current session), OR
  (b) explicitly listed in Task Inputs AND sdd explain returns 0 edges
      for that node (degraded mode — MUST log via sdd record-metric)
  Violation: MissingGraphJustification → STOP
  Enforcement: PROTOCOL-level (Phase 55). CODE-level в Phase 56.
```

**Graph Budget (обязателен — иначе LLM "гуляет" по графу как по файлам):**
```yaml
graph_budget:
  max_nodes_per_query: 20   # защита от взрыва traversal
  max_traversal_depth: 2    # FILE-level граф: глубже = транзитивные imports = шум
  max_graph_calls: 5        # 3 минимум (resolve+explain+trace), 2 запас
  traversal_edge_types:     # явный whitelist — imports исключён по умолчанию
    - implements
    - guards
    - emits
```

**Обязательный before-write шаг (добавляется в STEP 5 перед записью):**
```bash
# Перед изменением ЛЮБОГО файла:
sdd trace FILE:<target>   # кто зависит от этого файла
# LLM обязан учесть все зависимые узлы перед записью
# Если 0 результатов — это валидно (leaf node), не ошибка
```

---

### Phase 56 — Full Graph-First (после tested_by edges)

**Когда:** `tested_by` edges добавлены (TestedByEdgeExtractor реализован в Phase 56
как часть того же цикла), count > 0.

**Новый формат TaskSet:**
```yaml
T-NNN:
  anchor_nodes:
    - COMMAND:complete
    - INVARIANT:I-HANDLER-PURE-1
  allowed_traversal:
    - implements   # файл → команда
    - guards       # файл → инвариант
    - tested_by    # файл → тест (Phase 56)
    - imports      # файл → зависимости
  graph_budget:
    max_nodes: 20
    max_depth: 2
  write_scope:                          # только для записи — по-прежнему явно
    - FILE:src/sdd/commands/complete.py
```

**Что исчезает в Phase 56:**
- `Task Inputs` как список файлов → заменяется `anchor_nodes`
- `grep` любого вида
- Произвольное расширение scope
- Fallback (I-IMPLEMENT-GRAPH-2 запрещает его)

**Что появляется:**
- Scope = граф-достижимые узлы из anchor_nodes
- Context = индуцированный подграф — детерминирован и replay-able
- Enforcement = CODE-level (`sdd complete` проверяет graph_call_count в сессии)

---

## 4. Архитектура enforcement (ключевой вопрос)

### Почему "declared not enforced" не работает

I-PLAN-IMMUTABLE-AFTER-ACTIVATE — задекларирован, нарушается. I-IMPLEMENT-GRAPH-1
без enforcement постигнет та же судьба при первом же grep или Read без graph-вызова.

### Phase 55: Protocol-level enforcement (достаточно для начала)

**Механизм:** STEP 4.5 добавляется как MANDATORY precondition в implement.md.
Согласно SEM-13 — все guard-steps линейные и блокирующие. STEP 4.5 должен пройти
до STEP 5. Если LLM пропускает STEP 4.5 — это нарушение SEM-13, не только GRAPH-1.

**Audit trail:** LLM логирует degraded fallbacks через `sdd record-metric`:
```bash
sdd record-metric --key graph_degraded_reads --value 1 --phase N --task T-NNN
```

Это создаёт EventLog запись → аудируемо → виден паттерн деградации по фазам.

**Итого:** Protocol enforcement = SEM-13 + I-IMPLEMENT-GRAPH-1 + audit metric.
Это НЕ code-level, но достаточно строго: нарушение SEM-13 = STOP → report-error.

### Phase 56: Code-level enforcement

Реализовать `sdd graph-guard` — новую CLI-команду:
```bash
sdd graph-guard check --task T-NNN --session-log "$SESSION_LOG"
# Exit 0 если ≥1 graph-call (resolve/explain/trace) был вызван в сессии
# Exit 1 если 0 graph-calls → STOP
```

Добавить в STEP 8 (перед `sdd complete`):
```bash
sdd graph-guard check --task T-NNN --session-log "$SESSION_LOG"
sdd complete T-NNN
```

Это аналог паттерна `sdd phase-guard check` — guard как precondition before write.
Технически: graph-guard читает audit_log.jsonl текущей сессии, проверяет наличие
`graph_call` entries. Не требует нового хранилища — тот же audit_log.jsonl.

---

## 5. Что нужно изменить (артефакты)

### Phase 55 изменения:

| Артефакт | Изменение | Enforcement |
|----------|-----------|-------------|
| `.sdd/docs/sessions/implement.md` | добавить STEP 4.5 (Graph Discovery), before-write trace | SEM-13 |
| `CLAUDE.md §INV` | добавить I-IMPLEMENT-GRAPH-1 | Protocol |
| `.sdd/docs/ref/tool-reference.md` | `sdd resolve/explain/trace` — добавить как разрешённые в IMPLEMENT | Reference |
| `.sdd/norms/norm_catalog.yaml` | новая норма NORM-GRAPH-001: graph-first navigation | norm-guard |

### Phase 56 изменения (после tested_by extractor):

| Артефакт | Изменение |
|----------|-----------|
| `src/sdd/graph/extractors/` | добавить `tested_by_edges.py` (TestedByEdgeExtractor) |
| `src/sdd/commands/` | новая команда `sdd graph-guard` |
| `.sdd/templates/taskset.md` | новый формат `anchor_nodes` + `allowed_traversal` |
| `.sdd/docs/sessions/decompose.md` | генерировать anchor_nodes вместо Task Inputs |
| `CLAUDE.md §INV` | I-IMPLEMENT-GRAPH-2 (запрет fallback) |
| `.sdd/docs/sessions/implement.md` | STEP 4.5 → STEP 8: добавить `sdd graph-guard check` |

---

## 6. Риски и митигации

| Риск | Проявление | Митигация |
|------|-----------|-----------|
| imports = шум (91% edges) | explain возвращает нерелевантные результаты | traversal_edge_types whitelist (implements/guards/emits) |
| Граф неполный (сейчас) | explain → 0 edges для большинства файлов | fallback разрешён + `sdd record-metric` |
| LLM игнорирует граф | читает файлы без graph justification | SEM-13 block + I-IMPLEMENT-GRAPH-1 |
| Граф медленный | 5 CLI-вызовов на задачу | кэш уже есть (GraphCache + content-addressed) |
| Scope creep по графу | LLM traverses too deep | graph_budget (max_depth: 2) |
| Phase 56 до tested_by | граф не покроет тесты → регрессии | Phase 56 BLOCKED пока tested_by count == 0 |
| before-write trace = 0 | LLM думает что ошибка | явно задокументировать: 0 = leaf node, валидно |

**Главный риск Phase 55:** enforcement protocol-level, не code-level. Деградация
видна только через `sdd record-metric` анализ после фазы. Приемлемо для Phase 55 —
поведение учится, не принуждается. Phase 56 это исправит.

---

## 7. Конкретный пример (как выглядит в реальности)

**Задача:** реализовать изменение в `COMMAND:complete`.

**Phase 55 (Graph-Guided):**
```bash
# STEP 4.5
sdd resolve "complete command idempotency"
# → FILE:src/sdd/commands/complete.py, INVARIANT:I-CMD-IDEM-1

sdd explain COMMAND:complete
# → edges: [complete.py --implements--> COMMAND:complete]
# traversal: implements только (не imports)

sdd trace FILE:src/sdd/commands/complete.py
# → кто импортирует complete.py = [registry.py, cli.py]
# LLM видит зависимых перед записью

# ТОЛЬКО ТЕПЕРЬ: читаем complete.py
# Обоснование: appeared in explain output (implements edge)
# Обоснование registry.py: appeared in trace output
```

**Phase 56 (Graph-First):**
```yaml
T-NNN:
  anchor_nodes: [COMMAND:complete, INVARIANT:I-CMD-IDEM-1]
  allowed_traversal: [implements, guards, tested_by]
  write_scope: [FILE:src/sdd/commands/complete.py]
```
```bash
sdd explain COMMAND:complete
# → FILE:complete.py (implements)
# → INVARIANT:I-CMD-IDEM-1 (guards)
# → TEST:test_complete_idempotent.py (tested_by) ← Phase 56

sdd graph-guard check --task T-NNN  # блокирует complete если не было graph-calls
sdd complete T-NNN
```

---

## 8. Последовательность сессий

```
СЕЙЧАС:
  DRAFT_SPEC v55  → Phase 55 spec (Graph-Guided Implement)
  PLAN Phase 55   → изменения implement.md + инварианты (3-4 задачи)
  DECOMPOSE       → T-5501...T-5504
  IMPLEMENT       → изменить implement.md, CLAUDE.md, tool-reference.md, norm_catalog.yaml

ПОСЛЕ (когда tested_by = 0 перестанет быть правдой):
  DRAFT_SPEC v56  → Phase 56 spec (Graph-First + TestedByExtractor + graph-guard)
  PLAN Phase 56
  DECOMPOSE       → T-5601...T-560N
```

**Не надо делать всё сразу.** Phase 55 даёт 80% ценности при 20% риска.
Phase 56 требует новой инфраструктуры (extractor + guard command).

---

## 9. graph_budget: обоснование чисел

| Параметр | Значение | Обоснование |
|----------|----------|-------------|
| `max_traversal_depth: 2` | 2 | Граф FILE-level. Путь: COMMAND→implements→FILE (глубина 1), FILE→imports→FILE (глубина 2). Глубина 3+ = транзитивные зависимости = шум без tested_by |
| `max_graph_calls: 5` | 5 | Минимум: 3 (resolve + explain + trace). Запас: 2 для второго explain при нескольких anchor_nodes. Больше = "гуляем по графу" как по файлам |
| `max_nodes_per_query: 20` | 20 | GraphCache уже ограничивает. 20 nodes = достаточно для FILE-level задачи. Больше = context overflow риск |
| `traversal_edge_types` | implements, guards, emits | imports=91% рёбер — шум. Whitelist: только семантически значимые типы |

---

## 10. Ключевые формулировки для spec

```
Цель Phase 55: Graph-Guided Implement — сделать граф обязательным
               навигатором при реализации задач. Файлы доступны только
               через graph justification или явный fallback с метрикой.

I-IMPLEMENT-GRAPH-1: LLM MUST NOT read any src/ file unless graph-justified
                     OR Task Inputs fallback with degraded metric logged.
I-IMPLEMENT-GRAPH-2 (Phase 56): fallback запрещён. Граф = единственный source.

Инвариант "Context = subgraph":
  context LLM при реализации = детерминированный подграф
  (nodes + edges достижимые из anchor_nodes через whitelist traversal
  в пределах graph_budget)
  → детерминизм, explainability, replay, diff между состояниями
```
