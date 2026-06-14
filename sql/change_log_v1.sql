-- core change_log table (PRZEBUDOWA sekcja 4: rejestr zmian)
-- "każdy zaaplikowany patch zapisuje wpis (data, plik, przyczyna, ticket)
--  do qbot_v2.change_log. Koniec z patchami o których nikt nie pamięta."
-- Rozszerzone tez na action_execute writes (kazdy write z GPT/Planner).

CREATE TABLE IF NOT EXISTS qbot_v2.change_log (
    id              bigserial PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    kind            text NOT NULL,              -- 'action_execute' | 'patch' | 'incident'
    action_type     text,                       -- dla kind='action_execute'
    status          text,                       -- OK|ERROR|PARTIAL|DUPLICATE|DRY_RUN|BLOCKED...
    idempotency_key text,
    source          text,                       -- 'mcp'|'cli'|'planner'|...
    entity_ref      text,                       -- np. 'intake_logs:94', 'calendar_events:12'
    summary         text,
    detail_json     jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_change_log_created ON qbot_v2.change_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_change_log_kind ON qbot_v2.change_log(kind);
CREATE INDEX IF NOT EXISTS idx_change_log_action ON qbot_v2.change_log(action_type);
CREATE INDEX IF NOT EXISTS idx_change_log_status ON qbot_v2.change_log(status);
