# Spec_vN — Phase N: <Title>

Status: Draft
Baseline: <prior spec or SER architecture doc>

---

## 0. Goal

<One paragraph: what capability does this phase add to SER?>

---

## 1. Scope

<What this spec covers. Which BCs are added or extended.>

### In-Scope

- BC-N: <name>

### Out of Scope

See §12.

---

## 2. Architecture / BCs

### BC-N: <Name>

```
src/<bc_dir>/
  __init__.py
  <module>.py    # <purpose>
```

### Dependencies

```text
BC-N → BC-M : <reason>
```

---

## 3. Domain Events

All events are frozen dataclasses with hashable fields (no `list`/`dict`; use `tuple`).

```python
@dataclass(frozen=True)
class MyEvent(DomainEvent):
    execution_id: str
    some_value: float
    # All fields must be hashable
```

### Event Catalog

| Event | Emitter | Description |
|-------|---------|-------------|
| `MyEvent` | `MyComponent` | <when emitted and why> |

---

## 4. Types & Interfaces

```python
@dataclass(frozen=True)
class MyEntity:
    field: str
```

### Public Interface

```python
class MyComponent:
    def __init__(self, emit: Callable[[DomainEvent], None], config: MyConfig): ...
    def do_work(self, ...) -> ...: ...
```

---

## 5. Invariants

### New Invariants

| ID | Statement | Phase |
|----|-----------|-------|
| I-NEW-N | <deterministic/event-sourced/purity statement> | N |

### Preserved Invariants (referenced)

| ID | Statement |
|----|-----------|
| I-P-N | <statement> |

---

## 6. Pre/Post Conditions

### <EventOrOperation>

**Pre:**
- <condition>

**Post:**
- <condition>

---

## 7. Use Cases

### UC-N: <Name>

**Actor:** <who triggers>
**Trigger:** <what initiates this>
**Pre:** <invariants or state that must hold>
**Steps:**
1. <step>
2. <step>
**Post:** <resulting state>

---

## 8. Integration

### Dependencies on Other BCs

| BC | Direction | Purpose |
|----|-----------|---------|
| BC-7 Telemetry | this → BC-7 | EventLog; GlobalEventRegistry dedup |

### Reducer Extensions

```python
@_handler(MyEvent)
def _handle_my_event(self, state: PartitionState, event: MyEvent) -> None:
    state.data["my_key"] = event.some_value
    # Pure: no I/O, no randomness
```

---

## 9. Verification

| # | Test Name | Invariant(s) |
|---|-----------|--------------|
| 1 | `test_<component>_determinism` | I-NEW-N |
| 2 | `test_<component>_reconstructed_from_log` | I-P-3 |

---

## 10. Out of Scope

| Item | Owner / Phase |
|------|---------------|
| <excluded feature> | Phase N+1 |
