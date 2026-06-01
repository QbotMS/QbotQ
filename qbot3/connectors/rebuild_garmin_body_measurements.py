#!/usr/bin/env python3
"""rebuild_garmin_body_measurements.py — Rebuild canonical body measurements.

Pobiera WSZYSTKIE dane z Garmin Connect, deduplikuje per date (najlepszy
rekord wygrywa), zapisuje do qbot_v2.body_measurements_staging.
Po walidacji podmienia na qbot_v2.body_measurements.

Usage:
    .venv/bin/python3 qbot3/connectors/rebuild_garmin_body_measurements.py --days 180 --dry-run
    .venv/bin/python3 qbot3/connectors/rebuild_garmin_body_measurements.py --days 180 --apply
    .venv/bin/python3 qbot3/connectors/rebuild_garmin_body_measurements.py --from-date 2025-01-01 --to-date 2026-05-31 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))
import psycopg


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
    )


def _garmin_client():
    from garminconnect import Garmin
    email = os.getenv("GARMIN_EMAIL", "").strip()
    pwd = os.getenv("GARMIN_PASSWORD", "").strip()
    tokenstore = os.getenv("GARMIN_TOKENSTORE", "/opt/qbot/app/.garmin_tokens")
    g = Garmin(email, pwd)
    g.login(tokenstore=tokenstore)
    return g


def _sf(v):
    try: return float(v) if v is not None else None
    except: return None


def compute_completeness(entry: dict) -> int:
    """Score 0-5: weight=1 + each body comp field=1."""
    score = 1 if entry.get("weight_kg") else 0
    for k in ("bmi", "body_fat_pct", "body_water_pct", "muscle_mass_kg", "bone_mass_kg"):
        if entry.get(k) is not None:
            score += 1
    return score


def classify_quality(entry: dict) -> str:
    """Classify as full_body_composition, weight_only, or partial."""
    has_comp = any(entry.get(k) is not None for k in ("bmi", "body_fat_pct", "body_water_pct", "muscle_mass_kg", "bone_mass_kg"))
    if has_comp and entry.get("weight_kg") is not None:
        return "full_body_composition"
    if entry.get("weight_kg") is not None:
        return "weight_only"
    return "partial"


def extract_entries_from_day(day: dict) -> list[dict]:
    """Extract all entries from a dailyWeightSummary day dict.

    Returns list of raw entries with body comp fields normalized.
    """
    entries = []
    lw = day.get("latestWeight")
    if lw:
        entries.append(lw)
    for extra in day.get("allWeightMetrics", []):
        if extra.get("samplePk") != (lw or {}).get("samplePk"):
            entries.append(extra)
    return entries


def normalize_entry(entry: dict, default_date: str) -> dict | None:
    """Normalize a raw Garmin weight entry into canonical form.
    
    Returns None if weight is out of valid range.
    """
    w = _sf(entry.get("weight"))
    weight_kg = w / 1000.0 if (w and w > 500) else (w or 0)
    if weight_kg and (weight_kg < 20 or weight_kg > 300):
        return None

    st = entry.get("sourceType", "UNKNOWN").upper()
    bmi = _sf(entry.get("bmi"))
    bf = _sf(entry.get("bodyFat"))
    bw = _sf(entry.get("bodyWater"))
    bm = _sf(entry.get("boneMass"))
    mm = _sf(entry.get("muscleMass"))
    smm = _sf(entry.get("skeletalMuscleMass"))
    if mm and mm > 500:
        mm = mm / 1000.0
    if smm and smm > 500:
        smm = smm / 1000.0
    if bm and bm > 500:
        bm = bm / 1000.0

    return {
        "date": default_date,
        "weight_kg": round(weight_kg, 2) if weight_kg else None,
        "bmi": bmi,
        "body_fat_pct": bf,
        "body_water_pct": bw,
        "muscle_mass_kg": mm,
        "skeletal_muscle_mass_kg": smm,
        "bone_mass_kg": bm,
        "visceral_fat": _sf(entry.get("visceralFat")),
        "metabolic_age": _sf(entry.get("metabolicAge")),
        "physique_rating": _sf(entry.get("physiqueRating")),
        "source_type": st,
        "source_system": "garmin",
        "raw_json": entry,
    }


def fetch_garmin_all(days_back: int = 180, from_date: str | None = None, to_date: str | None = None) -> dict:
    """Fetch ALL body composition data from Garmin Connect using get_weigh_ins.

    Używa get_weigh_ins(start, end) → /weight-service/weight/range/{start}/{end}?includeAll=true
    zamiast get_body_composition, ponieważ /weight/range zwraca pełne dane INDEX_SCALE
    (bmi, bodyFat, bodyWater, boneMass, muscleMass).
    
    NEVER używa /weight/dateRange (get_body_composition), który zwraca tylko MFP weight-only.
    """
    g = _garmin_client()

    if from_date and to_date:
        start_d, end_d = from_date, to_date
    else:
        end_d = date.today().isoformat()
        start_d = (date.today() - timedelta(days=days_back)).isoformat()

    print(f"  Fetching Garmin get_weigh_ins: {start_d} → {end_d}")

    # Use get_weigh_ins (range endpoint with includeAll=true, NOT dateRange)
    raw = g.get_weigh_ins(start_d, end_d)

    summaries = raw.get("dailyWeightSummaries", []) if isinstance(raw, dict) else []
    print(f"  Days with data: {len(summaries)}")

    st_count: Counter = Counter()
    parsed: list[dict] = []

    for day in summaries:
        dt = day.get("summaryDate")
        if not dt:
            continue

        raw_entries = extract_entries_from_day(day)
        for entry in raw_entries:
            norm = normalize_entry(entry, dt)
            if norm is None:
                continue
            st_count[norm["source_type"]] += 1
            parsed.append(norm)

    # Deduplicate per date: keep best (highest completeness, then INDEX_SCALE > MFP)
    best_per_date: dict[str, dict] = {}
    for e in parsed:
        dt = e["date"]
        score = compute_completeness(e)
        # Prefer INDEX_SCALE over MFP for same score
        type_priority = 2 if e["source_type"] == "INDEX_SCALE" else 1
        e["_score"] = score
        e["_type_priority"] = type_priority
        if dt not in best_per_date:
            best_per_date[dt] = e
        else:
            cur = best_per_date[dt]
            if (score > cur["_score"]) or (score == cur["_score"] and type_priority > cur.get("_type_priority", 0)):
                best_per_date[dt] = e

    final = []
    for dt in sorted(best_per_date.keys(), reverse=True):
        e = best_per_date[dt]
        cs = e["_score"]
        qs = classify_quality(e)
        final.append({
            "date": dt,
            "weight_kg": e["weight_kg"],
            "bmi": e["bmi"],
            "body_fat_pct": e["body_fat_pct"],
            "body_water_pct": e["body_water_pct"],
            "muscle_mass_kg": e["muscle_mass_kg"],
            "skeletal_muscle_mass_kg": e.get("skeletal_muscle_mass_kg"),
            "bone_mass_kg": e["bone_mass_kg"],
            "visceral_fat": e.get("visceral_fat"),
            "metabolic_age": e.get("metabolic_age"),
            "physique_rating": e.get("physique_rating"),
            "source_system": "garmin",
            "source_type": e["source_type"],
            "quality_status": qs,
            "completeness_score": cs,
            "raw_json": e["raw_json"],
        })

    full_count = sum(1 for f in final if f["quality_status"] == "full_body_composition")
    wo_count = sum(1 for f in final if f["quality_status"] == "weight_only")

    return {
        "diagnostics": {
            "days_with_data": len(summaries),
            "total_parsed_entries": len(parsed),
            "source_type_distribution": dict(st_count),
            "final_days": len(final),
            "full_body_composition": full_count,
            "weight_only": wo_count,
        },
        "entries": final,
    }


def _ensure_staging_schema(cur):
    """Add columns to staging table if they don't exist yet."""
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
                    WHERE table_schema='qbot_v2' AND table_name='body_measurements_staging'
                    AND column_name='{col}'
                ) THEN
                    ALTER TABLE qbot_v2.body_measurements_staging ADD COLUMN {col} {col_type};
                END IF;
            END $$;
        """)


def write_staging(entries: list[dict], dry_run: bool = True) -> dict:
    """Write to body_measurements_staging."""
    if dry_run:
        return {"inserted": 0, "updated": 0, "mode": "dry-run"}

    inserted = 0
    updated = 0
    errors = 0
    now_ts = datetime.now(timezone.utc)

    with _conn() as conn, conn.cursor() as cur:
        # Ensure staging table has all columns
        _ensure_staging_schema(cur)
        # Clear staging
        cur.execute("TRUNCATE qbot_v2.body_measurements_staging")
        for e in entries:
            raw = json.dumps(e.get("raw_json", {}), default=str)
            try:
                cur.execute(
                    """INSERT INTO qbot_v2.body_measurements_staging
                       (date, weight_kg, bmi, body_fat_pct, body_water_pct,
                        muscle_mass_kg, skeletal_muscle_mass_kg, bone_mass_kg,
                        visceral_fat, metabolic_age, physique_rating,
                        source_system, source_type, quality_status,
                        completeness_score, raw_json, imported_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (e["date"], e["weight_kg"], e["bmi"], e["body_fat_pct"], e["body_water_pct"],
                     e["muscle_mass_kg"], e.get("skeletal_muscle_mass_kg"), e["bone_mass_kg"],
                     e.get("visceral_fat"), e.get("metabolic_age"), e.get("physique_rating"),
                     "garmin", e["source_type"], e["quality_status"],
                     e["completeness_score"], raw, now_ts),
                )
                inserted += 1
            except Exception as exc:
                print(f"    ERROR {e['date']}: {exc}", file=sys.stderr)
                errors += 1
        conn.commit()

    return {"inserted": inserted, "updated": updated, "errors": errors, "mode": "apply"}


