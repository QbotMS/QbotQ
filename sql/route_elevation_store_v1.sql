-- QBot route elevation samples + climb events store v1
-- Faza 2C: nowe tabele-dzieci route_base. Nie zmienia route_base ani
-- route_analysis_run. Profil gesty (SRTM30m) + wykryte podjazdy (progi Karoo),
-- segmenty 100 m trzymane jako JSON w wierszu podjazdu.

BEGIN;

SET search_path TO qbot_v2, public;

-- Gesty profil wysokosci: 1 wiersz / wezel 50 m. Surowa wysokosc trzymana
-- wiernie (elevation_m moze byc NULL przy dziurze DEM); wygladzanie/podjazdy
-- sa pochodne i NIE sa tu materializowane.
CREATE TABLE IF NOT EXISTS route_elevation_samples (
    route_elevation_sample_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    route_version_key TEXT NOT NULL,
    sample_index INTEGER NOT NULL,
    distance_m DOUBLE PRECISION NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lon DOUBLE PRECISION NOT NULL,
    elevation_m DOUBLE PRECISION,
    source TEXT NOT NULL,
    smoothing_version TEXT NOT NULL,
    elevation_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_elevation_samples_uq UNIQUE (route_base_id, sample_index)
);

CREATE INDEX IF NOT EXISTS idx_route_elevation_samples_base_id ON route_elevation_samples(route_base_id);
CREATE INDEX IF NOT EXISTS idx_route_elevation_samples_version_key ON route_elevation_samples(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_elevation_samples_distance_m ON route_elevation_samples(distance_m);

-- Wykryte podjazdy: naglowek + segmenty 100 m jako JSON (segments_json).
-- Liczba zdarzen zmienna miedzy przeliczeniami -> writer robi delete+insert,
-- ale UNIQUE(route_base_id, event_index) chroni przed duplikatami w obrebie wersji.
CREATE TABLE IF NOT EXISTS route_climb_events (
    route_climb_event_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    route_version_key TEXT NOT NULL,
    event_index INTEGER NOT NULL,
    start_m DOUBLE PRECISION NOT NULL,
    end_m DOUBLE PRECISION NOT NULL,
    length_m DOUBLE PRECISION NOT NULL,
    elevation_gain_m DOUBLE PRECISION NOT NULL,
    avg_gradient_pct DOUBLE PRECISION NOT NULL,
    max_gradient_pct DOUBLE PRECISION NOT NULL,
    severity TEXT NOT NULL,
    segments_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT NOT NULL,
    detection_version TEXT NOT NULL,
    climb_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_climb_events_uq UNIQUE (route_base_id, event_index)
);

CREATE INDEX IF NOT EXISTS idx_route_climb_events_base_id ON route_climb_events(route_base_id);
CREATE INDEX IF NOT EXISTS idx_route_climb_events_version_key ON route_climb_events(route_version_key);

COMMIT;
