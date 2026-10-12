-- Serce (2026-10-12): cisnienie, EKG, tetno przy stalej mocy.
-- Zrodlo danych: Garmin Connect (cisnienie trafia tam z Withings przez qbot-withings-sync,
-- EKG z zegarka). Import: qbot3/connectors/import_garmin_heart.py (straznik Garmina).
-- Dokumentacja: docs/SERCE.md

CREATE TABLE IF NOT EXISTS qbot_v2.blood_pressure (
    id             BIGSERIAL PRIMARY KEY,
    measured_at    TIMESTAMPTZ NOT NULL,
    measured_local TIMESTAMP   NOT NULL,
    systolic       SMALLINT    NOT NULL,
    diastolic      SMALLINT    NOT NULL,
    pulse          SMALLINT,
    source         TEXT        NOT NULL DEFAULT 'garmin',
    source_id      TEXT        NOT NULL,
    raw_json       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    imported_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS blood_pressure_local_idx ON qbot_v2.blood_pressure (measured_local);

CREATE TABLE IF NOT EXISTS qbot_v2.ecg_recording (
    id             BIGSERIAL PRIMARY KEY,
    detail_id      TEXT        NOT NULL UNIQUE,
    started_at     TIMESTAMPTZ,
    started_local  TIMESTAMP,
    classification TEXT,
    hr_avg         SMALLINT,
    rmssd_hrv      REAL,
    symptoms       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    device         TEXT,
    raw_json       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    imported_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ecg_recording_local_idx ON qbot_v2.ecg_recording (started_local);

-- Tetno przy stalej mocy: srednie HR w sekundach z moca 140-180 W, od 15. do 120. minuty jazdy.
CREATE TABLE IF NOT EXISTS qbot_v2.hr_at_power (
    external_id  TEXT PRIMARY KEY,
    ride_date    DATE        NOT NULL,
    band_lo_w    SMALLINT    NOT NULL,
    band_hi_w    SMALLINT    NOT NULL,
    sec          INTEGER     NOT NULL,
    hr_avg       REAL,
    power_avg    REAL,
    temp_avg     REAL,
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hr_at_power_date_idx ON qbot_v2.hr_at_power (ride_date);
