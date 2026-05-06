# Open Questions Index

_Updated: 2026-05-06 · Все 6 батчей применены (26 страниц, 229 открытых + 26 закрытых) — COMPLETE_

> Индекс нерешённых архитектурных вопросов.  
> Обновлять при открытии/закрытии P0, при >5 изменениях, перед релизом.  
> Источник правды — `## Open Questions` блоки в страницах wiki.  
> Поиск: `grep -r "- \[ \]" /obsidian-vault/llm-wiki/wiki/`

## P0 — Critical (must close before release)

### [[event-sourcing]]

- Q1 PARTIAL: total order EventLog — гарантия не формализована
- Q2 PARTIAL: event_index — глобальный? concurrent append в PostgreSQL?
- Q3 PARTIAL: batch semantics — batch failure path открыт
- Q5: partial failure между handle() и append()
- Q7: backward compatibility старого EventLog с новой версией reducer
- Q9: cross-stream events — один лог или несколько?
- Q10 PARTIAL: poison events — DLQ/quarantine механизм
- Q11 PARTIAL: log growth & compaction SLA для prod
- Q55: logical vs wall-clock time — canonical ordering
- Q56: Lamport/vector clock при multi-agent
- Q57: одинаковый wall-clock timestamp
- Q58: distributed reordering при concurrent append
- Q59: формализация "happened-before"
- Q60: deterministic tie-breaker

### [[execution-guard]]

- Q23: guard side effects — запрет или разрешение логирования
- Q24 PARTIAL: human override structural guard — механика
- Q25: guards при replay — policy change handling
- Q26: bypass protection — convention vs code-enforced

### [[eventstore-guard]]

- Q40: fsync/fdatasync durability гарантия
- Q41: payload checksums — silent data corruption detection
- Q42: bit-rot detection — periodic re-hash
- Q43: double write (WAL + EventLog) vs EventLog IS WAL
- Q44: backup без потери event_index порядка
- Q45: point-in-time recovery к конкретному event_index
- Q46: CI тест: backup → restore → replay → State equality
- Q47: torn write protection — partial row append
- Q48: canonical event format — JSON/MessagePack/Protobuf
- Q49: deterministic JSON key ordering
- Q50: schema_version/schema_hash в каждом событии
- Q51: missing fields при replay новым reducer
- Q52: canonical hash для State snapshot / ContextPacket
- Q53: bit-identical dump для cross-environment comparison
- Q54: serializer version drift — compatibility matrix

### [[optimistic-concurrency-control]]

- Q12 PARTIAL: backoff алгоритм не задан (max_retries есть)
- Q13: conflict semantics — всегда retry или иногда ABORT?
- Q14: long-running commands — heartbeat/timeout/re-read
- Q15: concurrent commands к одному aggregate — serialization point
- Q16 PARTIAL: logical write skew не рассмотрен
- Q17: livelock avoidance при высокой contention

### [[write-kernel]]

- Q5: partial failure между handle() и append()
- Q49: deterministic JSON key ordering в serialization
- Q50: schema_hash в каждом событии
- Q51: missing fields handling при replay
- Q54: serializer version drift

### [[classified-recovery]]

- Q30 PARTIAL: crash recovery — незавершённые сессии
- Q31 PARTIAL: desync detection EventLog vs State_index
- Q32: poison command — circuit breaker / DLQ
- Q33: handler timeout semantics — enforcement

### [[global-laws]]

- Q35: clock abstraction — datetime.now() запрет
- Q36: reproducible environment snapshot definition
- Q37: автоматическая проверка чистоты reducer
- Q38: детекция недетерминизма в runtime

## P1 — Important

### [[reducer]]

- Q35: clock abstraction в handlers — mock time
- Q36: reproducible environment snapshot
- Q37: автоматическая проверка чистоты reducer
- Q38: детекция недетерминизма в runtime
- Q39 PARTIAL: context reproducibility — нет formal proof
- Q80 PARTIAL: materialized snapshots для prod replay
- Q81: eviction policy для phases_snapshots
- Q82: partial replay с checkpoint
- Q83: post-condition assertions в reducer
- Q84: invariant violation — reducer vs guard
- Q85: State_index.yaml canonical format

### [[context-kernel]]

- Q72: token budget на ContextPacket — enforcement
- Q73 PARTIAL: алгоритм приоритизации context
- Q74: context staleness definition
- Q75 PARTIAL: context versioning → event_index binding
- Q76: external data в context — детерминизм
- Q77: context leakage через shared projections
- Q78: context diff инструмент

### [[replay-engine]]

- Q98 PARTIAL: replay failure handling — replay-specific flow
- Q99: replay performance SLA
- Q100: post-replay consistency check
- Q101 PARTIAL: replay CLI — `sdd replay-from` не задокументирован

