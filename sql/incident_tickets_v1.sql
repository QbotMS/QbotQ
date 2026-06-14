-- incident_tickets (PRZEBUDOWA sekcja 4: ticket automatyczny)
-- "kazdy ERROR / zlamany niezmiennik pakuje kontekst do
--  qbot_v2.incident_tickets: zapytanie, intent, traceback, ostatnie
--  linie logow, env. Komenda /incydenty zwraca gotowy prompt do Terminus."
--
-- change_log = pelny audit trail (wszystko). incident_tickets = wyselekcjowany
-- podzbior: problemy wymagajace dzialania (ERROR, zlamany niezmiennik).

CREATE TABLE IF NOT EXISTS qbot_v2.incident_tickets (
    id              bigserial PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    status          text NOT NULL DEFAULT 'open',   -- open|diagnosed|resolved|wontfix
    severity        text NOT NULL DEFAULT 'medium',  -- low|medium|high
    source          text,                            -- 'action_execute'|'invariant'|'manual'|...
    action_type     text,
    intent          text,
    query_text      text,
    summary         text NOT NULL,
    error_text      text,
    traceback       text,
    log_tail        text,
    env_snapshot    jsonb NOT NULL DEFAULT '{}'::jsonb,
    detail_json     jsonb NOT NULL DEFAULT '{}'::jsonb,
    change_log_id   bigint,                          -- powiazanie z change_log
    resolution      text
);

CREATE INDEX IF NOT EXISTS idx_incident_status ON qbot_v2.incident_tickets(status);
CREATE INDEX IF NOT EXISTS idx_incident_created ON qbot_v2.incident_tickets(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incident_severity ON qbot_v2.incident_tickets(severity);
