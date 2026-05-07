# План: wiki-страница `sdd-open-questions`

## Контекст

Задача: создать/заменить вопросный roadmap как wiki-страницу `idea/sdd-open-questions`, применив анализ:

1. Вопросы, уже **решённые** wiki-паттернами → статус `[SOLVED]` + ссылка
2. Вопросы **частично решённые** → `[PARTIAL]`
3. Вопросы **открытые** → `[OPEN]`
4. **Новые блоки** (20 доменов без покрытия в вопросах и wiki)
5. Приоритизация: P0 > P1 > P2 > P3
6. Вопросы явно лишние/тривиальные → удалены

## Целевой файл

`/root/project/obsidian-vault/llm-wiki/wiki/idea/sdd-open-questions.md`

## Шаги выполнения

1. Использовать wiki-skill `evolve` для создания страницы (страница новая, не существует)
2. Записать frontmatter + полный контент (см. ниже)

## Анализ покрытия (что решено wiki)

**SOLVED:**
- B8-Q4 Atomic append → `write-kernel` + OCC
- B8-Q7 Schema evolution → `upcaster-registry`
- B8-Q9 Event immutability → `eventstore-guard`
- B9-Q18 Idempotent retry → `idempotency-projection` + `idempotency-mode`
- B9-Q24 Command dedup → `idempotency-projection`
- B9-Q27 Expected_version source → `write-kernel` (всегда snapshot.version)
- B10-Q31 Reducer composition → `reducer` (один pure reducer)
- B10-Q35 Reducer versioning → `upcaster-registry`
- B10-Q36 Determinism enforcement → `global-laws` GL-1
- B11-Q46 Sync vs async projections → `projection-registry` (sync inline L1)
- B11-Q48 Projection rebuild trigger → `projection-registry`
- B11-Q52 Incremental updates → `projection-registry` (incremental)
- B12-Q61 Context boundary → `context-packet` (ContextPacket = seam S0→S1)
- B13-Q76 Guard ordering → `middleware-pipeline` (fixed slots)
- B13-Q77 Guard composition → `middleware-pipeline` (chain)
- B13-Q78 Guard determinism → `execution-guard` (by design)
- B14-Q91 Replay scope → `replay-engine` (full EventLog)
- B14-Q95 Replay isolation → `replay-engine` (stateless, no side effects)
- B14-Q101 Replay step-by-step → `replay-engine`
- B14-Q102 Replay snapshots → `golden-fixture`
- B15-Q106 Error classification → `error-classifier`
- B15-Q107 Retry backoff → `loop-policy`
- B15-Q110 Error events → `error-event`
- B15-Q120 Human intervention → `session-orchestrator` GATE outcome
- B16-Q121 Randomness control → determinism by design (GL-1)

**PARTIAL (есть паттерн, но вопрос не закрыт полностью):**
- B8-Q1 Гарантия порядка → OCC но нет total-order guarantee spec
- B8-Q2 event_index глобальный? → есть в EventStore, но не задокументировано явно
- B8-Q3 Batch semantics → частично закрыт инвариантом I-EVENTLOG-6, но batch failure path открыт
- B8-Q13 Poison events → `classified-recovery` ABORT, но нет quarantine/DLQ механизма
- B8-Q14 Snapshotting/compaction → `golden-fixture` для тестов, но не для prod EventLog
- B9-Q16 Retry policy → `loop-policy` есть max_retries, но backoff алгоритм не задан
- B9-Q22 Write skew → OCC ловит version conflicts, но logical write skew не рассмотрен
- B10-Q38 State snapshotting → `phases_snapshots` есть, но materialized snapshots для prod replay нет
- B11-Q53 Projection corruption detection → нет explicit mechanism
- B11-Q55 Multi-projection consistency → нет explicit guarantee
- B12-Q63 Context prioritization → `context-kernel` есть push+pull, но алгоритм приоритизации не описан
- B12-Q67 Context reproducibility → `deterministic-context` но нет формального proof
- B13-Q81 Guard override by human → `sdd-actor-model` but mechanics unclear
- B14-Q97 Replay failure handling → `classified-recovery` but replay-specific mismatch unresolved
- B15-Q116 Crash recovery → нет explicit recovery от process crash
- B15-Q117 State corruption detection → нет checksumming

**УДАЛЕНЫ (тривиальные или N/A):**
- B8-Q6 Event size limits — implementation detail, не архитектурный вопрос
- B9-Q25 Cross-aggregate transactions — N/A, single aggregate design по GL-2
- B10-Q34 Derived state — тривиально: все derived state = projections
- B11-Q57 Projection eviction — преждевременная оптимизация
- B16-Q125 Floating point determinism — N/A, нет float в core
- B16-Q126 Ordering guarantees — answered: event_index is the order
- B16-Q133 Cross-platform — out of scope, Linux-only
- B17-Q138 EventLog шардирование — преждевременно для текущей стадии
- B17-Q139 Horizontal projection scaling — преждевременно

## Новые блоки (отсутствуют в raw roadmap)

**P0 критические:**
- **Блок Z: Data Integrity & Storage Layer** — durability (fsync), checksums, bit-rot, torn writes, backup/restore, point-in-time recovery
- **Блок AA: Serialization & Canonical Formats** — canonical event format, deterministic serialization, schema hash, serializer drift
- **Блок AE: Time & Ordering Semantics** — logical vs wall-clock, Lamport clock, total order guarantee, tie-breaker

**P1 основной функционал:**
- **Блок AB: Command Model & Contracts** — command schema registry, pure vs computed, rejected log
- **Блок AC: Invariants System (Meta-Level)** — machine-checkable DSL, coverage, versioning, conflicts
- **Блок AD: Causality & Trace Model** — causal graph, lineage API, orphan detection, visualization
- **Блок AG: Testing Strategy (System-Level)** — golden master, fuzz, chaos, OCC under load
- **Блок AK: LLM Integration & Determinism Boundary** — LLM output logging, prompt snapshot, LLM stubbing, non-deterministic tolerance, model drift

