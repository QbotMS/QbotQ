-- QBot TRENER v5: wyciszone ostrzezenia per sesja ("rozumiem, zostaw").
BEGIN;
SET search_path TO qbot_v2, public;
ALTER TABLE trainer_session ADD COLUMN IF NOT EXISTS acks JSONB NOT NULL DEFAULT '[]'::jsonb;
COMMIT;
