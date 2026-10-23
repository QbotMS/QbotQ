-- TRENER v14 (2026-10-23): planer silowni AI - ustawienia uzytkownika (sprzet, akcenty, wskazowki dla AI).
-- equipment: [{id, n (nazwa), s (szczegoly), kind (hantle|lawka|mata|guma_mocna|guma_lekka|mini|sztanga|talerz|kettlebell|drazek|inne), on}]
-- accents:   ["biceps", ...]   (klucze z qbot_trener_sila_ai.ACCENTS)
-- tips:      ["tekst", ...]    (wskazowki - twarde zasady dla AI)
-- derived:   {hash, exclude: [klucze cwiczen], why: {klucz: powod}} - skutek wskazowek wyliczony przez AI (cache)
CREATE TABLE IF NOT EXISTS qbot_v2.trainer_sila_prefs (
  username    text PRIMARY KEY,
  equipment   jsonb NOT NULL DEFAULT '[]'::jsonb,
  accents     jsonb NOT NULL DEFAULT '[]'::jsonb,
  tips        jsonb NOT NULL DEFAULT '[]'::jsonb,
  derived     jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
