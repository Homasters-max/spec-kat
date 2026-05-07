# Unified Error Model — Architecture Plan

**Дата:** 2026-05-05  
**Статус:** agreed (все решения приняты через grill-me сессию)

---

## Контекст

Текущее состояние Error Model в SDD:
- `ErrorEvent` (terminal) — упоминается в agent-loop.md и loop-outcome.md, но без формального schema
- `ErrorClassified` — упоминается в error-classifier.md, без формального определения
- `error_type` значения (≥12 типов) разбросаны по файлам, нет центрального реестра
- severity имплицитна: выводится из стратегии, не из события
- Нет явной связи error_type → violated invariant/rule

**Цель:** управляемый recovery через явную, машиночитаемую схему ошибок.

---

## Принятые архитектурные решения

### Решение 1: Два типа событий оправданы разными точками записи

`ErrorEvent` (terminal) пишется напрямую из AgentLoop в EventStore (GL-7 exception для L1).  
`ErrorClassified` → **упразднён** (см. Решение 7). Audit данные переносятся в `LoopStepRecorded`.

Обоснование: разные гарантии записи, а не только разная семантика.

---

### Решение 2: Переименование поля `policy_id` → `rule_id`

`policy_id` создавал ложную импликацию "правило из PolicyProjection, изменяемо через HUMAN_GATE".  
L1 axioms — hardcoded в guards, не в PolicyProjection.

**Нейтральное поле `rule_id`:**
- L0: `rule_id = None`, `invariant_id = "GL-7"` (ссылка на Global Law)
- L1 axiom: `invariant_id = None`, `rule_id = "NO_EXPLAIN_BEFORE_WRITE"`
- L1 behavioral: `invariant_id = None`, `rule_id = "MAX_WRITE_CYCLES"`
- TRANSIENT: оба None
- UNKNOWN: оба None

---

### Решение 3: `abort_kind` вычисляется, не хранится в ErrorMeta

Убрать `abort_kind` из `ErrorMeta`. Вычисляется в `ClassificationResult`:

```python
@property
def effective_abort_kind(self) -> str | None:
    if self.strategy != "ABORT":
        return None
    return "CORE_ABORT" if self.origin == "VALIDATE_STRUCTURAL" else "PROTOCOL_ABORT"
```

---

### Решение 4: `HumanGateReached` получает `gate_reason`

Budget exhaustion — отдельная причина GATE, должна быть явной. `ErrorClassified` при budget exhaustion не пишется — это не ошибка классификации.

```python
@dataclass(frozen=True)
class HumanGateReached:
    gate_reason: Literal["STEP_BUDGET", "RETRY_BUDGET", "RE_EXPLAIN_BUDGET", "GUARD_VIOLATION"]
    error_code: str | None     # заполняется если reason == GUARD_VIOLATION
    rule_id: str | None        # из ErrorMeta, если применимо
    step: int
    phase_id: int
    task_id: str | None
```

---

### Решение 5: `strategy_override` в PolicyProjection — не добавлять

Механизм уже есть: `retry_budget: dict[str, int]` и `re_explain_budget`. Если `retry_budget["X"] = 0` — стратегия RETRY немедленно эскалирует в GATE. Достаточно.

`strategy_override` создавал риск: L1 axioms могли стать "пере-управляемыми" через конфиг, ослабляя защиту.

**Инвариант ERR-5 из исходного плана — удалён.**

---

### Решение 6: `layer="UNKNOWN"` для fallback случая

Fallback (error_code отсутствует в ERROR_REGISTRY) получает `layer="UNKNOWN"` — четвёртое значение:

```python
layer: Literal["L0", "L1", "TRANSIENT", "UNKNOWN"]
```

XOR-инвариант `bool(invariant_id) XOR bool(rule_id)` применяется только для L0/L1 (известных типов). TRANSIENT и UNKNOWN — оба None.

Fallback ErrorMeta:
```python
ErrorMeta(severity="ERROR", layer="UNKNOWN", invariant_id=None, rule_id=None, default_strategy="ABORT")
# abort_kind вычисляется: ERROR + GUARD → PROTOCOL_ABORT
```

Сигнал для MetaOptimization: "ошибка вне реестра, добавить в ERROR_REGISTRY".

---

### Решение 7: `ErrorClassified` упразднён, поля переносятся в `LoopStepRecorded`

