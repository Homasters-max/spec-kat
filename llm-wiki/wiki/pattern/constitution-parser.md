---
created: '2026-05-06'
domain: sdd
id: pattern/constitution-parser
layer: architecture
page_type: pattern
sdd_domain: Blueprint
sdd_layer: L2
sources:
- raw/SDD_Bounded_Contexts_Plan.md
tags:
- pipeline
- validation
- ssot
- automation
- domain/sdd
- sdd/l2
- sdd/blueprint
updated: '2026-05-06'
version: 1
---
# ConstitutionParser

**[proposed]** L2-компонент Blueprint-домена: парсит `constitution.md`, публикует `ConstitutionProjection`.

## How It Works

Читает `constitution.md` (tech stack, linter rules, архитектурные принципы) и конвертирует в `ConstitutionProjection`, доступную через `memory.blueprint.read.constitution()`.

```text
constitution.md
  → ConstitutionParser (L2, Blueprint)
  → ConstitutionProjection (Blueprint domain)
  → MemoryLayer.blueprint.read.constitution()
  → Потребители:
      SpecManager   — validation gate (нарушение → reject)
      Engine        — читает правила через MemoryLayer (не знает о парсере)
```

Engine никогда не парсит `constitution.md` напрямую — это domain knowledge Blueprint. Engine читает `ConstitutionProjection` через MemoryLayer.

Размещение в Blueprint (не в Engine) обосновано: парсинг формата constitution.md — domain knowledge Blueprint, не execution logic Engine.

## When To Use

При старте фазы или изменении `constitution.md`. Единственный источник `ConstitutionProjection`.

## Trade-offs

- ConstitutionParser владеет format knowledge constitution.md — изменение формата требует изменения только парсера, потребители через MemoryLayer не затронуты.

## See Also

- [[sdd-bounded-contexts]] — Blueprint domain, L2
- [[spec-manager]] — потребитель (validation gate)
- [[memory-layer]] — `memory.blueprint.read.constitution()`
- [[policy-kernel]] — смежный механизм governance rules
