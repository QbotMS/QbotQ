-- Qbot LLM Planner v1 — plan storage, artifacts, memory
-- Run idempotently via init_db() or manually

CREATE TABLE IF NOT EXISTS qbot_plans (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    user_query TEXT NOT NULL,
    planner_source TEXT DEFAULT 'rule_fallback',
    proposed_plan JSONB,
    validated_plan JSONB,
    policy_status TEXT DEFAULT 'PENDING',
    execution_status TEXT DEFAULT 'PENDING',
    requires_approval BOOLEAN DEFAULT FALSE,
    blocked_reasons JSONB,
    executed_at TIMESTAMPTZ,
    tool_results JSONB,
    answer_synthesized TEXT
);

CREATE TABLE IF NOT EXISTS qbot_artifacts (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    artifact_type TEXT NOT NULL DEFAULT 'report',
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    source_plan_id INTEGER REFERENCES qbot_plans(id),
    tags JSONB DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS qbot_memory (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    memory_type TEXT NOT NULL DEFAULT 'note',
    key TEXT NOT NULL UNIQUE,
    value JSONB NOT NULL DEFAULT '{}',
    source TEXT,
    confidence TEXT DEFAULT 'medium'
);