**P2 расширения:**
- **Блок T: Observability & Debugging UX** — операционный мониторинг, dashboards, distributed tracing
- **Блок U: Spec Quality & Completeness Metrics** — нет ни одного вопроса о качестве спеки
- **Блок V: System Bootstrap & Onboarding** — нет вопросов о запуске нового SDD-проекта
- **Блок W: CI/CD & Deployment Integration** — Q105 упоминает CI/CD, системного блока нет
- **Блок X: Multi-Phase Dependency Management** — cross-phase dependencies не моделируются
- **Блок Y: SDD Self-Improvement & Meta-Evolution** — meta-optimization есть, вопросный блок нет
- **Блок AF: Configuration & Dynamic Behavior** — runtime vs compile-time config, config in EventLog
- **Блок AH: Upgrade & Migration Strategy** — zero-downtime, rollback, multi-version compatibility
- **Блок AI: Security (System-Level)** — event signing, injection protection, bypass detection

**P3 исследование:**
- **Блок R: LLM Cost & Token Budget Management** — ни одного вопроса в raw; критично для production
- **Блок S: HITL Protocol & Human Gates** — системного блока нет; есть Q8 и Q25 разрозненно
- **Блок AJ: Formal Model & Proofs** — TLA+, determinism proof, trust boundary

---

## Полный контент wiki-страницы

