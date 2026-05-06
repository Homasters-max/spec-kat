# Pages by SDD Layer

_Generated: 2026-05-06_

## L0 (15)

| id | type | sdd_domain | tags | updated |
|---|---|---|---|---|
| command-bus | pattern | Core | pipeline, write-path, enforcement, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| command-context | idea | Core | pipeline, automation, ssot, domain/sdd, sdd/l0, sdd/core | 2026-05-05 |
| command-spec | pattern | Core | cli, ssot, write-path, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| cqrs-boundary | pattern | Core | cqrs, write-path, ssot, pipeline, domain/sdd, sdd/l0, sdd/core | 2026-05-05 |
| error-event | pattern | Core | enforcement, pipeline, write-path, domain/sdd, sdd/l0, sdd/core | 2026-05-05 |
| event-sourcing | idea | Core | ssot, write-path, pipeline, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| eventstore-guard | pattern | Core | enforcement, write-path, ssot, validation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| global-laws | idea | Core | ssot, enforcement, write-path, pipeline, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| observability-events | pattern | Core | enforcement, write-path, ssot, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| optimistic-concurrency-control | pattern | Core | write-path, ssot, automation, validation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| projection-registry | pattern | Core | ssot, write-path, pipeline, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| reducer | pattern | Core | ssot, automation, pipeline, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| replay-engine | pattern | Core | automation, validation, pipeline, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| upcaster-registry | pattern | Core | pipeline, validation, automation, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |
| write-kernel | pattern | Core | write-path, ssot, pipeline, enforcement, domain/sdd, sdd/l0, sdd/core | 2026-05-06 |

## L1 (17)

| id | type | sdd_domain | tags | updated |
|---|---|---|---|---|
| agent-handle | pattern | Core | llm, pipeline, automation, write-path, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| agent-loop | pattern | Engine | pipeline, automation, enforcement, llm, domain/sdd, sdd/l1, sdd/engine | 2026-05-06 |
| context-kernel | pattern | Core | pipeline, search, llm, ssot, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| error-classifier | pattern | Core | enforcement, validation, pipeline, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| execution-guard | pattern | Core | enforcement, pipeline, validation, write-path, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| idempotency-middleware | pattern | Core | dedup, write-path, pipeline, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| idempotency-projection | pattern | Core | dedup, write-path, ssot, validation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| input-port | pattern | Core | pipeline, write-path, llm, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| l1-l2-isolation | idea | Core | enforcement, validation, seam, ssot, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| memory-layer | pattern | Core | ssot, read-only, pipeline, llm, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| middleware-pipeline | pattern | Core | pipeline, write-path, enforcement, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| policy-kernel | pattern | Blueprint | enforcement, ssot, write-path, automation, domain/sdd, sdd/l1, sdd/blueprint | 2026-05-06 |
| sandbox-manager | pattern | Core | enforcement, pipeline, write-path, automation, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |
| scope-guard | pattern | Core | enforcement, write-path, validation, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| sdd-actor-model | idea | Core | enforcement, pipeline, automation, llm, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| session-orchestrator | pattern | Core | pipeline, automation, enforcement, write-path, domain/sdd, sdd/l1, sdd/core | 2026-05-06 |
| trace-store | tool | Core | pipeline, read-only, automation, write-path, domain/sdd, sdd/l1, sdd/core | 2026-05-05 |

## L2 (8)

| id | type | sdd_domain | tags | updated |
|---|---|---|---|---|
| audit-engine | pattern | Intelligence | validation, automation, pipeline, ssot, domain/sdd, sdd/l2, sdd/intelligence | 2026-05-06 |
| constitution-parser | pattern | Blueprint | pipeline, validation, ssot, automation, domain/sdd, sdd/l2, sdd/blueprint | 2026-05-06 |
| embedding-projection | pattern | Intelligence | pipeline, search, automation, domain/sdd, sdd/l2, sdd/intelligence | 2026-05-05 |
| meta-optimization | pattern | Intelligence | automation, pipeline, llm, validation, domain/sdd, sdd/l2, sdd/intelligence | 2026-05-06 |
| phase-orchestrator | pattern | Blueprint | pipeline, automation, write-path, enforcement, domain/sdd, sdd/l2, sdd/blueprint | 2026-05-06 |
| plan-manager | pattern | Blueprint | pipeline, validation, write-path, automation, domain/sdd, sdd/l2, sdd/blueprint | 2026-05-06 |
| scenario-gen | pattern | Intelligence | automation, validation, pipeline, ssot, domain/sdd, sdd/l2, sdd/intelligence | 2026-05-05 |
| spec-manager | pattern | Blueprint | pipeline, validation, write-path, ssot, domain/sdd, sdd/l2, sdd/blueprint | 2026-05-06 |
