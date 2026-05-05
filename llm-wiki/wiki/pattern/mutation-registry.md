---
id: pattern/mutation-registry
page_type: pattern
domain: sdd
layer: architecture
tags:
- validation
- automation
- pipeline
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/commandspec-deepening-plan.md
---
# MutationRegistry

Словарь `ErrorCode → MutationStrategy` в testing-модуле, заменяющий статический `MUTATION_TABLE` внутри `AdversarialScenarioMutator`. Обеспечивает compile-time и test-time согласованность с [[error-registry]] без смешения testing concerns в доменный слой.

## How It Works

```python
# testing/mutation_registry.py
MutationRegistry: dict[str, MutationStrategy] = {
    ErrorCode.SCOPE_VIOLATION:             InjectScopeViolation(),
    ErrorCode.GRAPH_CHANGED_AFTER_EXPLAIN: InjectGraphFingerprint(),
    ErrorCode.TIMEOUT:                     InjectSlowExecution(),
    ErrorCode.PERMISSION_DENIED:           InjectPermissionDenial(),
}
DEFAULT_MUTATION = InvertCriticalChecks()
```

**Invariant test — покрытие всех error codes:**

```python
def test_mutation_registry_covers_all_error_codes():
    known_codes = set(ErrorRegistry.keys()) - {ErrorCode.UNKNOWN}
    assert known_codes.issubset(MutationRegistry.keys()), \
        f"Missing mutation strategies: {known_codes - MutationRegistry.keys()}"
```

**Locality:** testing concern остаётся в `testing/` — `ErrorMeta` доменного объекта не знает о мутациях.

**Leverage:** добавить новый ErrorCode = один файл (`error-registry`); тест явно укажет на отсутствующую запись в MutationRegistry.

**Почему не `ErrorMeta.mutation_strategy`:** mutation — тестовый концепт, `ErrorMeta` — доменный. Смешение нарушает разделение слоёв L0/L1.

## When To Use

При добавлении нового `ErrorCode` в [[error-registry]]: добавить соответствующую запись в MutationRegistry, иначе `test_mutation_registry_covers_all_error_codes` провалится в CI.

## Trade-offs

**Плюсы:** testing concerns изолированы от домена; добавление error code → автоматическая CI-подсказка о необходимости mutation strategy; один тест вместо ручного аудита.

**Минусы:** MutationRegistry — второй словарь с теми же ключами, что ErrorRegistry; разработчик должен знать о необходимости синхронизации (но тест делает это видимым, а не silent).

## See Also

- [[error-registry]] — источник ErrorCode ключей
- [[error-classifier]] — классификация ошибок в middleware pipeline
