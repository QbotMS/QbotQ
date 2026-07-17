-- =====================================================================
-- !!! DEPRECATED / HISTORYCZNE — zastapione przez refaktor kalendarza 2026-07-16 !!!
-- Ponizsze tabele (calendar_days, calendar_daily_snapshots, calendar_events,
-- reminders, reminder_channels, import_jobs) NIE sa juz zywym schematem.
-- Zywe tabele kalendarza: calendar_entry (kolumna: day), calendar_day_route,
-- calendar_reminder_fired.
-- W SZCZEGOLNOSCI: calendar_events JUZ NIE ISTNIEJE. NIE uruchamiaj tego pliku
-- na slepo — odtworzylby martwe tabele. Zostawione wylacznie dla historii.
-- Trigger refresh_day_flags() wskazuje teraz calendar_entry(day)
-- — patrz sql/refresh_day_flags_fix.sql.
-- =====================================================================

-- QBot Calendar Core v1 — daily timeline, snapshots, events, reminders
BEGIN;

-- 1. Calendar days — per-date metadata
CREATE TABLE IF NOT EXISTS calendar_days (
    date            DATE PRIMARY KEY,
    timezone        TEXT NOT NULL DEFAULT 'Europe/Warsaw',
    day_type        TEXT,
    planned_day_type TEXT,
    actual_day_type TEXT,
    notes           TEXT,
    tags_json       JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Daily snapshots — cached context from all domain tables
CREATE TABLE IF NOT EXISTS calendar_daily_snapshots (
    date            DATE PRIMARY KEY REFERENCES calendar_days(date) ON DELETE CASCADE,
    snapshot_json   JSONB NOT NULL DEFAULT '{}',
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completeness_score DOUBLE PRECISION,
    missing_fields_json JSONB,
    missing_tables_json JSONB,
    source_tables_json JSONB
);

-- 3. Calendar events — general events
CREATE TABLE IF NOT EXISTS calendar_events (
    id              SERIAL PRIMARY KEY,
    date_start      DATE NOT NULL,
    date_end        DATE,
    event_type      TEXT NOT NULL DEFAULT 'note',
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'planned',
    source          TEXT NOT NULL DEFAULT 'manual',
    external_ref    TEXT,
    metadata_json   JSONB,
    affects_training BOOLEAN DEFAULT false,
    affects_nutrition BOOLEAN DEFAULT false,
    affects_health_advice BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cevent_date ON calendar_events(date_start);
CREATE INDEX IF NOT EXISTS idx_cevent_status ON calendar_events(status);

-- 4. Reminders
CREATE TABLE IF NOT EXISTS reminders (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    time            TIME,
    timezone        TEXT NOT NULL DEFAULT 'Europe/Warsaw',
    title           TEXT NOT NULL,
    message         TEXT,
    reminder_type   TEXT NOT NULL DEFAULT 'custom',
    status          TEXT NOT NULL DEFAULT 'pending',
    recurrence_rule TEXT,
    related_entity_type TEXT,
    related_entity_id   INTEGER,
    channel         TEXT NOT NULL DEFAULT 'cli',
    metadata_json   JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reminder_date ON reminders(date);
CREATE INDEX IF NOT EXISTS idx_reminder_status ON reminders(status);

-- 5. Reminder channels
CREATE TABLE IF NOT EXISTS reminder_channels (
    id              SERIAL PRIMARY KEY,
    channel         TEXT NOT NULL UNIQUE,
    enabled         BOOLEAN NOT NULL DEFAULT false,
    config_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 6. Import jobs — history import tracking
CREATE TABLE IF NOT EXISTS import_jobs (
    id              SERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    date_from       DATE NOT NULL,
    date_to         DATE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'planned',
    records_seen    INTEGER DEFAULT 0,
    records_imported INTEGER DEFAULT 0,
    records_skipped INTEGER DEFAULT 0,
    warnings_json   JSONB,
    errors_json     JSONB,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
