-- Centrum powiadomien (dzwonek w menu) - 2026-10-08. Logika: qbot_notif.py
CREATE TABLE IF NOT EXISTS qbot_v2.notif (
    id          BIGSERIAL PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT,
    url         TEXT,
    action      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at     TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS notif_active_idx ON qbot_v2.notif (resolved_at, updated_at DESC);
