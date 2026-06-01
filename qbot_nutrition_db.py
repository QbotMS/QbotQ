#!/usr/bin/env python3
"""QBot Nutrition DB — PostgreSQL CRUD for food_items, meal_logs, hydration, fueling."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

_DB_CONNECT_TIMEOUT_SEC = int(os.getenv("PG_CONNECT_TIMEOUT", "5"))


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=_DB_CONNECT_TIMEOUT_SEC,
    )




def _serialize_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    result = {}
    for key, value in row.items():
        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def _serialize_rows(rows: list[dict]) -> list[dict]:
    return [_serialize_row(r) for r in rows if r]


def _normalize_day_input(day_value: str | date | datetime | None) -> date | None:
    """Normalize user/date inputs to a real date object.

    Accepts ISO dates, ISO datetimes, and common Polish day-first forms like
    `29.05` or `29.05.2026`. A day-month form without year uses the current year.
    """
    if day_value is None:
        return None
    if isinstance(day_value, date) and not isinstance(day_value, datetime):
        return day_value
    if isinstance(day_value, datetime):
        return day_value.date()

    raw = str(day_value).strip()
    if not raw:
        return None

    raw = raw.replace("/", ".")
    if "T" in raw:
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            pass

    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass

    for fmt in ("%d.%m.%Y", "%d.%m"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            if fmt == "%d.%m":
                parsed = parsed.replace(year=date.today().year)
            return parsed
        except ValueError:
            continue
    return None


def ping() -> bool:
    try:
        with _conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


# ── Food Items ────────────────────────────────────────────────────────────

def food_item_create(
    name: str,
    *,
    brand: str | None = None,
    default_unit: str = "g",
    kcal_per_100g: float | None = None,
    carbs_per_100g: float | None = None,
    sugar_per_100g: float | None = None,
    protein_per_100g: float | None = None,
    fat_per_100g: float | None = None,
    fiber_per_100g: float | None = None,
    sodium_per_100g: float | None = None,
    source: str = "qbot",
    verified: bool = False,
) -> dict:
    with _conn() as conn:
        row = conn.execute(
            """INSERT INTO qbot_v2.food_items (name, brand, default_unit, kcal_per_100g, carbs_per_100g,
               sugar_per_100g, protein_per_100g, fat_per_100g, fiber_per_100g, sodium_per_100g,
               source, verified)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (name) DO UPDATE SET
               kcal_per_100g = COALESCE(EXCLUDED.kcal_per_100g, food_items.kcal_per_100g),
               carbs_per_100g = COALESCE(EXCLUDED.carbs_per_100g, food_items.carbs_per_100g),
               protein_per_100g = COALESCE(EXCLUDED.protein_per_100g, food_items.protein_per_100g),
               fat_per_100g = COALESCE(EXCLUDED.fat_per_100g, food_items.fat_per_100g),
                sodium_per_100g = COALESCE(EXCLUDED.sodium_per_100g, food_items.sodium_per_100g),
                source = EXCLUDED.source
                RETURNING *""",
            (name, brand, default_unit, kcal_per_100g, carbs_per_100g, sugar_per_100g,
             protein_per_100g, fat_per_100g, fiber_per_100g, sodium_per_100g, source, verified),
        ).fetchone()
        conn.commit()
        return _serialize_row(dict(row))


def food_item_search(query: str, limit: int = 20) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM qbot_v2.food_items
               WHERE name ILIKE %s OR brand ILIKE %s
               ORDER BY name LIMIT %s""",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return _serialize_rows(rows)


def food_item_get_by_name(name: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM qbot_v2.food_items WHERE name ILIKE %s LIMIT 1", (name,)
        ).fetchone()
        return _serialize_row(dict(row)) if row else None


def food_item_list(limit: int = 50, offset: int = 0) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM qbot_v2.food_items ORDER BY name LIMIT %s OFFSET %s", (limit, offset)
        ).fetchall()
        return _serialize_rows(rows)


# ── Meal Logs ─────────────────────────────────────────────────────────────

