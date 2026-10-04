-- TRENER v7 (2026-10-02): opcje sesji (np. sila bez wybranych partii) - prosba do AI o zmiane planu.
-- opts = {"skip_groups": ["nogi", ...]}; NULL = brak opcji.
ALTER TABLE qbot_v2.trainer_session ADD COLUMN IF NOT EXISTS opts jsonb;
