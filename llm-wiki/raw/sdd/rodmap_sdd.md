Ниже — **приоритетный список того, что реально усиливает SDD v2 как Meta Harness**, без расползания архитектуры.

---

# 🔴 P0 — без этого система не «закрывается»

## 1. Orchestrator (агенты / шаги выполнения)

```text
цель: управлять циклом resolve → explain → write
```

Минимум:

```text
AgentLoop:
  plan → step → observe → decide → next
```

Нужно:

* управление retry / stop
* интеграция с Policy (лимиты)
* контроль стадий (phase-aware)

---

## 2. Replay-based Testing (ядро качества)

```text
цель: гарантировать детерминизм
```

Нужно:

* replay любого task
* сравнение state/snapshot
* golden tests (expected outputs)

---

## 3. CommandBus (жёсткий контракт)

```text
цель: единственная точка записи
```

Добавить:

* idempotency (command_id)
* dedup
* middleware pipeline (logging, validation)

---

## 4. Error Model (единая схема ошибок)

```text
цель: управляемый recovery
```

Нужно:

```text
ErrorEvent:
  type
  invariant_id / policy_id
  severity
```

---

# 🟠 P1 — делает систему «умной»

## 5. ContextEngine (пересобрать чётко)

```text
цель: формировать контекст для LLM
```

Минимум стратегии:

```text
resolve  → расширение графа
explain  → причинность
trace    → история
invariant/policy → ограничения
```

---

## 6. Query DSL (минимальный, но строгий)

```text
цель: стабильный API к графу
```

Без строк:

```python
Query(
  start_nodes,
  edge_types,
  direction,
  max_depth
)
```

---

## 7. Graph Pipeline (deterministic build)

```text
цель: стабильный граф
```

Добавить:

* fingerprint
* cache
* incremental rebuild (optional позже)

---

## 8. Trace System (операционный слой)

```text
цель: анализ поведения агента
```

Минимум:

```text
trace:
  graph_calls
  file_reads
  file_writes
  decisions
```

---

# 🟡 P2 — масштабирование и эволюция

## 9. Policy System (расширить)

```text
цель: управлять поведением без кода
```

Добавить:

* rate limits
* budgets (context / steps)
* retry strategies

---

## 10. Metrics / Observability

```text
цель: видеть систему
```

Метрики:

* success rate задач
* violations per policy
* cycles per task

---

## 11. Snapshot / Caching Layer (опционально)

```text
цель: ускорение
```

Пока:

* in-memory cache достаточно

---

## 12. L2 Extensions Framework

```text
цель: безопасно добавлять ML / RAG
```

Контракт:

```text
read-only
async
non-blocking
```

---

# 🟢 P3 — продакшн-уровень

## 13. Migration System

```text
цель: эволюция схем
```

* event versioning
* projection rebuild

---

## 14. Multi-agent support

```text
цель: несколько агентов
```

* shared context
* coordination (через EventLog)

---

## 15. Security / Permissions

```text
цель: контроль доступа
```

* actor roles
* scope restrictions

---

# 🧠 Главное (суть приоритизации)

```text
P0 = делает систему замкнутой
P1 = делает её умной
P2 = делает её масштабируемой
P3 = делает её production-ready
```

---

# 🚀 Если сжать до must-have

```text
1. Orchestrator
2. Replay Testing
3. CommandBus
4. ContextEngine
5. Graph Pipeline
```

---

# Итог

```text
фокус:
не добавлять всё
а закрыть контур:
agent → context → decision → write → replay → improve
```

---

