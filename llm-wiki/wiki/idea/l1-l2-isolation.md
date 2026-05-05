---
id: idea/l1-l2-isolation
page_type: idea
domain: sdd
layer: architecture
tags:
- enforcement
- validation
- seam
- ssot
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/Memory Layer and Invariant Management.md
---
# L1/L2 Isolation

Архитектурный принцип [[memory-layer]]: строгая изоляция детерминированного L1 API от eventual-consistency L2 API. Guards и ContextKernel физически не имеют доступа к L2. Нарушение изоляции = нарушение ML-6.

## How It Works

**Четыре уровня enforcement:**

```text
1. API surface:
   L1-компоненты получают только:
     ReadModel
     QueryEngineDeterministic
   QueryEngineSemantic не импортируется в L1 namespace

2. Type-level:
   L1MemoryLayer — final/sealed класс
   L2 интерфейсы не входят в L1MemoryLayer
   Нельзя подменить на L2-содержащий тип

3. Runtime assert:
   assert isinstance(memory, L1MemoryLayer)
   Guard проверяет тип memory при каждом вызове

4. CI linter (tach / import-linter):
   правило: guards/* не импортирует memory/l2/*
   Нарушение = CI fail
```

**Физические модули:**

```python
# L1 module — Guards и AuditEngine видят только это
class ReadModel: ...
class QueryEngineDeterministic: ...

# L2 module — физически недоступен из L1
class QueryEngineSemantic: ...
```

**Почему это важно:**

L1 projections имеют strict read-after-write consistency (одна PostgreSQL транзакция). L2 — eventual consistency через outbox/async worker. Если Guard читает L2, он может принять решение на stale данных, нарушая детерминизм протокола. Изоляция предотвращает эту категорию ошибок на уровне типов и архитектуры.

**Где L2 разрешён:**

```text
L2 API доступен для:
  MetaOptimization (анализ трендов, proposals)
  ScenarioGen
  RAG pipeline
  Компоненты, явно работающие с eventual data

L2 недоступен для:
  Guards (все виды)
  ContextKernel (L1 ContextSnapshot)
  AuditEngine (L1 только)
```

## When To Use

Применяется автоматически через архитектурные слои. Разработчик нового компонента должен ответить: "этому компоненту нужен только детерминированный state или ему нужен semantic search?" — и получить соответствующий тип MemoryLayer.

## Trade-offs

- Более строгий API контракт упрощает тестирование L1-компонентов (нет моков для L2).
- CI linter добавляет build-time проверку, устраняя целый класс архитектурных регрессий.
- Разработка L2-компонентов требует явного документирования допустимости stale data.

## See Also

- [[memory-layer]] — где изоляция реализована
- [[embedding-projection]] — L2-проекция, изолированная от L1
- [[execution-guard]] — L1-компонент, получающий только L1MemoryLayer
- [[context-kernel]] — L1-компонент, строит ContextSnapshot только из L1
