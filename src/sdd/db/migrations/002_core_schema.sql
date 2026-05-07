-- Migration: 002_core_schema
-- BC-32-1: core schema for p_sdd project (event store + state projections)
-- Invariants: I-1, I-EVENT-DERIVE-1, I-STATE-REBUILD-1
-- Depends on: 001_shared_schema (shared schema + shared.projects)

CREATE SCHEMA IF NOT EXISTS p_sdd;

-- events: append-only event log (source of truth — I-1)
-- State is always derivable via reduce(events); this table is never modified.
CREATE TABLE p_sdd.events (
    seq         BIGSERIAL PRIMARY KEY,
    event_id    TEXT        NOT NULL UNIQUE,
    event_type  TEXT        NOT NULL,
    phase_id    INTEGER,
    task_id     TEXT,
    actor       TEXT        NOT NULL DEFAULT 'system',
    payload     JSONB       NOT NULL DEFAULT '{}',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_type  ON p_sdd.events (event_type);
CREATE INDEX idx_events_task  ON p_sdd.events (task_id);
CREATE INDEX idx_events_phase ON p_sdd.events (phase_id);

-- sdd_state: read-only projection of current state (I-1: never source of truth)
-- Rebuilt by replaying events; never written directly outside the Write Kernel.
CREATE TABLE p_sdd.sdd_state (
    id              INTEGER     PRIMARY KEY DEFAULT 1,
    phase_current   INTEGER     NOT NULL DEFAULT 0,
    phase_status    TEXT        NOT NULL DEFAULT 'PLANNED',
    plan_version    INTEGER,
    tasks_version   INTEGER,
    last_event_seq  BIGINT      NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT single_row CHECK (id = 1)
);

-- phases: per-phase lifecycle records
CREATE TABLE p_sdd.phases (
    phase_id     INTEGER     PRIMARY KEY,
    status       TEXT        NOT NULL DEFAULT 'PLANNED',
    spec_file    TEXT,
    plan_file    TEXT,
    activated_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    meta         JSONB       NOT NULL DEFAULT '{}'
);

-- phase_plan_versions: tracks plan file versions per phase (I-STATE-REBUILD-1)
CREATE TABLE p_sdd.phase_plan_versions (
    phase_id     INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    version      INTEGER     NOT NULL,
    plan_file    TEXT        NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta         JSONB       NOT NULL DEFAULT '{}',
    PRIMARY KEY (phase_id, version)
);
