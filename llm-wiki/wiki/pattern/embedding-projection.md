---
created: '2026-05-05'
domain: sdd
id: pattern/embedding-projection
layer: architecture
page_type: pattern
sdd_domain: Intelligence
sdd_layer: L2
sources:
- raw/Memory Layer and Invariant Management.md
tags:
- pipeline
- search
- automation
- domain/sdd
- sdd/l2
- sdd/intelligence
updated: '2026-05-05'
version: 1
---
# Embedding Projection

L2-проекция (eventual consistency): хранит векторные embeddings узлов графа для SemanticSearch. Обновляется через outbox/async worker — вне L1 транзакции EventLog.

## How It Works

**Схема EmbeddingEntry:**

```yaml
EmbeddingEntry:
  node_id: string
  embedding: vector
  model_id: "e5-small"
  version: "v1"
  config_hash: "abc123..."
```

**Версионирование (ML-7):** каждый embedding привязан к `model_id + version + config_hash`. Метаданные модели сохраняются в event metadata при записи:

```yaml
embedding:
  model_id: "e5-small"
  version: "v1"
  config_hash: "abc123..."
```

**Replay правило:** replay использует тот же embedding spec. Если модель недоступна → `EmbeddingProjection replay FAIL`. Это нарушение GL-1 (Determinism) для L2.

**Isolation (ML-9):** replay FAIL блокирует только L2 EmbeddingProjection. L1 projections восстанавливаются нормально. L2 SemanticSearch деградирует до `partial_result` — не ошибка.

**Async worker (ML-8):** обрабатывает события строго по `event_offset` (FIFO):
- один consumer per projection (single-writer, no parallel apply)
- retries идемпотентны по `event_id`
- gap apply запрещён: если `event_offset N+1` прибыл раньше `N` — ждать `N`

**Миграция модели:** отдельный `embedding-migration` процесс с human gate. Пересчитывает embeddings → эмитит `EmbeddingRecomputed` events с новым `model_id`. До завершения L2 помечается `STALE`.

## When To Use

Используется [[memory-layer]] L2 API (`QueryEngineSemantic`) для semantic search, similarity lookup. Не используется L1-компонентами (Guards, ContextKernel) — они работают только через L1 API.

```python
if embedding_not_ready:
    return partial_result  # не ошибка, L2 eventual
```

## Trade-offs

- Eventual consistency: L2 queries могут видеть stale data — это ожидаемо.
- Model migration требует human gate и временного STALE периода.
- L1 никогда не ждёт L2 readiness — система работает без embeddings.

## See Also

- [[memory-layer]] — фасад, предоставляющий L2 API
- [[l1-l2-isolation]] — изоляция L2 от L1 компонентов
- [[projection-registry]] — L1 projections (EmbeddingProjection НЕ регистрируется в ProjectionRegistry — только через outbox)
