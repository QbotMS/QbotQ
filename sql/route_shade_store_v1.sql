-- QBot route shade/land-cover cross-section store v1
-- Dokumentacja: docs/PROJEKT_OTOCZENIE.md (skad/gdzie/po co/dlaczego; sekcja 6 = co odrzucono).
-- Surowe klasy ESA WorldCover (v200/2021) w przekroju przez drogę, 1:1 z osią (~50 m).
-- Dziecko route_base. UWAGA: trzymamy WYŁĄCZNIE surowe klasy + kierunek jazdy.
-- Żadnych pochodnych (osłona, udziały, werdykty) — interpretację robi konsument
-- (WBGT liczy cień wzgl. słońca, ocena nawierzchni weźmie swoje itd.).
-- Nazwa "shade" pozostaje dla ciągłości, ale to ogólna warstwa pokrycia w przekroju.
--
-- Przekrój: 5 punktów co 10 m (rozdzielczość piksela WorldCover), pas ±20 m:
--   class_left_20, class_left_10, class_center, class_right_10, class_right_20
-- "left"/"right" względem kierunku jazdy (heading_deg).

BEGIN;

SET search_path TO qbot_v2, public;

-- Legenda klas WorldCover — żeby surowe kody same się tłumaczyły (JOIN po kodzie).
CREATE TABLE IF NOT EXISTS worldcover_classes (
    code SMALLINT PRIMARY KEY,
    name_pl TEXT NOT NULL,
    name_en TEXT NOT NULL,
    is_tree BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO worldcover_classes (code, name_pl, name_en, is_tree) VALUES
    (10,  'drzewa',        'Tree cover',                TRUE),
    (20,  'zarosla',       'Shrubland',                 FALSE),
    (30,  'trawy',         'Grassland',                 FALSE),
    (40,  'uprawy',        'Cropland',                  FALSE),
    (50,  'zabudowa',      'Built-up',                  FALSE),
    (60,  'goly grunt',    'Bare / sparse vegetation',  FALSE),
    (70,  'snieg/lod',     'Snow and ice',              FALSE),
    (80,  'woda',          'Permanent water bodies',    FALSE),
    (90,  'mokradla',      'Herbaceous wetland',        FALSE),
    (95,  'namorzyny',     'Mangroves',                 FALSE),
    (100, 'mchy/porosty',  'Moss and lichen',           FALSE)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS route_shade_layer (
    route_shade_layer_id BIGSERIAL PRIMARY KEY,
    route_base_id BIGINT NOT NULL REFERENCES route_base(route_base_id) ON DELETE CASCADE,
    route_version_key TEXT NOT NULL,
    segment_index INTEGER NOT NULL,             -- węzeł osi (1:1 z route_axis_segments)
    heading_deg DOUBLE PRECISION,               -- kierunek jazdy (do azymutu słońca)
    -- surowe klasy WorldCover w przekroju (kody z worldcover_classes; NULL = brak danych)
    class_center SMALLINT,
    class_left_10 SMALLINT,
    class_left_20 SMALLINT,
    class_right_10 SMALLINT,
    class_right_20 SMALLINT,
    n_valid SMALLINT NOT NULL DEFAULT 0,        -- ile z 5 pikseli odczytano
    source TEXT NOT NULL,                       -- 'worldcover_v200_2021'
    tile TEXT,                                  -- użyty kafel, np. N51E021
    coverage_status TEXT NOT NULL DEFAULT 'unknown',  -- 'ok'|'partial'|'missing'(->legacy)
    meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,     -- lat/lon węzła, offsety
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT route_shade_layer_uq UNIQUE (route_base_id, segment_index),
    CONSTRAINT route_shade_layer_coverage_chk
        CHECK (coverage_status IN ('ok', 'partial', 'missing', 'unknown'))
);

CREATE INDEX IF NOT EXISTS idx_route_shade_layer_base_id ON route_shade_layer(route_base_id);
CREATE INDEX IF NOT EXISTS idx_route_shade_layer_version_key ON route_shade_layer(route_version_key);
CREATE INDEX IF NOT EXISTS idx_route_shade_layer_segment ON route_shade_layer(route_base_id, segment_index);
CREATE INDEX IF NOT EXISTS idx_route_shade_layer_coverage ON route_shade_layer(coverage_status);
CREATE INDEX IF NOT EXISTS idx_route_shade_layer_class_center ON route_shade_layer(class_center);

COMMIT;
