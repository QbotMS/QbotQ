-- TRENER v15 (2026-10-23): joga w Down Dog - opcje aplikacji pobierane automatycznie + przepis AI przy sesji jogi.
-- Opcje: manifest Down Dog (https://www.downdogapp.com/json/manifest?version=...&language=pl, bez logowania).
-- Przepis sesji: qbot_v2.trainer_workout (sport='joga', data.recipe / data.alts / data.uwaga), jak zestaw silowy.
CREATE TABLE IF NOT EXISTS qbot_v2.downdog_options (
  id          integer PRIMARY KEY DEFAULT 1,
  version     text,                 -- wersja aplikacji, z ktora serwer oddal manifest
  fetched_at  timestamptz,          -- ostatnie udane pobranie
  checked_at  timestamptz,          -- ostatnia proba
  hash        text,                 -- skrot listy opcji (zmiana = nowosci)
  data        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {types: [{id, label, help, boosts: [..], settings: {nazwa: [opcje]}}]}
  error       text,
  CONSTRAINT downdog_options_one CHECK (id = 1)
);
