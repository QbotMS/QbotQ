-- Serce AI (2026-10-13): pamiec komentarzy AI do EKG i raportow po serii (qbot_heart_ai.py). docs/SERCE.md
CREATE TABLE IF NOT EXISTS qbot_v2.heart_ai (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
