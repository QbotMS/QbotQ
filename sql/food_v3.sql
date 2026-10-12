-- Jedzenie v3 (2026-10-12): zalecenia AI na stronie Jedzenie -> Analiza (jeden zapis na dzien).
CREATE TABLE IF NOT EXISTS qbot_v2.food_analysis (day date PRIMARY KEY, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
