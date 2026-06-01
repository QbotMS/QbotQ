#!/usr/bin/env python3
"""import_xert_profile_snapshot.py — Daily Xert profile snapshot import.

Harmonogram: codziennie 00:15 Europe/Warsaw przez cron.
Zapisuje jeden snapshot dziennie do qbot_v2.xert_profile_snapshots.

Usage:
    .venv/bin/python3 qbot3/connectors/import_xert_profile_snapshot.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

import httpx
import psycopg

try:
    import zoneinfo
    WARSAW = zoneinfo.ZoneInfo("Europe/Warsaw")
except Exception:
    from datetime import timedelta
    WARSAW = timezone(timedelta(hours=2))


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
    )


def _sf(v):
    """Safe float — returns None for None/0/empty."""
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def fetch_full_xert() -> dict | None:
    """Fetch FULL Xert API response + extracted fields."""
    email = os.getenv("XERT_EMAIL", "").strip()
    pwd = os.getenv("XERT_PASSWORD", "").strip()
    if not email or not pwd:
        print("  ERROR: XERT_EMAIL or XERT_PASSWORD not set", file=sys.stderr)
        return None

    with httpx.Client(timeout=5.0, trust_env=False) as client:
        token_resp = client.post(
            "https://www.xertonline.com/oauth/token",
            auth=("xert_public", "xert_public"),
            data={"grant_type": "password", "username": email, "password": pwd},
        )
        if token_resp.status_code != 200:
            print(f"  ERROR: token request failed (HTTP {token_resp.status_code})", file=sys.stderr)
            return None
        token = token_resp.json().get("access_token")
        if not token:
            print("  ERROR: no access_token in response", file=sys.stderr)
            return None

        training_resp = client.get(
            "https://www.xertonline.com/oauth/training",
            headers={"Authorization": f"Bearer {token}"},
        )
        if training_resp.status_code != 200:
            print(f"  ERROR: training request failed (HTTP {training_resp.status_code})", file=sys.stderr)
            return None

        raw = training_resp.json()

    if not isinstance(raw, dict) or not raw.get("success"):
        print(f"  ERROR: API returned success=false or unexpected type: {type(raw).__name__}", file=sys.stderr)
        return None

    advice = raw.get("advice", {})
    sig = advice.get("signature", {})
    ts = advice.get("training_status", {})
    at_state = advice.get("at_state", {})
    tomo = advice.get("tomorrow_status", {})

    extracted = {
        "ftp_watts": _sf(sig.get("ftp")),
        "ltp_watts": _sf(sig.get("ltp")),
        "w_prime_kj": round(_sf(sig.get("atc", 0)) / 1000, 1) if _sf(sig.get("atc")) else None,
        "peak_power_w": _sf(sig.get("pp")),
        "training_load": _sf(ts.get("tl_total")),
        "recovery_load": _sf(ts.get("rl_total")),
        "form_ratio": _sf(ts.get("form_ratio")),
        "ts_rating": _sf(ts.get("ts_rating")),
        "form_status": ts.get("form_cat") or advice.get("form_cat"),
        "freshness": _sf(at_state.get("form")),
        "fatigue": _sf(tomo.get("tl_total")),
        "strain": None,
        "difficulty": _sf(advice.get("difficulty")),
        "raw_json": raw,
    }
    return extracted


def get_today_daily_cron(cur) -> tuple | None:
    """Return existing daily_cron record for today, or None.
    Returns (id, training_load, quality_status) or None."""
    today = datetime.now(WARSAW).date()
    cur.execute(
        "SELECT id, training_load, quality_status FROM qbot_v2.xert_profile_snapshots "
        "WHERE date=%s AND source='daily_cron' ORDER BY snapshot_at DESC LIMIT 1",
        (today,),
    )
    return cur.fetchone()


def is_expanded(row: tuple | None) -> bool:
    """A record is 'expanded' if training_load (index 1) is not NULL."""
    return row is not None and row[1] is not None


def main():
    ts = datetime.now(timezone.utc)
    print(f"[{ts.isoformat()}] Xert profile snapshot import (expanded)")

    # Fetch full data
    print("  Fetching Xert API (full response)...")
    data = fetch_full_xert()
    if data is None:
        print("  FAILED: Xert API returned no data")
        sys.exit(1)

    ftp = data.get("ftp_watts")
    ltp = data.get("ltp_watts")
    wp = data.get("w_prime_kj")
    pp = data.get("peak_power_w")
    tl = data.get("training_load")
    rl = data.get("recovery_load")
    fr = data.get("form_ratio")
    tsr = data.get("ts_rating")
    fs = data.get("form_status")
    fresh = data.get("freshness")
    fat = data.get("fatigue")
    diff = data.get("difficulty")

    print(f"  FTP={ftp}, LTP={ltp}, W'={wp}, PP={pp}")
    print(f"  TL={tl:.1f}, RL={rl:.1f}, form_ratio={fr}, ts_rating={tsr}")
    print(f"  form_status={fs}, freshness={fresh}, fatigue={fat}, difficulty={diff}")

    if ftp is None:
        print("  FAILED: no FTP in response")
        sys.exit(1)

    # Write / Update DB
    now_utc = datetime.now(timezone.utc)
    now_warsaw = datetime.now(WARSAW)
    today_warsaw = now_warsaw.date()
    raw = json.dumps(data["raw_json"], default=str)

    with _conn() as conn, conn.cursor() as cur:
        existing = get_today_daily_cron(cur)

        if is_expanded(existing):
            print(f"  Expanded daily_cron already exists for {today_warsaw} — skipping")
            return

        if existing:
            # Sparse record exists — UPDATE it with expanded fields
            cur.execute(
                """UPDATE qbot_v2.xert_profile_snapshots
                   SET snapshot_at=%s, ftp_power_w=%s, ltp_power_w=%s, w_prime_kj=%s,
                       peak_power_w=%s, training_load=%s, recovery_load=%s,
                       form_ratio=%s, ts_rating=%s, form_status=%s,
                       freshness=%s, fatigue=%s, difficulty=%s,
                       quality_status='full', raw_json=%s, imported_at=%s
                   WHERE id=%s""",
                (now_utc, ftp, ltp, wp, pp, tl, rl, fr, tsr, fs,
                 fresh, fat, diff, raw, now_utc, existing[0]),
            )
            print(f"  Sparse daily_cron UPDATED with expanded fields for {today_warsaw}")
        else:
            # New record — INSERT with expanded fields
            cur.execute(
                """INSERT INTO qbot_v2.xert_profile_snapshots
                   (snapshot_at, date, source,
                    ftp_power_w, ltp_power_w, w_prime_kj, peak_power_w,
                    training_load, recovery_load, form_ratio, ts_rating,
                    form_status, freshness, fatigue, difficulty,
                    quality_status, raw_json, imported_at)
                   VALUES (%s, %s, %s,
                           %s, %s, %s, %s,
                           %s, %s, %s, %s,
                           %s, %s, %s, %s,
                           %s, %s, %s)""",
                (now_utc, today_warsaw, "daily_cron",
                 ftp, ltp, wp, pp,
                 tl, rl, fr, tsr,
                 fs, fresh, fat, diff,
                 "full", raw, now_utc),
            )
            print(f"  New snapshot saved: {today_warsaw}")
        conn.commit()

    print("  Done.")


if __name__ == "__main__":
    main()
