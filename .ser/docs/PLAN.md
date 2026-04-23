# SER v2.3 — Поэтапный план реализации

## Context

SER — детерминированная самоэволюционирующая система исполнения спецификаций. Цель: реализовать инкрементально, начиная с минимального ядра, способного загрузить само себя (Spec_0 bootstrap → детерминированное исполнение → воспроизводимый replay). Каждая последующая фаза надстраивается над этим фундаментом, не ломая инварианты предыдущей.

---

## Phase 1 — Self-Bootstrapping Core (минимальное ядро)

**Цель:** система способна запустить себя, выполнить Spec_0 и гарантировать детерминированный replay. Это фундамент: всё последующее — надстройка поверх него.

### Компоненты

#### 1.1 EventLog (BC-7 minimal + I-P-10)

- Append-only структура; хранение `(event_id, event_type, payload, timestamp)`.
- **GlobalEventRegistry**: hash-index `event_id → content_hash` — единственный источник exactly-once гарантии (I-NEW-26), обращается до Reducer на каждом событии.
- События: `EventDeduped` при дубликате.

#### 1.2 Reducer (I-NEW-30, I-P-3)

- Чистая функция: `(State × Event) → State` — без side-effects, без RNG.
- Partition-aware: один Reducer на partition (I-P-2).
- Schema upcasting: если `event_schema_version < current` — применить upcast-функцию перед обработкой, emit `SchemaVersionMigrated` (I-NEW-17).
- Порядок в partition: total order. Cross-partition: causal consistency (I-NEW-22).

#### 1.3 SpecManagement — BC-1 (minimal)

- Сущности: `Spec(id, definition_sql, parent_spec_id, version)`, `SpecArchive`.
- Валидация синтаксиса DSL; компиляция в SQL IR.
- Spec_0 bootstrap: 1000-шаговый entropy test → emit `ConvergenceValidated(entropy_trajectory, passed)` (I-NEW-11). Если `passed=false` — bootstrap заблокирован.
- Emit: `SpecCreated(spec_id, parent_spec_id, version, definition_sql)`.
- Иммутабельность: Spec(id) неизменяем после создания (I-P-1).
- Lineage DAG: `parent_spec_id` обязателен для всех Spec кроме Spec_0 (I-P-5).

#### 1.4 Policy — BC-8 (frozen v0)

- При bootstrap: emit `PolicyActivated(version=0, scheduler_weights, guard_config)`.
- `policy_version` замораживается в `ExecutionCreated` и не меняется до `ExecutionFinished` (I-NEW-2, I-NEW-13).
- Изменения Policy в Phase 1 — только ручные (UC-8 partial без approval flow).

#### 1.5 ExecutionRuntime — BC-2 (core)

- При старте исполнения:
    - Заморозить `cost_model_version`, `guard_policy_version`, `policy_version`.
    - Emit `ExecutionCreated(execution_id, spec_version_id, cost_model_version, policy_version, guard_policy_version)`.
    - Emit `ExecutionEnvironmentSnapshot(execution_id, python_version, lib_versions, sql_engine_version, hardware_class)` (I-NEW-21).
    - Emit `ExecutionSpecBinding(execution_id, spec_version_id)` до начала исполнения (I-NEW-5).
- Scheduler: `readyEvents(partition_key, state_version, policy_id)` → `SortedList` по `(priority DESC, partition_key, event_id)` (I-NEW-12). Starvation-free (I-NEW-23).
- Reducer применяет события: сначала проверка GlobalEventRegistry, затем 24h dedup-окно.
- Emit `ExecutionFinished(execution_id, final_state, spec_version_id)`.
- Replay: требует идентичного `ExecutionEnvironmentSnapshot`; отказ при расхождении (I-NEW-21).

#### 1.6 Telemetry — BC-7 (minimal)

- Consume все domain events.
- Хранение GlobalEventRegistry (hash index, постоянный).
- SchemaRegistry: `(event_type, version, upcast_rules)`.
- Независимый SLA: Telemetry не блокирует основной pipeline.

### Use Cases в Phase 1

- **UC-1** Bootstrap System: полностью.
- **UC-2** Execute Spec: полностью (без ContextAssembly).
- **UC-6** Rollback on Degradation: только emit `CircuitBreakerStateChange` + `Rollback`; без HumanGate.

