-- TRENER v11 (2026-10-06): wykonanie vs plan. Realny czas i obciazenie dopasowanej jazdy (XSS ModelQ, zapas TSS Garmina)
-- + znacznik, ze odchylke juz rozpatrzono (automatyczna reakcja planu tylko raz na sesje).
ALTER TABLE qbot_v2.trainer_session
  ADD COLUMN IF NOT EXISTS real_min integer,
  ADD COLUMN IF NOT EXISTS real_xss numeric,
  ADD COLUMN IF NOT EXISTS real_src text,
  ADD COLUMN IF NOT EXISTS adapt_at timestamptz;
