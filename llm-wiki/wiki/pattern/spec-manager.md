---
created: '2026-05-06'
domain: sdd
id: pattern/spec-manager
layer: architecture
page_type: pattern
sdd_domain: Blueprint
sdd_layer: L2
sources:
- raw/SDD_Bounded_Contexts_Plan.md
tags:
- pipeline
- validation
- write-path
- ssot
- domain/sdd
- sdd/l2
- sdd/blueprint
updated: '2026-05-06'
version: 1
---
# SpecManager

**[proposed]** L2-компонент Blueprint-домена: управляет жизненным циклом и качеством спецификаций.

## How It Works

**Traceability**: связывает спеку с исходными требованиями (Requirement ID). Каждая спека имеет ссылку на источник требований.

**Validation Gate**: проверяет спеку против `ConstitutionProjection` (читает через `memory.blueprint.read.constitution()`). Нарушение конституции → reject (SpecDrafted не эмитируется).

**Idempotency**: дедуплицирует спеки по hash/имени. `SpecDrafted` эмитируется только один раз для уникальной спеки.

**Coverage Tracking**: владеет данными о покрытии секций спеки задачами. Нельзя `ApproveSpec` при uncovered секциях.

```text
SpecDraftCommand → SpecManager
  ├─ validate against ConstitutionProjection (via MemoryLayer)
  ├─ dedup check (hash comparison)
  ├─ emit SpecDrafted (только если прошло обе проверки)
  └─ emit SpecApproved (только если все секции покрыты TaskSet)
```

Эмитирует события Blueprint-домена: `SpecDrafted`, `SpecApproved`.

Использует [[constitution-parser]] через `memory.blueprint.read.constitution()` — не знает о парсере напрямую.

## When To Use

При любом создании или изменении спецификации. Единственный путь к `SpecDrafted` и `SpecApproved` events.

## Trade-offs

- Validation Gate против ConstitutionProjection делает SpecManager зависимым от актуальности [[constitution-parser]] output.
- Coverage Tracking предотвращает неполные планы, но требует явного маппинга spec sections → tasks.

## See Also

- [[sdd-bounded-contexts]] — Blueprint domain, L2
- [[constitution-parser]] — поставляет ConstitutionProjection
- [[plan-manager]] — строит TaskSet для coverage
- [[memory-layer]] — `memory.blueprint.read.*`
- [[event-sourcing]]
