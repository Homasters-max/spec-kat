---
id: pattern/constitution-parser
page_type: pattern
domain: sdd
layer: architecture
tags:
- pipeline
- validation
- ssot
- automation
- domain/sdd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/SDD_Bounded_Contexts_Plan.md
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
