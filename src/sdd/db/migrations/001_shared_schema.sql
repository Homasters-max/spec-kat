-- Migration: 001_shared_schema
-- BC-32-0: shared schema — framework-level tables shared across all projects
-- Invariants: I-DB-SCHEMA-1, I-DB-1

CREATE SCHEMA IF NOT EXISTS shared;

-- shared.projects: registry of all SDD projects
-- Schema naming rule: db_schema = p_{project_name} (e.g. p_sdd, p_dwh)
CREATE TABLE shared.projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    db_schema   TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    meta        JSONB NOT NULL DEFAULT '{}'
);

-- shared.invariants: SDD framework invariants (I-1, I-2, I-DB-1, ...)
-- Project-scoped invariants live in p_{name}.invariants with FK → shared.invariants
CREATE TABLE shared.invariants (
    id              TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    statement       TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT 'framework',
    introduced_seq  BIGINT,
    meta            JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (id, version),
    CONSTRAINT scope_values CHECK (scope IN ('framework', 'shared'))
);
