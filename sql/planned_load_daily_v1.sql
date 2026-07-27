-- QBot planned load (planowane obciazenie) daily store v1
-- Planowane obciazenie treningowe (XSS) na konkretny dzien, ZANIM jazda sie odbedzie.
-- Trzymane OSOBNO od fitmodel_daily (fakty) - planowane nie miesza sie z faktycznym,
-- zeby model dnia mogl "widziec" nadchodzace dni bez skazenia historii.
-- Pierwsze zrodlo (source='planer_wyprawy'): podzial wyprawy z Planera na etapy/dni.
-- XSS liczony fizyka trasy (_planer_stage_xss -> route_xss_phys), wiec spojny z raportem/planerem.
-- Pole 'source' zostawione na przyszle zrodla (reczne, tygodniowy plan, itp.).
-- Konsumenci: Doradca formy (_forma_planned_events) + /api/calendar (badge dnia).

BEGIN;

SET search_path TO qbot_v2, public;

CREATE TABLE IF NOT EXISTS planned_load_daily (
    day        DATE NOT NULL,
    source     TEXT NOT NULL DEFAULT 'planer_wyprawy',
    entry_id   BIGINT,
    route_id   TEXT,
    stage_idx  INTEGER,
    xss        NUMERIC,
    dist_km    NUMERIC,
    moving_h   NUMERIC,
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, source)
);

CREATE INDEX IF NOT EXISTS planned_load_daily_entry_idx
    ON planned_load_daily (entry_id);

CREATE INDEX IF NOT EXISTS planned_load_daily_day_idx
    ON planned_load_daily (day);

COMMIT;
