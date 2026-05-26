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
            """INSERT INTO food_items (name, brand, default_unit, kcal_per_100g, carbs_per_100g,
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
            """SELECT * FROM food_items
               WHERE name ILIKE %s OR brand ILIKE %s
               ORDER BY name LIMIT %s""",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return _serialize_rows(rows)


def food_item_get_by_name(name: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM food_items WHERE name ILIKE %s LIMIT 1", (name,)
        ).fetchone()
        return _serialize_row(dict(row)) if row else None


def food_item_list(limit: int = 50, offset: int = 0) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM food_items ORDER BY name LIMIT %s OFFSET %s", (limit, offset)
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
            """INSERT INTO meal_logs (eaten_at, meal_type, note, context)
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
                """INSERT INTO meal_log_items (meal_log_id, food_item_id, food_name, amount, unit,
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
    return get_meal_log(meal_id)


def get_meal_log(meal_id: int) -> dict | None:
    with _conn() as conn:
        meal = conn.execute(
            "SELECT * FROM meal_logs WHERE id = %s", (meal_id,)
        ).fetchone()
        if not meal:
            return None
        items = conn.execute(
            "SELECT * FROM meal_log_items WHERE meal_log_id = %s ORDER BY id", (meal_id,)
        ).fetchall()
        result = _serialize_row(dict(meal))
        result["items"] = _serialize_rows(items)
        return result


def meal_log_list(date_str: str | None = None, limit: int = 20) -> list[dict]:
    with _conn() as conn:
        if date_str:
            rows = conn.execute(
                """SELECT * FROM meal_logs WHERE eaten_at::date = %s
                   ORDER BY eaten_at DESC LIMIT %s""",
                (date_str, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM meal_logs ORDER BY eaten_at DESC LIMIT %s", (limit,)
            ).fetchall()
        result = []
        for meal in rows:
            items = conn.execute(
                "SELECT * FROM meal_log_items WHERE meal_log_id = %s ORDER BY id",
                (meal["id"],),
            ).fetchall()
            d = _serialize_row(dict(meal))
            d["items"] = _serialize_rows(items)
            result.append(d)
        return result


# ── Hydration ─────────────────────────────────────────────────────────────

def hydration_event_create(fluid_ml: float, sodium_mg: float = 0, source: str = "qbot", note: str | None = None, drank_at: str | None = None) -> dict:
    drank_dt = datetime.fromisoformat(drank_at) if drank_at else datetime.now()
    with _conn() as conn:
        row = conn.execute(
            """INSERT INTO hydration_events (drank_at, fluid_ml, sodium_mg, source, note)
               VALUES (%s, %s, %s, %s, %s) RETURNING *""",
            (drank_dt, fluid_ml, sodium_mg, source, note),
        ).fetchone()
        conn.commit()
        return _serialize_row(dict(row))


def hydration_list(date_str: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        if date_str:
            rows = conn.execute(
                """SELECT * FROM hydration_events WHERE drank_at::date = %s
                   ORDER BY drank_at DESC LIMIT %s""",
                (date_str, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM hydration_events ORDER BY drank_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return _serialize_rows(rows)


# ── Fueling ───────────────────────────────────────────────────────────────

def fueling_event_create(carbs_g: float, source: str = "qbot", context: str | None = None, event_at: str | None = None) -> dict:
    event_dt = datetime.fromisoformat(event_at) if event_at else datetime.now()
    with _conn() as conn:
        row = conn.execute(
            """INSERT INTO fueling_events (event_at, carbs_g, source, context)
               VALUES (%s, %s, %s, %s) RETURNING *""",
            (event_dt, carbs_g, source, context),
        ).fetchone()
        conn.commit()
        return _serialize_row(dict(row))


def fueling_list(date_str: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        if date_str:
            rows = conn.execute(
                """SELECT * FROM fueling_events WHERE event_at::date = %s
                   ORDER BY event_at DESC LIMIT %s""",
                (date_str, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM fueling_events ORDER BY event_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return _serialize_rows(rows)


# ── Daily Summary ─────────────────────────────────────────────────────────

def daily_summary_compute(date_str: str) -> dict:
    day = date.fromisoformat(date_str)
    with _conn() as conn:
        meals = conn.execute(
            """SELECT COALESCE(SUM(mli.kcal), 0) AS kcal,
               COALESCE(SUM(mli.carbs_g), 0) AS carbs,
               COALESCE(SUM(mli.protein_g), 0) AS protein,
               COALESCE(SUM(mli.fat_g), 0) AS fat,
               COALESCE(SUM(mli.fiber_g), 0) AS fiber,
               COALESCE(SUM(mli.sodium_mg), 0) AS sodium
               FROM meal_log_items mli
               JOIN meal_logs ml ON ml.id = mli.meal_log_id
               WHERE ml.eaten_at::date = %s""",
            (day,),
        ).fetchone()

        hyd = conn.execute(
            """SELECT COALESCE(SUM(fluid_ml), 0) AS fluids,
               COALESCE(SUM(sodium_mg), 0) AS sodium
               FROM hydration_events WHERE drank_at::date = %s""",
            (day,),
        ).fetchone()

        fuel = conn.execute(
            "SELECT COALESCE(SUM(carbs_g), 0) AS carbs FROM fueling_events WHERE event_at::date = %s",
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
            """INSERT INTO nutrition_daily_summary (date, source, kcal_total, carbs_total,
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
            "SELECT * FROM nutrition_daily_summary WHERE date = %s AND source = 'qbot'", (day,)
        ).fetchone()
        if row:
            return _serialize_row(dict(row))
        return None


def daily_summary_range(from_date: str, to_date: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM nutrition_daily_summary
               WHERE source = 'qbot' AND date BETWEEN %s AND %s
               ORDER BY date""",
            (from_date, to_date),
        ).fetchall()
        return _serialize_rows(rows)
