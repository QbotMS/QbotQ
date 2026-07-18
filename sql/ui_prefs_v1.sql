-- QBot UI preferences store v1
-- Per-uzytkownik zapis ustawien interfejsu (klucz -> dowolny JSON).
-- Zrodlo prawdy dla konfiguracji, ktora ma "isc za kontem" (ten sam widok na
-- kazdym urzadzeniu/przegladarce), zamiast tylko localStorage.
-- Pierwszy konsument: zakladka DZIS (pref_key='dzis' -> {hero:bool, keys:[...]}).
-- Uzytkownik brany z ciasteczka sesji webauth (username). Endpointy:
--   GET  /api/prefs?key=<k>       -> {key, value|null}
--   POST /api/prefs {key, value}  -> upsert
-- Ogolne z zalozenia: kolejne ustawienia dokladamy jako nowe pref_key,
-- bez zmian schematu.

BEGIN;

SET search_path TO qbot_v2, public;

CREATE TABLE IF NOT EXISTS ui_prefs (
    username   TEXT NOT NULL,
    pref_key   TEXT NOT NULL,
    value      JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (username, pref_key)
);

COMMIT;