Одно событие на шаг вместо двух. AgentLoop уже пишет `LoopStepRecorded` напрямую (GL-7 exception задокументирован). TraceProjection уже подписана.

**Расширенный `LoopStepRecorded`** (новые поля — Optional, None для OK-шагов):
```python
@dataclass(frozen=True)
class LoopStepRecorded:
    # существующие поля
    step_count: int
    retry_counts: dict[str, int]
    re_explain_count: int
    policy_version: str
    # новые поля (None если status == OK)
    error_code: str | None
    severity: Literal["FATAL", "ERROR", "WARNING"] | None
    layer: Literal["L0", "L1", "TRANSIENT", "UNKNOWN"] | None
    invariant_id: str | None
    rule_id: str | None
    strategy: Literal["ABORT", "HUMAN_GATE", "RETRY", "RE_EXPLAIN"] | None
    origin: Literal["VALIDATE_STRUCTURAL", "VALIDATE_POLICY", "GUARD"] | None
```

---

### Решение 8: ERROR_REGISTRY живёт в shared-модуле `sdd.errors`

Не L0, не L1 — общий модуль. Error codes как константы класса:

```python
# sdd/errors.py
class ErrorCode:
    DIRECT_EVENTSTORE_ACCESS    = "DIRECT_EVENTSTORE_ACCESS"
    WRITE_KERNEL_FAILURE        = "WRITE_KERNEL_FAILURE"
    REDUCER_ERROR               = "REDUCER_ERROR"
    INVALID_TOOL_CALL_STRUCTURE = "INVALID_TOOL_CALL_STRUCTURE"
    PHASE_WRITE_NOT_ALLOWED     = "PHASE_WRITE_NOT_ALLOWED"
    NO_EXPLAIN_BEFORE_WRITE     = "NO_EXPLAIN_BEFORE_WRITE"
    GRAPH_CHANGED_AFTER_EXPLAIN = "GRAPH_CHANGED_AFTER_EXPLAIN"
    TASK_ISOLATED               = "TASK_ISOLATED"
    NO_PATH                     = "NO_PATH"
    CONTEXT_STALE               = "CONTEXT_STALE"
    SCOPE_VIOLATION             = "SCOPE_VIOLATION"
    PERMISSION_DENIED           = "PERMISSION_DENIED"
    MAX_WRITE_CYCLES_EXCEEDED   = "MAX_WRITE_CYCLES_EXCEEDED"
    TIMEOUT                     = "TIMEOUT"
    RATE_LIMIT                  = "RATE_LIMIT"
```

L0-guards пишут `raise SomeError(ErrorCode.DIRECT_EVENTSTORE_ACCESS)` — импортируют константу, не строку. Нет drift между guard и реестром.

---

### Решение 9: severity и abort_kind — независимые оси

**Исправление ошибки исходного плана:** FATAL severity ≠ CORE_ABORT.

| Путь обнаружения | abort_kind | Пример |
|------------------|------------|--------|
| validate() structural failure | CORE_ABORT | LLM вернул невалидный ToolCall |
| validate() policy failure | PROTOCOL_ABORT | phase_write_allowed=False |
| Guard через CommandBus | PROTOCOL_ABORT | DIRECT_EVENTSTORE_ACCESS, SCOPE_VIOLATION |

CORE_ABORT = только структурный мусор от LLM до dispatch.  
FATAL L0 violation через guard → PROTOCOL_ABORT (AuditEngine запускается).

**Таблица severity (исправленная):**

| Severity | Layer | Описание |
|----------|-------|----------|
| `FATAL` | L0 | L0 violation в execution pipeline → PROTOCOL_ABORT, AuditEngine runs |
| `ERROR` | L1 | L1 behavioral/axiom violation или budget → PROTOCOL_ABORT или GATE |
| `WARNING` | TRANSIENT | Транзиентная ошибка (timeout, rate limit) → RETRY/RE_EXPLAIN, loop продолжается |

---

### Решение 10: `validate()` возвращает `ClassificationResult`; трёхзначный `origin`

```python
origin: Literal["VALIDATE_STRUCTURAL", "VALIDATE_POLICY", "GUARD"]
```

Вычисление `effective_abort_kind`:
```python
"CORE_ABORT"     if origin == "VALIDATE_STRUCTURAL"
"PROTOCOL_ABORT" if origin in ("VALIDATE_POLICY", "GUARD")
```

