#!/usr/bin/env python3
"""fix_intervals_2026-05-26.py — Naprawia błędne 425 kcal na 2126 kcal z Intervals comment.

Użycie:
    python3 scripts/fix_intervals_2026-05-26.py

Co robi:
1. Ładuje komentarz Intervals dla 2026-05-26 (lub używa przykładowego tekstu)
2. Parsuje go zaktualizowanym _parse_comment_for_nutrition()
3. Zapisuje poprawny intake (2126 kcal) do qbot_nutrition_daily
4. Zapisuje surowy komentarz do qbot_wellness_notes
5. Aktualizuje daily_summary dla 2026-05-26
6. Test: porównuje przed/po
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
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


def fetch_intervals_comment(target_date: str) -> str | None:
    """Fetch wellness comment from Intervals API for target_date."""
    import base64
    import httpx
    from dotenv import load_dotenv
    load_dotenv(APP_DIR / ".env")

    api_key = os.getenv("INTERVALS_API_KEY", "")
    athlete_id = os.getenv("INTERVALS_ATHLETE_ID", "")
    if not api_key or not athlete_id:
        return None

    encoded = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    headers = {"Authorization": f"Basic {encoded}"}

    r = httpx.get(
        f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness",
        params={"oldest": target_date, "newest": target_date},
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data and isinstance(data, list) and len(data) > 0:
        return data[0].get("comments", "")
    return None


def main():
    from qbot_wellness_store import _parse_comment_for_nutrition

    target = "2026-05-26"
    print(f"=== Fix Intervals nutrition for {target} ===\n")

    # 1. Get comment
    comment = fetch_intervals_comment(target)
    if not comment:
        print("  Intervals API nie zwrócił komentarza, używam przykładowego.")
        comment = "🍽️ Zjedzone: 2126 kcal | B:140g W:198g T:81g\n🔥 Spalone: 3221 kcal (BMR:2287 + aktywne:934)\n⚖️ Bilans: -1095 kcal"

    print(f"  Comment:\n{comment}\n")

    # 2. Parse
    nutrition = _parse_comment_for_nutrition(comment)
    if not nutrition:
        print("  ERROR: parser nie zwrócił danych")
        sys.exit(1)

    print("  Parsed nutrition:")
    for k, v in nutrition.items():
        print(f"    {k}: {v}")
    print()

    expected = {
        "calories_kcal": 2126.0,
        "protein_g": 140.0,
        "carbs_g": 198.0,
        "fat_g": 81.0,
        "calories_burned_kcal": 3221.0,
        "bmr_kcal": 2287.0,
        "active_kcal": 934.0,
        "balance_kcal": -1095.0,
    }

    all_ok = True
    for k, v in expected.items():
        got = nutrition.get(k)
        if got != v:
            print(f"  ❌ MISMATCH {k}: expected {v}, got {got}")
            all_ok = False

    if all_ok:
        print("  ✅ Wszystkie pola zgadzają się z oczekiwanymi wartościami")
    print()

    # 3. Show before state
    before = {}
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT intake_kcal, intake_protein_g, intake_carbs_g, intake_fat_g, "
                    "expenditure_total, expenditure_resting, expenditure_active, "
                    "balance_kcal, intake_quality, intake_source, balance_quality "
                    "FROM qbot_v2.daily_summary WHERE date = %s", (target,))
        row = cur.fetchone()
        if row:
            cols = [d[0] for d in cur.description]
            before = dict(zip(cols, row))

    print("  BEFORE daily_summary:")
    for k, v in before.items():
        print(f"    {k}: {v}")
    print()

    # 4. Write to qbot_nutrition_daily (UPSERT)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO qbot_nutrition_daily (date, source, calories_kcal,
                carbs_g, protein_g, fat_g, raw_text, raw_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, source) DO UPDATE SET
                calories_kcal = EXCLUDED.calories_kcal,
                carbs_g = EXCLUDED.carbs_g,
                protein_g = EXCLUDED.protein_g,
                fat_g = EXCLUDED.fat_g,
                raw_text = EXCLUDED.raw_text,
                raw_json = EXCLUDED.raw_json,
                imported_at = now()
        """, (target, "intervals_comment_mfp",
              nutrition["calories_kcal"],
              nutrition["carbs_g"],
              nutrition["protein_g"],
              nutrition["fat_g"],
              comment,
              json.dumps(nutrition, ensure_ascii=False, default=str)))
        conn.commit()
        print(f"  ✅ Zapisano do qbot_nutrition_daily ({cur.rowcount} rows)")

    # 5. Write to qbot_wellness_notes
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO qbot_wellness_notes (date, source, note_type, text, source_record_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (date, source, note_type, text) DO NOTHING
        """, (target, "intervals_comment", "intervals_comment", comment, target))
        conn.commit()
        print(f"  ✅ Zapisano do qbot_wellness_notes ({cur.rowcount} rows)")

    # 6. Update daily_summary with correct values
    intake_kcal = nutrition["calories_kcal"]
    protein = nutrition.get("protein_g")
    carbs = nutrition.get("carbs_g")
    fat = nutrition.get("fat_g")
    expenditure = nutrition.get("calories_burned_kcal")
    resting = nutrition.get("bmr_kcal")
    active = nutrition.get("active_kcal")
    balance = nutrition.get("balance_kcal")

    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE qbot_v2.daily_summary
            SET intake_kcal = %s,
                intake_protein_g = %s,
                intake_carbs_g = %s,
                intake_fat_g = %s,
                intake_quality = 'imported',
                intake_source = 'intervals_comments',
                expenditure_total = COALESCE(%s, expenditure_total),
                expenditure_resting = COALESCE(%s, expenditure_resting),
                expenditure_active = COALESCE(%s, expenditure_active),
                balance_kcal = %s,
                balance_quality = CASE WHEN %s IS NOT NULL THEN 'full' ELSE balance_quality END,
                balance_note = CASE WHEN %s IS NOT NULL THEN NULL ELSE balance_note END,
                updated_at = now()
            WHERE date = %s
        """, (intake_kcal, protein, carbs, fat,
              expenditure, resting, active,
              balance, balance, balance,
              target))
        conn.commit()
        print(f"  ✅ Zaktualizowano daily_summary ({cur.rowcount} rows)")

    print()

    # 7. Show after state
    after = {}
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT intake_kcal, intake_protein_g, intake_carbs_g, intake_fat_g, "
                    "expenditure_total, expenditure_resting, expenditure_active, "
                    "balance_kcal, intake_quality, intake_source, balance_quality "
                    "FROM qbot_v2.daily_summary WHERE date = %s", (target,))
        row = cur.fetchone()
        if row:
            cols = [d[0] for d in cur.description]
            after = dict(zip(cols, row))

    print("  AFTER daily_summary:")
    for k, v in after.items():
        print(f"    {k}: {v}")
    print()

    # Verify
    if after.get("intake_kcal") == 2126.0:
        print("✅ NAPRAWA UDAŁA SIĘ: daily_summary dla 2026-05-26 pokazuje 2126 kcal")
    else:
        print(f"❌ NAPRAWA NIEUDANA: daily_summary pokazuje {after.get('intake_kcal')} kcal")

    return 0


if __name__ == "__main__":
    sys.exit(main())
