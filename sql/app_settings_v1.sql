-- Ustawienia serwisu (SETUP), 2026-10-08. Pierwszy klucz: notif.enabled (qbot_notif.SOURCES)
CREATE TABLE IF NOT EXISTS qbot_v2.app_settings (key TEXT PRIMARY KEY, value JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
