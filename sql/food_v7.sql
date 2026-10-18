-- 2026-10-18: album zdjec z Telegrama (media_group_id) = JEDEN wpis jedzenia; lista zdjec wpisu.
ALTER TABLE qbot_v2.food_entries ADD COLUMN IF NOT EXISTS media_group_id text;
ALTER TABLE qbot_v2.food_entries ADD COLUMN IF NOT EXISTS photo_file_ids jsonb;
CREATE INDEX IF NOT EXISTS food_entries_mgid_idx ON qbot_v2.food_entries (media_group_id) WHERE media_group_id IS NOT NULL;
