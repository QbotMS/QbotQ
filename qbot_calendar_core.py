#!/usr/bin/env python3
"""QBot Calendar Core — DB CRUD + Snapshot Builder."""

import json
import os
from datetime import date, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
    )


def _s(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v


def _table_exists(name: str) -> bool:
    try:
        with _conn() as c:
            r = c.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=%s)", (name,)).fetchone()
            return r["exists"] if r else False
    except Exception:
        return False


# ── Calendar Days ──

def day_upsert(date_str: str, day_type: str | None = None, notes: str | None = None,
               planned_day_type: str | None = None, tags: list[str] | None = None) -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO calendar_days (date, day_type, notes, planned_day_type, tags_json, updated_at)
               VALUES (%s,%s,%s,%s,%s,now())
               ON CONFLICT (date) DO UPDATE SET
               day_type=COALESCE(EXCLUDED.day_type, calendar_days.day_type),
               notes=COALESCE(EXCLUDED.notes, calendar_days.notes),
               planned_day_type=COALESCE(EXCLUDED.planned_day_type, calendar_days.planned_day_type),
               tags_json=COALESCE(EXCLUDED.tags_json, calendar_days.tags_json),
               updated_at=now()
               RETURNING *""",
            (date_str, day_type, notes, planned_day_type,
             json.dumps(tags) if tags else None),
        ).fetchone()
        c.commit()
    return {k: _s(v) for k, v in dict(r).items()}


def day_get(date_str: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM calendar_days WHERE date=%s", (date_str,)).fetchone()
    if not r:
        return None
    d = {k: _s(v) for k, v in dict(r).items()}
    for k in ("tags_json",):
        if d.get(k) and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d


def day_list(date_from: str, date_to: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM calendar_days WHERE date BETWEEN %s AND %s ORDER BY date",
            (date_from, date_to),
        ).fetchall()
    return [{k: _s(v) for k, v in dict(r).items()} for r in rows]


# ── Events ──

def event_create(date_start: str, title: str, event_type: str = "note",
                 description: str | None = None, date_end: str | None = None,
                 status: str = "planned", source: str = "manual",
                 external_ref: str | None = None, metadata: dict | None = None,
                 affects_training: bool = False, affects_nutrition: bool = False,
                 affects_health: bool = False) -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO calendar_events (date_start, date_end, event_type, title, description,
               status, source, external_ref, metadata_json,
               affects_training, affects_nutrition, affects_health_advice)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (date_start, date_end, event_type, title, description, status, source,
             external_ref, json.dumps(metadata) if metadata else None,
             affects_training, affects_nutrition, affects_health),
        ).fetchone()
        c.commit()
    return {k: _s(v) for k, v in dict(r).items()}


def event_list(date_from: str | None = None, date_to: str | None = None,
               status: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as c:
        conds, params = [], []
        if date_from:
            conds.append("date_start>=%s"); params.append(date_from)
        if date_to:
            conds.append("date_start<=%s"); params.append(date_to)
        if status:
            conds.append("status=%s"); params.append(status)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = c.execute(f"SELECT * FROM calendar_events {where} ORDER BY date_start, id LIMIT %s",
                         params + [limit]).fetchall()
    return [{k: _s(v) for k, v in dict(r).items()} for r in rows]


def event_get(eid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM calendar_events WHERE id=%s", (eid,)).fetchone()
    return {k: _s(v) for k, v in dict(r).items()} if r else None


def event_delete(eid: int) -> dict | None:
    ev = event_get(eid)
    if not ev:
        return None
    with _conn() as c:
        c.execute("DELETE FROM calendar_events WHERE id=%s", (eid,))
        c.commit()
    return ev


# ── Reminders ──

def reminder_create(date_str: str, title: str, time_str: str | None = None,
                    reminder_type: str = "custom", message: str | None = None,
                    channel: str = "cli", recurrence: str | None = None,
                    related_entity_type: str | None = None, related_entity_id: int | None = None) -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO reminders (date,time,title,message,reminder_type,recurrence_rule,
               related_entity_type,related_entity_id,channel)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (date_str, time_str, title, message, reminder_type, recurrence,
             related_entity_type, related_entity_id, channel),
        ).fetchone()
        c.commit()
    return {k: _s(v) for k, v in dict(r).items()}


def reminder_list(date_str: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as c:
        conds, params = [], []
        if date_str:
            conds.append("date=%s"); params.append(date_str)
        if status:
            conds.append("status=%s"); params.append(status)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = c.execute(f"SELECT * FROM reminders {where} ORDER BY date, time LIMIT %s",
                         params + [limit]).fetchall()
    return [{k: _s(v) for k, v in dict(r).items()} for r in rows]


def reminder_update_status(rid: int, status_val: str) -> dict | None:
    with _conn() as c:
        c.execute("UPDATE reminders SET status=%s, updated_at=now() WHERE id=%s", (status_val, rid))
        c.commit()
        r = c.execute("SELECT * FROM reminders WHERE id=%s", (rid,)).fetchone()
    return {k: _s(v) for k, v in dict(r).items()} if r else None


def reminder_delete(rid: int) -> dict | None:
    r = reminder_list()
    r = next((x for x in r if x.get("id") == rid), None)
    if not r:
        return None
    with _conn() as c:
        c.execute("DELETE FROM reminders WHERE id=%s", (rid,))
        c.commit()
    return r


# ── Import Jobs ──

def import_job_create(source: str, date_from: str, date_to: str) -> dict:
    with _conn() as c:
        r = c.execute("INSERT INTO import_jobs (source,date_from,date_to,status) VALUES (%s,%s,%s,'planned') RETURNING *",
                      (source, date_from, date_to)).fetchone()
        c.commit()
    return {k: _s(v) for k, v in dict(r).items()}


# ═══════════════════════════════════════════════════════════════════════════
# SNAPSHOT BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def _safe_query(q: str, params: tuple = ()) -> list[dict]:
    try:
        with _conn() as c:
            rows = c.execute(q, params).fetchall()
        return [{k: _s(v) for k, v in dict(r).items()} for r in rows]
    except Exception:
        return []


def build_snapshot(date_str: str) -> dict[str, Any]:
    """Aggregate all domain data for a given date into a snapshot dict."""
    day_upsert(date_str)
    snap: dict[str, Any] = {
        "date": date_str,
        "timezone": "Europe/Warsaw",
    }
    missing_tables: list[str] = []
    missing_fields: list[str] = []
    source_tables: list[str] = []
    total_fields = 0
    found_fields = 0

    # Nutrition
    if _table_exists("nutrition_daily_summary"):
        rows = _safe_query("SELECT * FROM nutrition_daily_summary WHERE date=%s AND source='qbot'", (date_str,))
        snap["nutrition"] = rows[0] if rows else None
        source_tables.append("nutrition_daily_summary")
        total_fields += 1
        if rows:
            found_fields += 1
    else:
        missing_tables.append("nutrition_daily_summary")

    # Meals
    if _table_exists("meal_logs"):
        meals = _safe_query(
            "SELECT ml.*, COUNT(mli.id) AS item_count FROM meal_logs ml LEFT JOIN meal_log_items mli ON mli.meal_log_id=ml.id WHERE ml.eaten_at::date=%s GROUP BY ml.id ORDER BY ml.eaten_at",
            (date_str,))
        snap["meals"] = meals
        source_tables.append("meal_logs")
        total_fields += 1
        if meals:
            found_fields += 1
    else:
        missing_tables.append("meal_logs")

    # Nutrition plans
    if _table_exists("nutrition_day_plans"):
        plans = _safe_query("SELECT * FROM nutrition_day_plans WHERE date=%s", (date_str,))
        snap["nutrition_plans"] = plans
        source_tables.append("nutrition_day_plans")
        total_fields += 1
        if plans:
            found_fields += 1
    else:
        missing_tables.append("nutrition_day_plans")

    # Training (Intervals wellness)
    if _table_exists("qbot_wellness_daily"):
        wellness = _safe_query("SELECT * FROM qbot_wellness_daily WHERE date=%s ORDER BY source_priority", (date_str,))
        snap["training"] = wellness[0] if wellness else None
        source_tables.append("qbot_wellness_daily")
        total_fields += 1
        if wellness:
            found_fields += 1
    else:
        missing_tables.append("qbot_wellness_daily")
        missing_fields.append("training_sessions")

    # Sleep
    if _table_exists("qbot_sleep_daily"):
        sleep = _safe_query("SELECT * FROM qbot_sleep_daily WHERE date=%s", (date_str,))
        snap["sleep"] = sleep[0] if sleep else None
        source_tables.append("qbot_sleep_daily")
        total_fields += 1
        if sleep:
            found_fields += 1
    else:
        missing_tables.append("qbot_sleep_daily")
        missing_fields.append("sleep_data")

    # Health events
    if _table_exists("health_events"):
        hevents = _safe_query("SELECT * FROM health_events WHERE date_start<=%s AND (date_end IS NULL OR date_end>=%s) AND status='active'",
                              (date_str, date_str))
        snap["health_events"] = hevents
        source_tables.append("health_events")
        total_fields += 1
        if hevents:
            found_fields += 1
    else:
        missing_tables.append("health_events")

    # Health risk notes
    if _table_exists("health_risk_notes"):
        risks = _safe_query("SELECT * FROM health_risk_notes WHERE status='active'")
        snap["health_risk_notes"] = risks
        source_tables.append("health_risk_notes")
        total_fields += 1
        if risks:
            found_fields += 1
    else:
        missing_tables.append("health_risk_notes")

    # Supplements
    if _table_exists("supplement_inventory"):
        supp = _safe_query("SELECT * FROM supplement_inventory WHERE status='active'")
        prot = _safe_query("SELECT * FROM supplement_protocols WHERE status='active'")
        intake = _safe_query("SELECT * FROM supplement_intake_log WHERE date=%s", (date_str,))
        snap["supplements"] = {"inventory": supp, "protocols": prot, "intake": intake}
        source_tables.append("supplement_inventory")
        total_fields += 1
        if supp or prot:
            found_fields += 1
    else:
        missing_tables.append("supplement_inventory")

    # Health goals
    if _table_exists("health_goals"):
        goals = _safe_query("SELECT * FROM health_goals WHERE status='active'")
        snap["goals"] = goals
        source_tables.append("health_goals")
        total_fields += 1
        if goals:
            found_fields += 1
    else:
        missing_tables.append("health_goals")

    # Advisor reports
    if _table_exists("health_advice_reports"):
        reports = _safe_query("SELECT * FROM health_advice_reports WHERE date=%s ORDER BY id DESC LIMIT 3", (date_str,))
        snap["advisor_reports"] = reports
        source_tables.append("health_advice_reports")
        total_fields += 1
        if reports:
            found_fields += 1
    else:
        missing_tables.append("health_advice_reports")

    # Calendar events
    snap["calendar_events"] = _safe_query("SELECT * FROM calendar_events WHERE date_start<=%s AND (date_end IS NULL OR date_end>=%s) ORDER BY date_start",
                                          (date_str, date_str))
    source_tables.append("calendar_events")

    # Reminders
    snap["reminders"] = _safe_query("SELECT * FROM reminders WHERE date=%s ORDER BY time", (date_str,))
    source_tables.append("reminders")

    # Calendar day metadata
    day = day_get(date_str)
    if day:
        snap["day_type"] = day.get("day_type")
        snap["day_notes"] = day.get("notes")
    source_tables.append("calendar_days")

    # Xert / form — no local table
    missing_tables.append("xert_metrics")
    missing_fields.extend(["threshold_power_w", "form_score", "freshness", "fatigue", "training_load"])

    # Weight / body composition — no table
    missing_tables.extend(["weight_history", "body_composition"])
    missing_fields.extend(["weight_kg", "body_fat_pct"])

    score = found_fields / max(total_fields, 1)

    # Upsert full snapshot
    with _conn() as c:
        c.execute(
            """INSERT INTO calendar_daily_snapshots (date, snapshot_json, completeness_score,
               missing_fields_json, missing_tables_json, source_tables_json, computed_at)
               VALUES (%s,%s,%s,%s,%s,%s,now())
               ON CONFLICT (date) DO UPDATE SET
               snapshot_json=EXCLUDED.snapshot_json, completeness_score=EXCLUDED.completeness_score,
               missing_fields_json=EXCLUDED.missing_fields_json,
               missing_tables_json=EXCLUDED.missing_tables_json,
               source_tables_json=EXCLUDED.source_tables_json,
               computed_at=now()""",
            (date_str, json.dumps(snap, ensure_ascii=False, default=str), score,
             json.dumps(missing_fields), json.dumps(missing_tables),
             json.dumps(source_tables)),
        )
        c.commit()

    snap["_completeness_score"] = score
    snap["_missing_fields"] = missing_fields
    snap["_missing_tables"] = missing_tables
    snap["_source_tables"] = source_tables
    return snap


def get_snapshot(date_str: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM calendar_daily_snapshots WHERE date=%s", (date_str,)).fetchone()
    if not r:
        return None
    d = {k: _s(v) for k, v in dict(r).items()}
    for k in ("snapshot_json", "missing_fields_json", "missing_tables_json", "source_tables_json"):
        if d.get(k) and isinstance(d[k], str):
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d


def rebuild_range(date_from: str, date_to: str) -> dict:
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    cur = start
    count = 0
    errors = []
    while cur <= end:
        ds = cur.isoformat()
        try:
            build_snapshot(ds)
            count += 1
        except Exception as e:
            errors.append(f"{ds}: {e}")
        cur += timedelta(days=1)
    return {"rebuilt": count, "errors": errors, "range": f"{date_from} → {date_to}"}


def import_history_audit(source: str = "all", date_from: str = "2025-01-01", date_to: str = "") -> dict:
    """Audit existing data sources — counts per table."""
    if not date_to:
        date_to = date.today().isoformat()
    available: dict[str, dict] = {}
    tables_to_check = []
    if source in ("all", "nutrition"):
        tables_to_check.extend(["nutrition_daily_summary", "meal_logs", "nutrition_day_plans", "meal_templates"])
    if source in ("all", "health"):
        tables_to_check.extend(["health_events", "health_risk_notes", "health_goals", "health_advice_reports", "qbot_wellness_daily", "qbot_sleep_daily"])
    if source in ("all", "supplements"):
        tables_to_check.extend(["supplement_inventory", "supplement_protocols", "supplement_intake_log"])
    if source in ("all", "intervals"):
        tables_to_check.extend(["qbot_wellness_daily"])
    if source in ("all", "calendar"):
        tables_to_check.extend(["calendar_events", "reminders"])
    if source in ("all", "routes"):
        tables_to_check.extend(["route_artifacts", "route_surface_profiles"])

    for t in tables_to_check:
        if _table_exists(t):
            try:
                with _conn() as c:
                    total = c.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
                    if date_from and date_to:
                        date_col = "date" if "date" in t else None
                        if "nutrition_daily_summary" == t:
                            date_col = "date"
                        if date_col:
                            in_range = c.execute(
                                f"SELECT COUNT(*) AS c FROM {t} WHERE {date_col} BETWEEN %s AND %s",
                                (date_from, date_to),
                            ).fetchone()["c"]
                        else:
                            in_range = None
                    available[t] = {"exists": True, "total_rows": total, "rows_in_range": in_range}
            except Exception:
                available[t] = {"exists": True, "error": "query_failed"}
        else:
            available[t] = {"exists": False}

    return {
        "source": source,
        "date_from": date_from,
        "date_to": date_to,
        "tables": available,
        "note": "Dry-run audit only. No data imported. Use --yes to execute actual import.",
    }
