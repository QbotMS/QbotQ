-- Jedzenie: etap 1-2 (2026-10-12). Dok.: docs/BROKUL.md
-- Brokul: lodowka (zjem pozniej), odwolane dni, dzien zjedzenia != dzien dostawy.
ALTER TABLE qbot_v2.brokul_meals DROP CONSTRAINT IF EXISTS brokul_meals_status_check;
ALTER TABLE qbot_v2.brokul_meals ADD CONSTRAINT brokul_meals_status_check
    CHECK (status IN ('pending','eaten','skipped','fridge','discarded','cancelled'));
ALTER TABLE qbot_v2.brokul_meals ADD COLUMN IF NOT EXISTS eaten_day date;

-- Harmonogram dostaw z panelu (/customer/diets/day/order_item_id/<id>/).
CREATE TABLE IF NOT EXISTS qbot_v2.brokul_delivery_days (
    day            date NOT NULL,
    order_item_id  text NOT NULL,
    seen_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (day, order_item_id)
);

-- Jedzenie spoza diety: kazda wiadomosc/zdjecie/szybki przycisk = 1 wpis. Surowa tresc zapisana ZAWSZE najpierw.
CREATE TABLE IF NOT EXISTS qbot_v2.food_entries (
    id               serial PRIMARY KEY,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    kind             text NOT NULL CHECK (kind IN ('text','photo','quick')),
    tg_message_id    bigint UNIQUE,          -- idempotencja (ponowny przebieg crona nie dubluje)
    raw_text         text,
    photo_file_id    text,
    day              date NOT NULL,
    status           text NOT NULL DEFAULT 'new' CHECK (status IN ('new','asking','logged','failed','deleted','not_food')),
    phrase_norm      text,
    items            jsonb,                   -- [{name, portion, kcal, protein_g, carbs_g, fat_g}] (przed skala)
    options          jsonb,                   -- warianty porcji, gdy QBot pyta
    question         text,
    scale            double precision NOT NULL DEFAULT 1,
    kcal             double precision,
    protein_g        double precision,
    carbs_g          double precision,
    fat_g            double precision,
    intake_log_id    int,
    reply_message_id bigint,
    attempts         int NOT NULL DEFAULT 0,
    error            text
);
CREATE INDEX IF NOT EXISTS food_entries_day_idx ON qbot_v2.food_entries (day);

-- Katalog Michala: fraza -> ostatnio potwierdzona porcja (uczenie sie porcji).
CREATE TABLE IF NOT EXISTS qbot_v2.food_catalog (
    phrase_norm  text PRIMARY KEY,
    items        jsonb NOT NULL,
    label        text,
    n            int NOT NULL DEFAULT 1,
    last_used    timestamptz NOT NULL DEFAULT now()
);

-- Zamkniecie dnia (pod pas Jedzenia).
CREATE TABLE IF NOT EXISTS qbot_v2.food_day (
    day          date PRIMARY KEY,
    extras_none  boolean NOT NULL DEFAULT false,   -- klik 'Nic poza dieta'
    closed_at    timestamptz,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
