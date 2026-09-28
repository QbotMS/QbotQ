-- 2026-09-28: usuniecie wpisu Kalendarza czysci wszystko, co od niego zalezy (wczesniej zostawal plan obciazenia
-- z planera wyprawy w planned_load_daily - np. 3.10 wyprawa 339 km / XSS 908 po usunietym wydarzeniu zawyzala
-- prognoze formy). calendar_day_route mial juz FK; dokladamy ON DELETE CASCADE dla pozostalych tabel z entry_id.
BEGIN;
DELETE FROM qbot_v2.planned_load_daily p
 WHERE p.entry_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM qbot_v2.calendar_entry e WHERE e.id = p.entry_id);
DELETE FROM qbot_v2.report_schedule s
 WHERE s.entry_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM qbot_v2.calendar_entry e WHERE e.id = s.entry_id);
DELETE FROM qbot_v2.calendar_reminder_fired f
 WHERE f.entry_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM qbot_v2.calendar_entry e WHERE e.id = f.entry_id);
ALTER TABLE qbot_v2.planned_load_daily
  ADD CONSTRAINT planned_load_daily_entry_fk FOREIGN KEY (entry_id) REFERENCES qbot_v2.calendar_entry(id) ON DELETE CASCADE;
ALTER TABLE qbot_v2.report_schedule
  ADD CONSTRAINT report_schedule_entry_fk FOREIGN KEY (entry_id) REFERENCES qbot_v2.calendar_entry(id) ON DELETE CASCADE;
ALTER TABLE qbot_v2.calendar_reminder_fired
  ADD CONSTRAINT calendar_reminder_fired_entry_fk FOREIGN KEY (entry_id) REFERENCES qbot_v2.calendar_entry(id) ON DELETE CASCADE;
COMMIT;
