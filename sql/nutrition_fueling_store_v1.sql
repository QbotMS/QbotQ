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

-- 7. Meal templates — szablony posiłków do szybkiego logowania
CREATE TABLE IF NOT EXISTS meal_templates (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    serving_label   TEXT NOT NULL DEFAULT 'porcja',
    kcal            DOUBLE PRECISION NOT NULL DEFAULT 0,
    carbs_g         DOUBLE PRECISION NOT NULL DEFAULT 0,
    protein_g       DOUBLE PRECISION NOT NULL DEFAULT 0,
    fat_g           DOUBLE PRECISION NOT NULL DEFAULT 0,
    fiber_g         DOUBLE PRECISION DEFAULT 0,
    sodium_mg       DOUBLE PRECISION DEFAULT 0,
    source          TEXT NOT NULL DEFAULT 'manual',
    confidence      TEXT NOT NULL DEFAULT 'high',
    notes           TEXT,
    assumptions_json JSONB DEFAULT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_template_name UNIQUE (name)
);

CREATE INDEX IF NOT EXISTS idx_template_name ON meal_templates(name);
CREATE INDEX IF NOT EXISTS idx_template_source ON meal_templates(source);

-- 8. Nutrition day plans — zaplanowane jadłospisy
CREATE TABLE IF NOT EXISTS nutrition_day_plans (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    goal            TEXT NOT NULL DEFAULT 'maintenance',
    day_type        TEXT NOT NULL DEFAULT 'rest',
    status          TEXT NOT NULL DEFAULT 'draft',
    planned_training_ref  TEXT,
    planned_ride_km       DOUBLE PRECISION,
    estimated_base_kcal   DOUBLE PRECISION,
    estimated_activity_kcal DOUBLE PRECISION,
    estimated_total_expenditure DOUBLE PRECISION,
    target_deficit_kcal   DOUBLE PRECISION,
    target_intake_kcal    DOUBLE PRECISION NOT NULL DEFAULT 0,
    target_protein_g      DOUBLE PRECISION,
    target_carbs_g        DOUBLE PRECISION,
    target_fat_g          DOUBLE PRECISION,
    planned_meals_count   INTEGER DEFAULT 3,
    available_foods       TEXT,
    used_templates        BOOLEAN DEFAULT false,
    confidence            TEXT NOT NULL DEFAULT 'medium',
    source                TEXT NOT NULL DEFAULT 'llm_plan',
    assumptions_json      JSONB,
    warnings_json         JSONB,
    shopping_list_json    JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plan_date ON nutrition_day_plans(date);
CREATE INDEX IF NOT EXISTS idx_plan_status ON nutrition_day_plans(status);

-- 9. Planned meals — posiłki w ramach planu dnia
CREATE TABLE IF NOT EXISTS nutrition_day_plan_meals (
    id              SERIAL PRIMARY KEY,
    plan_id         INTEGER NOT NULL REFERENCES nutrition_day_plans(id) ON DELETE CASCADE,
    meal_order      INTEGER NOT NULL DEFAULT 1,
    meal_name       TEXT NOT NULL DEFAULT 'posiłek',
    template_id     INTEGER REFERENCES meal_templates(id) ON DELETE SET NULL,
    planned_time    TEXT,
    kcal            DOUBLE PRECISION NOT NULL DEFAULT 0,
    carbs_g         DOUBLE PRECISION DEFAULT 0,
    protein_g       DOUBLE PRECISION DEFAULT 0,
    fat_g           DOUBLE PRECISION DEFAULT 0,
    fiber_g         DOUBLE PRECISION DEFAULT 0,
    sodium_mg       DOUBLE PRECISION DEFAULT 0,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plan_meal_plan ON nutrition_day_plan_meals(plan_id);

COMMIT;
