---
created: '2026-05-05'
domain: sdd
id: idea/command-context
layer: architecture
page_type: idea
sdd_domain: Core
sdd_layer: L0
sources:
- raw/SDD Meta Harness Core.md
tags:
- pipeline
- automation
- ssot
- domain/sdd
- sdd/l0
- sdd/core
updated: '2026-05-05'
version: 1
---
# Command Context

Контекст исполнения команды в SDD: создаётся один раз при `start-task` и неявно передаётся через весь execution pipeline. Копируется в `metadata` каждого Event.

## How It Works

```yaml
CommandContext:
  actor: string
  session_id: string
  task_id: string
  timestamp: ts
```

**Правила:**

- Создаётся **один раз** при `sdd start-task`.
- Передаётся **неявно** через весь pipeline (не передаётся явно в каждом вызове).
- Копируется в `metadata` каждого `Event`, что обеспечивает полную трассировку.
- Handler signature: `handle(command, state, ctx) → list[Event]`.

Отличие от `Command`: `Command` = **что** сделать (атомарное действие), `CommandContext` = **в каком контексте** исполняется.

## When To Use

Автоматически создаётся SDD при `start-task`. Все последующие команды в сессии получают этот контекст.

## Trade-offs

- Один контекст на всю task session — если нужно изменить actor/session_id, нужна новая сессия.

## See Also

- [[sdd-meta-harness]]
- [[graph-session-state]]
- [[trace-store]]
