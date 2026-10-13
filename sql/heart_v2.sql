-- EKG szczegoly (2026-10-13): surowy przebieg i analiza uderzen (qbot_ecg.py). docs/SERCE.md
ALTER TABLE qbot_v2.ecg_recording ADD COLUMN IF NOT EXISTS sample_rate REAL;
ALTER TABLE qbot_v2.ecg_recording ADD COLUMN IF NOT EXISTS lead TEXT;
ALTER TABLE qbot_v2.ecg_recording ADD COLUMN IF NOT EXISTS samples JSONB;
ALTER TABLE qbot_v2.ecg_recording ADD COLUMN IF NOT EXISTS analysis JSONB;
