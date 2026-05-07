# Plan: CommandBus — Idempotency, Dedup, Middleware Pipeline

## Context

Текущий `command-bus.md` описывает L0-шину с жёстко зашитым порядком вызовов.
Задача: развить в три направления — idempotency, dedup, middleware pipeline.
Все изменения — wiki-only (`obsidian-vault/llm-wiki/wiki`).

---

## Принятые решения (после grill-me)

| # | Решение |
|---|---------|
| 1 | Pipeline — **фиксированные слоты**, не свободно-composable. Порядок слотов — конвенция в `create_command_bus()`. |
| 2 | **Semantic dedup удалён**. Только exact dedup по `idempotency_key`. |
| 3 | **ValidationMiddleware удалена** — валидация уже в InputPort/CLI. |
| 4 | **LoggingMiddleware** → только stderr/stdout, не постоянное хранилище. |
| 5 | **EventStoreGuardMiddleware удалена** — guard прозрачен, явный вызов не нужен. |
| 6 | `command_id` на Command переименован в **`idempotency_key: UUID`**. |
| 7 | `idempotency_key = uuid5(NAMESPACE_SDD, f"{tool_call.id}:{call.name}")` — генерируется в **InputPort**. CLI использует `uuid4()`. |
| 8 | **ErrorClassifierMiddleware** — самый внешний слой. Guards бросают `GuardError`, не возвращают Result. |
| 9 | **IdempotencyProjection** — вне EventLog-транзакции, `INSERT ... ON CONFLICT DO NOTHING` после commit. Кешируются **только OK**. Ошибки всегда проходят полный pipeline. |
| 10 | **GL-3 не меняется** — он описывает минимальный инвариантный порядок; pipeline реализует его, расширяя. |
| 11 | `create_command_bus()` — фабричная функция, `build_pipeline` — тупая свёртка. |

---

## Финальная архитектура

### Pipeline (слоты зафиксированы в `create_command_bus`)

```
slot 0:   ErrorClassifierMiddleware   L0  — перехватывает GuardError из всего ниже
          LoggingMiddleware            L0  — stderr/stdout, timing
slot 0.5: IdempotencyMiddleware        L1  — lookup(idempotency_key) → short-circuit или pass + store
slot 1:   L0GuardMiddleware            L0  — state invariants, бросает GuardError
slot 2:   L1ExecutionGuardMiddleware   L1  — resolve→explain→write, бросает GuardError
          L1ScopeGuardMiddleware       L1  — file scope, бросает GuardError
terminal: WriteKernel.execute_and_project
```

GL-5 соблюдён: L0 ядро (slot 1 + terminal) не имеет L1-зависимостей.

### Middleware интерфейс

```python
Next = Callable[[Command], CommandResult]

class Middleware(Protocol):
    def __call__(self, cmd: Command, next: Next) -> CommandResult: ...

def build_pipeline(middlewares: list[Middleware], terminal: Next) -> Next:
    chain = terminal
    for mw in reversed(middlewares):
        prev = chain
        chain = lambda cmd, m=mw, p=prev: m(cmd, p)
    return chain
```

### CommandBus

```python
class CommandBus:
    def __init__(self, pipeline: Next):
        self._pipeline = pipeline

    def dispatch(self, cmd: Command) -> CommandResult:
        return self._pipeline(cmd)
```

### create_command_bus (фабрика)

```python
def create_command_bus(db, policy_reader, write_kernel, ...) -> CommandBus:
    pipeline = build_pipeline([
        ErrorClassifierMiddleware(),          # slot 0
        LoggingMiddleware(),                  # slot 0
        IdempotencyMiddleware(               # slot 0.5
            IdempotencyProjection(db)
        ),
        L0GuardMiddleware(...),              # slot 1
        L1ExecutionGuardMiddleware(policy_reader),  # slot 2
        L1ScopeGuardMiddleware(),            # slot 2
    ], terminal=write_kernel.execute_and_project)
    return CommandBus(pipeline)
```

### idempotency_key в Command

```python
@dataclass
class Command:
    idempotency_key: UUID = field(default_factory=uuid4)
```

### InputPort генерирует idempotency_key

```python
def _translate(self, call: ToolUseBlock) -> Command:
    spec = TOOL_REGISTRY[call.name]
    key  = uuid5(NAMESPACE_SDD, f"{call.id}:{call.name}")
    return spec.command_type(**call.input, idempotency_key=key)
```

### IdempotencyProjection

```sql
CREATE TABLE command_idempotency (
    idempotency_key UUID        PRIMARY KEY,
    result_json     JSONB       NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

- Не регистрируется в ProjectionRegistry.
- Пишется из IdempotencyMiddleware после успешного `next(cmd)` (`INSERT ... ON CONFLICT DO NOTHING`).
- At-least-once семантика: потеря записи → retry обрабатывается повторно (допустимо).

---

## Wiki Files (6 файлов)

| Файл | Действие | Ключевые изменения |
|------|----------|--------------------|
| `command-bus.md` | UPDATE | Новый `dispatch()` без hardcoded шагов; ссылка на `create_command_bus`; `idempotency_key`; guards бросают GuardError |
| `middleware-pipeline.md` | CREATE | Pattern: `Middleware` интерфейс, `build_pipeline`, слотовая структура, GL-3 совместимость |
| `idempotency-middleware.md` | CREATE | L1 middleware: exact dedup, только OK кешируется, `idempotency_key`, at-least-once |
| `idempotency-projection.md` | CREATE | L1 projection: PostgreSQL-схема, вне EventLog-транзакции, INSERT ON CONFLICT |
| `sdd-component-inventory.md` | UPDATE | 28→30 блоков: добавить IdempotencyMiddleware (L1) и IdempotencyProjection (L1) |
| `input-port.md` | UPDATE | Добавить генерацию `idempotency_key` в `_translate()`; See Also → idempotency-middleware |

---

## Verification

1. `command-bus.md`: нет hardcoded шагов в `dispatch()`; есть ссылка на `create_command_bus`.
2. `middleware-pipeline.md`: покрывает интерфейс, `build_pipeline`, 6 слотов, GL-3 совместимость.
3. `idempotency-middleware.md`: явно разграничивает exact dedup vs semantic (отсутствует); ссылается на at-least-once семантику; документирует "кешируем только OK".
4. `idempotency-projection.md`: SQL-схема, `INSERT ON CONFLICT DO NOTHING`, at-least-once.
5. `sdd-component-inventory.md`: счётчик 30, два новых блока в L1-секции.
6. `input-port.md`: `uuid5(NAMESPACE_SDD, ...)` в `_translate()`, See Also обновлён.
7. Все новые страницы: frontmatter `domain: sdd`, `page_type: pattern`, корректный `layer`.
8. Cross-references между всеми 6 файлами и: `command-bus`, `projection-registry`, `global-laws`, `error-classifier`.
