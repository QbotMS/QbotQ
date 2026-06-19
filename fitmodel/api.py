from __future__ import annotations

"""FITMODEL E8/B3 -- payload aktywnego bloku dla pola na Karoo (QExt2).

Spec sek. 8. GET /fitmodel/buckets/active zwraca:
  { ride_mode, block_source, targeting: bool,
    today_targets: {low,high,peak},
    week_fill_pct: {low,high,peak},
    params: {ftp_w, kj_gate, torque_ref} }

Pole pobiera na starcie; brak sieci -> ostatni znany + offline (po stronie Karoo).
ride_mode=expedition -> targeting_off (silnik liczy, pole milczy).
Sam silnik; pole danych Karoo poza zakresem (Michal robi osobno).
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2


def _db_connect():
    """Polaczenie BEZ czytania /etc/qbot/qbot-api.env (root-only) -- usluga
    qbot-api dziala jako user 'qbot' z lokalnym trustem do Postgresa."""
    kwargs = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return psycopg2.connect(**kwargs)


def _week_monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _params(cur) -> dict[str, Any]:
    cur.execute("SELECT key, value FROM qbot_v2.fitmodel_param")
    p = {k: float(v) for k, v in cur.fetchall() if v is not None}
    # FTP biezace: ostatni niepusty ftp_est, fallback ftp_anchor
    cur.execute(
        "SELECT ftp_est_w FROM qbot_v2.fitmodel_daily "
        "WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1"
    )
    row = cur.fetchone()
    ftp_w = float(row[0]) if row and row[0] else p.get("ftp_anchor_w")
    return {
        "ftp_w": round(ftp_w, 1) if ftp_w else None,
        "kj_gate": p.get("kj_gate", 1500.0),  # nie ma w param -> stala silnika
        "torque_ref": p.get("torque_ref"),  # §5.4 -- None dopoki niepoliczony
    }


def build_active_payload(db_conn, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    week = _week_monday(today)
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT mode, focus_source, target_low, target_high, target_peak, feasible "
            "FROM qbot_v2.fitmodel_week_plan WHERE week <= %s ORDER BY week DESC LIMIT 1",
            (week,),
        )
        plan = cur.fetchone()
        if plan:
            mode, focus_source, t_low, t_high, t_peak, feasible = plan
            t_low = float(t_low or 0); t_high = float(t_high or 0); t_peak = float(t_peak or 0)
        else:
            mode, focus_source, feasible = "podtrzymanie", "deficit", None
            t_low = t_high = t_peak = 0.0

        # Wypelnienie tygodnia: strain z ride_buckets od poniedzialku
        cur.execute(
            "SELECT COALESCE(SUM(low_strain),0), COALESCE(SUM(high_strain),0), "
            "COALESCE(SUM(peak_strain),0) FROM qbot_v2.fitmodel_ride_buckets "
            "WHERE started_at::date >= %s",
            (week,),
        )
        f_low, f_high, f_peak = (float(x) for x in cur.fetchone())
        params = _params(cur)

    ride_mode = mode or "podtrzymanie"
    targeting = ride_mode != "expedition"

    def _pct(filled, target):
        return round(filled / target * 100, 1) if target and target > 0 else None

    # Dzienny plasterek = tygodniowy target / 7 (spec 5.5)
    def _slice(x):
        return round(x / 7.0, 1)

    return {
        "ride_mode": ride_mode,
        "block_source": focus_source,
        "targeting": targeting,
        "week": week.isoformat(),
        "feasible": feasible,
        "today_targets": {
            "low": _slice(t_low) if targeting else None,
            "high": _slice(t_high) if targeting else None,
            "peak": _slice(t_peak) if targeting else None,
        },
        "week_fill_pct": {
            "low": _pct(f_low, t_low),
            "high": _pct(f_high, t_high),
            "peak": _pct(f_peak, t_peak),
        },
        "params": params,
    }


def active_payload(today: date | None = None) -> dict[str, Any]:
    conn = _db_connect()
    try:
        return build_active_payload(conn, today)
    finally:
        conn.close()


if __name__ == "__main__":
    import json
    print(json.dumps(active_payload(), ensure_ascii=False, indent=2))
