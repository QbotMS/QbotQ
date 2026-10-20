-- 20.10.2026 (sesja hrv-h10-2010, TODO [HRV-JAZDA] etap 3): wyniki analizy HRV z jazdy (fitmodel/hrv_ride.py).
-- Jedno nagranie z pasa (qext2_hrv_rr.exercise_id) = jeden wiersz. NIE wplywa na ModelQ (etap 5: walidacja).
CREATE TABLE IF NOT EXISTS qbot_v2.hrv_ride_result (
    exercise_id   text PRIMARY KEY REFERENCES qbot_v2.qext2_hrv_rr(exercise_id) ON DELETE CASCADE,
    session_id    text,              -- activity_fit_raw.external_id (null = jazda jeszcze nie dotarla)
    version       integer NOT NULL,  -- wersja metody (hrv_ride.VERSION) -> przeliczenie po zmianie
    lag_s         integer,           -- przesuniecie czasu pas vs Karoo (z tetna)
    hr_corr       real,              -- zgodnosc tetna pas vs Karoo (r); <0.5 = podejrzane dopasowanie
    artifact_pct  real,              -- odsetek blednych uderzen (kondycja paska / jakosc sygnalu)
    n_windows     integer,
    n_steady      integer,           -- okna rownej jazdy z a1
    ltp_w         integer,           -- moc przy DFA a1 = 0.75 (LTP z HRV)
    ltp_conf      text,              -- wysoka | srednia | niska | brak
    ltp_hr        integer,           -- tetno przy a1 = 0.75
    tp_w          integer,           -- moc przy a1 = 0.5 (okolice TP)
    tp_conf       text,
    r_power       real,              -- korelacja a1 ~ moc
    drift_a1      real,              -- a1 2. polowa - 1. polowa w tym samym pasmie mocy (ujemne = zmeczenie)
    warmup_a1     real,              -- srednie a1 z pierwszych 15 min
    ltp_modelq_w  real,              -- LTP ModelQ z dnia jazdy (do porownania)
    tp_modelq_w   real,              -- prog ModelQ z dnia jazdy
    details       jsonb,             -- pelny wynik z oknami
    computed_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hrv_ride_result_session_idx ON qbot_v2.hrv_ride_result (session_id);
