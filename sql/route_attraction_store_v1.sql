BEGIN;

CREATE SCHEMA IF NOT EXISTS qbot_v2;

CREATE TABLE IF NOT EXISTS qbot_v2.route_attraction_run (
    run_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES qbot_v2.route_base(route_base_id) ON DELETE CASCADE,
    route_version_key TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('complete', 'partial', 'failed')),
    published BOOLEAN NOT NULL DEFAULT false,
    result_hash TEXT,
    source_status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS route_attraction_one_published_uq
    ON qbot_v2.route_attraction_run(route_base_id) WHERE published;
CREATE INDEX IF NOT EXISTS route_attraction_run_route_idx
    ON qbot_v2.route_attraction_run(route_base_id, created_at DESC);

CREATE TABLE IF NOT EXISTS qbot_v2.route_attraction_layer (
    attraction_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES qbot_v2.route_attraction_run(run_id) ON DELETE CASCADE,
    route_base_id BIGINT NOT NULL REFERENCES qbot_v2.route_base(route_base_id) ON DELETE CASCADE,
    candidate_key TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    category_label TEXT,
    km_on_route DOUBLE PRECISION NOT NULL,
    distance_from_route_m DOUBLE PRECISION,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    visit_min INTEGER,
    score DOUBLE PRECISION NOT NULL,
    selection_score DOUBLE PRECISION,
    candidate_rank INTEGER NOT NULL,
    is_recommended BOOLEAN NOT NULL DEFAULT false,
    recommended_rank INTEGER,
    why TEXT,
    extract TEXT,
    wiki_url TEXT,
    wikidata_id TEXT,
    image_url TEXT,
    rating DOUBLE PRECISION,
    rating_count INTEGER,
    components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    osm_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    nearby_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_attraction_layer_run_key_uq UNIQUE (run_id, candidate_key)
);

CREATE INDEX IF NOT EXISTS route_attraction_layer_route_km_idx
    ON qbot_v2.route_attraction_layer(route_base_id, km_on_route);
CREATE INDEX IF NOT EXISTS route_attraction_layer_run_rank_idx
    ON qbot_v2.route_attraction_layer(run_id, candidate_rank);
CREATE INDEX IF NOT EXISTS route_attraction_layer_recommended_idx
    ON qbot_v2.route_attraction_layer(run_id, recommended_rank) WHERE is_recommended;

COMMIT;