validate() смотрит в ERROR_REGISTRY. Добавить в реестр:
```python
ErrorCode.INVALID_TOOL_CALL_STRUCTURE: ErrorMeta(
    severity="FATAL", layer="L0",
    invariant_id="GL-3", rule_id=None,
    default_strategy="ABORT",
)
ErrorCode.PHASE_WRITE_NOT_ALLOWED: ErrorMeta(
    severity="ERROR", layer="L1",
    invariant_id=None, rule_id="PHASE_WRITE_NOT_ALLOWED",
    default_strategy="ABORT",
)
```

`ClassificationResult` (возвращается и validate(), и ErrorClassifier):
```python
@dataclass(frozen=True)
class ClassificationResult:
    strategy: Literal["ABORT", "HUMAN_GATE", "RETRY", "RE_EXPLAIN"]
    meta: ErrorMeta
    origin: Literal["VALIDATE_STRUCTURAL", "VALIDATE_POLICY", "GUARD"]

    @property
    def effective_abort_kind(self) -> Literal["CORE_ABORT", "PROTOCOL_ABORT"] | None:
        if self.strategy != "ABORT":
            return None
        return "CORE_ABORT" if self.origin == "VALIDATE_STRUCTURAL" else "PROTOCOL_ABORT"
```

**Важно:** `origin` в `ErrorClassifier.classify()` всегда = `"GUARD"` (classifier не знает о validate-пути). validate() сам выставляет `"VALIDATE_STRUCTURAL"` или `"VALIDATE_POLICY"`.

---

### Решение 11: `details: dict[str, Any]` → `context: str | None`

Untyped dict — дыра для replay-safety. Заменить:

```python
class ErrorEvent:
    ...
    message: str          # человекочитаемое описание
    context: str | None   # дополнительный контекст (file path, command name, etc.)
```

Структурные данные per error_code — отдельный event через CommandBus, не поле в ErrorEvent.

---

### Решение 12: origin трёхзначный (уточнение к Решению 10)

Решено в Решении 10: `Literal["VALIDATE_STRUCTURAL", "VALIDATE_POLICY", "GUARD"]`.

---

### Решение 13: Скоуп изменений wiki-страниц

| Действие | Файл | Что меняется |
|----------|------|--------------|
| CREATE | `pattern/error-registry.md` | ERROR_REGISTRY, ErrorMeta, ErrorCode constants, XOR-инвариант |
| CREATE | `pattern/error-event.md` | ErrorEvent schema, LoopStepRecorded extension, HumanGateReached extension, ClassificationResult |
| UPDATE v3 | `pattern/error-classifier.md` | ClassificationResult, ERROR_REGISTRY lookup, нет strategy_override, origin="GUARD" |
| UPDATE v2 | `pattern/agent-loop.md` | LoopStepRecorded новые поля, validate() возвращает ClassificationResult, origin-логика в DECIDE |
| UPDATE v2 | `pattern/loop-outcome.md` | FATAL → PROTOCOL_ABORT clarification, CORE_ABORT = только structural ToolCall |
| DEPRECATE | `idea/classified-recovery.md` | устарела, заменена error-registry + error-event |

---

## Итоговые схемы

### ErrorMeta

```python
@dataclass(frozen=True)
class ErrorMeta:
    severity: Literal["FATAL", "ERROR", "WARNING"]
    layer: Literal["L0", "L1", "TRANSIENT", "UNKNOWN"]
    invariant_id: str | None   # L0: "GL-7", "I-ERROR-1", "GL-1", "GL-3"
    rule_id: str | None        # L1: axiom или policy key name
    default_strategy: Literal["ABORT", "HUMAN_GATE", "RETRY", "RE_EXPLAIN"]
    # abort_kind НЕ хранится — вычисляется из origin + strategy
```

### ErrorEvent (terminal)

```python
@dataclass(frozen=True)
class ErrorEvent:
    event_id: UUID
    timestamp: datetime
    # из ERROR_REGISTRY
    error_code: str
    severity: Literal["FATAL", "ERROR"]    # WARNING → loop продолжается → сюда не доходит
    layer: Literal["L0", "L1", "UNKNOWN"]  # TRANSIENT → WARNING → не terminal
    invariant_id: str | None
    rule_id: str | None
    abort_kind: Literal["CORE_ABORT", "PROTOCOL_ABORT"]
    # контекст
    phase_id: int
    task_id: str
    message: str
    context: str | None
```

