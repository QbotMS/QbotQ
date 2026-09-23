-- QBot TRENER v2 (Etap 3): stan dnia "brak czasu" (short) niezalezny od Kalendarza.
-- REST DAY / choroba / delegacja ida do calendar_entry (istniejaca konwencja: kind='event' event_type rest/delegacja,
-- kind='illness'). "Brak czasu" nie jest wydarzeniem kalendarzowym -> osobna tabela.
BEGIN;
SET search_path TO qbot_v2, public;
CREATE TABLE IF NOT EXISTS trainer_day (
    username    TEXT NOT NULL,
    day         DATE NOT NULL,
    state       TEXT NOT NULL CHECK (state IN ('short')),
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (username, day)
);
COMMIT;
