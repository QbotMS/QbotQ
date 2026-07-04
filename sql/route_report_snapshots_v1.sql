-- QBot: archiwum wygenerowanych raportow trasy (persist + historia po odswiezeniu)
-- Kontekst: docs/RAPORT_WEB.md. Kazde wygenerowanie /api/report/data zapisuje tu
-- pelny blok DATA. Retencja: 4 najnowsze NA TRASE (route_id) - biezacy + 3 archiwalne,
-- starsze kasowane automatycznie przy kazdym nowym zapisie (patrz qbot_web.py).

BEGIN;

SET search_path TO qbot_v2, public;

CREATE TABLE IF NOT EXISTS route_report_snapshots (
    route_report_snapshot_id BIGSERIAL PRIMARY KEY,
    route_id TEXT NOT NULL,             -- zewnetrzny id trasy (jak w /api/report/data?route_id=)
    report_date TEXT NOT NULL,          -- data jazdy z formularza (YYYY-MM-DD)
    start_time TEXT NOT NULL,           -- godzina startu z formularza (HH:MM)
    long_stops INTEGER NOT NULL DEFAULT 0,
    long_stop_min INTEGER NOT NULL DEFAULT 0,
    data_json JSONB NOT NULL,           -- pelny blok DATA - identyczny z odpowiedzia endpointu
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_route_report_snapshots_route_created
    ON route_report_snapshots(route_id, created_at DESC);

COMMIT;
