-- Diety od Brokula: jadlospis z panelu klienta (qbot_brokul.py). 2026-10-12
-- Jeden wiersz = jeden posilek dnia. Do bilansu (intake_logs/items) trafia DOPIERO po
-- potwierdzeniu na Telegramie (status 'eaten'); 'skipped' = pominiety; 'pending' = brak decyzji.
CREATE TABLE IF NOT EXISTS qbot_v2.brokul_meals (
    id              serial PRIMARY KEY,
    day             date NOT NULL,
    meal_type       text NOT NULL,          -- nazwa z panelu, np. 'Śniadanie'
    meal_order      int  NOT NULL,          -- kolejnosc w dniu (1..)
    name            text NOT NULL,
    kcal            double precision,
    kj              double precision,
    fat_g           double precision,
    sat_fat_g       double precision,
    carbs_g         double precision,
    sugars_g        double precision,
    protein_g       double precision,
    salt_g          double precision,
    ingredients     text,
    allergen_notice text,
    menu_item_id    text,
    status          text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','eaten','skipped')),
    decided_at      timestamptz,
    intake_log_id   int,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (day, meal_type)
);
CREATE INDEX IF NOT EXISTS brokul_meals_day_idx ON qbot_v2.brokul_meals (day);

-- Wyslane podsumowania dnia na Telegramie (id wiadomosci do edycji po kliknieciu).
CREATE TABLE IF NOT EXISTS qbot_v2.brokul_notify (
    day         date PRIMARY KEY,
    chat_id     text,
    message_id  bigint,
    sent_at     timestamptz NOT NULL DEFAULT now()
);
