-- [GARMIN-DANE] Etap 5 (2026-10-14): oznaczenia "pobudka przed budzikiem" (przycisk w porannej wiadomosci).
-- Idempotentne. Aplikowane: .venv/bin/python3 -c ... przez fitmodel.sleep_target.ensure_schema (patrz docs/GARMIN_DANE.md)
CREATE TABLE IF NOT EXISTS qbot_v2.sleep_wake_label (
    date        date        PRIMARY KEY,          -- dzien pobudki (= data nocy w qbot_sleep_daily)
    early_wake  boolean     NOT NULL DEFAULT true, -- obudzil sie sam przed budzikiem
    created_at  timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qbot_ro') THEN
        GRANT SELECT ON qbot_v2.sleep_wake_label TO qbot_ro;
    END IF;
END $$;