### [[global-laws]] (P1 часть)

- Q109: единый реестр инвариантов — machine-checkable format?
- Q110: DSL для автоматической проверки инвариантов
- Q111: timing проверки инвариантов — pre/post/replay
- Q112: старый EventLog + новый инвариант — migration path
- Q113: versioning инвариантов — backward-compatible vs breaking
- Q114: coverage metric — какие инварианты покрыты тестами
- Q115: конфликты между инвариантами — статически или runtime

### [[command-bus]]

- Q102: реестр всех допустимых commands со схемами
- Q103: pure intent vs computed commands — различие в EventLog
- Q104: точка валидации command schema — middleware vs handler
- Q105: external state в command payload — replay determinism
- Q106: формальная гарантия command determinism
- Q107: replay commands для debugging actor intent
- Q108: rejected command log — RejectedCommandEvent vs отдельный store

### [[command-spec]]

- Q104: точка валидации command schema
- Q106: формальная гарантия command determinism

### [[causal-linkage]]

- Q116: единая модель causal graph — формализована в спеке?
- Q117: полная цепочка причинности — SQL query vs projection
- Q118: API get_lineage(event_id) → [ancestor_events]
- Q119: гарантия no orphan events — invariant?
- Q120: cycles в causal graph — acyclicity check
- Q121: visualizaton causal graph — CLI / Graphviz

### [[session-orchestrator]]

- Q66: обязательные шаги pipeline фазы — конфигурируемы?
- Q67: параллельные шаги — concurrent writes coordination
- Q68: abort незакрытой фазы — PhaseAbandoned event
- Q69: reopening закрытой фазы — monotonicity impact
- Q70: lifecycle документа DRAFT→OBSOLETE — mechanics

### [[projection-registry]]

- Q88 PARTIAL: corruption detection — desync EventLog vs projection
- Q89 PARTIAL: multi-projection consistency guarantee
- Q90: schema migration без полного rebuild
- Q91: projection dependencies — порядок обновления
- Q92: hot vs cold projections — SLA
- Q93: property-based tests для детерминизма проекций

## P2 — Optimization

### [[agent-loop]]

- Q138: canonical список ролей агентов — переопределяемы через PolicyKernel?
- Q139: паттерн оркестрации фазы — sequential vs streaming
- Q140: tool ACL по роли (Reviewer read-only, Executor read+write)
- Q141: sub-executor delegation — tracing в EventLog
- Q142: reviewer/executor loop budget — escalation to HUMAN_GATE
- Q143: actor_id lifecycle в сессии

### [[replay-based-testing]]

- Q122: golden master end-to-end tests
- Q123: fuzz testing для reducer
- Q124: property-based tests (commutativity, idempotency)
- Q125: replay(EventLog) N раз → bit-identical State в CI
- Q126: chaos tests — crash, disk full, DB drop
- Q127: OCC contention stress tests
- Q128: deterministic test harness — seed, mock clock
- Q181: replay-verification в CI pipeline
- Q182: PR validation через SDD
- Q183: check-dod как deployment gate
- Q184: EventStore schema parity dev/staging/prod
- Q185: upcaster migration tests в CI

### [[audit-engine]]

- Q164: dashboard метрики для human-оператора
- Q165: real-time stream событий для monitoring
- Q166: distributed tracing CLI→EventLog (OpenTelemetry?)
- Q167: log correlation с TaskRun/event_id
- Q168: `sdd debug-task` step-by-step replay
- Q169: alerting rules (ABORT loop, corruption, projection lag)
- Q170: audit_log.jsonl просмотр — CLI vs web UI
- Q171: spec quality metrics (completeness, ambiguity)
- Q172: spec coverage verification
- Q173: spec linting — противоречия, пустые секции
- Q174: spec → task coverage gap analysis
- Q175: spec aging detection

### [[meta-optimization]]

- Q191: quality metric для proposals MetaOptimization
- Q192: policy change latency → next TaskRun
- Q193: SDD self-hosted development — bootstrap problem
- Q194: добавление нового invariant в работающую систему
- Q195: граница wiki-знания vs PolicyKernel behavior
- Q196: capability regression detection при смене модели

## P3 — Research

### [[agent-loop]] (P3 часть)

- Q215: token budget per TaskRun — enforcement
- Q216: LLM API costs recording
- Q217: budget alert threshold — HUMAN_GATE vs ABORT
- Q218: model selection policy через PolicyKernel
- Q219: context compression при нехватке budget
- Q220: phase-level cost budget
- Q221: ROI metric AgentScore / tokens_spent

