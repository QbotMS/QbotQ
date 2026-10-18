-- food_v6 (2026-10-17): status 'choice' -- wiadomosc z Telegrama do 15 min po wpisie czeka na wybor
-- "Dopisz do #N" / "Nowy wpis" (przyciski); bez odpowiedzi po 30 min liczy sie jako nowy wpis (retry_pending).
ALTER TABLE qbot_v2.food_entries DROP CONSTRAINT IF EXISTS food_entries_status_check;
ALTER TABLE qbot_v2.food_entries ADD CONSTRAINT food_entries_status_check
  CHECK (status = ANY (ARRAY['new','asking','logged','failed','deleted','not_food','choice']));
