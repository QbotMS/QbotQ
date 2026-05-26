-- QBot Nutrition / Fueling local PostgreSQL store v1
-- Food tracking, meals, hydration, fueling — source-of-truth for nutrition
-- Non-destructive: uses IF NOT EXISTS + ON CONFLICT UPSERT

BEGIN;

-- 1. Food items — stałe produkty + jednorazowe z etykiety
CREATE TABLE IF NOT EXISTS food_items (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    brand           TEXT,
    default_unit    TEXT NOT NULL DEFAULT 'g',
    kcal_per_100g   DOUBLE PRECISION,
    carbs_per_100g  DOUBLE PRECISION,
    sugar_per_100g  DOUBLE PRECISION,
    protein_per_100g DOUBLE PRECISION,
    fat_per_100g    DOUBLE PRECISION,
    fiber_per_100g  DOUBLE PRECISION,
    sodium_per_100g DOUBLE PRECISION,
    source          TEXT NOT NULL DEFAULT 'qbot',
    verified        BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_food_name UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_food_items_name ON food_items(name);
CREATE INDEX IF NOT EXISTS idx_food_items_source ON food_items(source);

-- 2. Meal logs — pojedynczy posiłek
CREATE TABLE IF NOT EXISTS meal_logs (
    id              SERIAL PRIMARY KEY,
    eaten_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    meal_type       TEXT NOT NULL DEFAULT 'meal',
    note            TEXT,
    context         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meal_logs_eaten_at ON meal_logs(eaten_at);
CREATE INDEX IF NOT EXISTS idx_meal_logs_meal_type ON meal_logs(meal_type);

-- 3. Meal log items — składniki posiłku
CREATE TABLE IF NOT EXISTS meal_log_items (
    id              SERIAL PRIMARY KEY,
    meal_log_id     INTEGER NOT NULL REFERENCES meal_logs(id) ON DELETE CASCADE,
    food_item_id    INTEGER REFERENCES food_items(id) ON DELETE SET NULL,
    food_name       TEXT NOT NULL,
    amount          DOUBLE PRECISION NOT NULL,
    unit            TEXT NOT NULL DEFAULT 'g',
    kcal            DOUBLE PRECISION,
    carbs_g         DOUBLE PRECISION,
    protein_g       DOUBLE PRECISION,
    fat_g           DOUBLE PRECISION,
    fiber_g         DOUBLE PRECISION,
    sodium_mg       DOUBLE PRECISION,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meal_log_items_meal ON meal_log_items(meal_log_id);
CREATE INDEX IF NOT EXISTS idx_meal_log_items_food ON meal_log_items(food_item_id);

-- 4. Hydration events — picie
CREATE TABLE IF NOT EXISTS hydration_events (
    id              SERIAL PRIMARY KEY,
    drank_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    fluid_ml        DOUBLE PRECISION NOT NULL,
    sodium_mg       DOUBLE PRECISION DEFAULT 0,
    source          TEXT NOT NULL DEFAULT 'qbot',
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hydration_drank_at ON hydration_events(drank_at);

-- 5. Fueling events — żelowanie / carbs na trasie
CREATE TABLE IF NOT EXISTS fueling_events (
    id              SERIAL PRIMARY KEY,
    event_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    carbs_g         DOUBLE PRECISION NOT NULL,
    source          TEXT NOT NULL DEFAULT 'qbot',
    context         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fueling_event_at ON fueling_events(event_at);

-- 6. Nutrition daily summary — agregat dzienny z QBot (nie Cronometer)
CREATE TABLE IF NOT EXISTS nutrition_daily_summary (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    source          TEXT NOT NULL DEFAULT 'qbot',
    kcal_total      DOUBLE PRECISION DEFAULT 0,
    carbs_total     DOUBLE PRECISION DEFAULT 0,
    protein_total   DOUBLE PRECISION DEFAULT 0,
    fat_total       DOUBLE PRECISION DEFAULT 0,
    fiber_total     DOUBLE PRECISION DEFAULT 0,
    sodium_total    DOUBLE PRECISION DEFAULT 0,
    fluids_total    DOUBLE PRECISION DEFAULT 0,
    carb_balance    DOUBLE PRECISION,
    hydration_balance DOUBLE PRECISION,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_nutrition_summary_date_source UNIQUE (date, source)
);

CREATE INDEX IF NOT EXISTS idx_nutrition_summary_date ON nutrition_daily_summary(date);

COMMIT;
