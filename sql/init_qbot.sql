CREATE TABLE IF NOT EXISTS tool_calls (
    id         SERIAL PRIMARY KEY,
    tool       TEXT NOT NULL,
    args       JSONB DEFAULT '{}'::jsonb,
    result     JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls (tool);
CREATE INDEX IF NOT EXISTS idx_tool_calls_created_at ON tool_calls (created_at);