def promote_staging(dry_run: bool = True) -> str:
    """Promote staging to body_measurements."""
    if dry_run:
        return "dry-run — no promote"

    with _conn() as conn, conn.cursor() as cur:
        # Add columns to production table if they don't exist yet
        _ensure_staging_schema(cur)  # these are on the staging table
        # Ensure production table has same columns as staging
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
        # Create production table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS qbot_v2.body_measurements (LIKE qbot_v2.body_measurements_staging INCLUDING ALL);
        """)
        # Clear and insert from staging
        cur.execute("TRUNCATE qbot_v2.body_measurements")
        cur.execute("INSERT INTO qbot_v2.body_measurements SELECT * FROM qbot_v2.body_measurements_staging")
        conn.commit()

    return "Promoted staging → body_measurements"


def main():
    p = argparse.ArgumentParser(description="Rebuild canonical body measurements from Garmin")
    p.add_argument("--days", type=int, default=180, help="Days back (default: 180)")
    p.add_argument("--from-date", help="Start date YYYY-MM-DD")
    p.add_argument("--to-date", help="End date YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true", default=True, help="Print only (default)")
    p.add_argument("--apply", action="store_true", default=False, help="Actually write + promote")
    args = p.parse_args()
    do_apply = args.apply
    do_dry = not do_apply

    print("=" * 70)
    print("Rebuild Garmin Body Measurements")
    print("=" * 70)

    # 1. Fetch
    result = fetch_garmin_all(
        days_back=args.days,
        from_date=args.from_date,
        to_date=args.to_date,
    )
    diag = result["diagnostics"]
    entries = result["entries"]

    print(f"\n  SourceType distribution: {diag['source_type_distribution']}")
    print(f"  Days with data:     {diag['days_with_data']}")
    print(f"  Parsed entries:     {diag['total_parsed_entries']}")
    print(f"  Final days:         {diag['final_days']} (after dedup)")
    print(f"  Full body comp:     {diag['full_body_composition']}")
    print(f"  Weight-only:        {diag['weight_only']}")

    # 2. Diagnostic output
    print(f"\n  --- Sample records (last 5 days) ---")
    for e in entries[:5]:
        print(f"  {e['date']} | {e['source_type']:12s} | {e['quality_status']:22s}"
              f" | score={e['completeness_score']} | w={e['weight_kg']}"
              f" | bf={e['body_fat_pct']} | bmi={e['bmi']}"
              f" | water={e['body_water_pct']} | muscle={e['muscle_mass_kg']}")

    # 3. Check 2026-05-31 specifically
    print(f"\n  --- Check 2026-05-31 ---")
    may31 = [e for e in entries if e["date"] == "2026-05-31"]
    if may31:
        e = may31[0]
        print(f"  Found: {e['quality_status']} | {e['source_type']} | score={e['completeness_score']}")
        print(f"    w={e['weight_kg']} bf={e['body_fat_pct']} bmi={e['bmi']} water={e['body_water_pct']}")
    else:
        print(f"  No data for 2026-05-31 in Garmin response")

    if do_dry:
        print(f"\n{'='*70}")
        print(f"DRY RUN — no data written")
        print(f"Run with --apply to write staging + promote")
        print(f"{'='*70}")
        return

    # 4. Write staging
    print(f"\n  Writing to body_measurements_staging...")
    stats = write_staging(entries, dry_run=False)
    print(f"  Inserted: {stats['inserted']}, Errors: {stats['errors']}")

    # 5. Promote
    print(f"  Promoting to body_measurements...")
    msg = promote_staging(dry_run=False)
    print(f"  {msg}")

    # 6. Verify
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM qbot_v2.body_measurements")
        cnt = cur.fetchone()[0]
        cur.execute("SELECT date, quality_status, source_type FROM qbot_v2.body_measurements ORDER BY date DESC LIMIT 5")
        rows = cur.fetchall()
    print(f"\n  Production table: {cnt} rows")
    for r in rows:
        print(f"    {r[0]} | {str(r[1]):22s} | {r[2]}")

    print(f"\n{'='*70}")
    print(f"APPLY COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
