-- QBot route base / axis / analysis run store v1
-- Phase 2A: new DB contracts only, legacy/source tables remain read-only sources.

BEGIN;

CREATE TABLE IF NOT EXISTS route_base (
    route_base_id BIGSERIAL PRIMARY KEY,
    route_id TEXT NOT NULL,
    route_artifact_id INTEGER,
    route_parse_result_id INTEGER,
    route_version_key TEXT NOT NULL,
    route_modified_at TIMESTAMPTZ,
    route_updated_at TIMESTAMPTZ,
    geometry_hash TEXT,
    sha256 TEXT,
    distance_m DOUBLE PRECISION,
    track_points INTEGER,
    source_provider TEXT,
    source_path TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    source_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_base_uq UNIQUE (route_id, route_version_key),
    CONSTRAINT route_base_status_chk CHECK (status IN ('active', 'stale', 'disabled', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_route_base_route_id ON route_base(route_id);
CREATE INDEX IF NOT EXISTS idx_route_base_route_version_key ON route_base(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_base_route_artifact_id ON route_base(route_artifact_id);
CREATE INDEX IF NOT EXISTS idx_route_base_status ON route_base(status);
CREATE INDEX IF NOT EXISTS idx_route_base_updated_at ON route_base(updated_at);

CREATE TABLE IF NOT EXISTS route_axis_segments (
    route_axis_segment_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    route_version_key TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    km_from NUMERIC(8,3) NOT NULL,
    km_to NUMERIC(8,3) NOT NULL,
    distance_m DOUBLE PRECISION NOT NULL,
    segment_geojson JSONB NOT NULL,
    elevation_start_m DOUBLE PRECISION,
    elevation_end_m DOUBLE PRECISION,
    elevation_gain_m DOUBLE PRECISION,
    elevation_loss_m DOUBLE PRECISION,
    avg_grade_pct DOUBLE PRECISION,
    source_quality TEXT NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_axis_segments_uq UNIQUE (route_base_id, segment_index)
);

CREATE INDEX IF NOT EXISTS idx_route_axis_segments_base_id ON route_axis_segments(route_base_id);
CREATE INDEX IF NOT EXISTS idx_route_axis_segments_version_key ON route_axis_segments(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_axis_segments_km_from ON route_axis_segments(km_from);
CREATE INDEX IF NOT EXISTS idx_route_axis_segments_km_to ON route_axis_segments(km_to);

CREATE TABLE IF NOT EXISTS route_surface_layer (
    route_surface_layer_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    route_version_key TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    surface TEXT,
    highway TEXT,
    tracktype TEXT,
    source TEXT NOT NULL,
    confidence TEXT,
    coverage_status TEXT NOT NULL DEFAULT 'unknown',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    surface_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_surface_layer_uq UNIQUE (route_base_id, segment_index)
);

CREATE INDEX IF NOT EXISTS idx_route_surface_layer_base_id ON route_surface_layer(route_base_id);
CREATE INDEX IF NOT EXISTS idx_route_surface_layer_version_key ON route_surface_layer(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_surface_layer_coverage_status ON route_surface_layer(coverage_status);
CREATE INDEX IF NOT EXISTS idx_route_surface_layer_source ON route_surface_layer(source);

CREATE TABLE IF NOT EXISTS route_landcover_layer (
    route_landcover_layer_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    route_version_key TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    landuse TEXT,
    osm_natural TEXT,
    forest_wood_context TEXT,
    building_context TEXT,
    water_context TEXT,
    source TEXT NOT NULL,
    confidence TEXT,
    coverage_status TEXT NOT NULL DEFAULT 'unknown',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    landcover_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_landcover_layer_uq UNIQUE (route_base_id, segment_index)
);

CREATE INDEX IF NOT EXISTS idx_route_landcover_layer_base_id ON route_landcover_layer(route_base_id);
CREATE INDEX IF NOT EXISTS idx_route_landcover_layer_version_key ON route_landcover_layer(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_landcover_layer_coverage_status ON route_landcover_layer(coverage_status);
CREATE INDEX IF NOT EXISTS idx_route_landcover_layer_source ON route_landcover_layer(source);

CREATE TABLE IF NOT EXISTS route_poi_layer (
    route_poi_layer_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    route_version_key TEXT NOT NULL,
    poi_key TEXT NOT NULL,
    poi_id TEXT,
    source_place_id TEXT,
    provider TEXT NOT NULL,
    name TEXT,
    category TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    km_on_route DOUBLE PRECISION,
    distance_from_route_m DOUBLE PRECISION,
    opening_hours TEXT,
    opening_hours_fetched_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    confidence TEXT,
    validity_hint TEXT,
    stale_after TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active',
    poi_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_poi_layer_uq UNIQUE (route_base_id, poi_key),
    CONSTRAINT route_poi_layer_status_chk CHECK (status IN ('active', 'stale', 'disabled'))
);

CREATE INDEX IF NOT EXISTS idx_route_poi_layer_base_id ON route_poi_layer(route_base_id);
CREATE INDEX IF NOT EXISTS idx_route_poi_layer_version_key ON route_poi_layer(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_poi_layer_provider ON route_poi_layer(provider);
CREATE INDEX IF NOT EXISTS idx_route_poi_layer_category ON route_poi_layer(category);
CREATE INDEX IF NOT EXISTS idx_route_poi_layer_km_on_route ON route_poi_layer(km_on_route);
CREATE INDEX IF NOT EXISTS idx_route_poi_layer_stale_after ON route_poi_layer(stale_after);

CREATE TABLE IF NOT EXISTS route_precompute_jobs (
    job_id BIGSERIAL PRIMARY KEY,
    route_id TEXT NOT NULL,
    route_artifact_id INTEGER,
    route_version_key TEXT NOT NULL,
    route_base_id BIGINT REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    trigger_source TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error TEXT,
    layer_status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_precompute_jobs_idem_uq UNIQUE (idempotency_key),
    CONSTRAINT route_precompute_jobs_status_chk CHECK (status IN ('pending', 'running', 'complete', 'failed', 'partial'))
);

CREATE INDEX IF NOT EXISTS idx_route_precompute_jobs_route_id ON route_precompute_jobs(route_id);
CREATE INDEX IF NOT EXISTS idx_route_precompute_jobs_version_key ON route_precompute_jobs(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_precompute_jobs_version_job ON route_precompute_jobs(route_version_key, job_type);
CREATE INDEX IF NOT EXISTS idx_route_precompute_jobs_status ON route_precompute_jobs(status);
CREATE INDEX IF NOT EXISTS idx_route_precompute_jobs_trigger_source ON route_precompute_jobs(trigger_source);
CREATE INDEX IF NOT EXISTS idx_route_precompute_jobs_created_at ON route_precompute_jobs(created_at);

CREATE TABLE IF NOT EXISTS route_analysis_run (
    analysis_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    route_id TEXT NOT NULL,
    route_artifact_id INTEGER,
    route_version_key TEXT NOT NULL,
    requested_start_time TIMESTAMPTZ NOT NULL,
    analysis_generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    forecast_provider TEXT NOT NULL DEFAULT 'unknown',
    forecast_fetched_at TIMESTAMPTZ,
    assumed_speed_model TEXT NOT NULL DEFAULT 'default',
    weather_overlay_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    wbgt_overlay_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    cold_risk_overlay_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    poi_decision_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    resupply_plan_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    nutrition_hydration_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_assessment_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    rendered_report_artifact_ref TEXT,
    rendered_report_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_analysis_run_idem_uq UNIQUE (idempotency_key),
    CONSTRAINT route_analysis_run_version_start_uq UNIQUE (route_version_key, requested_start_time, forecast_provider, assumed_speed_model),
    CONSTRAINT route_analysis_run_status_chk CHECK (status IN ('pending', 'running', 'complete', 'failed', 'partial'))
);

CREATE INDEX IF NOT EXISTS idx_route_analysis_run_base_id ON route_analysis_run(route_base_id);
CREATE INDEX IF NOT EXISTS idx_route_analysis_run_version_key ON route_analysis_run(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_analysis_run_requested_start_time ON route_analysis_run(requested_start_time);
CREATE INDEX IF NOT EXISTS idx_route_analysis_run_status ON route_analysis_run(status);
CREATE INDEX IF NOT EXISTS idx_route_analysis_run_forecast_fetched_at ON route_analysis_run(forecast_fetched_at);

COMMIT;
