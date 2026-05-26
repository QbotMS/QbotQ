-- QBot RWGPS route artifact store v1
-- Hybrid storage: file artifacts on disk, metadata and analysis in PostgreSQL.

CREATE TABLE IF NOT EXISTS route_artifacts (
    id SERIAL PRIMARY KEY,
    route_id TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'rwgps',
    export_format TEXT NOT NULL DEFAULT 'gpx_track',
    artifact_path TEXT NOT NULL,
    artifact_relative_path TEXT,
    filename TEXT NOT NULL,
    file_size_bytes BIGINT,
    sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    parser_version TEXT,
    source_artifact_sha256 TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT route_artifacts_unique_artifact_path UNIQUE (artifact_path)
);

CREATE INDEX IF NOT EXISTS idx_route_artifacts_route_id ON route_artifacts (route_id);
CREATE INDEX IF NOT EXISTS idx_route_artifacts_sha256 ON route_artifacts (sha256);
CREATE INDEX IF NOT EXISTS idx_route_artifacts_source_sha256 ON route_artifacts (source_artifact_sha256);
CREATE INDEX IF NOT EXISTS idx_route_artifacts_created_at ON route_artifacts (created_at);

CREATE TABLE IF NOT EXISTS route_parse_results (
    id SERIAL PRIMARY KEY,
    route_artifact_id INTEGER NOT NULL REFERENCES route_artifacts(id) ON DELETE CASCADE,
    parsed_at TIMESTAMPTZ DEFAULT now(),
    parser_version TEXT NOT NULL,
    source_artifact_sha256 TEXT NOT NULL,
    track_points INTEGER,
    distance_m DOUBLE PRECISION,
    distance_km DOUBLE PRECISION,
    elevation_gain_m DOUBLE PRECISION,
    elevation_loss_m DOUBLE PRECISION,
    bbox_min_lat DOUBLE PRECISION,
    bbox_min_lon DOUBLE PRECISION,
    bbox_max_lat DOUBLE PRECISION,
    bbox_max_lon DOUBLE PRECISION,
    start_lat DOUBLE PRECISION,
    start_lon DOUBLE PRECISION,
    end_lat DOUBLE PRECISION,
    end_lon DOUBLE PRECISION,
    min_ele DOUBLE PRECISION,
    max_ele DOUBLE PRECISION,
    looks_valid BOOLEAN,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT route_parse_results_unique_revision UNIQUE (route_artifact_id, parser_version, source_artifact_sha256)
);

CREATE INDEX IF NOT EXISTS idx_route_parse_results_artifact_id ON route_parse_results (route_artifact_id);
CREATE INDEX IF NOT EXISTS idx_route_parse_results_source_sha256 ON route_parse_results (source_artifact_sha256);
CREATE INDEX IF NOT EXISTS idx_route_parse_results_parsed_at ON route_parse_results (parsed_at);

CREATE TABLE IF NOT EXISTS route_surface_profiles (
    id SERIAL PRIMARY KEY,
    route_artifact_id INTEGER NOT NULL REFERENCES route_artifacts(id) ON DELETE CASCADE,
    enriched_at TIMESTAMPTZ DEFAULT now(),
    enrichment_version TEXT NOT NULL,
    source_artifact_sha256 TEXT NOT NULL,
    surface_source TEXT NOT NULL DEFAULT 'unknown',
    sample_every_m INTEGER,
    confidence TEXT,
    coverage_pct DOUBLE PRECISION,
    sampled_points INTEGER,
    matched_points INTEGER,
    unmatched_points INTEGER,
    dominant_surface TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    surface_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    surface_segments_json JSONB,
    surface_segments_path TEXT,
    CONSTRAINT route_surface_profiles_unique_revision UNIQUE (route_artifact_id, enrichment_version, source_artifact_sha256, sample_every_m)
);

CREATE INDEX IF NOT EXISTS idx_route_surface_profiles_artifact_id ON route_surface_profiles (route_artifact_id);
CREATE INDEX IF NOT EXISTS idx_route_surface_profiles_source_sha256 ON route_surface_profiles (source_artifact_sha256);
CREATE INDEX IF NOT EXISTS idx_route_surface_profiles_enriched_at ON route_surface_profiles (enriched_at);

CREATE TABLE IF NOT EXISTS route_surface_segments (
    id SERIAL PRIMARY KEY,
    route_surface_profile_id INTEGER NOT NULL REFERENCES route_surface_profiles(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    distance_m DOUBLE PRECISION,
    surface TEXT,
    confidence TEXT,
    source TEXT,
    start_lat DOUBLE PRECISION,
    start_lon DOUBLE PRECISION,
    end_lat DOUBLE PRECISION,
    end_lon DOUBLE PRECISION,
    geometry_json JSONB,
    CONSTRAINT route_surface_segments_unique_segment UNIQUE (route_surface_profile_id, segment_index)
);

CREATE INDEX IF NOT EXISTS idx_route_surface_segments_profile_id ON route_surface_segments (route_surface_profile_id);
