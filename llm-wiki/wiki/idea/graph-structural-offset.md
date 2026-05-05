---
id: idea/graph-structural-offset
page_type: idea
domain: sdd
layer: architecture
tags:
- search
- pipeline
- ssot
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/sdd-v2-architecture-deepening.md
---
# Graph Structural Offset

## Summary

Graph Structural Offset — замена `event_offset` в cache fingerprint [[graph-query-engine]]. Вместо номера последнего события в EventLog используется offset последнего **графо-структурного** события — события от команды с `CommandSpec.graph_structural = true`. Большинство событий в write-heavy TaskRun (TraceEntry, SessionDeclared, ErrorClassified) не меняют граф — кэш перестаёт инвалидироваться на каждый append.

## How It Works

**Новый fingerprint:**

```text
graph_structural_offset = max(
    event.offset
    for event in EventLog
    if REGISTRY[event.command_name].graph_structural == true
)

fingerprint = hash(code_hash + spec_hash + graph_structural_offset)
```

**`CommandSpec.graph_structural: bool`** — флаг в CommandRegistry, default `false`. Команды с `true`:

```text
activate-phase   — новая фаза = новые узлы в графе
complete T-NNN   — задача завершена = edge status меняется
define-invariant — новый инвариант = новый узел
update-policy    — политика влияет на доступность узлов
bootstrap-policy — начальное состояние политики
```

Команды с `false` (кэш не инвалидируется по этому фактору):

```text
resolve       — read-only query
explain       — read-only, фиксирует fingerprint
record-session — мета-данные сессии
switch-phase  — навигация, не мутация
```

**`code_hash` остаётся в fingerprint:** каждый `write` (Edit/Write tool call) меняет `code_hash` → кэш инвалидируется. Это намеренно — изменение кода может добавить/удалить узлы графа (новые функции, удалённые классы). Три `write` подряд = три rebuild. Это ожидаемое поведение, оптимизация batch writes вне scope.

**Locality:** решение "какие команды меняют граф" живёт в CommandRegistry рядом с определением команд — не в отдельном whitelist или конфиге.

## When To Use

При проектировании cache invalidation для любого компонента, который строит представление из Code + Specs + EventLog. Принцип: инвалидация только на события, которые могут изменить результат query.

## Trade-offs

**Плюсы:** в рамках одного TaskRun (цикл `resolve → explain → write × N`) граф не перестраивается между шагами (если нет `write`); locality — флаг `graph_structural` живёт там же где команда; нет отдельного whitelist файла.

**Минусы:** разработчик добавляющий новую команду обязан явно подумать о `graph_structural` — риск пропустить флаг; `graph_structural_offset = max(...)` требует O(N) scan EventLog при каждом вычислении fingerprint (но это read-only, не критично при наличии индекса по `command_name`).

**Invariant:** `write` инвалидирует кэш через `code_hash`, не через `graph_structural_offset`. Это два независимых канала инвалидации.

## See Also

- [[graph-query-engine]] — компонент где применяется этот подход
- [[command-bus]] — CommandRegistry где задаётся `graph_structural` флаг
- [[event-sourcing]] — принцип, из которого следует что только определённые события меняют граф