### [[loop-policy]] (P3 часть)

- Q12 PARTIAL: backoff алгоритм (exponential/fixed) не задан
- Q216: LLM API costs recording
- Q217: budget alert threshold
- Q220: phase-level cost budget

### [[policy-kernel]]

- Q149: RBAC модель — PolicyKernel vs hardcoded
- Q150: actor_id и role при старте AgentLoop
- Q151: constitution.md — состав и попадание в ContextKernel
- Q152: prompt injection protection в ContextKernel
- Q153: secret management — credentials никогда в EventLog
- Q197: runtime vs compile-time config граница
- Q198: config изменение и детерминизм EventLog replay
- Q199: ConfigUpdated event в EventLog
- Q200: replay старого EventLog с новой конфигурацией
- Q201: граница системный конфиг vs PolicyKernel policy
- Q202: config rollback — git revert vs ConfigRolledBack event
- Q209: event_id forgery — cryptographic signing?
- Q210: event signing HMAC/Ed25519
- Q211: INSERT protection — Row-level security
- Q212: физический write-доступ к EventLog DB
- Q213: DB-level audit trail (pg_audit)
- Q214: bypass detection — triggers + anomaly detection

### [[sdd-actor-model]]

- Q24 PARTIAL: human override structural guard — механика
- Q138: canonical список ролей — переопределяемы через PolicyKernel?
- Q139: паттерн оркестрации фазы — sequential vs streaming
- Q140: tool ACL по роли
- Q143: actor_id lifecycle в сессии

### [[upcaster-registry]]

- Q203: zero-downtime upgrade — blue-green vs rolling
- Q204: когда обязателен full replay при upgrade
- Q205: system version rollback — downgrade path
- Q206: multi-version compatibility при rolling upgrade
- Q207: upgrade testing на production данных
- Q208: feature flags механизм — PolicyKernel?

### [[sdd-component-inventory]]

- Q61: схема идентификаторов сущностей
- Q62: дедупликация при повторном создании документа
- Q63: versioning документов — новый документ vs новая версия
- Q64: иерархия в ID — composite keys vs flat global IDs
- Q65: bidirectional traceability task → spec
- Q154: изоляция проектов — DB vs schema vs project_id
- Q155: canonical directory layout SDD-проекта
- Q156: global vs project config разделение
- Q157: context switch между проектами
- Q158: cross-project spec/policy sharing
- Q176: `sdd init` — bootstrap нового проекта
- Q177: minimal viable setup для первого TaskRun
- Q178: migration от non-SDD проекта
- Q179: template library для типовых фаз
- Q180: getting started guide — актуальность

### [[scope-guard]]

- Q147: sandbox для run_terminal_cmd — Docker/nsjail/путь-фильтр
- Q149: RBAC permissions — PolicyKernel vs hardcoded

### [[replay-engine]] (P2 часть)

- Q159: throughput limits — bottleneck DB/reducer/projections
- Q160: latency SLA P50/P95/P99
- Q161: ContextPacket assembly latency budget
- Q162: cold start cost после idle
- Q163: performance profiling tooling

### [[session-orchestrator]] (P2 часть)

- Q186: cross-phase dependencies при строгой последовательности (I-PHASE-SEQ-1)
- Q187: artifact traceability Spec→Plan→Task→code bidirectional
- Q188: phase rollback механизм — PhaseReverted event
- Q189: concurrent phases — нарушаемые инварианты
- Q190: reusable phase templates

### [[global-laws]] (P3 часть)

- Q228: математическая модель системы — TLA+/Alloy
- Q229: formal proof детерминизма reduce(EventLog)
- Q230: proof eventual consistency projections
- Q231: proof replay correctness vs live execution
- Q232: model checking — deadlock freedom, safety, liveness
- Q233: trust boundary — верим vs доказали

---

## Backlog (без выделенной страницы)

### Domain Events (→ event-catalog, создать позже)

Q134–137 добавлены в [[event-sourcing]] до создания страницы `event-catalog`:

- Q134: canonical список всех событий системы
- Q135: tool-level events (FileWritten vs TaskStepRecorded)
- Q136: negative events — как записать «решил не делать»
- Q137: event granularity policy — слишком много vs слишком мало

---

## Обязательные страницы (добавить блок при первой возможности)

| Страница | Статус |
|----------|--------|
| [[event-sourcing]] | ✅ блок добавлен (Батч 1) |
| [[reducer]] | ✅ блок добавлен (Батч 1) |
| [[context-kernel]] | ✅ блок добавлен (Батч 1) |
| [[execution-guard]] | ✅ блок добавлен (Батч 1) |
| [[replay-engine]] | ✅ блок добавлен (Батч 1) |
