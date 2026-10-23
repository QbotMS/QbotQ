-- TRENER v12 (2026-10-23): katalog cwiczen Garmina (jedna baza cwiczen QBota).
-- Zrodlo: biblioteka garminconnect (1527 cwiczen) + klasyfikacja domowej silowni:
--   sql/garmin_exercises_v1.csv       - 663 cwiczenia sprawdzone przez GPT (2 rundy) i walidowane
--   sql/garmin_exercises_klasy_v1.csv - reguly sprzetu dla calego katalogu (fallback)
-- Import: scripts/garmin_catalog_import.py (idempotentny, UPSERT).
-- status: ok = da sie dzis w domu; uspione = po zakupie sprzetu (sztanga/talerz/kettlebell/drazek); off = nie dla domu.
CREATE TABLE IF NOT EXISTS qbot_v2.garmin_exercise (
  kod          text PRIMARY KEY,            -- CATEGORY/EXERCISE (klucz do wysylki treningu na Garmina)
  category     text NOT NULL,
  exercise     text NOT NULL,
  name_en      text NOT NULL,
  name_pl      text,
  sprzet       text[] NOT NULL DEFAULT '{}',
  status       text NOT NULL,
  partia       text,
  dup_of       text,                         -- w praktyce to samo co inne cwiczenie
  weighted_of  text,                         -- wariant "Weighted ..." -> cwiczenie bazowe
  zrodlo       text NOT NULL,                -- gpt | reczne | reguly | wariant
  uwagi        text,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT garmin_exercise_status_chk CHECK (status IN ('ok','uspione','off'))
);
CREATE INDEX IF NOT EXISTS garmin_exercise_status_idx ON qbot_v2.garmin_exercise (status);

-- powiazanie 100 cwiczen Trenera (z grafikami) z katalogiem Garmina
ALTER TABLE qbot_v2.trainer_exercise ADD COLUMN IF NOT EXISTS garmin_kod text;
