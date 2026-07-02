-- QBot route POI meta store v1
-- Dokumentacja: docs/DECISIONS.md (2026-07-02 "route_poi_meta").
-- Jeden wiersz na wersje trasy (route_base) z metadanymi JAKOSCI analizy POI,
-- ktore analyze_route_poi_artifact liczy na poziomie CALEJ trasy (nie per-punkt):
-- status zaopatrzenia, kompletnosc techniczna, najdluzsza luka, liczniki open/unknown/closed,
-- tryb zrodla (google/overpass), liczba punktow z Google, oraz "braki chunkow" (ktore
-- geograficzne kawalki trasy nie pobraly sie z Overpass) - te ostatnie sa artefaktem
-- MOMENTU pobrania i nie da sie ich odtworzyc z zapisanych punktow, dlatego zapisujemy je tu.
-- Dziecko route_base: kasuje sie kaskadowo z trasa (zero sierot). Upsert po route_base_id.
-- Zasila: qbot3/routes/route_poi_store.ensure_route_poi (ta sama transakcja co route_poi_layer).
-- Czyta: qbot3/routes/route_canonical_read + raport (qbot_route_report_tool).

BEGIN;

SET search_path TO qbot_v2, public;

CREATE TABLE IF NOT EXISTS route_poi_meta (
    route_poi_meta_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    route_version_key TEXT NOT NULL,
    analysis_status TEXT,
    supply_status TEXT,
    technical_completeness TEXT,
    supply_longest_gap_km DOUBLE PRECISION,
    supply_longest_gap_from_km DOUBLE PRECISION,
    supply_open_count INTEGER,
    supply_unknown_count INTEGER,
    supply_closed_count INTEGER,
    poi_source_mode TEXT,
    google_supply_count INTEGER,
    missing_chunks_count INTEGER,
    km_from DOUBLE PRECISION,
    km_to DOUBLE PRECISION,
    avg_speed_kmh DOUBLE PRECISION,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    missing_chunks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    buffers_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_poi_meta_uq UNIQUE (route_base_id)
);

CREATE INDEX IF NOT EXISTS idx_route_poi_meta_base_id ON route_poi_meta(route_base_id);
CREATE INDEX IF NOT EXISTS idx_route_poi_meta_version_key ON route_poi_meta(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_poi_meta_fetched_at ON route_poi_meta(fetched_at);

COMMIT;
