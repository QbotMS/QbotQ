from __future__ import annotations

"""FITMODEL B2 -- przetworz jazdy (FIT) -> fitmodel_ride_buckets.

Uruchamia silnik B1 (fitmodel.buckets.compute_buckets) na strumieniu mocy
z parse_fit_to_seconds (odporny czytnik z fit_ingest) i zapisuje rozklad
strainu per jazda. UPSERT po ride_id (idempotentne).

FTP do strainu = FTP_est obowiazujace w dniu jazdy (fitmodel_daily, ostatni
niepusty <= data jazdy); fallback ftp_anchor_w z param.
ride_mode pozostaje NULL do czasu warstwy zarzadzania (T1).
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitparse import FitFile

from fitmodel.ftp_resolver import _db_connect
from fitmodel.buckets import compute_buckets

FIT_DIR = Path("/opt/qbot/artifacts/fit")


# ── Czytnik FIT (skopiowany 1:1 z fit_ingest.py, bez zaleznosci od psycopg2) ──
def extract_ride_id(fit_path: str) -> str:
    return Path(fit_path).stem


def _get_field_value(message: Any, field_name: str) -> Any:
    try:
        if hasattr(message, "get_value"):
            return message.get_value(field_name)
    except Exception:
        pass
    try:
        for field in getattr(message, "fields", []):
            if getattr(field, "name", None) == field_name:
                return getattr(field, "value", None)
    except Exception:
        pass
    return None


def parse_fit_to_seconds(fit_path: str) -> list[dict]:
    rows: list[dict[str, Any]] = []
    try:
        fit = FitFile(fit_path)
        for message in fit.get_messages("record"):
            timestamp = _get_field_value(message, "timestamp")
            if timestamp is None:
                continue
            if isinstance(timestamp, datetime):
                timestamp = timestamp.replace(microsecond=0)
            rows.append({"timestamp": timestamp,
                         "power": _get_field_value(message, "power")})
    except Exception:
        return []
    if not rows:
        return []
    rows.sort(key=lambda item: item["timestamp"])
    first_ts, last_ts = rows[0]["timestamp"], rows[-1]["timestamp"]
    if not isinstance(first_ts, datetime) or not isinstance(last_ts, datetime):
        return rows
    second_map: dict[datetime, dict[str, Any]] = {}
    for row in rows:
        ts = row["timestamp"]
        if isinstance(ts, datetime):
            second_map[ts.replace(microsecond=0)] = dict(row, timestamp=ts.replace(microsecond=0))
    timeline: list[dict[str, Any]] = []
    current, end = first_ts.replace(microsecond=0), last_ts.replace(microsecond=0)
    while current <= end:
        timeline.append(second_map.get(current, {"timestamp": current, "power": None}))
        current += timedelta(seconds=1)
    return timeline

DDL = """
CREATE TABLE IF NOT EXISTS qbot_v2.fitmodel_ride_buckets (
    ride_id       text PRIMARY KEY,
    started_at    timestamptz,
    low_strain    numeric,
    high_strain   numeric,
    peak_strain   numeric,
    d_strain      numeric,
    total_strain  numeric,
    ride_mode     text,
    ftp_used_w    int,
    created_at    timestamptz DEFAULT now()
)
"""


def ensure_table(db_conn) -> None:
    with db_conn.cursor() as cur:
        cur.execute(DDL)
    db_conn.commit()


def _ftp_for_date(db_conn, day: date, default: float = 245.0) -> float:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT ftp_est_w FROM qbot_v2.fitmodel_daily "
            "WHERE ftp_est_w IS NOT NULL AND day <= %s ORDER BY day DESC LIMIT 1",
            (day,),
        )
        row = cur.fetchone()
        if row and row[0]:
            return float(row[0])
        cur.execute("SELECT value FROM qbot_v2.fitmodel_param WHERE key='ftp_anchor_w'")
        row = cur.fetchone()
        if row and row[0]:
            return float(row[0])
    return default


def _existing_ride_ids(db_conn) -> set[str]:
    with db_conn.cursor() as cur:
        cur.execute("SELECT ride_id FROM qbot_v2.fitmodel_ride_buckets")
        return {r[0] for r in cur.fetchall()}


def process_rides(db_conn, only_new: bool = True, dry_run: bool = False,
                  kj_gate: float = 1500.0) -> list[dict]:
    ensure_table(db_conn)
    existing = _existing_ride_ids(db_conn) if only_new else set()
    results: list[dict] = []

    for fit_file in sorted(FIT_DIR.glob("*.fit")):
        ride_id = extract_ride_id(str(fit_file))
        if only_new and ride_id in existing:
            continue
        timeline = parse_fit_to_seconds(str(fit_file))
        if not timeline:
            continue
        power = [row.get("power") for row in timeline]
        if not any(p for p in power):
            continue  # FIT bez mocy (np. trening sily) — pomijamy
        started_at = timeline[0]["timestamp"]
        day = started_at.date() if isinstance(started_at, datetime) else date.today()
        ftp = _ftp_for_date(db_conn, day)
        b = compute_buckets(power, ftp, kj_gate=kj_gate)
        rec = {
            "ride_id": ride_id, "started_at": started_at,
            "low_strain": b["low"], "high_strain": b["high"],
            "peak_strain": b["peak"], "d_strain": b["d_strain"],
            "total_strain": b["total"], "ride_mode": None,
            "ftp_used_w": int(round(ftp)),
        }
        results.append({**rec, "pct": b["pct"], "kj": b["kj"]})

    if not dry_run and results:
        with db_conn.cursor() as cur:
            for r in results:
                cur.execute(
                    """
                    INSERT INTO qbot_v2.fitmodel_ride_buckets
                        (ride_id, started_at, low_strain, high_strain, peak_strain,
                         d_strain, total_strain, ride_mode, ftp_used_w)
                    VALUES (%(ride_id)s, %(started_at)s, %(low_strain)s, %(high_strain)s,
                            %(peak_strain)s, %(d_strain)s, %(total_strain)s,
                            %(ride_mode)s, %(ftp_used_w)s)
                    ON CONFLICT (ride_id) DO UPDATE SET
                        started_at=EXCLUDED.started_at, low_strain=EXCLUDED.low_strain,
                        high_strain=EXCLUDED.high_strain, peak_strain=EXCLUDED.peak_strain,
                        d_strain=EXCLUDED.d_strain, total_strain=EXCLUDED.total_strain,
                        ftp_used_w=EXCLUDED.ftp_used_w
                    """,
                    {k: r[k] for k in ("ride_id", "started_at", "low_strain",
                                       "high_strain", "peak_strain", "d_strain",
                                       "total_strain", "ride_mode", "ftp_used_w")},
                )
        db_conn.commit()
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="FITMODEL B2 -- ride buckets -> DB")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", help="przetworz rowniez juz zapisane")
    ap.add_argument("--kj-gate", type=float, default=1500.0)
    args = ap.parse_args()

    conn = _db_connect()
    try:
        res = process_rides(conn, only_new=not args.all, dry_run=args.dry_run,
                            kj_gate=args.kj_gate)
        print(f"{'DRY-RUN' if args.dry_run else 'ZAPIS'} -- {len(res)} jazd:")
        print(f"  {'ride':14} {'data':10} {'ftp':>4} {'LOW%':>5} {'HIGH%':>6} "
              f"{'PEAK%':>6} {'total':>7} {'D':>6}")
        for r in res:
            d = r["started_at"].date().isoformat() if isinstance(r["started_at"], datetime) else "?"
            print(f"  {r['ride_id'].split('.')[-1][-12:]:14} {d:10} {r['ftp_used_w']:>4} "
                  f"{r['pct']['low']:>5} {r['pct']['high']:>6} {r['pct']['peak']:>6} "
                  f"{r['total_strain']:>7} {r['d_strain']:>6}")
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM qbot_v2.fitmodel_ride_buckets")
            print("  wierszy w fitmodel_ride_buckets:", cur.fetchone()[0])
    finally:
        conn.close()
