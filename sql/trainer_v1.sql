-- QBot TRENER v1 (Etap 1: fundament danych)
-- Sekcja TRENER w Formie: cele, wpisy tygodnia (zajete/elastyczne/okna treningu),
-- nadpisania kalibracji, plan sesji dzien po dniu, dziennik zmian (cofanie).
-- Tabele startuja PUSTE - dane wprowadza uzytkownik w UI (decyzja 2026-09-23).
-- Wartosci "auto" kalibracji NIE sa tu trzymane - licza sie na zywo z bazy;
-- trainer_settings trzyma tylko RECZNE nadpisania uzytkownika.
-- Idempotentne (IF NOT EXISTS).

BEGIN;

SET search_path TO qbot_v2, public;

CREATE TABLE IF NOT EXISTS trainer_goal (
    id                BIGSERIAL PRIMARY KEY,
    username          TEXT NOT NULL,
    kind              TEXT NOT NULL CHECK (kind IN ('trip','long_ride','volume','weight','power','habit','other')),
    name              TEXT NOT NULL,
    priority          TEXT NOT NULL DEFAULT 'B' CHECK (priority IN ('A','B','C')),
    date_from         DATE,
    date_to           DATE,
    target            JSONB NOT NULL DEFAULT '{}'::jsonb,
    status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','done','dropped')),
    calendar_entry_id BIGINT,
    note              TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS trainer_goal_user_idx ON trainer_goal (username, status);

-- windows: [{"d":[7 x 0|1|2], "k":"h"|"all"|"var", "a":"HH:MM", "b":"HH:MM", "ac":["rower","sila","wiosl","joga"]}]
--   d: 0=nie, 1=tak, 2=czasem; ac puste = wszystkie aktywnosci (sens tylko dla flex/pref)
-- period:  {"m":"all"} | {"m":"yearly","f":"DD.MM","t":"DD.MM"} | {"m":"once","f":"YYYY-MM-DD","t":"YYYY-MM-DD"}
CREATE TABLE IF NOT EXISTS trainer_rule (
    id          BIGSERIAL PRIMARY KEY,
    username    TEXT NOT NULL,
    icon        TEXT NOT NULL DEFAULT '📌',
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('busy','flex','pref')),
    windows     JSONB NOT NULL DEFAULT '[]'::jsonb,
    period      JSONB NOT NULL DEFAULT '{"m":"all"}'::jsonb,
    max_min     INTEGER,
    note        TEXT,
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    sort        INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS trainer_rule_user_idx ON trainer_rule (username, active);

-- Tylko reczne nadpisania (klucz -> wartosc). Brak klucza = wartosc auto.
CREATE TABLE IF NOT EXISTS trainer_settings (
    username    TEXT PRIMARY KEY,
    overrides   JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trainer_session (
    id                  BIGSERIAL PRIMARY KEY,
    username            TEXT NOT NULL,
    day                 DATE NOT NULL,
    sport               TEXT NOT NULL CHECK (sport IN ('rower','sila','wiosl','joga')),
    name                TEXT NOT NULL,
    start_time          TIME,
    dur_min             INTEGER NOT NULL CHECK (dur_min > 0 AND dur_min <= 1440),
    min_min             INTEGER CHECK (min_min IS NULL OR (min_min > 0 AND min_min <= 1440)),
    zone                SMALLINT CHECK (zone IS NULL OR zone BETWEEN 1 AND 7),
    xss                 NUMERIC,
    is_long             BOOLEAN NOT NULL DEFAULT FALSE,
    status              TEXT NOT NULL DEFAULT 'plan' CHECK (status IN ('plan','done','skip')),
    cut                 BOOLEAN NOT NULL DEFAULT FALSE,
    source              TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','auto')),
    training_session_id BIGINT,
    garmin_workout_id   TEXT,
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS trainer_session_user_day_idx ON trainer_session (username, day);

CREATE TABLE IF NOT EXISTS trainer_change (
    id          BIGSERIAL PRIMARY KEY,
    username    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    week_start  DATE,
    action      TEXT NOT NULL,
    payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    before      JSONB,
    after       JSONB,
    accepted    BOOLEAN
);
CREATE INDEX IF NOT EXISTS trainer_change_user_idx ON trainer_change (username, created_at DESC);

COMMIT;
