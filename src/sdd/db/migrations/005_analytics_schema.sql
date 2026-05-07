-- Migration: 005_analytics_schema
-- BC-32-4: analytics schema — cross-domain read-only views for observability (I-DB-SCHEMA-1)
-- Depends on: 004_artifacts_schema (p_sdd.invariants_current), 003_tasks_schema (p_sdd.tasks),
--             002_core_schema (p_sdd.events, p_sdd.phases)

CREATE SCHEMA analytics;

-- all_events: unified event log (explicit col_map — SELECT * forbidden, I-DB-SCHEMA-1)
CREATE VIEW analytics.all_events AS
SELECT
    e.seq,
    e.event_id,
    e.event_type,
    e.phase_id,
    e.task_id,
    e.actor,
    e.payload,
    e.recorded_at
FROM p_sdd.events e;

-- all_tasks: current task state with phase context
CREATE VIEW analytics.all_tasks AS
SELECT
    t.task_id,
    t.phase_id,
    t.status,
    t.origin_seq,
    t.last_seq,
    t.recorded_at
FROM p_sdd.tasks t;

-- all_phases: phase lifecycle records
CREATE VIEW analytics.all_phases AS
SELECT
    ph.phase_id,
    ph.status,
    ph.spec_file,
    ph.plan_file,
    ph.activated_at,
    ph.completed_at,
    ph.meta
FROM p_sdd.phases ph;

-- all_invariants: latest result per invariant_id (derived from p_sdd.invariants_current)
CREATE VIEW analytics.all_invariants AS
SELECT
    ic.invariant_id,
    ic.phase_id,
    ic.result,
    ic.detail,
    ic.event_seq,
    ic.recorded_at
FROM p_sdd.invariants_current ic;
