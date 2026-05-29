#!/usr/bin/env python3
"""Import historycznych danych żywienia z komentarzy Intervals.icu do DB.

Zakres: 2026-05-04 do 2026-05-25.

Dane są w polu `comments` wellness API w formacie:
    🍽️ Zjedzone: N kcal | B:Ng W:Ng T:Ng

Użycie:
    python -m qbot.tools.import_intervals_nutrition_comments \\
        --from 2026-05-04 --to 2026-05-25

    python -m qbot.tools.import_intervals_nutrition_comments \\
        --from 2026-05-04 --to 2026-05-25 --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

import httpx
from dotenv import load_dotenv

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, APP_DIR)

load_dotenv(os.path.join(APP_DIR, ".env"))


NUTRITION_RE = re.compile(
    r"Zjedzone:\s*([\d.]+)\s*kcal\s*\|\s*"
    r"B:\s*([\d.]+)g\s+"
    r"W:\s*([\d.]+)g\s+"
    r"T:\s*([\d.]+)g",
    re.I,
)


def _parse_nutrition(comments: str) -> dict | None:
    """Wyciąga dane żywieniowe z komentarza Intervals.

    Format: 🍽️ Zjedzone: 2561 kcal | B:150g W:278g T:108g
    """
    m = NUTRITION_RE.search(comments)
    if not m:
        return None
    return {
        "kcal_total": round(float(m.group(1)), 1),
        "protein_g": round(float(m.group(2)), 1),
        "carbs_g": round(float(m.group(3)), 1),
        "fat_g": round(float(m.group(4)), 1),
    }


def _fetch_intervals(from_date: str, to_date: str) -> list[dict]:
    """Pobiera dane wellness z Intervals.icu dla zakresu dat."""
    api_key = os.getenv("INTERVALS_API_KEY", "")
    athlete_id = os.getenv("INTERVALS_ATHLETE_ID", "")
    if not api_key or not athlete_id:
        print("Brak INTERVALS_API_KEY lub INTERVALS_ATHLETE_ID w .env", file=sys.stderr)
        sys.exit(1)

    encoded = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    headers = {"Authorization": f"Basic {encoded}"}
    params = {"oldest": from_date, "newest": to_date}

    r = httpx.get(
        f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness",
        params=params,
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _insert_to_db(day: str, nutrition: dict, dry_run: bool) -> dict:
    """Zapisuje wpis żywieniowy do meal_logs + meal_log_items."""
    from qbot_nutrition_db import meal_log_create, daily_summary_compute

    eaten_at = f"{day}T12:00:00+02:00"
    note = (
        f"Intervals historyczny import: "
        f"{nutrition['kcal_total']} kcal | "
        f"B:{nutrition['protein_g']}g W:{nutrition['carbs_g']}g T:{nutrition['fat_g']}g"
    )
    items = [
        {
            "food_name": "intervals_import",
            "amount": 1,
            "unit": "szt",
            "kcal": nutrition["kcal_total"],
            "carbs_g": nutrition["carbs_g"],
            "protein_g": nutrition["protein_g"],
            "fat_g": nutrition["fat_g"],
        },
    ]

    if dry_run:
        return {"day": day, "status": "DRY_RUN", "nutrition": nutrition, "note": note}

    meal = meal_log_create(
        meal_type="meal",
        note=note,
        context="intervals_import",
        eaten_at=eaten_at,
        items=items,
    )

    # Recompute daily summary — usuń starą przed INSERT (daily_summary_compute nie ma UPSERT)
    try:
        import psycopg
        conn = psycopg.connect(
            host=os.getenv("PGHOST", "127.0.0.1"),
            dbname=os.getenv("PGDATABASE", "qbot"),
            user=os.getenv("PGUSER", "qbot"),
            password=os.getenv("PGPASSWORD", ""),
        )
        conn.execute("DELETE FROM nutrition_daily_summary WHERE date = %s AND source = 'qbot'", (day,))
        conn.commit()
        conn.close()
    except Exception:
        pass

    daily_summary_compute(day)
    return {"day": day, "status": "OK", "meal_id": meal.get("id") if isinstance(meal, dict) else None}


def main():
    parser = argparse.ArgumentParser(description="Import nutrition data from Intervals.icu comments")
    parser.add_argument("--from", dest="date_from", default="2026-05-04", help="Początek zakresu (YYYY-MM-DD)")
    parser.add_argument("--to", dest="date_to", default="2026-05-25", help="Koniec zakresu (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Tylko pokaż co zostanie zaimportowane")
    args = parser.parse_args()

    print(f"Pobieranie danych Intervals.icu: {args.date_from} → {args.date_to}")
    records = _fetch_intervals(args.date_from, args.date_to)
    print(f"Pobrano {len(records)} rekordów wellness")

    imported = 0
    skipped = 0
    errors = 0

    for rec in records:
        day = rec.get("id", "")
        comments = (rec.get("comments") or "").strip()
        if not comments:
            skipped += 1
            continue

        nutrition = _parse_nutrition(comments)
        if not nutrition:
            skipped += 1
            continue

        result = _insert_to_db(day, nutrition, args.dry_run)
        if result.get("status") == "OK":
            imported += 1
            print(f"  ✅ {day}: {nutrition['kcal_total']} kcal (B:{nutrition['protein_g']} W:{nutrition['carbs_g']} T:{nutrition['fat_g']})")
        elif result.get("status") == "DRY_RUN":
            imported += 1
            print(f"  📋 {day}: {nutrition['kcal_total']} kcal (dry-run)")
        else:
            errors += 1
            print(f"  ❌ {day}: {result}")

    print()
    print(f"Podsumowanie ({'DRY-RUN' if args.dry_run else 'IMPORT'}):")
    print(f"  Zaimportowano: {imported}")
    print(f"  Pominięto (brak danych): {skipped}")
    print(f"  Błędy: {errors}")
    print(f"  Zakres: {args.date_from} → {args.date_to}")

    if args.dry_run and imported:
        print()
        print("Uruchom bez --dry-run aby zapisać do DB.")


if __name__ == "__main__":
    main()