def meal_log_create(
    meal_type: str = "meal",
    note: str | None = None,
    context: str | None = None,
    eaten_at: str | None = None,
    items: list[dict] | None = None,
) -> dict:
    eaten_dt = datetime.fromisoformat(eaten_at) if eaten_at else datetime.now()
    items = items or []
    with _conn() as conn:
        meal = conn.execute(
            """INSERT INTO qbot_v2.meal_logs (eaten_at, meal_type, note, context)
               VALUES (%s, %s, %s, %s) RETURNING *""",
            (eaten_dt, meal_type, note, context),
        ).fetchone()
        meal_id = meal["id"]
        for item in items:
            food = item.get("food")
            food_id = None
            if food:
                lookup = food_item_get_by_name(food)
                if lookup:
                    food_id = lookup["id"]
            conn.execute(
                """INSERT INTO qbot_v2.meal_log_items (meal_log_id, food_item_id, food_name, amount, unit,
                   kcal, carbs_g, protein_g, fat_g, fiber_g, sodium_mg)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    meal_id,
                    food_id,
                    food or item.get("food_name", "unknown"),
                    item.get("amount", 0),
                    item.get("unit", "g"),
                    item.get("kcal"),
                    item.get("carbs_g"),
                    item.get("protein_g"),
                    item.get("fat_g"),
                    item.get("fiber_g"),
                    item.get("sodium_mg"),
                ),
            )
        conn.commit()

        # Równoległy zapis do qbot_v2
        try:
            import os, psycopg
            from psycopg.rows import dict_row
            from datetime import timezone
            v2 = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"),
                port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"),
                user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""),
                row_factory=dict_row,
                connect_timeout=3,
            )
            eaten_date = eaten_dt.date() if hasattr(eaten_dt, 'date') else eaten_dt
            with v2:
                v2.execute(
                    "INSERT INTO qbot_v2.days (date) VALUES (%s) ON CONFLICT DO NOTHING",
                    (eaten_date,)
                )
                v2_log = v2.execute(
                    """INSERT INTO qbot_v2.intake_logs
                       (date, eaten_at, meal_type, note, source, quality_status)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (eaten_date, eaten_dt, meal_type, note,
                     'chatgpt_mcp', 'manual'),
                ).fetchone()
                v2_log_id = v2_log["id"]
                for item in items:
                    v2.execute(
                        """INSERT INTO qbot_v2.intake_items
                           (intake_log_id, food_name, amount, unit,
                            kcal, protein_g, carbs_g, fat_g, fiber_g, sodium_mg)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            v2_log_id,
                            item.get("food") or item.get("food_name", "unknown"),
                            item.get("amount", 0),
                            item.get("unit", "g"),
                            item.get("kcal"),
                            item.get("protein_g"),
                            item.get("carbs_g"),
                            item.get("fat_g"),
                            item.get("fiber_g"),
                            item.get("sodium_mg"),
                        ),
                    )
            v2.close()
        except Exception as _v2_err:
            pass  # v2 zapis nigdy nie blokuje v1

    return get_meal_log(meal_id)


def intake_log_create(
    meal_type: str = "meal",
    note: str | None = None,
    context: str | None = None,
    eaten_at: str | None = None,
    items: list[dict] | None = None,
    *,
    source: str = "qbot3",
    quality_status: str = "manual",
) -> dict:
    """Create a nutrition log in qbot_v2 only.

    This is the qbot3 runtime path. It deliberately avoids the legacy public
    meal_logs/meal_log_items mirror so read-after-write can validate qbot_v2
    as the source of truth.
    """
    eaten_dt = datetime.fromisoformat(eaten_at) if eaten_at else datetime.now()
    eaten_date = eaten_dt.date()
    items = items or []

    with _conn() as conn:
        conn.execute(
            "INSERT INTO qbot_v2.days (date) VALUES (%s) ON CONFLICT DO NOTHING",
            (eaten_date,),
        )
        meal = conn.execute(
            """INSERT INTO qbot_v2.intake_logs
               (date, eaten_at, meal_type, note, source, quality_status)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (eaten_date, eaten_dt, meal_type, note, source, quality_status),
        ).fetchone()
        meal_id = meal["id"]
        inserted_items: list[dict] = []
        for item in items:
            food = item.get("food") or item.get("food_name", "unknown")
            food_id = None
            if food:
                lookup = food_item_get_by_name(str(food))
                if lookup:
                    food_id = lookup["id"]
            row = conn.execute(
                """INSERT INTO qbot_v2.intake_items
                   (intake_log_id, food_item_id, food_name, amount, unit,
                    kcal, protein_g, carbs_g, fat_g, fiber_g, sodium_mg, source)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING *""",
                (
                    meal_id,
                    food_id,
                    food,
                    item.get("amount", 0),
                    item.get("unit", "g"),
                    item.get("kcal"),
                    item.get("protein_g"),
                    item.get("carbs_g"),
                    item.get("fat_g"),
                    item.get("fiber_g"),
                    item.get("sodium_mg"),
                    source,
                ),
            ).fetchone()
            inserted_items.append(dict(row))
        conn.commit()

    result = _serialize_row(dict(meal))
    result["items"] = _serialize_rows(inserted_items)
    return result


