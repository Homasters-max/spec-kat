-- Migration: 003_tasks_schema
-- BC-32-2: task-domain projections derived from events (I-EVENT-DERIVE-1)
-- Depends on: 002_core_schema (p_sdd.events, p_sdd.phases)

-- tasks: current projection of each task's state
-- status has no DEFAULT — must be set explicitly from the originating event (I-EVENT-DERIVE-1)
CREATE TABLE p_sdd.tasks (
    task_id      TEXT        PRIMARY KEY,
    phase_id     INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    status       TEXT        NOT NULL,
    origin_seq   BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    last_seq     BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- task_transitions: append-only log of every status change event
CREATE TABLE p_sdd.task_transitions (
    id           BIGSERIAL   PRIMARY KEY,
    task_id      TEXT        NOT NULL REFERENCES p_sdd.tasks (task_id),
    phase_id     INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    from_status  TEXT,
    to_status    TEXT        NOT NULL,
    event_seq    BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- task_validations: validation outcomes per task (PASS / FAIL)
CREATE TABLE p_sdd.task_validations (
    id           BIGSERIAL   PRIMARY KEY,
    task_id      TEXT        NOT NULL REFERENCES p_sdd.tasks (task_id),
    phase_id     INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    result       TEXT        NOT NULL,
    detail       JSONB       NOT NULL DEFAULT '{}',
    event_seq    BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- task_metrics: metric values recorded during task execution
CREATE TABLE p_sdd.task_metrics (
    id           BIGSERIAL   PRIMARY KEY,
    task_id      TEXT        NOT NULL REFERENCES p_sdd.tasks (task_id),
    phase_id     INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    metric_name  TEXT        NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    event_seq    BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- task_sessions: session declarations scoped to a task
CREATE TABLE p_sdd.task_sessions (
    id            BIGSERIAL   PRIMARY KEY,
    task_id       TEXT        NOT NULL REFERENCES p_sdd.tasks (task_id),
    phase_id      INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    session_type  TEXT        NOT NULL,
    actor         TEXT        NOT NULL DEFAULT 'llm',
    event_seq     BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- task_decisions: decisions recorded during task implementation
CREATE TABLE p_sdd.task_decisions (
    id            BIGSERIAL   PRIMARY KEY,
    task_id       TEXT        NOT NULL REFERENCES p_sdd.tasks (task_id),
    phase_id      INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    decision_text TEXT        NOT NULL,
    rationale     TEXT,
    event_seq     BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
