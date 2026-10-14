-- HRR60 (2026-10-14): tetno odpoczynku po akcentach w jazdach, liczone z FIT (qbot_hrr.py).
CREATE TABLE IF NOT EXISTS qbot_v2.ride_hrr (
  external_id TEXT PRIMARY KEY, day DATE NOT NULL, n INT NOT NULL, hrr60 NUMERIC(5,1), hrr30 NUMERIC(5,1), peak_hr NUMERIC(5,1),
  cp_w NUMERIC(6,1), events JSONB, computed_at TIMESTAMPTZ NOT NULL DEFAULT now());
