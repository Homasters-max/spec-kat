---
id: pattern/snapshot-comparator
page_type: pattern
domain: sdd
layer: architecture
tags:
- validation
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/replay-based-testing-architecture.md
---
# SnapshotComparator

Сравнивает фактический State с `expected_state` из [[golden-fixture]]. Partial match по умолчанию — только явно заявленные ключи. `expected_state: {}` → full compare с `initial_state()`. Нормализует timestamps/UUIDs перед сравнением.

## How It Works

```python
class SnapshotComparator:
    SENTINEL_ANY = "__any__"

    def compare(self, actual: State, expected: dict) -> CompareResult:
        if not expected:
            # expected_state: {} → regression check: ничего не изменилось
            return self._compare_full(actual, initial_state())
        # Partial match: только явно указанные ключи
        return self._compare_partial(actual, expected)

    def _compare_partial(self, actual: State, expected: dict) -> CompareResult:
        # 1. Нормализует timestamps/UUIDs в actual и expected (I-REPLAY-5)
        # 2. Сравнивает ТОЛЬКО ключи из expected (I-REPLAY-6)
        # 3. __any__ → любое значение OK
        # 4. list поля → subset check (actual ⊇ expected_list) если strict_lists=False
        # 5. strict_lists=True → exact match для list
        ...
```

**Семантика:**

| Ситуация | Поведение |
|---------|---------|
| `expected = {}` | Full compare с `initial_state()` — ничего не изменилось |
| `expected = {key: val}` | Partial match — только заявленные ключи проверяются |
| `value = "__any__"` | Этот ключ не проверяется (любое значение OK) |
| list поле, `strict_lists: false` | `actual_list ⊇ expected_list` (subset check) |
| list поле, `strict_lists: true` | `actual_list == expected_list` (exact match) |

## When To Use

Вызывается `GoldenTestRunner` после `ReplayEngine().replay()`:

```python
state_ok = SnapshotComparator().compare(result.final_state, fixture.expected_state)
```

## Trade-offs

- Partial match упрощает написание тестов, но может пропустить неожиданные мутации в незаявленных полях
- `expected_state: {}` строг: любое отличие от `initial_state()` → fail — используйте осознанно

## See Also

- [[replay-engine]]
- [[golden-fixture]]
- [[replay-based-testing]]
