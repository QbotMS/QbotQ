-- Jedzenie v2 (2026-10-12): okno zywieniowe 10:00-20:00 (pas na zaufaniu) + pora jedzenia z wpisu.
ALTER TABLE qbot_v2.food_day ADD COLUMN IF NOT EXISTS window_ok boolean;          -- klik: true dotrzymane / false zlamane
ALTER TABLE qbot_v2.food_day ADD COLUMN IF NOT EXISTS window_set_at timestamptz;
ALTER TABLE qbot_v2.food_entries ADD COLUMN IF NOT EXISTS eaten_time time;        -- pora podana we wpisie (AI), np. 'o 21:30'
