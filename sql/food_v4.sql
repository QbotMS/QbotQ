-- Jedzenie v4 (2026-10-12): obwody ciala (talia obowiazkowa, reszta opcjonalna). Wpis: Jedzenie -> Bilans i waga -> Obwody.
CREATE TABLE IF NOT EXISTS qbot_v2.body_circumference (
  date date PRIMARY KEY,
  waist_cm numeric(5,1), hips_cm numeric(5,1), chest_cm numeric(5,1), thigh_cm numeric(5,1), arm_cm numeric(5,1), neck_cm numeric(5,1),
  note text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
