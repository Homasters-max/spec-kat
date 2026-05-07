# Session: INIT_STATE
<!-- source: §K.1 Init State N -->

## When to use

Only when `State_index.yaml` does NOT exist (fresh project or after full EventLog loss+restore).

## Exemption

INIT_STATE is exempt from State Guard — the ONLY command allowed without `State_index.yaml`.

---

## Preconditions

- Human provides: phase number N
- `State_index.yaml` MUST NOT exist (if it does → do not use INIT_STATE, use `sdd sync-state`)
- `TaskSet_vN.md` exists in `.sdd/tasks/`

---

## Steps

```
1. Read .sdd/tasks/TaskSet_vN.md
   → count total tasks, completed tasks, done_ids list

2. Create .sdd/runtime/State_index.yaml with:
   phase:
     current: N
     status: ACTIVE
   plan:
     status: ACTIVE
     version: N
   tasks:
     version: N
     total: <count from TaskSet>
     completed: <count of DONE tasks>
     done_ids: [<list of DONE task IDs>]
   invariants:
     status: UNKNOWN
   tests:
     status: UNKNOWN
   meta:
     last_updated: <ISO8601 now>
     schema_version: 1
```

---

## After Init

```
sdd show-state    ← verify State_index reflects TaskSet
```

If mismatch → `sdd sync-state --phase N` (idempotent rebuild from EventLog).
