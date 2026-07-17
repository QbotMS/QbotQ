-- Fix: refresh_day_flags() odwolywala sie do usunietej tabeli qbot_v2.calendar_events
-- po refaktorze kalendarza z 2026-07-16 (calendar_events -> calendar_entry, kolumna `day`).
-- Skutek: KAZDY zapis do intake_logs / energy_daily / sleep_daily / training_sessions /
-- wellness_daily wywalal sie (trigger rzucal UndefinedTable, transakcja rollback) = WRITE_INCONSISTENT.
-- Naprawa: has_calendar wskazuje teraz qbot_v2.calendar_entry(day). Wdrozone na zywo 2026-07-17.
BEGIN;
CREATE OR REPLACE FUNCTION qbot_v2.refresh_day_flags()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
        DECLARE d date;
        BEGIN
            IF TG_TABLE_NAME = 'intake_items' THEN
                SELECT il.date INTO d
                FROM qbot_v2.intake_logs il
                WHERE il.id = COALESCE(NEW.intake_log_id, OLD.intake_log_id);
            ELSE
                d := COALESCE(NEW.date, OLD.date);
            END IF;
            IF d IS NOT NULL THEN
                INSERT INTO qbot_v2.days(date) VALUES (d) ON CONFLICT DO NOTHING;
                UPDATE qbot_v2.days SET
                    has_intake      = EXISTS(SELECT 1 FROM qbot_v2.intake_logs WHERE date = d),
                    has_expenditure = EXISTS(SELECT 1 FROM qbot_v2.energy_daily WHERE date = d),
                    has_sleep       = EXISTS(SELECT 1 FROM qbot_v2.sleep_daily WHERE date = d),
                    has_training    = EXISTS(SELECT 1 FROM qbot_v2.training_sessions WHERE date = d),
                    has_wellness    = EXISTS(SELECT 1 FROM qbot_v2.wellness_daily WHERE date = d),
                    has_calendar    = EXISTS(SELECT 1 FROM qbot_v2.calendar_entry WHERE day = d),
                    updated_at      = now()
                WHERE date = d;
            END IF;
            RETURN NULL;
        END;
        $function$;
COMMIT;
