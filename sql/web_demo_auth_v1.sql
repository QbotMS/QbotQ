-- web_demo_auth_v1 (2026-10-07): tymczasowy dostep demo do qbot-web przez QR.
-- Zadanie autoryzacji urzadzenia (QR, ~2 min) -> zatwierdzenie na telefonie wlasciciela
-- -> jednorazowy odbior -> sesja demo (1 h, bez przedluzania, tylko odczyt).
-- Surowe sekrety NIE trafiaja do bazy (tylko sha256).

CREATE TABLE IF NOT EXISTS qbot_v2.web_device_auth_requests (
    id                  text PRIMARY KEY,                 -- losowy identyfikator (w QR)
    browser_secret_hash text NOT NULL,                    -- sha256 sekretu z ciasteczka komputera
    user_code           text NOT NULL,                    -- kod porownawczy pokazywany na obu ekranach
    status              text NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING','APPROVED','CONSUMED','DENIED','EXPIRED')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    expires_at          timestamptz NOT NULL,
    approved_by         text,
    approved_at         timestamptz,
    scope               text,
    session_ttl_s       integer CHECK (session_ttl_s IS NULL OR session_ttl_s BETWEEN 60 AND 14400),
    consumed_at         timestamptz,
    session_id          bigint,
    device_info         text
);
CREATE INDEX IF NOT EXISTS web_device_auth_requests_pending_idx
    ON qbot_v2.web_device_auth_requests (expires_at) WHERE status = 'PENDING';

CREATE TABLE IF NOT EXISTS qbot_v2.web_sessions (
    id          bigserial PRIMARY KEY,
    token_hash  text NOT NULL UNIQUE,                     -- sha256 tokenu z ciasteczka qbot_demo
    owner       text NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('demo')),
    scope       text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,                     -- bezwzgledny termin, bez przedluzania
    revoked_at  timestamptz,
    request_id  text UNIQUE REFERENCES qbot_v2.web_device_auth_requests(id),
    device_info text
);
CREATE INDEX IF NOT EXISTS web_sessions_owner_active_idx
    ON qbot_v2.web_sessions (owner, expires_at) WHERE revoked_at IS NULL;
