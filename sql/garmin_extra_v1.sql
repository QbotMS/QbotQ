-- [GARMIN-DANE] Etap 1 (2026-10-14): pelne dane snu/HRV z Garmina + pola dodatkowe.
-- Idempotentne. Aplikowane przez: .venv/bin/python3 scripts/garmin_extra_backfill.py --migrate-only
-- Dok.: docs/GARMIN_DANE.md

-- Pelna odpowiedz Garmina (kind: 'sleep' = get_sleep_data, 'hrv' = get_hrv_data).
CREATE TABLE IF NOT EXISTS qbot_v2.garmin_daily_raw (
    date        date        NOT NULL,
    kind        text        NOT NULL,
    payload     jsonb       NOT NULL,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (date, kind)
);

-- Pola wyciagniete z pelnej odpowiedzi (wiersz source='garmin').
ALTER TABLE qbot_v2.qbot_wellness_daily
    ADD COLUMN IF NOT EXISTS skin_temp_dev_c          double precision,  -- sleep.avgSkinTempDeviationC (odchylenie od normy Garmina)
    ADD COLUMN IF NOT EXISTS sleep_need_min           integer,           -- sleep.dailySleepDTO.sleepNeed.actual (potrzeba na TE noc)
    ADD COLUMN IF NOT EXISTS sleep_need_baseline_min  integer,           -- sleepNeed.baseline
    ADD COLUMN IF NOT EXISTS sleep_need_feedback      text,              -- sleepNeed.feedback
    ADD COLUMN IF NOT EXISTS next_sleep_need_min      integer,           -- nextSleepNeed.actual (potrzeba na NASTEPNA noc -> zalecenie wieczorne)
    ADD COLUMN IF NOT EXISTS next_sleep_need_feedback text,              -- nextSleepNeed.feedback
    ADD COLUMN IF NOT EXISTS garmin_hrv_status        text,              -- hrv.hrvSummary.status (tylko do porownan; status wlasny liczy QBot)
    ADD COLUMN IF NOT EXISTS hrv_weekly_avg           double precision,  -- hrvSummary.weeklyAvg
    ADD COLUMN IF NOT EXISTS hrv_balanced_low         double precision,  -- hrvSummary.baseline.balancedLow
    ADD COLUMN IF NOT EXISTS hrv_balanced_high        double precision;  -- hrvSummary.baseline.balancedUpper

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qbot_ro') THEN
        GRANT SELECT ON qbot_v2.garmin_daily_raw TO qbot_ro;
    END IF;
END $$;
