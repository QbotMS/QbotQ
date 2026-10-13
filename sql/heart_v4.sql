-- SpO2 nocne (2026-10-13): srednia i najnizsza saturacja z Garmina (get_spo2_data). docs/SERCE.md
CREATE TABLE IF NOT EXISTS qbot_v2.spo2_daily (
    day             DATE PRIMARY KEY,
    avg_spo2        REAL,
    sleep_avg_spo2  REAL,
    lowest_spo2     REAL,
    raw_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