def get_meal_log(meal_id: int) -> dict | None:
    with _conn() as conn:
        meal = conn.execute(
            "SELECT * FROM qbot_v2.meal_logs WHERE id = %s", (meal_id,)
        ).fetchone()
        if not meal:
            return None
        items = conn.execute(
            "SELECT * FROM qbot_v2.meal_log_items WHERE meal_log_id = %s ORDER BY id", (meal_id,)
        ).fetchall()
        result = _serialize_row(dict(meal))
        result["items"] = _serialize_rows(items)
        return result


def meal_log_list(date_str: str | None = None, limit: int = 20) -> list[dict]:
    day = _normalize_day_input(date_str)
    with _conn() as conn:
        if day:
            rows = conn.execute(
                """SELECT * FROM qbot_v2.intake_logs
                   WHERE date = %s
                   ORDER BY eaten_at DESC LIMIT %s""",
                (day, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM qbot_v2.intake_logs ORDER BY eaten_at DESC LIMIT %s", (limit,)
            ).fetchall()
        result = []
        for meal in rows:
            items = conn.execute(
                "SELECT * FROM qbot_v2.intake_items WHERE intake_log_id = %s ORDER BY id",
                (meal["id"],),
            ).fetchall()
            d = _serialize_row(dict(meal))
            d["items"] = _serialize_rows(items)
            result.append(d)
        return result


def meal_log_delete(meal_id: int) -> dict | None:
    """Delete a meal log by ID (cascades to meal_log_items). Returns deleted meal or None."""
    with _conn() as conn:
        meal = get_meal_log(meal_id)
        if not meal:
            return None
        conn.execute("DELETE FROM qbot_v2.meal_log_items WHERE meal_log_id = %s", (meal_id,))
        conn.execute("DELETE FROM qbot_v2.meal_logs WHERE id = %s", (meal_id,))
        conn.commit()
        return meal


# ── Hydration ─────────────────────────────────────────────────────────────

def hydration_event_create(fluid_ml: float, sodium_mg: float = 0, source: str = "qbot", note: str | None = None, drank_at: str | None = None) -> dict:
    drank_dt = datetime.fromisoformat(drank_at) if drank_at else datetime.now()
    with _conn() as conn:
        row = conn.execute(
            """INSERT INTO qbot_v2.hydration_events (drank_at, fluid_ml, sodium_mg, source, note)
               VALUES (%s, %s, %s, %s, %s) RETURNING *""",
            (drank_dt, fluid_ml, sodium_mg, source, note),
        ).fetchone()
        conn.commit()
        return _serialize_row(dict(row))


def hydration_list(date_str: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        if date_str:
            rows = conn.execute(
                """SELECT * FROM qbot_v2.hydration_events WHERE drank_at::date = %s
                   ORDER BY drank_at DESC LIMIT %s""",
                (date_str, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM qbot_v2.hydration_events ORDER BY drank_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return _serialize_rows(rows)


# ── Fueling ───────────────────────────────────────────────────────────────

def fueling_event_create(carbs_g: float, source: str = "qbot", context: str | None = None, event_at: str | None = None) -> dict:
    event_dt = datetime.fromisoformat(event_at) if event_at else datetime.now()
    with _conn() as conn:
        row = conn.execute(
            """INSERT INTO qbot_v2.fueling_events (event_at, carbs_g, source, context)
               VALUES (%s, %s, %s, %s) RETURNING *""",
            (event_dt, carbs_g, source, context),
        ).fetchone()
        conn.commit()
        return _serialize_row(dict(row))


def fueling_list(date_str: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        if date_str:
            rows = conn.execute(
                """SELECT * FROM qbot_v2.fueling_events WHERE event_at::date = %s
                   ORDER BY event_at DESC LIMIT %s""",
                (date_str, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM qbot_v2.fueling_events ORDER BY event_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return _serialize_rows(rows)


# ── Daily Summary ─────────────────────────────────────────────────────────

def daily_summary_compute(date_str: str) -> dict:
    day = date.fromisoformat(date_str)
    with _conn() as conn:
        intake_count = conn.execute(
            "SELECT COUNT(*) AS n FROM qbot_v2.intake_logs WHERE date = %s",
            (day,),
        ).fetchone()["n"]
        if intake_count:
            meals = conn.execute(
                """SELECT COALESCE(SUM(ii.kcal), 0) AS kcal,
                   COALESCE(SUM(ii.carbs_g), 0) AS carbs,
                   COALESCE(SUM(ii.protein_g), 0) AS protein,
                   COALESCE(SUM(ii.fat_g), 0) AS fat,
                   COALESCE(SUM(ii.fiber_g), 0) AS fiber,
                   COALESCE(SUM(ii.sodium_mg), 0) AS sodium
                   FROM qbot_v2.intake_items ii
                   JOIN qbot_v2.intake_logs il ON il.id = ii.intake_log_id
                   WHERE il.date = %s""",
                (day,),
            ).fetchone()
        else:
            meals = conn.execute(
                """SELECT COALESCE(SUM(mli.kcal), 0) AS kcal,
                   COALESCE(SUM(mli.carbs_g), 0) AS carbs,
                   COALESCE(SUM(mli.protein_g), 0) AS protein,
                   COALESCE(SUM(mli.fat_g), 0) AS fat,
                   COALESCE(SUM(mli.fiber_g), 0) AS fiber,
                   COALESCE(SUM(mli.sodium_mg), 0) AS sodium
                   FROM qbot_v2.meal_log_items mli
                   JOIN qbot_v2.meal_logs ml ON ml.id = mli.meal_log_id
                   WHERE ml.eaten_at::date = %s""",
                (day,),
            ).fetchone()

        hyd = conn.execute(
            """SELECT COALESCE(SUM(fluid_ml), 0) AS fluids,
               COALESCE(SUM(sodium_mg), 0) AS sodium
               FROM qbot_v2.hydration_events WHERE drank_at::date = %s""",
            (day,),
        ).fetchone()

        fuel = conn.execute(
            "SELECT COALESCE(SUM(carbs_g), 0) AS carbs FROM qbot_v2.fueling_events WHERE event_at::date = %s",
            (day,),
        ).fetchone()

    kcal_total = (meals["kcal"] or 0)
    carbs_total = (meals["carbs"] or 0) + (fuel["carbs"] or 0)
    protein_total = (meals["protein"] or 0)
    fat_total = (meals["fat"] or 0)
    fiber_total = (meals["fiber"] or 0)
    sodium_total = (meals["sodium"] or 0) + (hyd["sodium"] or 0)
    fluids_total = (hyd["fluids"] or 0)

    with _conn() as conn:
        row = conn.execute(
            """INSERT INTO qbot_v2.nutrition_daily_summary (date, source, kcal_total, carbs_total,
               protein_total, fat_total, fiber_total, sodium_total, fluids_total)
               VALUES (%s, 'qbot', %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (date, source) DO UPDATE SET
               kcal_total = EXCLUDED.kcal_total,
               carbs_total = EXCLUDED.carbs_total,
               protein_total = EXCLUDED.protein_total,
               fat_total = EXCLUDED.fat_total,
               fiber_total = EXCLUDED.fiber_total,
               sodium_total = EXCLUDED.sodium_total,
               fluids_total = EXCLUDED.fluids_total,
               computed_at = now()
               RETURNING *""",
            (day, kcal_total, carbs_total, protein_total, fat_total, fiber_total, sodium_total, fluids_total),
        ).fetchone()
        conn.commit()
        return _serialize_row(dict(row))


def daily_summary_get(date_str: str) -> dict | None:
    day = date.fromisoformat(date_str)
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM qbot_v2.nutrition_daily_summary WHERE date = %s AND source = 'qbot'", (day,)
        ).fetchone()
        if row:
            return _serialize_row(dict(row))
        return None


def daily_summary_range(from_date: str, to_date: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM qbot_v2.nutrition_daily_summary
               WHERE source = 'qbot' AND date BETWEEN %s AND %s
               ORDER BY date""",
            (from_date, to_date),
        ).fetchall()
        return _serialize_rows(rows)


# ── Meal Templates ──────────────────────────────────────────────────────────

def template_create(
    name: str,
    serving_label: str = "porcja",
    kcal: float = 0,
    carbs_g: float = 0,
    protein_g: float = 0,
    fat_g: float = 0,
    fiber_g: float = 0,
    sodium_mg: float = 0,
    source: str = "manual",
    confidence: str = "high",
    notes: str | None = None,
    assumptions_json: dict | None = None,
) -> dict:
    import json as _json
    with _conn() as conn:
        row = conn.execute(
            """INSERT INTO qbot_v2.meal_templates (name, serving_label, kcal, carbs_g, protein_g, fat_g,
               fiber_g, sodium_mg, source, confidence, notes, assumptions_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING *""",
            (name, serving_label, kcal, carbs_g, protein_g, fat_g,
             fiber_g, sodium_mg, source, confidence, notes,
             _json.dumps(assumptions_json) if assumptions_json else None),
        ).fetchone()
        conn.commit()
        return _serialize_row(dict(row))


def template_update(
    template_id: int,
    name: str | None = None,
    serving_label: str | None = None,
    kcal: float | None = None,
    carbs_g: float | None = None,
    protein_g: float | None = None,
    fat_g: float | None = None,
    fiber_g: float | None = None,
    sodium_mg: float | None = None,
    source: str | None = None,
    confidence: str | None = None,
    notes: str | None = None,
    assumptions_json: dict | None = None,
) -> dict | None:
    import json as _json
    existing = template_get(template_id)
    if not existing:
        return None
    with _conn() as conn:
        row = conn.execute(
            """UPDATE qbot_v2.meal_templates SET
               name=COALESCE(%s,name), serving_label=COALESCE(%s,serving_label),
               kcal=COALESCE(%s,kcal), carbs_g=COALESCE(%s,carbs_g),
               protein_g=COALESCE(%s,protein_g), fat_g=COALESCE(%s,fat_g),
               fiber_g=COALESCE(%s,fiber_g), sodium_mg=COALESCE(%s,sodium_mg),
               source=COALESCE(%s,source), confidence=COALESCE(%s,confidence),
               notes=COALESCE(%s,notes),
               assumptions_json=COALESCE(%s,assumptions_json),
               updated_at=now()
               WHERE id=%s RETURNING *""",
            (name, serving_label, kcal, carbs_g, protein_g, fat_g,
             fiber_g, sodium_mg, source, confidence, notes,
             _json.dumps(assumptions_json) if assumptions_json else None,
             template_id),
        ).fetchone()
        conn.commit()
        return _serialize_row(dict(row))


def template_get(template_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM qbot_v2.meal_templates WHERE id=%s", (template_id,)
        ).fetchone()
    return _serialize_row(dict(row)) if row else None


def template_get_by_name(name: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM qbot_v2.meal_templates WHERE name=%s", (name,)
        ).fetchone()
    return _serialize_row(dict(row)) if row else None


def template_list(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM qbot_v2.meal_templates ORDER BY name LIMIT %s", (limit,)
        ).fetchall()
    return _serialize_rows(rows)


def template_delete(template_id: int) -> dict | None:
    existing = template_get(template_id)
    if not existing:
        return None
    with _conn() as conn:
        conn.execute("DELETE FROM qbot_v2.meal_templates WHERE id=%s", (template_id,))
        conn.commit()
    return existing


def template_import_batch(templates: list[dict], dry_run: bool = False) -> dict:
    """Import a list of templates. Returns counts and preview."""
    created = 0
    updated = 0
    skipped = 0
    preview: list[dict] = []
    for t in templates:
        name = t.get("name", "")
        if not name:
            skipped += 1
            continue
        exists = template_get_by_name(name)
        if dry_run:
            preview.append({"name": name, "action": "update" if exists else "create"})
            continue
        if exists:
            template_update(exists["id"],
                serving_label=t.get("serving_label"),
                kcal=t.get("kcal"),
                carbs_g=t.get("carbs_g"),
                protein_g=t.get("protein_g"),
                fat_g=t.get("fat_g"),
                fiber_g=t.get("fiber_g"),
                sodium_mg=t.get("sodium_mg"),
                source=t.get("source"),
                confidence=t.get("confidence"),
                notes=t.get("notes"),
                assumptions_json=t.get("assumptions_json"),
            )
            updated += 1
        else:
            template_create(
                name=name,
                serving_label=t.get("serving_label", "porcja"),
                kcal=t.get("kcal", 0),
                carbs_g=t.get("carbs_g", 0),
                protein_g=t.get("protein_g", 0),
                fat_g=t.get("fat_g", 0),
                fiber_g=t.get("fiber_g", 0),
                sodium_mg=t.get("sodium_mg", 0),
                source=t.get("source", "manual"),
                confidence=t.get("confidence", "high"),
                notes=t.get("notes"),
                assumptions_json=t.get("assumptions_json"),
            )
            created += 1
    return {
        "created": created, "updated": updated, "skipped": skipped,
        "preview": preview if dry_run else [],
        "dry_run": dry_run,
    }


# ── Day Plans ───────────────────────────────────────────────────────────────

def plan_create(
    date_str: str,
    goal: str = "deficit",
    day_type: str = "rest",
    status: str = "draft",
    planned_ride_km: float | None = None,
    estimated_base_kcal: float | None = None,
    estimated_activity_kcal: float | None = None,
    estimated_total_expenditure: float | None = None,
    target_deficit_kcal: float | None = None,
    target_intake_kcal: float = 0,
    target_protein_g: float | None = None,
    target_carbs_g: float | None = None,
    target_fat_g: float | None = None,
    planned_meals_count: int = 3,
    available_foods: str | None = None,
    used_templates: bool = False,
    confidence: str = "medium",
    source: str = "llm_plan",
    assumptions_json: dict | None = None,
    warnings_json: dict | None = None,
    shopping_list_json: dict | None = None,
    meals: list[dict] | None = None,
) -> dict:
    import json as _json
    with _conn() as conn:
        row = conn.execute(
            """INSERT INTO qbot_v2.nutrition_day_plans (date, goal, day_type, status,
               planned_ride_km, estimated_base_kcal, estimated_activity_kcal,
               estimated_total_expenditure, target_deficit_kcal, target_intake_kcal,
               target_protein_g, target_carbs_g, target_fat_g, planned_meals_count,
               available_foods, used_templates, confidence, source,
               assumptions_json, warnings_json, shopping_list_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING *""",
            (date_str, goal, day_type, status,
             planned_ride_km, estimated_base_kcal, estimated_activity_kcal,
             estimated_total_expenditure, target_deficit_kcal, target_intake_kcal,
             target_protein_g, target_carbs_g, target_fat_g, planned_meals_count,
             available_foods, used_templates, confidence, source,
             _json.dumps(assumptions_json) if assumptions_json else None,
             _json.dumps(warnings_json) if warnings_json else None,
             _json.dumps(shopping_list_json) if shopping_list_json else None),
        ).fetchone()
        plan_id = row["id"]

        if meals:
            for i, m in enumerate(meals):
                conn.execute(
                    """INSERT INTO qbot_v2.nutrition_day_plan_meals
                       (plan_id, meal_order, meal_name, template_id, planned_time,
                        kcal, carbs_g, protein_g, fat_g, fiber_g, sodium_mg, notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (plan_id, i + 1,
                     m.get("meal_name", m.get("template_name", f"posiłek {i+1}")),
                     m.get("template_id"),
                     m.get("planned_time"),
                     m.get("kcal", 0), m.get("carbs_g", 0),
                     m.get("protein_g", 0), m.get("fat_g", 0),
                     m.get("fiber_g", 0), m.get("sodium_mg", 0),
                     m.get("notes")),
                )
        conn.commit()
    return plan_get(plan_id)


def plan_get(plan_id: int) -> dict | None:
    with _conn() as conn:
        plan = conn.execute("SELECT * FROM qbot_v2.nutrition_day_plans WHERE id=%s", (plan_id,)).fetchone()
        if not plan:
            return None
        meals = conn.execute("SELECT * FROM qbot_v2.nutrition_day_plan_meals WHERE plan_id=%s ORDER BY meal_order", (plan_id,)).fetchall()
        result = _serialize_row(dict(plan))
        result["meals"] = _serialize_rows(meals)
        # Parse JSON fields
        for k in ("assumptions_json", "warnings_json", "shopping_list_json"):
            if result.get(k) and isinstance(result[k], str):
                try:
                    result[k] = __import__("json").loads(result[k])
                except Exception:
                    pass
        return result


def plan_list(date_str: str | None = None, status: str | None = None, limit: int = 20) -> list[dict]:
    with _conn() as conn:
        conds = []
        params: list = []
        if date_str:
            conds.append("date=%s"); params.append(date_str)
        if status:
            conds.append("status=%s"); params.append(status)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = conn.execute(
            f"SELECT * FROM qbot_v2.nutrition_day_plans {where} ORDER BY date DESC, id DESC LIMIT %s",
            params + [limit],
        ).fetchall()
        results = []
        for r in rows:
            d = _serialize_row(dict(r))
            d["meals_count"] = conn.execute(
                "SELECT COUNT(*) AS c FROM qbot_v2.nutrition_day_plan_meals WHERE plan_id=%s", (r["id"],)
            ).fetchone()["c"]
            results.append(d)
        return results


def plan_update_status(plan_id: int, status: str) -> dict | None:
    with _conn() as conn:
        conn.execute(
            "UPDATE qbot_v2.nutrition_day_plans SET status=%s, updated_at=now() WHERE id=%s",
            (status, plan_id),
        )
        conn.commit()
    return plan_get(plan_id)


def plan_delete(plan_id: int) -> dict | None:
    existing = plan_get(plan_id)
    if not existing:
        return None
    with _conn() as conn:
        conn.execute("DELETE FROM qbot_v2.nutrition_day_plan_meals WHERE plan_id=%s", (plan_id,))
        conn.execute("DELETE FROM qbot_v2.nutrition_day_plans WHERE id=%s", (plan_id,))
        conn.commit()
    return existing


def plan_apply(plan_id: int) -> dict:
    """Apply a plan: log all planned meals as actual meals, recompute summary."""
    plan = plan_get(plan_id)
    if not plan:
        return {"status": "not_found", "error": f"plan {plan_id} not found"}

    from qbot_nutrition_db import meal_log_create, daily_summary_compute
    import json as _json
    items = []
    for m in plan.get("meals", []):
        items.append({
            "food_name": m.get("meal_name", "posiłek"),
            "amount": 1, "unit": "porcja",
            "kcal": m.get("kcal"), "carbs_g": m.get("carbs_g"),
            "protein_g": m.get("protein_g"), "fat_g": m.get("fat_g"),
            "fiber_g": m.get("fiber_g"), "sodium_mg": m.get("sodium_mg"),
        })

    if not items:
        return {"status": "no_meals", "error": "plan has no meals"}
    date_str = str(plan["date"])[:10]
    context = _json.dumps({"source": "plan_applied", "plan_id": plan_id})
    meal_log_create(meal_type="meal", context=context,
                    note=f"plan applied: id={plan_id}",
                    eaten_at=f"{date_str}T12:00:00", items=items)
    daily_summary_compute(date_str)
    plan_update_status(plan_id, "applied")
    plan_applied = plan_get(plan_id)
    return {"status": "ok", "plan": plan_applied}
