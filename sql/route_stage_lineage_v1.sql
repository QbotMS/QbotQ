-- Planner day routes keep a stable relation to the canonical expedition route.
-- Attraction discovery stays on the parent; day routes read a km slice of it.

BEGIN;

CREATE TABLE IF NOT EXISTS qbot_v2.route_stage_lineage (
    stage_route_base_id BIGINT PRIMARY KEY
        REFERENCES qbot_v2.route_base(route_base_id) ON DELETE CASCADE,
    stage_route_id TEXT NOT NULL,
    parent_route_base_id BIGINT NOT NULL
        REFERENCES qbot_v2.route_base(route_base_id) ON DELETE CASCADE,
    parent_route_id TEXT NOT NULL,
    split_key TEXT NOT NULL,
    day_index INTEGER NOT NULL CHECK (day_index >= 1),
    parent_km_from DOUBLE PRECISION NOT NULL CHECK (parent_km_from >= 0),
    parent_km_to DOUBLE PRECISION NOT NULL CHECK (parent_km_to > parent_km_from),
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_stage_lineage_split_day_uq
        UNIQUE (parent_route_base_id, split_key, day_index)
);

CREATE INDEX IF NOT EXISTS idx_route_stage_lineage_parent
    ON qbot_v2.route_stage_lineage(parent_route_base_id, active);
CREATE INDEX IF NOT EXISTS idx_route_stage_lineage_stage_route_id
    ON qbot_v2.route_stage_lineage(stage_route_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON qbot_v2.route_stage_lineage TO qbot;

COMMIT;
