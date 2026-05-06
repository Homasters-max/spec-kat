---
id: pattern/replay-engine
page_type: pattern
domain: sdd
layer: architecture
tags:
- automation
- validation
- pipeline
- domain/sdd
version: 3
created: '2026-05-05'
updated: '2026-05-06'
sources:
- raw/replay-based-testing-architecture.md
---
# ReplayEngine

L0-компонент: pure функция `replay(events) → ReplayResult`. Воспроизводит State из list[Event] без доступа к БД. Генерирует `synthetic_trace` инкрементально — Tier 1 тесты получают trace assertions бесплатно.

## How It Works

```python
@dataclass
class StateSnapshot:
    event_id: str
    state: State

@dataclass
class TraceEntry:
    kind: str       # = event.type
    payload: dict
    event_id: str

@dataclass
class ReplayResult:
    final_state: State
    snapshots: list[StateSnapshot]
    synthetic_trace: list[TraceEntry]

class ReplayEngine:
    def replay(self, events: list[Event]) -> ReplayResult:
        state = initial_state()
        snapshots, trace = [], []
        for e in events:
            state = reduce(state, upcast(e))
            snapshots.append(StateSnapshot(event_id=e.id, state=state))
            trace.append(TraceEntry(kind=e.type, payload=e.payload, event_id=e.id))
        return ReplayResult(
            final_state=state,
            snapshots=snapshots,
            synthetic_trace=trace,
        )
```

**Ключевые свойства:**

- Никакого DB-доступа (I-REPLAY-1)
- `upcast()` применяется к каждому событию перед `reduce()` (I-REPLAY-2)
- `initial_state()` детерминирован — без timestamps, без random (I-REPLAY-3)
- `synthetic_trace` строится инкрементально из events; TraceProjection не читается (I-REPLAY-11)

## When To Use

Вызывается `GoldenTestRunner` при запуске Tier 2 тестов через [[golden-fixture]]. Также напрямую в Tier 1 unit replay с hand-crafted events.

## Trade-offs

- Pure функция: нет side-effects, но требует полного event slice на входе
- `snapshots` растут линейно с длиной event sequence — для длинных sequences только `final_state` может быть достаточно

## See Also

- [[reducer]]
- [[upcaster-registry]]
- [[task-event-slice]]
- [[golden-fixture]]
- [[replay-based-testing]]

## Open Questions

- [ ] (P1) Q98 PARTIAL: Mismatch между replay result и expected state. Alerting? Auto-quarantine? → [[classified-recovery]] но нет replay-specific flow.
- [ ] (P1) Q99: При каком объёме EventLog full replay неприемлем? Метрики? Benchmark?
- [ ] (P1) Q100: Проверяются ли все projections на консистентность после replay? Что считается mismatch?
- [ ] (P1) Q101 PARTIAL: Команды для replay существуют? `sdd replay-from --event-id N`? → [[replay-engine]] (code), но CLI не задокументирован.

- [ ] (P2) Q159: Сколько команд/сек принимает система? Где bottleneck — DB, reducer, projections?
- [ ] (P2) Q160: SLA на command execution: P50, P95, P99?
- [ ] (P2) Q161: Budget на сборку ContextPacket? Graph query timeout?
- [ ] (P2) Q162: Стоимость первого TaskRun после idle? Projection warm-up?
- [ ] (P2) Q163: Как измерять performance hotpaths? Встроенная instrumentация?

## Decisions

- [x] (P1) Q94: Replay scope — full EventLog → [[replay-engine]]
- [x] (P1) Q95: Replay isolation — stateless, no side effects → [[replay-engine]]
- [x] (P1) Q96: Replay step-by-step — поддерживается → [[replay-engine]]
- [x] (P1) Q97: Replay with snapshots — golden-fixture → [[golden-fixture]]
