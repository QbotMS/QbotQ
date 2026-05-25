CREATE TABLE IF NOT EXISTS qbot_garage_sources (
    id              SERIAL PRIMARY KEY,
    source_path     TEXT NOT NULL,
    source_sha256   TEXT NOT NULL UNIQUE,
    file_size_bytes BIGINT,
    source_type     TEXT DEFAULT 'sqlite',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS qbot_garage_raw_records (
    id             SERIAL PRIMARY KEY,
    source_id      INTEGER NOT NULL REFERENCES qbot_garage_sources(id),
    source_table   TEXT NOT NULL,
    record_index   INTEGER NOT NULL,
    raw_data       JSONB NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS qbot_garage_import_runs (
    id              SERIAL PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES qbot_garage_sources(id),
    rows_imported   INTEGER NOT NULL DEFAULT 0,
    table_counts    JSONB DEFAULT '{}'::jsonb,
    status          TEXT DEFAULT 'completed',
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    finished_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_garage_raw_source_id ON qbot_garage_raw_records (source_id);
CREATE INDEX IF NOT EXISTS idx_garage_raw_table ON qbot_garage_raw_records (source_table);
CREATE INDEX IF NOT EXISTS idx_garage_sources_sha256 ON qbot_garage_sources (source_sha256);
CREATE INDEX IF NOT EXISTS idx_garage_import_runs_source ON qbot_garage_import_runs (source_id);
