# Pages by SDD Domain

_Generated: 2026-05-06_

## Blueprint (L1: 1, L2: 4)

| id | type | sdd_layer | tags | updated |
|---|---|---|---|---|
| constitution-parser | pattern | L2 | pipeline, validation, ssot, automation, domain/sdd, sdd/l2, sdd/blueprint | 2026-05-06 |
| phase-orchestrator | pattern | L2 | pipeline, automation, write-path, enforcement, domain/sdd, sdd/l2, sdd/blueprint | 2026-05-06 |
| plan-manager | pattern | L2 | pipeline, validation, write-path, automation, domain/sdd, sdd/l2, sdd/blueprint | 2026-05-06 |
| policy-kernel | pattern | L1 | enforcement, ssot, write-path, automation, domain/sdd, sdd/l1, sdd/blueprint | 2026-05-06 |
| spec-manager | pattern | L2 | pipeline, validation, write-path, ssot, domain/sdd, sdd/l2, sdd/blueprint | 2026-05-06 |

## Core (L0: 15, L1: 15)

| id | type | sdd_layer | tags | updated |
|---|---|---|---|---|
| agent-handle | pattern | L1 | llm, pipeline, automation, write-path, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| command-bus | pattern | L0 | pipeline, write-path, enforcement, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| command-context | idea | L0 | pipeline, automation, ssot, domain/sdd, sdd/l0, sdd/core | 2026-05-05 |
| command-spec | pattern | L0 | cli, ssot, write-path, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| context-kernel | pattern | L1 | pipeline, search, llm, ssot, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| cqrs-boundary | pattern | L0 | cqrs, write-path, ssot, pipeline, domain/sdd, sdd/l0, sdd/core | 2026-05-05 |
| error-classifier | pattern | L1 | enforcement, validation, pipeline, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| error-event | pattern | L0 | enforcement, pipeline, write-path, domain/sdd, sdd/l0, sdd/core | 2026-05-05 |
| event-sourcing | idea | L0 | ssot, write-path, pipeline, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| eventstore-guard | pattern | L0 | enforcement, write-path, ssot, validation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| execution-guard | pattern | L1 | enforcement, pipeline, validation, write-path, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| global-laws | idea | L0 | ssot, enforcement, write-path, pipeline, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| idempotency-middleware | pattern | L1 | dedup, write-path, pipeline, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| idempotency-projection | pattern | L1 | dedup, write-path, ssot, validation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| input-port | pattern | L1 | pipeline, write-path, llm, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| l1-l2-isolation | idea | L1 | enforcement, validation, seam, ssot, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| memory-layer | pattern | L1 | ssot, read-only, pipeline, llm, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| middleware-pipeline | pattern | L1 | pipeline, write-path, enforcement, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| observability-events | pattern | L0 | enforcement, write-path, ssot, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| optimistic-concurrency-control | pattern | L0 | write-path, ssot, automation, validation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| projection-registry | pattern | L0 | ssot, write-path, pipeline, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| reducer | pattern | L0 | ssot, automation, pipeline, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| replay-engine | pattern | L0 | automation, validation, pipeline, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| sandbox-manager | pattern | L1 | enforcement, pipeline, write-path, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| scope-guard | pattern | L1 | enforcement, write-path, validation, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| sdd-actor-model | idea | L1 | enforcement, pipeline, automation, llm, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| session-orchestrator | pattern | L1 | pipeline, automation, enforcement, write-path, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| trace-store | tool | L1 | pipeline, read-only, automation, write-path, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| upcaster-registry | pattern | L0 | pipeline, validation, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| write-kernel | pattern | L0 | write-path, ssot, pipeline, enforcement, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |

## Engine (L1: 1)

| id | type | sdd_layer | tags | updated |
|---|---|---|---|---|
| agent-loop | pattern | L1 | pipeline, automation, enforcement, llm, domain/sdd, sdd/l1, sdd/engine | 2026-05-06 |

## Intelligence (L2: 4)

| id | type | sdd_layer | tags | updated |
|---|---|---|---|---|
| audit-engine | pattern | L2 | validation, automation, pipeline, ssot, domain/sdd, sdd/l2, sdd/intelligence | 2026-05-06 |
| embedding-projection | pattern | L2 | pipeline, search, automation, domain/sdd, sdd/l2, sdd/intelligence | 2026-05-05 |
| meta-optimization | pattern | L2 | automation, pipeline, llm, validation, domain/sdd, sdd/l2, sdd/intelligence | 2026-05-06 |
| scenario-gen | pattern | L2 | automation, validation, pipeline, ssot, domain/sdd, sdd/l2, sdd/intelligence | 2026-05-05 |
