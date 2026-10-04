-- TRENER v9 (2026-10-03): ocena cwiczen - podstawowe / rotacyjne / pomijaj + pierwszenstwo 1-3.
-- trainer_exercise.tier/prio = propozycja (qbot_trener_exercises.PROPOSAL); trainer_exercise_user.tier/prio = ocena uzytkownika
-- (wygrywa z propozycja; NULL = wez propozycje). tier: P = podstawowe, R = rotacyjne, X = pomijaj (silnik nie wybiera).
ALTER TABLE qbot_v2.trainer_exercise ADD COLUMN IF NOT EXISTS tier text NOT NULL DEFAULT 'R';
ALTER TABLE qbot_v2.trainer_exercise ADD COLUMN IF NOT EXISTS prio smallint NOT NULL DEFAULT 0;
ALTER TABLE qbot_v2.trainer_exercise_user ADD COLUMN IF NOT EXISTS tier text;
ALTER TABLE qbot_v2.trainer_exercise_user ADD COLUMN IF NOT EXISTS prio smallint;
DO $$ BEGIN
  ALTER TABLE qbot_v2.trainer_exercise ADD CONSTRAINT trainer_exercise_tier_chk CHECK (tier IN ('P','R','X') AND prio BETWEEN 0 AND 3);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE qbot_v2.trainer_exercise_user ADD CONSTRAINT trainer_exercise_user_tier_chk CHECK ((tier IS NULL OR tier IN ('P','R','X')) AND (prio IS NULL OR prio BETWEEN 0 AND 3));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
