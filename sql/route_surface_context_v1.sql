-- route_surface_context: warstwa kontekstu + ryzyka nawierzchni dla odcinkow BEZ tagu OSM.
-- Nie dotyka route_surface_layer.surface (etykieta nawierzchni zostaje silnika).
-- Zrodla: route_surface_layer (source='osm_contextual') + route_shade_layer (WorldCover, zlaczenie po km) + sygnal geologii.
-- Audyt nawierzchni 2026-07-02.
CREATE TABLE IF NOT EXISTS qbot_v2.route_surface_context (
    route_surface_context_id BIGSERIAL PRIMARY KEY,
    route_base_id      BIGINT  NOT NULL REFERENCES qbot_v2.route_base(route_base_id) ON DELETE CASCADE,
    route_version_key  TEXT    NOT NULL,
    segment_index      INTEGER NOT NULL,
    km_from            DOUBLE PRECISION,
    km_to              DOUBLE PRECISION,
    highway            TEXT,
    tracktype          TEXT,
    dominant_class     INTEGER,      -- kod klasy WorldCover (class_center)
    dominant_pl        TEXT,         -- 'las'/'trawy'/'uprawy'/'zabudowa'/...
    agreement_pct      INTEGER,      -- % wezlow shade w klasie dominujacej
    n_nodes            INTEGER,      -- liczba wezlow shade (coverage ok) w zakresie km
    shade_coverage     TEXT,         -- 'ok' gdy uzyto WorldCover, 'none' gdy brak pokrycia
    geology_sand       BOOLEAN,      -- sygnal piachu z geologii (risk_flags)
    surface_estimate   TEXT,         -- wynik reguly (np. 'grunt/ubity', 'MOZLIWY GLEBOKI PIACH')
    estimate_confidence TEXT,        -- 'ni' | 'ni-sr' | 'sr'
    sand_risk          TEXT,         -- NISKIE | NISKO-SR | UMIARK. | SREDNIE | WYSOKIE
    reason             TEXT,         -- jednozdaniowe uzasadnienie
    source             TEXT NOT NULL DEFAULT 'route_surface_context_v1',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (route_base_id, segment_index)
);
CREATE INDEX IF NOT EXISTS route_surface_context_base_idx ON qbot_v2.route_surface_context (route_base_id);
CREATE INDEX IF NOT EXISTS route_surface_context_risk_idx ON qbot_v2.route_surface_context (sand_risk);
