-- Jedzenie v5 (2026-10-12): zalecenia AI tygodnia (Analiza), jeden wpis na tydzien (poniedzialek).
CREATE TABLE IF NOT EXISTS qbot_v2.food_week_ai (week date PRIMARY KEY, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
