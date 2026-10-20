-- 20.10.2026 (sesja hrv-h10-2010, TODO [HRV-JAZDA] etap 2): surowe odstepy RR z pamieci pasa Polar H10,
-- przyslane przez QExt2 (Karoo) po jezdzie: POST /ride-readiness {"hrvRr": {...}} -> mcp_server._qext2_hrv_rr.
-- Jedno nagranie = jedna jazda (exercise_id = "QX<czas startu zapisu w ms, zegar Karoo>"). Surowe dane zachowane
-- zawsze (przeliczenie inna metoda). Dopasowanie do jazdy i analiza DFA a1 = etap 3 (docs/HRV_JAZDA.md).
CREATE TABLE IF NOT EXISTS qbot_v2.qext2_hrv_rr (
    exercise_id   text PRIMARY KEY,
    rec_start_ms  bigint NOT NULL,          -- start zapisu w pasie (zegar Karoo)
    rec_end_ms    bigint,                   -- koniec (pobrane na koncu jazdy) albo start + suma RR
    end_known     boolean NOT NULL DEFAULT false,
    device_id     text,
    battery_pct   integer,                  -- bateria pasa przy pobraniu (-1 = brak odczytu)
    build         integer,                  -- versionCode QExt2
    n_rr          integer NOT NULL,
    sum_ms        bigint,
    rr_ms         integer[] NOT NULL,       -- odstepy RR w ms, w kolejnosci
    session_id    text,                     -- etap 3: dopasowana jazda (wypelni analiza)
    received_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS qext2_hrv_rr_start_idx ON qbot_v2.qext2_hrv_rr (rec_start_ms);
