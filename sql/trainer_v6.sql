-- TRENER v6: oceny planu przez uzytkownika (1-5 + komentarz). Osobna tabela, bo sesje auto sa przekladane
-- od nowa przy przeliczaniu tygodnia (trainer_session.id sie zmienia) - ocena nie moze zniknac.
-- Klucz: (username, day, sport). exercises = kopia zestawu z chwili oceny (do preferencji cwiczen silowych).
CREATE TABLE IF NOT EXISTS qbot_v2.trainer_rating (
    id          bigserial PRIMARY KEY,
    username    text        NOT NULL,
    day         date        NOT NULL,
    sport       text        NOT NULL,
    session_id  bigint,
    rating      smallint    NOT NULL CHECK (rating BETWEEN 1 AND 5),
    note        text,
    title       text,
    exercises   jsonb,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (username, day, sport)
);
CREATE INDEX IF NOT EXISTS trainer_rating_user_day ON qbot_v2.trainer_rating (username, day DESC);
