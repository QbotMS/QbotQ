-- TRENER v10 (2026-10-03): zapisany zestaw silowy z bazy cwiczen (qbot_trener_sila.workout_for).
-- Jeden zestaw na (uzytkownik, dzien, sport); sig = okres|czas|minimum|pominiete partie - zmiana podpisu = nowe losowanie.
CREATE TABLE IF NOT EXISTS qbot_v2.trainer_workout (
    username    text        NOT NULL,
    day         date        NOT NULL,
    sport       text        NOT NULL,
    sig         text        NOT NULL,
    data        jsonb       NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (username, day, sport)
);
