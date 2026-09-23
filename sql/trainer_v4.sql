-- QBot TRENER v4 (Etap 5): dziennik wyslanych powiadomien Telegram (deduplikacja ticka co 15 min).
BEGIN;
SET search_path TO qbot_v2, public;
CREATE TABLE IF NOT EXISTS trainer_notify_log (
    key       TEXT PRIMARY KEY,          -- plan:2026-W40 / review:2026-W40 / day:2026-09-28 / pre:<session_id>
    username  TEXT NOT NULL,
    sent_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ok        BOOLEAN NOT NULL,
    detail    TEXT
);
COMMIT;
