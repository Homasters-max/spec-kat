---
id: pattern/bootstrap-policy
page_type: pattern
domain: sdd
layer: architecture
tags:
- enforcement
- ssot
- write-path
- automation
- domain/sdd
version: 1
created: '2026-05-05'
updated: '2026-05-05'
sources:
- raw/sdd-v2-architecture-deepening.md
---
# Bootstrap Policy

## Summary

`bootstrap-policy` — явная L1-команда, выполняемая один раз при первом деплое системы. Решает проблему "курицы и яйца": [[policy-kernel]] хранит правила как `PolicyUpdated` events в EventLog (SSOT), но при первом старте EventLog пуст и guards не знают правил. Команда читает `norm_catalog.yaml` и эмитит поток стандартных `PolicyUpdated` событий — по одному на каждую норму. После bootstrap YAML становится артефактом деплоя, не рантайм-источником.

## How It Works

**Handler:**

```text
bootstrap-policy handler:
    for norm in parse_yaml(path):
        emit PolicyUpdated(
            norm_id   = norm.id,
            rule      = norm.rule,
            actor     = "human",
            source    = "bootstrap",
            yaml_hash = hash(norm_catalog.yaml)
        )
```

Не `PolicySeeded` — стандартный `PolicyUpdated`. [[projection-registry]] строит PolicyProjection из этих событий без специального кода для "сидирования" — тот же механизм что при `update-policy`.

**Idempotency guard:** повторный `bootstrap-policy` проверяет EventLog на наличие `PolicyUpdated` с `source="bootstrap"` и тем же `yaml_hash`:
- Совпадение → NOOP + предупреждение
- YAML изменился → требует `--force` флаг с явным подтверждением

**Статус YAML после bootstrap:**
- Артефакт сборки/деплоя — не рантайм-источник
- [[policy-kernel]] в рантайме читает только PolicyProjection (EventLog-based)
- YAML используется для: `bootstrap-policy`, документации, code review
- Изменение нормы в рантайме = новый `PolicyUpdated` event через `sdd update-policy`

**Human-only команда:** actor validation guard отклоняет вызов от LLM.

## When To Use

Ровно один раз — при первом деплое sdd_v2 в новое окружение. После успешного bootstrap PolicyProjection содержит все нормы из YAML и система может стартовать с заполненными guards.

## Trade-offs

**Плюсы:** EventLog остаётся единственным SSOT — начальное состояние также в нём с полным аудитом; `PolicyUpdated` (не специальный тип) → PolicyProjection строится без спецкода; idempotency guard предотвращает случайный повторный импорт; replay-based-testing работает автоматически.

**Минусы:** bootstrap должен быть выполнен до первого старта guards — порядок деплоя имеет значение; `--force` при смене YAML — потенциально опасная операция (нужен review изменений норм).

**Изменение норм:** после первого bootstrap не нужно трогать YAML для изменения правил. Правильный путь: `sdd update-policy --norm-id N --rule "..."` → новый `PolicyUpdated` event. YAML хранится для документирования начального состояния.

## See Also

- [[policy-kernel]] — L2 компонент, управляющий governance rules
- [[projection-registry]] — строит PolicyProjection из PolicyUpdated events
- [[event-sourcing]] — принцип SSOT, который нарушался без bootstrap-policy
- [[global-laws]] — GL-2 (EventLog is SSOT)
