-- TRENER v8 (2026-10-02): baza cwiczen (katalog 100, zrodlo: qbot_trener_exercises.CATALOG -> seed()).
-- Grafiki poza baza: /opt/qbot/web/public/cwiczenia/<key>.webp + manifest.json.
-- wclass: C = 10-12 kg, S = 6-8 kg, L = 2-4 kg, 0 = bez hantli (do ukladania treningu w bloki ciezaru).
CREATE TABLE IF NOT EXISTS qbot_v2.trainer_exercise (
    key         text PRIMARY KEY,
    name        text        NOT NULL,
    grp         text        NOT NULL,
    level       smallint    NOT NULL CHECK (level BETWEEN 1 AND 3),
    wclass      text        NOT NULL CHECK (wclass IN ('C','S','L','0')),
    equip       text[]      NOT NULL DEFAULT '{}',
    unilateral  boolean     NOT NULL DEFAULT false,
    dose        text,
    muscles     text,
    warmup      boolean     NOT NULL DEFAULT false,
    img_desc    text,
    steps       jsonb,
    ok          text,
    bad         text,
    batch       smallint,
    active      boolean     NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS trainer_exercise_grp ON qbot_v2.trainer_exercise (grp, level);
-- Twoje ciezary w cwiczeniach (podpowiedz na sciadze; uzupelniane pozniej)
CREATE TABLE IF NOT EXISTS qbot_v2.trainer_exercise_user (
    username    text        NOT NULL,
    key         text        NOT NULL REFERENCES qbot_v2.trainer_exercise(key),
    weight_kg   numeric(4,1),
    note        text,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (username, key)
);
