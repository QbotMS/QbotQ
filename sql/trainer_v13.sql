-- TRENER v13 (2026-10-23): wysylka sesji silowej Trenera do Garmin Connect (trening + kalendarz).
-- Jedna linia na dzien/sport: ostatnio wyslany trening (do podmiany przy zmianie sesji).
CREATE TABLE IF NOT EXISTS qbot_v2.trainer_garmin_push (
  username    text NOT NULL,
  day         date NOT NULL,
  sport       text NOT NULL,
  workout_id  text,
  sig         text,              -- podpis sesji (zmiana -> nowa wysylka)
  status      text NOT NULL,     -- ok | blad
  info        text,
  pushed_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (username, day, sport)
);