### Инварианты, покрытые в Phase 1

I-P-1, I-P-2, I-P-3, I-P-4, I-P-5, I-P-6, I-P-10, I-NEW-2, I-NEW-5, I-NEW-11, I-NEW-12, I-NEW-13, I-NEW-16, I-NEW-17, I-NEW-21, I-NEW-22, I-NEW-23, I-NEW-26, I-NEW-30, I-MOD-1 (convergence test), I-MOD-4 (cost_model frozen), I-MOD-7 (SpecBinding mandatory).

### Критические файлы / модули

```
src/
  event_log/
    global_registry.py       # GlobalEventRegistry (hash index)
    event_log.py             # append-only store
    dedup_aggregate.py       # 24h dedup window
  reducer/
    reducer.py               # pure (State × Event) → State
    schema_registry.py       # upcasting
  spec_management/
    spec.py                  # Spec entity + lineage DAG
    bootstrap.py             # entropy test → ConvergenceValidated
    dsl_compiler.py          # DSL → SQL IR
  execution_runtime/
    execution.py             # ExecutionCreated, SpecBinding, Finished
    scheduler.py             # readyEvents, tie-breaking, starvation-free
    environment_snapshot.py  # python/lib/sql/hw capture
  policy/
    policy.py                # PolicyActivated v0
  telemetry/
    telemetry.py             # consume all events, independent SLA
```

### Верификация Phase 1

1. `pytest tests/bootstrap/` — entropy test on Spec_0 passes; ConvergenceValidated emitted.
2. `pytest tests/execution/` — ExecutionCreated → SpecBinding → Finished; event order preserved.
3. Replay test: replay same EventLog → identical `final_state` (I-P-3).
4. Dedup test: submit same event_id twice → only one processed, EventDeduped emitted.
5. Environment mismatch test: replay with different `python_version` → rejected.
6. Scheduler test: identical state → identical `ExecSet` (I-NEW-12).

---

## Phase 2 — Evaluation & Context Assembly

**Цель:** система умеет оценивать результаты исполнения и собирать контекст для агента.

### Добавляется

- **BC-3 ContextAssembly**: fragment selection (tie-breaker I-NEW-7), slot boundaries (I-NEW-8), TRUNCATE_ONLY default, tokenizer/algorithm versioning (I-NEW-28). Events: `FragmentSelected`, `ContextWindowBuilt`, `ContextSlotTruncated/Overflowed`.
- **BC-4 Evaluation**: deterministic metrics (no RNG, no APIs — I-NEW-19), RiskModel(seed=42 — I-NEW-14), Phase 1 Simulator(seed — I-NEW-15). Events: `MetricComputed`, `RiskModelTrained`, `SimulationCompleted`.
- **BC-6 GuardSystem (basic)**: CircuitBreaker (error_rate > 0.1, 5m window, consecutive_failures ≥ 3 — I-NEW-13). Events: `CircuitBreakerStateChange`.
- **W8b partial**: начало мониторинга латентности (без enforcement).

### Use Cases в Phase 2

- UC-3 Evaluate Execution: полностью.
- UC-7 Assemble Context for Agent: полностью (включая SafetyFilter).
- UC-6 Rollback: полностью (с CircuitBreaker).

### Инварианты, добавляемые в Phase 2

I-NEW-1, I-NEW-7, I-NEW-8, I-NEW-14, I-NEW-15, I-NEW-19, I-NEW-20, I-NEW-28, I-P-8 (Pareto frontier — начало), I-P-11, I-P-12.

### Верификация Phase 2

1. MetricComputed: одинаковые inputs → одинаковый value при двух запусках.
2. ContextWindowBuilt: идентичный hash при идентичном state/policy/spec.
3. Slot overflow: TRUNCATE применён, ContextSlotTruncated emitted.
4. RiskModel: seed=42, одинаковые features → одинаковый risk_score.
5. CircuitBreaker: 3 consecutive failures → OPEN; новое исполнение заблокировано.

---

## Phase 3 — Evolution & Human Gate

**Цель:** система способна предлагать и безопасно продвигать новые Spec в production.

### Добавляется

