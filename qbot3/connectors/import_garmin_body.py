#!/usr/bin/env python3
"""import_garmin_body.py — Daily Garmin body composition import.

Źródła:
  - INDEX_SCALE (Garmin Index Scale): pełne body comp → source='garmin_index_scale'
  - MFP (MyFitnessPal sync): weight-only fallback → source='garmin_mfp'

Priorytet:
  INDEX_SCALE zawsze wygrywa z MFP dla tej samej daty.
  MFP zapisywany tylko jeśli INDEX_SCALE nie istnieje dla tej daty.

Usage:
    .venv/bin/python qbot3/connectors/import_garmin_body.py
    .venv/bin/python qbot3/connectors/import_garmin_body.py --days 7
    .venv/bin/python qbot3/connectors/import_garmin_body.py --days 30 --diagnose
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

import psycopg
from garminconnect import Garmin


def _garmin_client():
    email = os.getenv("GARMIN_EMAIL", "").strip()
    password = os.getenv("GARMIN_PASSWORD", "").strip()
    tokenstore = os.getenv("GARMIN_TOKENSTORE", "/opt/qbot/app/.garmin_tokens")
    g = Garmin(email, password)
    g.login(tokenstore=tokenstore)
    return g


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
    )


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def fetch_garmin_raw(days_back: int) -> dict:
    """Call Garmin get_weigh_ins (range endpoint with includeAll=true, gives full INDEX_SCALE data).

    NEVER używa get_body_composition (dateRange endpoint), który zwraca tylko MFP weight-only.
    """
    g = _garmin_client()
    end = date.today()
    start = (end - timedelta(days=days_back)).isoformat()
    end_s = end.isoformat()

    # Use get_weigh_ins (range endpoint with includeAll=true) for full body comp
    raw = g.get_weigh_ins(start, end_s)

    # Collect all entries from dailyWeightSummaries
    summaries = raw.get("dailyWeightSummaries", []) if isinstance(raw, dict) else []
    raw_entries: list[dict] = []
    for day in summaries:
        lw = day.get("latestWeight")
        if lw:
            raw_entries.append(lw)
        for extra in day.get("allWeightMetrics", []):
            if extra.get("samplePk") != (lw or {}).get("samplePk"):
                raw_entries.append(extra)

    # Diagnostic counters
    st_count: Counter = Counter()
    full_bc = 0
    weight_only = 0
    parsed = []

    for entry in raw_entries:
        d = entry.get("calendarDate") or entry.get("date")
        if isinstance(d, str) and len(d) >= 10:
            d = d[:10]
        else:
            continue

        st = entry.get("sourceType", "UNKNOWN").upper()
        st_count[st] += 1

        w = _safe_float(entry.get("weight"))
        weight_kg = w / 1000.0 if (w and w > 500) else (w or 0)
        if weight_kg < 20 or weight_kg > 300:
            continue

        bmi = _safe_float(entry.get("bmi"))
        bf = _safe_float(entry.get("bodyFat"))
        bw = _safe_float(entry.get("bodyWater"))
        bm = _safe_float(entry.get("boneMass"))
        mm = _safe_float(entry.get("muscleMass"))
        smm = _safe_float(entry.get("skeletalMuscleMass"))
        if mm and mm > 500:
            mm = mm / 1000.0
        if smm and smm > 500:
            smm = smm / 1000.0
        if bm and bm > 500:
            bm = bm / 1000.0

        has_body_comp = bool(bmi or bf or bw or bm or mm)
        if has_body_comp:
            full_bc += 1
        else:
            weight_only += 1

        source = f"garmin_{st.lower()}" if st else "garmin_unknown"

        parsed.append({
            "date": d,
            "source": source,
            "source_type": st,
            "weight_kg": round(weight_kg, 2),
            "body_fat_pct": bf,
            "bmi": bmi,
            "body_water_pct": bw,
            "bone_mass_kg": bm,
            "muscle_mass_kg": mm,
            "skeletal_muscle_mass_kg": smm,
            "has_body_comp": has_body_comp,
            "raw_json": entry,
        })

    return {
        "diagnostics": {
            "days_with_data": len(summaries),
            "total_entries": len(raw_entries),
            "source_type_distribution": dict(st_count),
            "full_body_comp": full_bc,
            "weight_only": weight_only,
            "parsed_count": len(parsed),
        },
        "entries": parsed,
    }


def has_index_scale_for_date(cur, ds: str) -> bool:
    """Check if a INDEX_SCALE full record exists for this date."""
    cur.execute(
        "SELECT 1 FROM qbot_v2.body_measurements WHERE date=%s AND source_type='INDEX_SCALE'",
        (ds,),
    )
    return cur.fetchone() is not None


def _compute_quality(e: dict) -> tuple[str, int]:
    """Return (quality_status, completeness_score)."""
    has_bc = any(e.get(k) is not None for k in ("bmi", "body_fat_pct", "body_water_pct", "muscle_mass_kg", "bone_mass_kg"))
    score = 1 if e.get("weight_kg") else 0
    for k in ("bmi", "body_fat_pct", "body_water_pct", "muscle_mass_kg", "bone_mass_kg"):
        if e.get(k) is not None:
            score += 1
    if has_bc and e.get("weight_kg"):
        return ("full_body_composition", score)
    if e.get("weight_kg"):
        return ("weight_only", score)
    return ("partial", score)


def _ensure_schema(cur):
    """Add columns if they don't exist yet."""
    for col, col_type in [
        ("skeletal_muscle_mass_kg", "DOUBLE PRECISION"),
        ("visceral_fat", "DOUBLE PRECISION"),
        ("metabolic_age", "DOUBLE PRECISION"),
        ("physique_rating", "DOUBLE PRECISION"),
    ]:
        cur.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='qbot_v2' AND table_name='body_measurements'
                    AND column_name='{col}'
                ) THEN
                    ALTER TABLE qbot_v2.body_measurements ADD COLUMN {col} {col_type};
                END IF;
            END $$;
        """)


def write_to_body_measurements(entries: list[dict]) -> dict:
    inserted = 0
    updated = 0
    skipped_mfp = 0
    errors = 0
    accepted = 0

    with _conn() as conn, conn.cursor() as cur:
        _ensure_schema(cur)
        for e in entries:
            ds = e["date"]
            st = e["source_type"]
            raw = json.dumps(e.get("raw_json", {}))

            # Priority: INDEX_SCALE always wins. MFP only as fallback.
            if st == "MFP":
                if has_index_scale_for_date(cur, ds):
                    skipped_mfp += 1
                    continue

            qs, cs = _compute_quality(e)

            try:
                cur.execute(
                    """INSERT INTO qbot_v2.body_measurements
                       (date, weight_kg, bmi, body_fat_pct, body_water_pct,
                        muscle_mass_kg, skeletal_muscle_mass_kg, bone_mass_kg,
                        visceral_fat, metabolic_age, physique_rating,
                        source_system, source_type, quality_status,
                        completeness_score, raw_json, imported_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                       ON CONFLICT (date) DO UPDATE SET
                           weight_kg = EXCLUDED.weight_kg,
                           bmi = EXCLUDED.bmi,
                           body_fat_pct = EXCLUDED.body_fat_pct,
                           body_water_pct = EXCLUDED.body_water_pct,
                           muscle_mass_kg = EXCLUDED.muscle_mass_kg,
                           skeletal_muscle_mass_kg = EXCLUDED.skeletal_muscle_mass_kg,
                           bone_mass_kg = EXCLUDED.bone_mass_kg,
                           visceral_fat = EXCLUDED.visceral_fat,
                           metabolic_age = EXCLUDED.metabolic_age,
                           physique_rating = EXCLUDED.physique_rating,
                           quality_status = EXCLUDED.quality_status,
                           completeness_score = EXCLUDED.completeness_score,
                           raw_json = EXCLUDED.raw_json,
                           imported_at = now()""",
                    (ds, e["weight_kg"], e["bmi"], e["body_fat_pct"],
                     e["body_water_pct"], e["muscle_mass_kg"],
                     e.get("skeletal_muscle_mass_kg"), e["bone_mass_kg"],
                     e.get("visceral_fat"), e.get("metabolic_age"), e.get("physique_rating"),
                     "garmin", st, qs, cs, raw),
                )
                if cur.rowcount > 1:
                    updated += 1
                else:
                    inserted += 1
                accepted += 1
            except Exception as exc:
                print(f"    ERROR writing {ds} ({st}): {exc}", file=sys.stderr)
                errors += 1
        conn.commit()

    return {
        "accepted": accepted,
        "inserted": inserted,
        "updated": updated,
        "skipped_mfp": skipped_mfp,
        "errors": errors,
    }


def main():
    import argparse
    p = argparse.ArgumentParser(description="Import Garmin body composition to qbot_v2.body_daily")
    p.add_argument("--days", type=int, default=3, help="Days back to fetch")
    p.add_argument("--diagnose", action="store_true", default=False,
                   help="Print raw API diagnostics and exit without writing")
    args = p.parse_args()

    ts = datetime.now(timezone.utc)
    print(f"[{ts.isoformat()}] Garmin body composition import")
    print(f"  Fetching last {args.days} days...")

    result = fetch_garmin_raw(days_back=args.days)
    diag = result["diagnostics"]
    entries = result["entries"]

    print(f"  Days with data:     {diag['days_with_data']}")
    print(f"  Total entries:      {diag['total_entries']}")
    print(f"  SourceType dist:    {diag['source_type_distribution']}")
    print(f"  Full body comp:     {diag['full_body_comp']}")
    print(f"  Weight-only:        {diag['weight_only']}")
    print(f"  Parsed (valid):     {diag['parsed_count']}")

    if args.diagnose:
        print(f"\n  === DIAGNOSTIC MODE — no write ===")
        if entries:
            for e in entries:
                bc = "✓" if e["has_body_comp"] else "✗"
                print(f"  {e['date']} | {e['source']:25s} | {bc} body_comp"
                      f" | w={e['weight_kg']:>6.1f}"
                      f" | bf={e['body_fat_pct'] or '-':>5}"
                      f" | bmi={e['bmi'] or '-':>5}"
                      f" | mm={e['muscle_mass_kg'] or '-':>5}"
                      f" | bm={e['bone_mass_kg'] or '-':>5}"
                      f" | bw={e['body_water_pct'] or '-':>5}")
        print("  (no data written)")
        return

    if not entries:
        print("  No entries to import.")
        return

    # Filter to requested date range
    cutoff = date.today()
    min_date = cutoff - timedelta(days=args.days)
    entries = [e for e in entries if e["date"] >= min_date.isoformat()]

    print(f"  In range:           {len(entries)}")
    stats = write_to_body_measurements(entries)
    print(f"  Accepted:           {stats['accepted']}")
    print(f"  Inserted:           {stats['inserted']}")
    print(f"  Updated:            {stats['updated']}")
    print(f"  Skipped (MFP dup):  {stats['skipped_mfp']}")
    print(f"  Errors:             {stats['errors']}")

    for e in entries:
        qs, cs = (e.get("quality_status"), e.get("completeness_score")) if False else (None, None)
        qs, cs = "", 0
        st = "INDEX" if e["source_type"] == "INDEX_SCALE" else e["source_type"]
        bc = "✓" if e.get("has_body_comp") else "✗"
        print(f"  {e['date']} | {st:10s} | {bc}"
              f" | w={e['weight_kg']:>6.1f}"
              f" | bf={e['body_fat_pct'] or '-':>5}"
              f" | bmi={e['bmi'] or '-':>5}"
              f" | mm={e['muscle_mass_kg'] or '-':>5}"
              f" | bm={e['bone_mass_kg'] or '-':>5}"
              f" | bw={e['body_water_pct'] or '-':>5}")

    index_count = sum(1 for e in entries if e["source_type"] == "INDEX_SCALE")
    mfp_count = sum(1 for e in entries if e["source_type"] == "MFP")
    print(f"\n  Summary: {index_count} INDEX_SCALE, {mfp_count} MFP"
          f" ({stats['skipped_mfp']} MFP skipped due to existing INDEX_SCALE)")
    print(f"  Done. Log: /opt/qbot/logs/garmin_body_import.log")


if __name__ == "__main__":
    main()
