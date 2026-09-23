-- QBot TRENER v3 (Etap 4): cache wartosci auto liczonych dlugo (pogoda z historii jazd) + wyniki badan.
BEGIN;
SET search_path TO qbot_v2, public;
CREATE TABLE IF NOT EXISTS trainer_auto_cache (
    key          TEXT PRIMARY KEY,
    value        JSONB NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS trainer_lab (
    id          BIGSERIAL PRIMARY KEY,
    username    TEXT NOT NULL,
    day         DATE NOT NULL,
    name        TEXT NOT NULL,
    value       NUMERIC,
    unit        TEXT,
    ref_range   TEXT,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS trainer_lab_user_idx ON trainer_lab (username, day DESC);
COMMIT;
