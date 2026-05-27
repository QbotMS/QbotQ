-- QBot Health Advisor + Supplement Tracking store v1
BEGIN;

-- 1. Health goals
CREATE TABLE IF NOT EXISTS health_goals (
    id              SERIAL PRIMARY KEY,
    goal_name       TEXT NOT NULL,
    goal_type       TEXT NOT NULL DEFAULT 'weight_loss',
    start_date      DATE,
    start_weight_kg DOUBLE PRECISION,
    target_weight_kg DOUBLE PRECISION,
    target_date     DATE,
    next_target_weight_kg DOUBLE PRECISION,
    next_target_date DATE,
    priority        TEXT NOT NULL DEFAULT 'balanced',
    status          TEXT NOT NULL DEFAULT 'active',
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Supplement inventory
CREATE TABLE IF NOT EXISTS supplement_inventory (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    brand           TEXT,
    form            TEXT DEFAULT 'capsule',
    dose_per_unit   DOUBLE PRECISION,
    dose_unit       TEXT DEFAULT 'mg',
    units_total     DOUBLE PRECISION,
    units_remaining DOUBLE PRECISION,
    purchase_date   DATE,
    opened_date     DATE,
    expiry_date     DATE,
    source_shop     TEXT,
    price           DOUBLE PRECISION,
    currency        TEXT DEFAULT 'PLN',
    notes           TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. Supplement protocols
CREATE TABLE IF NOT EXISTS supplement_protocols (
    id              SERIAL PRIMARY KEY,
    supplement_id   INTEGER REFERENCES supplement_inventory(id) ON DELETE SET NULL,
    supplement_name TEXT NOT NULL,
    dose            DOUBLE PRECISION NOT NULL DEFAULT 1,
    dose_unit       TEXT DEFAULT 'mg',
    frequency       TEXT NOT NULL DEFAULT 'daily',
    timing          TEXT DEFAULT 'morning',
    with_food       BOOLEAN,
    goal            TEXT DEFAULT 'general_health',
    start_date      DATE,
    end_date        DATE,
    status          TEXT NOT NULL DEFAULT 'active',
    reason          TEXT,
    cautions        TEXT,
    assumptions_json JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. Supplement intake log
CREATE TABLE IF NOT EXISTS supplement_intake_log (
    id              SERIAL PRIMARY KEY,
    supplement_id   INTEGER REFERENCES supplement_inventory(id) ON DELETE SET NULL,
    protocol_id     INTEGER REFERENCES supplement_protocols(id) ON DELETE SET NULL,
    date            DATE NOT NULL DEFAULT now(),
    time            TIME,
    dose            DOUBLE PRECISION,
    dose_unit       TEXT,
    taken           BOOLEAN NOT NULL DEFAULT true,
    source          TEXT DEFAULT 'manual',
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_intake_date ON supplement_intake_log(date);

-- 6. Health events — illness, wellbeing, symptoms, recovery anomalies
CREATE TABLE IF NOT EXISTS health_events (
    id              SERIAL PRIMARY KEY,
    date_start      DATE NOT NULL DEFAULT now(),
    date_end        DATE,
    event_type      TEXT NOT NULL DEFAULT 'illness',
    title           TEXT NOT NULL,
    description     TEXT,
    severity        TEXT NOT NULL DEFAULT 'mild',
    status          TEXT NOT NULL DEFAULT 'active',
    symptoms_json   JSONB,
    constraints_json JSONB,
    source          TEXT NOT NULL DEFAULT 'manual',
    confidence      TEXT NOT NULL DEFAULT 'high',
    affects_training BOOLEAN DEFAULT true,
    affects_nutrition BOOLEAN DEFAULT true,
    affects_recovery BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_event_status ON health_events(status);
CREATE INDEX IF NOT EXISTS idx_event_type ON health_events(event_type);

-- 7. Health event observations — daily measurements per event
CREATE TABLE IF NOT EXISTS health_event_observations (
    id              SERIAL PRIMARY KEY,
    event_id        INTEGER REFERENCES health_events(id) ON DELETE SET NULL,
    date            DATE NOT NULL DEFAULT now(),
    observation_type TEXT NOT NULL DEFAULT 'symptom',
    value_text      TEXT,
    value_number    DOUBLE PRECISION,
    unit            TEXT,
    source          TEXT NOT NULL DEFAULT 'manual',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 8. Health risk notes — user-reported metabolic/cardio/etc risks
CREATE TABLE IF NOT EXISTS health_risk_notes (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    risk_type       TEXT NOT NULL DEFAULT 'other',
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    evidence_json   JSONB,
    constraints_json JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_risk_status ON health_risk_notes(status);

COMMIT;
