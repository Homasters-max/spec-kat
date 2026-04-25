---
source: CLAUDE.md §0.12
last_synced: 2026-04-24
update_trigger: when hook mechanism changes or SDD_SEQ_CHECKPOINT needs updating
---

# Ref: Audit Hooks & Hook Infrastructure
<!-- Loaded for debugging hooks or seq reset operations -->

## Hook Mechanism (Phase 13 M1 complete)

```
PreToolUse  (.*)  → sdd-hook-log pre  → sdd.hooks.log_tool.main()
                                        → emits ToolUseStarted → sdd_events.duckdb only

PostToolUse (.*)  → sdd-hook-log post → sdd.hooks.log_tool.main()
                                        → emits ToolUseCompleted → sdd_events.duckdb only
```

Hook is configured in `~/.claude/settings.json`. Matcher: `.*` (all tools).
Hook NEVER blocks execution (exit 0) — informational only (NORM-AUDIT-BASH).

## ToolUse Event Payloads

**ToolUseStarted payload by tool:**

| tool_name | extra fields |
|-----------|-------------|
| `Bash` | `command` (≤300 chars), `description` |
| `Read` | `file_path`, `offset`?, `limit`? |
| `Edit` | `file_path`, `old_len`, `new_len` |
| `Write` | `file_path`, `content_len` |
| `Glob` | `pattern`, `path` |
| `Grep` | `pattern`, `glob`, `path`, `output_mode` |
| `Agent` | `description` (≤120 chars), `subagent_type` |
| others | `keys` (list of input key names) |

**ToolUseCompleted** always adds: `output_len` (bytes), `interrupted` (bool), `error_snippet` (if error).

## SDD_SEQ_CHECKPOINT (SDD-SEQ-1) — CRITICAL

```python
# in src/sdd/infra/sdd_db.py
SDD_SEQ_CHECKPOINT = 85   # floor; update when manually resetting sequence
```

DuckDB does not always persist sequence state across connections. `sdd_db.py` compensates:
```python
next_seq = max(SDD_SEQ_CHECKPOINT, current_max + 1)
CREATE OR REPLACE SEQUENCE sdd_event_seq START {next_seq}
```

**When to update SDD_SEQ_CHECKPOINT:**
- ONLY when DuckDB file is recreated or events manually deleted
- Set to `MAX(seq) + 1` from new DB state
- Update BOTH `sdd_db.py` AND CLAUDE.md §0.12 simultaneously

**Rule:** dynamic `MAX(seq)+1` is authoritative. `SDD_SEQ_CHECKPOINT` is a safety floor.

## Querying BashCommand Events

BashCommand events have NO `phase_id` in payload:

```bash
sdd query-events --event BashCommandStarted
sdd query-events --phase N --include-bash    # phase events + bash commands
```

## NORM-AUDIT-BASH

```
norm_id:     NORM-AUDIT-BASH
actor:       llm
type:        informational (not enforcement)
result:      always "allowed" — hook NEVER blocks execution
applies_to:  every tool call (matcher: ".*"), regardless of phase
```

## Legacy Note

Before Phase 13 M1: matcher was `Bash` → `log_bash.py` → emitted `BashCommandStarted`/`BashCommandCompleted` → DuckDB + audit_log.jsonl. These events remain as historical record.
