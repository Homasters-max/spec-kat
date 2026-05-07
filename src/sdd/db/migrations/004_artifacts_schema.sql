-- Migration: 004_artifacts_schema
-- BC-32-3: artifact-domain projections derived from events (I-EVENT-DERIVE-1)
-- Depends on: 003_tasks_schema (p_sdd.tasks)

-- specs: approved spec snapshots (immutable after SpecApproved event, SDD-9)
-- status has no DEFAULT — must be set explicitly from the originating event (I-EVENT-DERIVE-1)
CREATE TABLE p_sdd.specs (
    spec_id      TEXT        PRIMARY KEY,       -- e.g. "Spec_v32"
    phase_id     INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    version      INTEGER     NOT NULL,
    content_hash TEXT        NOT NULL,
    status       TEXT        NOT NULL,
    origin_seq   BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    last_seq     BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- specs_draft: editable draft specs (mutable until SpecApproved)
-- status has no DEFAULT — must be set explicitly from the originating event (I-EVENT-DERIVE-1)
CREATE TABLE p_sdd.specs_draft (
    draft_id     BIGSERIAL   PRIMARY KEY,
    phase_id     INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    version      INTEGER     NOT NULL,
    content_hash TEXT        NOT NULL,
    status       TEXT        NOT NULL,
    event_seq    BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- invariants: append-only log of all invariant check results (I-DB-SCHEMA-1)
-- result has no DEFAULT — must be set explicitly from the originating event (I-EVENT-DERIVE-1)
CREATE TABLE p_sdd.invariants (
    id             BIGSERIAL   PRIMARY KEY,
    invariant_id   TEXT        NOT NULL,        -- e.g. "I-1", "I-DB-TEST-1"
    phase_id       INTEGER     NOT NULL REFERENCES p_sdd.phases (phase_id),
    result         TEXT        NOT NULL,        -- PASS / FAIL
    detail         JSONB       NOT NULL DEFAULT '{}',
    event_seq      BIGINT      NOT NULL REFERENCES p_sdd.events (seq),
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- invariants_current: latest result per invariant_id (derived from invariants)
-- VIEW satisfies FK relationship via invariant_id reference to p_sdd.invariants
CREATE VIEW p_sdd.invariants_current AS
SELECT DISTINCT ON (invariant_id)
    invariant_id,
    phase_id,
    result,
    detail,
    event_seq,
    recorded_at
FROM p_sdd.invariants
ORDER BY invariant_id, recorded_at DESC;