- **BC-5 Evolution**: proposer (immutable strategy, seed=42 — I-NEW-4, I-P-15), adaptive trust region Δ_t (I-NEW-24), Phase 1→3 evaluation pipeline, self-mutation guard (I-NEW-10), SpecDelta validation (I-NEW-9).
    - Phase 3: ≥2 independent statistical tests must agree at alpha=0.05 (I-NEW-25 — t-test + bootstrap или Mann-Whitney).
    - Events: `CandidateProposed`, `TrustRegionUpdated`, `PromotionStatisticalTest`, `AttributionPhase3Complete`, `DeltaAccepted/Rejected`, `ProposerSelfMutationBlocked`, `SpecDeltaValidated`.
- **BC-6 GuardSystem (full)**: HumanGate fully event-sourced (I-NEW-27). Events: `HumanGatePending`, `HumanGateApproved/Denied`, `HumanGateTimeoutApproaching`.
- **Canary rollout**: мониторинг → `Rollback` при деградации (I-P-13).
- **BC-1 SpecManagement**: SpecArchive + Archive novelty distance (I-P-6, I-P-7).
- **Policy rollback**: UC-9 полностью (I-NEW-29).
- **Phase 2 Shadow deployment**: без impact на пользователей.

### Use Cases в Phase 3

- UC-4 Propose Spec Delta: полностью.
- UC-5 Promote Candidate: полностью (включая HumanGate).
- UC-9 Rollback Policy: полностью.
- UC-8 Update Policy: полностью (с approval flow).

### Инварианты, добавляемые в Phase 3

I-NEW-3, I-NEW-4, I-NEW-6, I-NEW-9, I-NEW-10, I-NEW-18, I-NEW-24, I-NEW-25, I-NEW-27, I-NEW-29, I-P-7, I-P-8 (full Pareto), I-P-9, I-P-13, I-P-14, I-P-15, I-MOD-5, I-MOD-6.

### Верификация Phase 3

1. ProposerSelfMutationBlocked: target == proposer → rejected.
2. Trust region: d(parent, new) > Δ_t → DeltaRejected.
3. Phase 3: одиночный тест → DeltaRejected (I-NEW-25).
4. Phase 3: два теста p < 0.05, confidence ≥ 0.7 → DeltaAccepted.
5. HumanGateDenied → DeltaRejected, событие в EventLog.
6. Canary degradation → CircuitBreakerStateChange(OPEN) + Rollback.
7. TrustRegionUpdated emitted after each evolution cycle.

---

## Phase 4 — Production Hardening

**Цель:** закрыть оставшиеся gaps из §8 архитектуры (W8a–d, R-*).

### Добавляется

- **W8a** Backpressure: per-partition admission control; `BackpressureSignal` event; producers throttle.
- **W8b** Latency SLA: p99 как trigger для CircuitBreaker; `LatencySLABreached` event.
- **W8c** Failure Domain Isolation: Reducer per process boundary; per-partition resource quotas.
- **W8d** Multi-tenant Isolation: tenant-scoped partitions; per-tenant GuardPolicy + latency SLA.
- **R-CONSENSUS-1** Raft consensus для Spec promotion (вместо centralized approval MVP).
- **R-PARTITION-1** Dynamic partition rebalancing.
- **R-COST-2** Gradient-based cost model anomaly detection.
- **ProposerStrategy online learning** (W4): ProposerStrategyTrained events, PROTECTED ACL.
- **Fairness metrics**, cost variance/tail risk (G-M7, G-M11).
- **TEXRANK_SEED_0** deterministic summarization: полная спецификация.

### Верификация Phase 4

1. Backpressure: queue depth > threshold → BackpressureSignal emitted, producer throttled.
2. Multi-tenant: burst от tenant A не влияет на latency tenant B (измерение p99).
3. Partition rebalance: добавление partition без потери событий.
4. ProposerStrategy update: ProposerStrategyTrained → новая стратегия применяется в следующем цикле.

---

## Сводная таблица фаз

|Фаза|Ключевой результат|BC покрыты|Инвариантов|
|---|---|---|---|
|1|Само-запуск: Spec_0 → детерминированный replay|BC-1(min), BC-2, BC-7(min), BC-8(v0)|19|
|2|Оценка исполнений + контекст для агента|+ BC-3, BC-4, BC-6(CB)|+12|
|3|Полный эволюционный цикл + HumanGate|+ BC-5, BC-6(full), BC-1(full)|+14|
|4|Production hardening: backpressure, multitenancy, consensus|все|оставшиеся|