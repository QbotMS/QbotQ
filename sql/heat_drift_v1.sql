-- [GARMIN-DANE] Etap 7 (2026-10-14): dryf tetna i czas w upale na jazdach > 1,5 h. Idempotentne.
CREATE TABLE IF NOT EXISTS qbot_v2.ride_heat_drift (
    external_id  text        PRIMARY KEY,
    ride_date    date        NOT NULL,
    duration_s   integer,
    drift_pct    double precision,   -- (EF1 - EF2) / EF1 * 100, EF = moc/tetno, polowy jazdy, bez 10 pierwszych min
    hot_min      double precision,   -- minuty z temperatura Karoo >= 25 C
    temp_avg     double precision,
    computed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ride_heat_drift_date ON qbot_v2.ride_heat_drift (ride_date);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qbot_ro') THEN
        GRANT SELECT ON qbot_v2.ride_heat_drift TO qbot_ro;
    END IF;
END $$;
