-- QBot wellness / sleep / nutrition local PostgreSQL store v1
-- Non-destructive: uses IF NOT EXISTS + ON CONFLICT UPSERT

BEGIN;

-- 1. Daily wellness (snapshot per date+source)
CREATE TABLE IF NOT EXISTS qbot_wellness_daily (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    source          TEXT NOT NULL,
    source_priority INTEGER NOT NULL DEFAULT 0,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_record_id TEXT,
    sleep_duration_min DOUBLE PRECISION,
    sleep_score     INTEGER,
    sleep_quality   TEXT,
    hrv_ms          DOUBLE PRECISION,
    resting_hr_bpm  INTEGER,
    body_battery_start INTEGER,
    body_battery_end   INTEGER,
    stress_avg      DOUBLE PRECISION,
    weight_kg       DOUBLE PRECISION,
    subjective_feel TEXT,
    mood            TEXT,
    soreness        TEXT,
    fatigue         TEXT,
    readiness_label TEXT,
    raw_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_wellness_date_source UNIQUE (date, source)
);

-- 2. Sleep detail (per date+source)
CREATE TABLE IF NOT EXISTS qbot_sleep_daily (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    source          TEXT NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    sleep_start     TIMESTAMPTZ,
    sleep_end       TIMESTAMPTZ,
    sleep_duration_min DOUBLE PRECISION,
    deep_sleep_min  DOUBLE PRECISION,
    light_sleep_min DOUBLE PRECISION,
    rem_sleep_min   DOUBLE PRECISION,
    awake_min       DOUBLE PRECISION,
    sleep_score     INTEGER,
    hrv_ms          DOUBLE PRECISION,
    resting_hr_bpm  INTEGER,
    raw_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_sleep_date_source UNIQUE (date, source)
);

-- 3. Nutrition daily (per date+source)
CREATE TABLE IF NOT EXISTS qbot_nutrition_daily (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    source          TEXT NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    calories_kcal   DOUBLE PRECISION,
    carbs_g         DOUBLE PRECISION,
    protein_g       DOUBLE PRECISION,
    fat_g           DOUBLE PRECISION,
    fiber_g         DOUBLE PRECISION,
    sugar_g         DOUBLE PRECISION,
    sodium_mg       DOUBLE PRECISION,
    fluid_ml        DOUBLE PRECISION,
    raw_text        TEXT,
    raw_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_nutrition_date_source UNIQUE (date, source)
);

-- 4. Wellness notes/comments
CREATE TABLE IF NOT EXISTS qbot_wellness_notes (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    source          TEXT NOT NULL,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    note_type       TEXT NOT NULL,
    text            TEXT NOT NULL,
    parsed_json     JSONB,
    source_record_id TEXT,
    CONSTRAINT uq_notes_date_src_type_text UNIQUE (date, source, note_type, text)
);

-- 5. Import runs log
CREATE TABLE IF NOT EXISTS qbot_import_runs (
    id              SERIAL PRIMARY KEY,
    import_type     TEXT NOT NULL,
    source          TEXT NOT NULL,
    date_from       DATE NOT NULL,
    date_to         DATE NOT NULL,
    dry_run         BOOLEAN NOT NULL DEFAULT true,
    status          TEXT NOT NULL DEFAULT 'started',
    rows_seen       INTEGER NOT NULL DEFAULT 0,
    rows_inserted   INTEGER NOT NULL DEFAULT 0,
    rows_updated    INTEGER NOT NULL DEFAULT 0,
    warnings        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wellness_daily_date ON qbot_wellness_daily(date);
CREATE INDEX IF NOT EXISTS idx_wellness_daily_source ON qbot_wellness_daily(source);
CREATE INDEX IF NOT EXISTS idx_sleep_daily_date ON qbot_sleep_daily(date);
CREATE INDEX IF NOT EXISTS idx_sleep_daily_source ON qbot_sleep_daily(source);
CREATE INDEX IF NOT EXISTS idx_nutrition_daily_date ON qbot_nutrition_daily(date);
CREATE INDEX IF NOT EXISTS idx_nutrition_daily_source ON qbot_nutrition_daily(source);
CREATE INDEX IF NOT EXISTS idx_wellness_notes_date ON qbot_wellness_notes(date);
CREATE INDEX IF NOT EXISTS idx_wellness_notes_source ON qbot_wellness_notes(source);
CREATE INDEX IF NOT EXISTS idx_import_runs_type ON qbot_import_runs(import_type, source);

COMMIT;
