-- QBot sandbox artifacts store for qbot_v2
-- Idempotent bootstrap DDL for projects and artifacts.

CREATE SCHEMA IF NOT EXISTS qbot_v2;

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
EXCEPTION
    WHEN insufficient_privilege THEN
        NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE qbot_v2.artifact_type AS ENUM (
        'route',
        'poi',
        'plan',
        'report',
        'export',
        'database',
        'import',
        'document'
    );
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE qbot_v2.artifact_status AS ENUM (
        'active',
        'archived',
        'deleted',
        'tmp'
    );
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END $$;

DO $$
BEGIN
    CREATE TYPE qbot_v2.mutation_type AS ENUM (
        'source',
        'copy',
        'split',
        'merge',
        'edit',
        'export',
        'analysis',
        'generated'
    );
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END $$;

DO $$
BEGIN
    ALTER TYPE qbot_v2.mutation_type ADD VALUE IF NOT EXISTS 'import';
EXCEPTION
    WHEN duplicate_object THEN
        NULL;
END $$;

CREATE TABLE IF NOT EXISTS qbot_v2.projects (
    project_id      text        PRIMARY KEY,
    title           text        NOT NULL,
    description     text,
    project_type    text        NOT NULL DEFAULT 'trip',
    status          text        NOT NULL DEFAULT 'active',
    start_date      date,
    end_date        date,
    metadata_json   jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS qbot_v2.artifacts (
    artifact_id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          text        REFERENCES qbot_v2.projects(project_id),
    artifact_type       qbot_v2.artifact_type NOT NULL,
    mutation_type       qbot_v2.mutation_type NOT NULL DEFAULT 'source',
    title               text        NOT NULL,
    filename            text,
    mime_type           text,
    file_path           text,
    size_bytes          bigint,
    sha256              text,
    source              text,
    status              qbot_v2.artifact_status NOT NULL DEFAULT 'active',
    parent_artifact_id  uuid        REFERENCES qbot_v2.artifacts(artifact_id),
    version             int         NOT NULL DEFAULT 1,
    expires_at          timestamptz,
    idempotency_key     text        UNIQUE,
    metadata_json       jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS artifacts_project_idx   ON qbot_v2.artifacts(project_id);
CREATE INDEX IF NOT EXISTS artifacts_type_idx      ON qbot_v2.artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS artifacts_status_idx    ON qbot_v2.artifacts(status);
CREATE INDEX IF NOT EXISTS artifacts_parent_idx    ON qbot_v2.artifacts(parent_artifact_id);
CREATE INDEX IF NOT EXISTS artifacts_expires_idx   ON qbot_v2.artifacts(expires_at) WHERE expires_at IS NOT NULL;

INSERT INTO qbot_v2.projects (
    project_id, title, description, project_type, start_date, end_date
) VALUES (
    'tuscany_2026',
    'Bikepacking Toskania 2026',
    'Florencja, ~560km, ~7500m, 7-9 dni, z kolegą, hotele',
    'trip',
    '2026-06-02',
    '2026-06-13'
)
ON CONFLICT (project_id) DO NOTHING;
