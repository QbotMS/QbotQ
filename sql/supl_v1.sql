-- Suplementy i leki (2026-10-13): qbot_supplements.py, docs/SUPLEMENTY.md
CREATE TABLE IF NOT EXISTS qbot_v2.supplement (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'suplement' CHECK (kind IN ('suplement', 'lek')),
    slot       TEXT NOT NULL DEFAULT 'dowolnie' CHECK (slot IN ('rano', 'wieczor', 'przed_snem', 'dowolnie')),
    days       INTEGER[],               -- dni tygodnia 0=pn..6=nd; NULL = codziennie
    active     BOOLEAN NOT NULL DEFAULT true,
    deleted    BOOLEAN NOT NULL DEFAULT false,
    note       TEXT,
    sort       INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS qbot_v2.supplement_dose (     -- wersje dawki: obowiazuje od valid_from
    supplement_id INTEGER NOT NULL REFERENCES qbot_v2.supplement(id),
    valid_from    DATE NOT NULL,
    dose          REAL,
    unit          TEXT,
    PRIMARY KEY (supplement_id, valid_from)
);
CREATE TABLE IF NOT EXISTS qbot_v2.supplement_log (
    day           DATE NOT NULL,
    supplement_id INTEGER NOT NULL REFERENCES qbot_v2.supplement(id),
    status        TEXT NOT NULL CHECK (status IN ('taken', 'skipped')),
    dose          REAL,
    unit          TEXT,
    source        TEXT,
    at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, supplement_id)
);
