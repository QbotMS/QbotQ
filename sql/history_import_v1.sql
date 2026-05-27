-- QBot History Import v1 — weight, body composition, training sessions
BEGIN;

CREATE TABLE IF NOT EXISTS weight_history (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    measured_at     TIMESTAMPTZ,
    weight_kg       DOUBLE PRECISION NOT NULL,
    source          TEXT NOT NULL DEFAULT 'garmin',
    external_id     TEXT,
    raw_json        JSONB,
    imported_at     TIMESTAMPTZ DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_weight_date ON weight_history(date);

CREATE TABLE IF NOT EXISTS body_composition (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    measured_at     TIMESTAMPTZ,
    weight_kg       DOUBLE PRECISION,
    body_fat_pct    DOUBLE PRECISION,
    bmi             DOUBLE PRECISION,
    lean_mass_kg    DOUBLE PRECISION,
    muscle_mass_kg  DOUBLE PRECISION,
    body_water_pct  DOUBLE PRECISION,
    bone_mass_kg    DOUBLE PRECISION,
    source          TEXT NOT NULL DEFAULT 'garmin',
    external_id     TEXT,
    raw_json        JSONB,
    imported_at     TIMESTAMPTZ DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bcomp_date ON body_composition(date);

CREATE TABLE IF NOT EXISTS training_sessions (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    started_at      TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ,
    source          TEXT NOT NULL DEFAULT 'garmin',
    external_id     TEXT,
    activity_type   TEXT,
    title           TEXT,
    duration_sec    DOUBLE PRECISION,
    distance_km     DOUBLE PRECISION,
    elevation_gain_m DOUBLE PRECISION,
    calories_kcal   DOUBLE PRECISION,
    avg_hr          INTEGER,
    max_hr          INTEGER,
    avg_power_w     DOUBLE PRECISION,
    max_power_w     DOUBLE PRECISION,
    training_load   DOUBLE PRECISION,
    training_effect DOUBLE PRECISION,
    route_ref       TEXT,
    raw_json        JSONB,
    imported_at     TIMESTAMPTZ DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tsession_date ON training_sessions(date);
CREATE INDEX IF NOT EXISTS idx_tsession_extid ON training_sessions(external_id);

COMMIT;