```markdown
---
id: idea/sdd-open-questions
page_type: idea
domain: sdd
layer: architecture
tags:
- ssot
- enforcement
- pipeline
- automation
- domain/sdd
- roadmap
- ddd
version: 1
created: '2026-05-06'
updated: '2026-05-06'
sources:
- raw/sdd-open-questions-plan.md
---
# SDD Open Questions

Архитектурный backlog вопросов для SDD-системы. Цель — найти идеи для доработки, расширения, стабилизации; обнаружить архитектурные ловушки, баги и дыры.

Статусы: `[OPEN]` — не решён · `[PARTIAL]` — есть паттерн, вопрос не закрыт · `[SOLVED]` — закрыт wiki-паттерном.
Приоритеты: **P0** (стабильность ядра) → **P1** (основной функционал) → **P2** (расширения) → **P3** (исследование).

---

## P0 — Стабильность ядра

*Критические вопросы. Нерешённые P0 → риск краша или silent corruption системы.*

### Блок A: EventLog Semantics & Consistency

1. `[PARTIAL]` **Гарантия порядка:** Как обеспечивается total order EventLog? single-writer vs partition+merge? Где формализован инвариант? → [[optimistic-concurrency-control]]
2. `[PARTIAL]` **event_index:** Является ли он глобальным монотонным счётчиком? Что происходит при concurrent append в PostgreSQL? Нужен ли advisory lock или SERIAL достаточно?
3. `[PARTIAL]` **Batch semantics:** Что является границей batch? Одна команда = один batch? Что если handler эмитирует N events — атомарны ли они все? Частично закрыт инвариантом I-EVENTLOG-6, но batch failure path открыт.
4. `[SOLVED]` **Atomic append:** Гарантируется через Write Kernel + OCC → [[write-kernel]]
5. `[OPEN]` **Partial failure:** Что происходит при падении процесса между handle() и append()? Как обнаружить и компенсировать незавершённый batch?
6. `[SOLVED]` **Schema evolution:** upcasting старых событий → [[upcaster-registry]]
7. `[OPEN]` **Backward compatibility:** Можно ли replay старого EventLog новой версией reducer без потери инвариантов? Как тестировать совместимость?
8. `[SOLVED]` **Event immutability:** Технически запрещено через DB constraints + eventstore-guard → [[eventstore-guard]]
9. `[OPEN]` **Cross-stream events:** Есть ли несколько логов или один глобальный? Если несколько — как гарантировать causality между ними?
10. `[PARTIAL]` **Poison events:** Событие ломает reducer на replay. Что делать? Quarantine-механизм? Dead Letter Queue (DLQ)? Manual upcasting? → [[classified-recovery]] (ABORT), но нет repair flow
11. `[PARTIAL]` **Log growth & compaction:** Нужен ли snapshotting для prod EventLog? При каком объёме событий replay становится неприемлемо медленным? SLA? → [[golden-fixture]] для тестов, но не для prod

### Блок B: OCC, Concurrency & Isolation

12. `[PARTIAL]` **Retry policy:** Сколько retry допустимо? Max_retries есть в loop-policy, но backoff алгоритм (exponential/fixed) не задан → [[loop-policy]]
13. `[OPEN]` **Conflict semantics:** Всегда ли OCC-конфликт → retry? Когда конфликт должен приводить к ABORT вместо retry? Как отличить transient от systemic conflict?
14. `[OPEN]` **Long-running commands:** Handler работает долго, snapshot устаревает. Heartbeat? Timeout? Re-read snapshot?
15. `[OPEN]` **Concurrent commands:** Разрешены ли параллельные команды к одному aggregate? Если нет — где serialization point?
16. `[PARTIAL]` **Write skew:** OCC ловит version mismatch, но logical write skew (два агента читают одно состояние, принимают разные решения) не рассмотрен. Возможен?
17. `[OPEN]` **Deadlock / livelock avoidance:** Может ли OCC с несколькими агентами привести к livelock при высокой contention? Jitter на retry?
18. `[SOLVED]` **Command dedup:** Idempotency key → [[idempotency-projection]] + [[idempotency-mode]]
19. `[OPEN]` **Multi-command workflows:** Нужны ли saga/compensation patterns? Если handle() эмитирует событие, которое запускает следующую команду — это сага? Как rollback?

### Блок C: Guards & Enforcement

20. `[SOLVED]` **Guard ordering:** Фиксированные слоты middleware-pipeline → [[middleware-pipeline]]
21. `[SOLVED]` **Guard composition:** Chain через pipeline → [[middleware-pipeline]]
22. `[SOLVED]` **Guard determinism:** Все guards детерминированы по дизайну → [[execution-guard]]
23. `[OPEN]` **Guard side effects:** Строго запрещены? Что если guard нужно логировать решение (запись в TraceStore) — это side effect?
24. `[PARTIAL]` **Guard override by human:** Может ли human override structural guard (не policy)? Механика не описана → [[sdd-actor-model]]
25. `[OPEN]` **Guard replay:** Применяются ли guards при replay EventLog? Если да — что если policy изменилась с момента записи события?
26. `[OPEN]` **Guard bypass protection:** Как технически запрещён прямой вызов handler минуя guards? Только convention или code-enforced?

### Блок D: Error Handling & Resilience

27. `[SOLVED]` **Error classification:** RETRY/RE_EXPLAIN/HUMAN_GATE/ABORT → [[error-classifier]]
28. `[SOLVED]` **Error events:** Все ошибки пишутся как ErrorEvent → [[error-event]]
29. `[SOLVED]` **Human intervention trigger:** GATE outcome → [[session-orchestrator]]
30. `[PARTIAL]` **Crash recovery:** Как восстановиться после process crash? EventLog цел, но in-flight команда потеряна. Автоматическое обнаружение незавершённых сессий?
31. `[PARTIAL]` **State corruption detection:** Как обнаружить desync между EventLog и State_index? Checksumming projections? Periodic verify?
32. `[OPEN]` **Poison command:** Команда всегда падает. Circuit breaker? Dead letter queue? Как изолировать от влияния на другие команды?
33. `[OPEN]` **Timeout semantics:** Где задаются timeouts для handler execution? Кто их enforces? Что если handler завис?

### Блок E: Determinism & Reproducibility

34. `[SOLVED]` **Randomness control:** Детерминизм по дизайну, GL-1 → [[global-laws]]
35. `[OPEN]` **Time control:** Запрет datetime.now() в handlers? Как внедрять clock abstraction? Тестирование с mock time?
36. `[OPEN]` **Environment snapshot:** Что входит в reproducible environment? OS version, lib versions, DB version? Где фиксируется?
37. `[OPEN]` **Determinism tests:** Как автоматически проверяется, что reducer pure? Mutation testing? Property-based testing?
38. `[OPEN]` **Determinism violations detection:** Как ловить недетерминизм в runtime? Двойной запуск с проверкой идентичности output?
39. `[PARTIAL]` **Context reproducibility:** Как гарантировать replay_context при изменении graph? → [[deterministic-context]] но нет формального proof

### Блок Z: Data Integrity & Storage Layer *(новый)*

40. `[OPEN]` **fsync durability:** Как гарантируется durability EventLog? Есть ли fsync/fdatasync после каждого append или полагаемся на PostgreSQL WAL? Что при OS crash между append и fsync?
41. `[OPEN]` **Payload checksums:** Есть ли checksums на уровне каждого события (payload integrity)? Как обнаружить silent data corruption без checksum?
42. `[OPEN]` **Bit-rot detection:** Как обнаружить corruption на уровне storage? Периодический re-hash всех событий EventLog? Cron job или triggered?
43. `[OPEN]` **Write path duality:** Есть ли двойная запись (WAL + EventLog) или EventLog IS the WAL? Один источник истины или два? Что если они расходятся?
44. `[OPEN]` **Backup & restore:** Как делается backup EventLog без потери порядка events? pg_dump? Streaming replication? Гарантируется ли сохранение event_index sequence?
45. `[OPEN]` **Point-in-time recovery:** Поддерживается ли восстановление к конкретному event_index? Что нужно кроме EventLog (projections, config snapshot)?
46. `[OPEN]` **Restore → replay → equality:** Как тестируется: backup → restore → full replay → State == original State? Автоматически в CI?
47. `[OPEN]` **Torn write protection:** Что происходит при partial write (OS crash mid-row-append)? Достаточна ли PostgreSQL транзакционность? Partial event = invalid state?

### Блок AA: Serialization & Canonical Formats *(новый)*

48. `[OPEN]` **Canonical event format:** JSON, MessagePack или Protobuf? Критерии: human-readability vs performance vs schema enforcement. Текущий выбор и почему?
49. `[OPEN]` **Deterministic serialization:** Как гарантируется deterministic key ordering в JSON? sorted_keys? custom encoder? Тест на ordering stability?
50. `[OPEN]` **Schema hash per event:** Есть ли schema_version или schema_hash в каждом событии для обнаружения schema drift между версиями системы?
51. `[OPEN]` **Optional/missing fields в replay:** Как обрабатываются поля отсутствующие в старых событиях при replay новым reducer? Default values? Strict validation?
52. `[OPEN]` **Canonical hashing strategy:** Есть ли canonical hash для State snapshot и ContextPacket? Используется для integrity verification и dedup?
53. `[OPEN]` **Bit-identical dump:** Можно ли получить bit-identical dump всего состояния системы для cross-environment comparison или migration verification?
54. `[OPEN]` **Serializer version drift:** Как избежать расхождения если разные версии кода читают одни события? Serializer compatibility matrix? Migration tests?

### Блок AE: Time & Ordering Semantics *(новый)*

55. `[OPEN]` **Logical vs wall-clock time:** Явное различие между logical time (event_index) и wall-clock time (timestamp)? Для каких операций используется каждое? Что является canonical ordering?
56. `[OPEN]` **Lamport/vector clock:** Нужен ли Lamport clock для causality ordering если single-writer? При multi-agent или distributed — vector clock обязателен?
57. `[OPEN]` **Одинаковый timestamp:** Как обрабатываются события с идентичным wall-clock timestamp? Определяет ли порядок event_index? Monotonic clock required?
58. `[OPEN]` **Distributed append reordering:** При distributed setup возможен ли reordering при concurrent append? Как гарантировать total order без distributed lock?
59. `[OPEN]` **Happened-before formalization:** Как формализовано "happened-before" для команд и событий? EventLog position достаточен или нужна явная causality ссылка?
60. `[OPEN]` **Deterministic tie-breaker:** Если два события конкурентны, какой deterministic tie-breaker используется для ordering? UUID lexicographic? Timestamp + sequence?

---

## P1 — Основной функционал

*Вопросы, необходимые для завершённой системы.*

### Блок F: Domain Model & Identity

61. `[OPEN]` **Схема ID:** Какова схема идентификаторов для каждой сущности? (`T-034`, `P-012`, `S-001`). Auto-increment или детерминированный hash? Уникальность в рамках проекта или глобально?
62. `[OPEN]` **Идемпотентность документов:** Если агент дважды создаёт спеку "Auth Module" — дедупликация по имени/hash или создаётся два документа?
63. `[OPEN]` **Версионирование документов:** Спека изменилась — новый документ или новая версия? История в EventLog или Git-like commits?
64. `[OPEN]` **Иерархия в ID:** Как выражается Project→Phase→Task→Step в ID? Composite keys? Flat global IDs?
65. `[OPEN]` **Traceability:** Как задача ссылается на спеку из которой порождена? Как code artifact ссылается на задачу? Bidirectional?

### Блок G: Lifecycle & Workflows

66. `[OPEN]` **Стандартный pipeline фазы:** Какие шаги ОБЯЗАТЕЛЬНЫ? Могут ли фазы иметь разные pipeline-конфигурации?
67. `[OPEN]` **Параллелизм внутри задачи:** Могут ли шаги выполняться параллельно? Как координировать конкурентные writes к одному файлу?
68. `[OPEN]` **Прерывание фазы (Abort/Transition):** Как перейти с незакрытой фазы на следующую? PhaseAbandoned event? Влияние на projections?
69. `[OPEN]` **Переоткрытие (Reopening):** Можно ли открыть закрытую задачу/фазу? Как это влияет на монотонность EventLog и I-PHASE-LIFECYCLE-2?
70. `[OPEN]` **Lifecycle документа:** Статусы спеки/плана: DRAFT→REVIEW→APPROVED→OBSOLETE. Кто и как переводит? Что происходит при OBSOLETE с зависимыми задачами?

### Блок H: Context System

71. `[SOLVED]` **Context boundary:** ContextPacket = seam между Stage 0 и Stage 1 → [[context-packet]]
72. `[OPEN]` **Context size budget:** Ограничение токенов на ContextPacket? Кто enforces? Что если budget exceeded?
73. `[PARTIAL]` **Context prioritization:** Алгоритм приоритизации данных в context при нехватке бюджета? → [[context-kernel]] push+pull, но алгоритм не формализован
74. `[OPEN]` **Context invalidation:** Когда context считается stale? Только при graph change или также при state change?
75. `[PARTIAL]` **Context versioning:** Привязан ли context к event_index? Как воспроизвести точный context для debugging? → [[deterministic-context]]
76. `[OPEN]` **External data в context:** Разрешено ли включать внешние источники (web, API)? Как они влияют на детерминизм?
77. `[OPEN]` **Context leakage:** Может ли context одного TaskRun "протечь" в другой через shared projections?
78. `[OPEN]` **Context diff:** Как сравнить два context? Инструмент для debugging context changes между TaskRuns?

### Блок I: Reducers & State Model

79. `[SOLVED]` **Reducer composition:** Один pure reducer → [[reducer]]
80. `[PARTIAL]` **State snapshotting:** phases_snapshots есть в SDDState, но materialized snapshots для ускорения prod replay не реализованы. SLA на полный replay vs snapshot replay?
81. `[OPEN]` **State size limits:** Как ограничить рост state? Eviction policy для старых phases_snapshots?
82. `[OPEN]` **Partial replay:** Можно ли replay с checkpoint вместо начала? Как гарантировать корректность?
83. `[OPEN]` **State validation:** Проверяется ли state после каждого события? Post-condition assertions в reducer?
84. `[OPEN]` **Invariant violation в reducer:** Где ловится — reducer или guard? Что если reducer нарушил инвариант?
85. `[OPEN]` **State serialization format:** Canonical format для State_index.yaml? Versioned? Migration path?

### Блок J: Projections & Materialization

86. `[SOLVED]` **Sync vs async:** Sync inline в L1 → [[projection-registry]]
87. `[SOLVED]` **Rebuild trigger:** Проекции перестраиваются при rebuild → [[projection-registry]]
88. `[PARTIAL]` **Corruption detection:** Нет explicit механизма обнаружения desync проекции и EventLog → [[projection-registry]]
89. `[PARTIAL]` **Multi-projection consistency:** Все ли projections консистентны между собой в одной точке времени? Нет explicit guarantee
90. `[OPEN]` **Projection versioning:** Как обновить schema проекции без полного rebuild? Rolling migration?
91. `[OPEN]` **Projection dependencies:** Разрешены ли? Проекция А зависит от Проекции Б? Какой порядок обновления?
92. `[OPEN]` **Hot vs cold projections:** Какие держать в памяти, какие только в DB? SLA на cold projection read?
93. `[OPEN]` **Projection testing:** Как тестировать детерминизм проекций? Property-based tests?

### Блок K: Replay & Verification

94. `[SOLVED]` **Replay scope:** Full EventLog → [[replay-engine]]
95. `[SOLVED]` **Replay isolation:** Stateless, no side effects → [[replay-engine]]
96. `[SOLVED]` **Replay step-by-step:** Поддерживается → [[replay-engine]]
97. `[SOLVED]` **Replay with snapshots:** golden-fixture → [[golden-fixture]]
98. `[PARTIAL]` **Replay failure handling:** Mismatch между replay result и expected state. Alerting? Auto-quarantine? → [[classified-recovery]] но нет replay-specific flow
99. `[OPEN]` **Replay performance SLA:** При каком объёме EventLog full replay неприемлем? Метрики? Benchmark?
100. `[OPEN]` **Replay consistency check:** Проверяются ли все projections на консистентность после replay? Что считается mismatch?
101. `[PARTIAL]` **Replay CLI:** Команды для replay существуют? `sdd replay-from --event-id N`? → [[replay-engine]] (code), но CLI не задокументирован

### Блок AB: Command Model & Contracts *(новый)*

102. `[OPEN]` **Command schema registry:** Есть ли строгий реестр всех допустимых commands с их схемами? Аналог EventLog schema registry для событий?
103. `[OPEN]` **Pure vs computed commands:** Command всегда pure intent (от actor) или допустимы "computed commands" (generated by system logic)? Как различать в EventLog?
104. `[OPEN]` **Command validation point:** Где валидируется command schema — до guards (middleware) или внутри handler? Кто отвечает за well-formedness input?
105. `[OPEN]` **External state в command:** Может ли command payload содержать snapshot external state? Как это влияет на replay determinism?
106. `[OPEN]` **Command determinism:** Формально гарантируется: одинаковый input command + одинаковый State → одинаковые output events? Где доказательство?
107. `[OPEN]` **Command replay:** Нужен ли replay commands (не только events)? Как воспроизвести исходный actor intent для debugging?
108. `[OPEN]` **Rejected command log:** Как логируются команды, отклонённые guards? В EventLog (RejectedCommandEvent) или отдельный store? Как анализировать паттерны rejection?

### Блок AC: Invariants System (Meta-Level) *(новый)*

109. `[OPEN]` **Invariant registry:** Где хранится единый реестр всех инвариантов? CLAUDE.md таблица достаточна или нужен machine-checkable format (YAML, JSON schema)?
110. `[OPEN]` **Machine-checkable DSL:** Есть ли DSL для invariants позволяющий автоматическую проверку — TLA+, Alloy, или custom YAML с assertions?
111. `[OPEN]` **Invariant check timing:** Когда проверяются инварианты: pre-command (guard), post-command (post-condition assertion), при replay? Должны ли быть все три?
112. `[OPEN]` **Old EventLog + new invariant:** Старый EventLog нарушает новый инвариант добавленный в новой версии. Migration event? Upcaster? Quarantine? Это breaking change?
113. `[OPEN]` **Invariant versioning:** Как версионируются инварианты? Какие backward-compatible (новое ограничение), какие breaking (изменение semantics)?
114. `[OPEN]` **Invariant coverage metric:** Есть ли метрика — сколько инвариантов покрыты тестами, какие нет? Enforcement gap analysis?
115. `[OPEN]` **Invariant conflicts:** Как обнаруживаются и разрешаются конфликты между инвариантами (I-X требует A, I-Y требует ¬A)? Статически или при runtime?

### Блок AD: Causality & Trace Model *(новый)*

116. `[OPEN]` **Causal graph model:** Есть ли единая модель causal graph (event→event через causation_event_id, command→event через command_id)? Формализована в спеке? → [[causal-linkage]]
117. `[OPEN]` **Full causal chain reconstruction:** Как восстановить полную цепочку причинности для произвольного event без ambiguity? SQL query или projection?
118. `[OPEN]` **Event lineage API:** Есть ли API: `get_lineage(event_id) → [ancestor_events]`? Через EventLog query или отдельная lineage projection?
119. `[OPEN]` **No orphan events guarantee:** Как гарантировать что нет orphan events (событий без причины/команды)? Root events = user commands — это invariant?
120. `[OPEN]` **Causality cycle detection:** Возможны ли циклы в causal graph? Где проверяется acyclicity — при append или при rebuild?
121. `[OPEN]` **Causality visualization:** Как визуализируется causal graph для debugging? CLI `sdd trace-graph T-NNN`? Graphviz export?

### Блок AG: Testing Strategy (System-Level) *(новый)*

122. `[OPEN]` **Golden master tests:** Есть ли golden master tests для системы end-to-end? (full scenario commands → expected final EventLog state snapshot)?
123. `[OPEN]` **EventLog fuzz testing:** Есть ли fuzz testing — случайные sequences событий не должны ломать reducer? Hypothesis или custom fuzzer?
124. `[OPEN]` **Property-based tests для reducer:** Используются ли property-based tests (Hypothesis) для reducer и guards? Какие свойства — commutativity, idempotency, monotonicity?
125. `[OPEN]` **Idempotency of replay:** Есть ли тест: replay(EventLog) N раз → bit-identical State? Запускается ли в CI как regression gate?
126. `[OPEN]` **Chaos testing:** Есть ли chaos тесты — crash mid-append, disk full, DB connection drop? Как система ведёт себя при каждом сценарии?
127. `[OPEN]` **OCC contention testing:** Как тестируется OCC при высокой concurrency? Есть ли stress tests с параллельными командами и проверкой no livelock?
128. `[OPEN]` **Deterministic test harness:** Есть ли test harness гарантирующий полный детерминизм тестов — seed, mock clock, mock random, network disabled?

### Блок AK: LLM Integration & Determinism Boundary *(новый)*

129. `[OPEN]` **LLM output logging:** Записывается ли полный raw output LLM в EventLog (как LLMResponseReceived event) или только parsed tool_call? Если только parsed — как реплеить сбой парсинга?
130. `[OPEN]` **Prompt snapshot:** Записывается ли финальный assembled prompt (после ContextKernel) в EventLog? Как реплеить если промпт изменился из-за изменения кода ContextKernel?
131. `[OPEN]` **LLM stubbing для replay:** При replay — можно ли подменять LLM на stub (возвращающий записанные ответы)? Как технически изолировать LLM-вызов от CommandBus?
132. `[OPEN]` **Non-deterministic tolerance:** Допускает ли система расхождение в текстовых ответах LLM при replay (fuzzy match), или требует bit-identical? Как настраивается tolerance?
133. `[OPEN]` **Model version drift:** Что если версия LLM (например, claude-sonnet-4 → claude-opus-4) изменилась между записью события и replay? Это ошибка или допустимая вариация?

---

## P2 — Расширения

*Production-grade features.*

### Блок L: Domain Events (Event Storming)

134. `[OPEN]` **Стандартный список событий:** Каков исчерпывающий canonical список всех событий системы? (ProjectCreated, PhaseStarted, SpecDrafted, SpecApproved, TaskSpawned, TaskCompleted, PhaseAborted…). Где он живёт — в вики или как enum в коде?
135. `[OPEN]` **Tool-level events:** Должен ли каждый вызов write_file порождать FileWritten event, или это деталь TaskStepRecorded?
136. `[OPEN]` **Negative events:** Как записать что агент *решил не делать* что-то? SkippedTest? DecisionRecorded?
137. `[OPEN]` **Event granularity policy:** На каком уровне детализации записываются события? Стратегия для "слишком много vs слишком мало" событий?

### Блок M: Agents & Orchestration

138. `[OPEN]` **Роли агентов:** Canonical список ролей: Planner, Executor, Reviewer, Auditor. Могут ли переопределяться через PolicyKernel?
139. `[OPEN]` **Оркестрация паттернов:** Sequential (Planner→Executor→Reviewer) vs Streaming (Generator→Critic loop). Где описывается паттерн оркестрации фазы?
140. `[OPEN]` **Tool permissions по роли:** Reviewer имеет только read+comment, Executor — read+write? Где задаётся tool ACL?
141. `[OPEN]` **Sub-agents (делегирование):** Может ли Executor породить Sub-executor? Как отслеживаются деревья вызовов в EventLog? causation_event_id?
142. `[OPEN]` **Разрешение конфликтов:** Reviewer и Executor бесконечный цикл правок. Какой budget/timeout? Escalation to HUMAN_GATE?
143. `[OPEN]` **Agent identity lifecycle:** Как создаётся, передаётся и инвалидируется actor_id агента в сессии?

### Блок N: Tools & Skills

144. `[OPEN]` **Базовый набор инструментов:** Canonical список System Skills? (read_file, write_file, search_code, run_terminal_cmd, ask_human). Где задаётся минимальный набор?
145. `[OPEN]` **Мета-инструменты:** Может ли агент вызывать sdd CLI изнутри TaskRun? Кто авторизует это?
146. `[OPEN]` **Extended skills (plugins):** Как добавить browser (Playwright) или внешний API? Через CommandBus plugin point?
147. `[OPEN]` **Sandbox для run_terminal_cmd:** Как изолируется? Docker, nsjail, ScopeGuard на путях? Сетевой доступ?
148. `[OPEN]` **Human CLI:** Canonical список команд для человека? `sdd start-phase`, `sdd approve`, `sdd debug-projection`, `sdd replay-step` — где задокументированы?

### Блок O: RBAC & Security

149. `[OPEN]` **Модель прав (RBAC):** Role = set[Permissions]. Уровни: project:read, spec:write, phase:approve, policy:update. Где задаётся — PolicyKernel или hardcoded?
150. `[OPEN]` **Атрибуты агента:** Откуда берётся actor_id и role при старте AgentLoop? JWT? Конфиг? EventLog?
151. `[OPEN]` **Конституция проекта:** Что входит в constitution.md? Tech stack, linter rules, архитектурные принципы. Где живёт? Как попадает в ContextKernel?
152. `[OPEN]` **Prompt Injection protection:** Как ContextKernel экранирует файлы, которые читает агент, чтобы не стали "злыми инструкциями"? Sanitization strategy?
153. `[OPEN]` **Secret management:** Как credentials (DB passwords, API keys) передаются агенту? Никогда в EventLog?

### Блок P: Multi-Project & Layout

154. `[OPEN]` **Изоляция проектов:** Разные DB, разные схемы (schemas) или изоляция через project_id в таблицах?
155. `[OPEN]` **Стандартная структура каталога:** Canonical layout SDD-проекта? `.sdd/eventlog/`, `.sdd/projections/`, `specs/`, `src/`, `tests/`?
156. `[OPEN]` **Глобальный конфиг vs проектный:** Что в `~/.sdd/config.yaml` vs `project/.sdd/config.yaml`?
157. `[OPEN]` **Context переключения проекта:** `sdd switch project-B`. Как Memory Layer понимает чьи projections читать?
158. `[OPEN]` **Шаринг между проектами:** Может ли Проект А импортировать спеку или policy из Проекта Б? Механика?

### Блок Q: Performance & Scaling

159. `[OPEN]` **Throughput limits:** Сколько команд/сек принимает система? Где bottleneck — DB, reducer, projections?
160. `[OPEN]` **Latency targets:** SLA на command execution: P50, P95, P99?
161. `[OPEN]` **Context assembly latency:** Budget на сборку ContextPacket? Graph query timeout?
162. `[OPEN]` **Cold start cost:** Стоимость первого TaskRun после idle? Projection warm-up?
163. `[OPEN]` **Profiling tooling:** Как измерять performance hotpaths? Встроенная instrumentация?

### Блок T: Observability, Monitoring & Debugging UX *(новый)*

164. `[OPEN]` **Dashboard требования:** Какие метрики нужны human-оператору в реальном времени? (активные TaskRuns, queue depth, AgentScore trend, error rate)
165. `[OPEN]` **Event streaming:** Нужен ли real-time stream событий для monitoring? SSE, WebSocket, или poll?
166. `[OPEN]` **Distributed tracing:** Как traced запрос от CLI команды до EventLog append? OpenTelemetry?
167. `[OPEN]` **Log correlation:** Как связать log lines с конкретным TaskRun/event_id?
168. `[OPEN]` **Debug mode:** `sdd debug-task T-NNN` — step-by-step воспроизведение с инспекцией каждого состояния?
169. `[OPEN]` **Alerting rules:** Какие условия → alert? (ABORT loop, state corruption, EventLog gap, projection lag)
170. `[OPEN]` **Audit log UI:** Как человек просматривает audit_log.jsonl? CLI, web UI, grep?

### Блок U: Spec Quality & Completeness Metrics *(новый)*

171. `[OPEN]` **Spec quality metrics:** Как измерить "хорошесть" спеки перед запуском фазы? (completeness, ambiguity score, coverage of acceptance criteria)
172. `[OPEN]` **Spec coverage:** Как убедиться что спека покрывает все требования? Checklist? Automated analysis?
173. `[OPEN]` **Spec linting:** Автоматические проверки спеки — нет ли противоречий, неопределённостей, пустых секций?
174. `[OPEN]` **Spec → task coverage:** Все ли секции спеки отражены в TaskSet? Как обнаружить uncovered spec items?
175. `[OPEN]` **Spec aging:** Как обнаружить что спека устарела (код изменился, спека не обновлялась)?

### Блок V: System Bootstrap & Onboarding *(новый)*

176. `[OPEN]` **New project bootstrap:** Canonical процедура запуска нового SDD-проекта с нуля? `sdd init` команда?
177. `[OPEN]` **Minimal viable setup:** Что минимально необходимо для первого TaskRun? (DB, config, schema, initial phase)
178. `[OPEN]` **Migration from non-SDD:** Как перевести существующий проект на SDD? Импорт истории?
179. `[OPEN]` **Template library:** Есть ли готовые шаблоны спек/планов для типовых фаз (auth, CRUD, API)?
180. `[OPEN]` **Onboarding documentation:** Где human-читаемый getting started guide? Как он поддерживается в актуальности?

### Блок W: CI/CD & Deployment Integration *(новый)*

181. `[OPEN]` **CI/CD replay gate:** Как интегрировать replay-verification в CI pipeline? `sdd verify --ci`?
182. `[OPEN]` **PR validation:** Как SDD-система проверяет PR перед merge? Replay? Guard checks?
183. `[OPEN]` **Deployment gate:** Должен ли `sdd check-dod` блокировать деплой при FAIL?
184. `[OPEN]` **Environment parity:** Как гарантировать что dev/staging/prod имеют идентичные EventStore schemas?
185. `[OPEN]` **Migration in CI:** Как schema migrations (upcasters) тестируются в CI перед применением в prod?

### Блок X: Multi-Phase Dependency Management *(новый)*

186. `[OPEN]` **Cross-phase dependencies:** Фазы строго последовательны (I-PHASE-SEQ-1), но может ли задача из Phase 3 зависеть от артефакта Phase 1? Как моделировать?
187. `[OPEN]` **Artifact traceability:** Как отследить цепочку: Spec_v1 → Plan_v1 → T-001 → code_file.py? Bidirectional graph?
188. `[OPEN]` **Phase rollback:** Если Phase 3 провалилась и нужно вернуться к Phase 2 — какой механизм? PhaseReverted event?
189. `[OPEN]` **Concurrent phases:** Возможно ли выполнение двух независимых фаз параллельно? Какие инварианты нарушаются?
190. `[OPEN]` **Phase templates:** Есть ли reusable phase templates? Как фаза "Add tests" переиспользуется в разных проектах?

### Блок Y: SDD Self-Improvement & Meta-Evolution *(новый)*

191. `[OPEN]` **Policy proposal quality:** Как измерить качество proposals от MetaOptimization? Какой процент предложений принимается человеком? → [[meta-optimization]]
192. `[OPEN]` **Feedback loop latency:** Как быстро изменение policy влияет на следующий TaskRun? Немедленно или после phase boundary?
193. `[OPEN]` **SDD self-hosted development:** Может ли SDD использоваться для разработки самой себя? Bootstrap problem?
194. `[OPEN]` **Invariant evolution:** Как добавить новый invariant в уже работающую систему? Нужен ли EventLog replay для проверки старых событий?
195. `[OPEN]` **Knowledge base evolution:** Как wiki-знания влияют на system behavior? Где граница между wiki и PolicyKernel?
196. `[OPEN]` **Capability regression detection:** Как обнаружить что новая версия модели ухудшила AgentScore по историческим задачам?

### Блок AF: Configuration & Dynamic Behavior *(новый)*

197. `[OPEN]` **Runtime vs compile-time config:** Какие параметры configurable в runtime (через PolicyKernel), а какие требуют rebuild/restart? Где граница?
198. `[OPEN]` **Config & determinism:** Как изменение конфига влияет на детерминизм EventLog replay? Конфиг — часть reproducible environment snapshot?
199. `[OPEN]` **Config snapshot в EventLog:** Записывается ли config state как событие при изменении (ConfigUpdated)? Как гарантировать reproducibility?
200. `[OPEN]` **Old EventLog + new config:** Можно ли replay старого EventLog с новой конфигурацией? Ожидаемый результат — тот же или undefined behavior?
201. `[OPEN]` **Config vs Policy граница:** Где граница между системным конфигом (.yaml файлы) и policy (PolicyKernel EventLog-events)? Что должно быть где?
202. `[OPEN]` **Config rollback:** Как откатить конфигурацию к предыдущей версии? Git revert достаточен или нужен ConfigRolledBack event в EventLog?

### Блок AH: Upgrade & Migration Strategy *(новый)*

203. `[OPEN]` **Zero-downtime upgrade:** Как делается upgrade системы без потери событий и downtime? Blue-green? Rolling with multi-version compatibility?
204. `[OPEN]` **Upgrade requires full replay?:** При каких изменениях (reducer, projection, guard) обязателен full replay EventLog? Можно ли incremental migration?
205. `[OPEN]` **System version rollback:** Как откатить версию системы если новый код несовместим со старым EventLog? Downgrade path?
206. `[OPEN]` **Multi-version compatibility:** При rolling upgrade — могут ли разные версии нод одновременно читать/писать один EventLog? Compatibility contract?
207. `[OPEN]` **Upgrade testing on prod data:** Как тестировать upgrade на production данных? Snapshot EventLog → staging → test upgrade → verify State equality?
208. `[OPEN]` **Feature flags для rollout:** Есть ли механизм feature flags для постепенного включения новой функциональности? Через PolicyKernel или отдельный mechanism?

### Блок AI: Security (System-Level) *(новый)*

209. `[OPEN]` **Event ID forgery:** Можно ли подделать event_id или command_id? Нужна ли cryptographic signing для integrity verification?
210. `[OPEN]` **Event signing:** Есть ли подпись событий (HMAC/Ed25519 на payload)? Как проверяется при replay и при backup restore?
211. `[OPEN]` **Event injection protection:** Как защититься от прямой INSERT в EventLog в обход системы? DB-level permissions? Row-level security?
212. `[OPEN]` **Physical EventLog access control:** Кто имеет физический write-доступ к EventLog DB? Минимальные привилегии service account?
213. `[OPEN]` **Storage-level audit trail:** Есть ли audit trail на уровне DB — кто и когда SELECT/INSERT к EventLog таблицам? pg_audit?
214. `[OPEN]` **Bypass detection:** Как обнаружить прямой доступ в обход системы? DB triggers на direct insert? Anomaly detection на event sequences?

---

## P3 — Исследование & Рост

*Долгосрочные вопросы. Не нужны для MVP, критичны для production scale.*

### Блок R: LLM Cost & Token Budget Management *(новый)*

215. `[OPEN]` **Token budget per task:** Как задаётся максимум токенов на TaskRun? Кто enforces — LoopPolicy или отдельный budget guard?
216. `[OPEN]` **Cost tracking:** Как записываются LLM API costs? В EventLog как metric event или отдельный store?
217. `[OPEN]` **Budget alerts:** При каком % budget usage агент предупреждает? При 100% — HUMAN_GATE или ABORT?
218. `[OPEN]` **Model selection policy:** Как PolicyKernel управляет выбором модели (дорогая/дешёвая) для разных типов задач?
219. `[OPEN]` **Context compression:** При нехватке token budget — автоматическое сжатие context? Какой алгоритм? Влияние на детерминизм?
220. `[OPEN]` **Phase cost budget:** Суммарный бюджет на фазу? Как распределяется между задачами?
221. `[OPEN]` **Cost vs quality tradeoff:** Как измерить ROI задачи — AgentScore / tokens_spent? Метрика M10?

### Блок S: HITL Protocol & Human Gates *(новый)*

222. `[OPEN]` **Canonical список human gates:** Где исчерпывающий список всех точек, требующих human approval? Spec approve, plan approve, phase complete, policy update… что ещё?
223. `[OPEN]` **Gate timeout:** Что происходит если human не реагирует N часов? Auto-expire? Freeze state?
224. `[OPEN]` **Gate notification:** Как человек узнаёт что его ожидают? Telegram, email, CLI poll?
225. `[OPEN]` **Async human review:** Человек может дать feedback через время после завершения задачи? Как применяется к уже выполненному?
226. `[OPEN]` **Partial approval:** Человек одобряет план частично — "делай пункты 1-3, пункт 4 переработай". Механика?
227. `[OPEN]` **Delegation:** Может ли human делегировать gate approval другому human или автоматической проверке?

### Блок AJ: Formal Model & Proofs *(новый)*

228. `[OPEN]` **Формальная модель:** Есть ли математическая модель системы (state machine, temporal logic)? TLA+, Alloy, или иное? Где хранится?
229. `[OPEN]` **Proof of determinism:** Можно ли формально доказать: ∀ EventLog, reduce(EventLog) детерминирован (одинаковые входы → одинаковые выходы)?
230. `[OPEN]` **Proof of eventual consistency:** Можно ли доказать eventual consistency projections: при eventual EventLog delivery все projections сходятся?
231. `[OPEN]` **Proof of replay correctness:** Формальное доказательство: replay(EventLog) воспроизводит точно тот же State что и live execution?
232. `[OPEN]` **Model checking:** Используется ли model checking (TLA+) для проверки core invariants — deadlock freedom, safety properties, liveness?
233. `[OPEN]` **Trust boundary:** Где граница "мы верим в корректность" vs "мы доказали корректность"? Какие инварианты наиболее критичны для formal proof?

---

## Отброшенные вопросы

Удалены как тривиальные, N/A или implementation details без архитектурной ценности:

- Event size limits — DB-specific, не архитектурный выбор
- Cross-aggregate transactions — N/A, single aggregate по GL-2
- Derived state — тривиально: always projections
- Projection eviction — преждевременная оптимизация
- Floating point determinism — нет float в core domain
- Cross-platform consistency — out of scope, Linux-only target
- EventLog шардирование — преждевременно до performance benchmarks

## See Also

- [[global-laws]]
- [[sdd-component-inventory]]
- [[sdd-actor-model]]
- [[sdd-meta-harness]]
- [[meta-optimization]]
- [[audit-engine]]
- [[error-classifier]]
- [[session-orchestrator]]
- [[replay-engine]]
- [[policy-kernel]]
- [[causal-linkage]]
```

---

## Проверка

После создания страницы:
1. Проверить что frontmatter валиден (id, page_type, domain, layer, tags, version, created, updated, sources)
2. Проверить что все `[[...]]` ссылки указывают на существующие wiki-страницы
3. Убедиться что нумерация строго последовательна: 1–233 без пропусков и дублей
4. Убедиться что файл создан в правильном месте: `wiki/idea/sdd-open-questions.md`