### ERROR_REGISTRY (полный)

```python
ERROR_REGISTRY: dict[str, ErrorMeta] = {
    # L0 — FATAL, invariant_id
    ErrorCode.DIRECT_EVENTSTORE_ACCESS:    ErrorMeta("FATAL", "L0", "GL-7",    None, "ABORT"),
    ErrorCode.WRITE_KERNEL_FAILURE:        ErrorMeta("FATAL", "L0", "I-ERROR-1",None,"ABORT"),
    ErrorCode.REDUCER_ERROR:               ErrorMeta("FATAL", "L0", "GL-1",    None, "ABORT"),
    ErrorCode.INVALID_TOOL_CALL_STRUCTURE: ErrorMeta("FATAL", "L0", "GL-3",    None, "ABORT"),

    # L1 — ERROR, rule_id
    ErrorCode.PHASE_WRITE_NOT_ALLOWED:     ErrorMeta("ERROR", "L1", None, "PHASE_WRITE_NOT_ALLOWED", "ABORT"),
    ErrorCode.NO_EXPLAIN_BEFORE_WRITE:     ErrorMeta("ERROR", "L1", None, "NO_EXPLAIN_BEFORE_WRITE", "RETRY"),
    ErrorCode.GRAPH_CHANGED_AFTER_EXPLAIN: ErrorMeta("ERROR", "L1", None, "GRAPH_FINGERPRINT",       "RE_EXPLAIN"),
    ErrorCode.TASK_ISOLATED:               ErrorMeta("ERROR", "L1", None, "TASK_ISOLATED",           "RE_EXPLAIN"),
    ErrorCode.NO_PATH:                     ErrorMeta("ERROR", "L1", None, "NO_GRAPH_BEFORE_EXPLAIN", "RE_EXPLAIN"),
    ErrorCode.CONTEXT_STALE:               ErrorMeta("ERROR", "L1", None, "CONTEXT_STALE",           "RE_EXPLAIN"),
    ErrorCode.SCOPE_VIOLATION:             ErrorMeta("ERROR", "L1", None, "GL-6",                    "HUMAN_GATE"),
    ErrorCode.PERMISSION_DENIED:           ErrorMeta("ERROR", "L1", None, "PERMISSION_DENIED",       "HUMAN_GATE"),
    ErrorCode.MAX_WRITE_CYCLES_EXCEEDED:   ErrorMeta("ERROR", "L1", None, "MAX_WRITE_CYCLES",        "HUMAN_GATE"),

    # TRANSIENT — WARNING, без rule linkage
    ErrorCode.TIMEOUT:                     ErrorMeta("WARNING","TRANSIENT",None,None,"RETRY"),
    ErrorCode.RATE_LIMIT:                  ErrorMeta("WARNING","TRANSIENT",None,None,"RETRY"),
}
```

---

## Инварианты

| ID | Формулировка |
|----|--------------|
| ERR-1 | `ERROR_REGISTRY` в `sdd.errors` — единственный источник (severity, layer, invariant_id, rule_id). Никакой компонент не хардкодит эти значения. |
| ERR-2 | `bool(invariant_id) XOR bool(rule_id)` для layer L0/L1. TRANSIENT и UNKNOWN — оба None. |
| ERR-3 | `ErrorEvent.severity ∈ {"FATAL", "ERROR"}` — WARNING никогда не terminal event. |
| ERR-4 | Error classification audit → `LoopStepRecorded` (extended). `ErrorEvent` — только один раз на loop, при CORE_ABORT/PROTOCOL_ABORT. |
| ERR-5 | ~~Policy override разрешён для severity=ERROR~~ — **удалён**. `retry_budget` достаточно. |
| ERR-6 | Неизвестный `error_code` → `layer="UNKNOWN"`, оба None, strategy=ABORT, origin="GUARD" → PROTOCOL_ABORT. |
| ERR-7 | CORE_ABORT = только structural ToolCall validation failure (origin="VALIDATE_STRUCTURAL"). Всё остальное → PROTOCOL_ABORT. |
| ERR-8 | `abort_kind` в `ErrorEvent` вычисляется из `ClassificationResult.effective_abort_kind`, не хранится в ErrorMeta. |
| ERR-9 | Guards импортируют `ErrorCode` константы из `sdd.errors`, не пишут строки напрямую. |
