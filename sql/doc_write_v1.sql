CREATE TABLE IF NOT EXISTS qbot_doc_write_audit (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    action_type TEXT NOT NULL,
    target_document TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    backup_path TEXT,
    payload_hash TEXT,
    result_json JSONB,
    source TEXT DEFAULT 'chatgpt_mcp'
);

CREATE INDEX IF NOT EXISTS idx_qbot_doc_write_audit_idem ON qbot_doc_write_audit (idempotency_key);
CREATE INDEX IF NOT EXISTS idx_qbot_doc_write_audit_created_at ON qbot_doc_write_audit (created_at);
