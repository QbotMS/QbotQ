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


def _table_exists(name: str, schema: str | None = None) -> bool:
    try:
        with _conn() as c:
            if schema:
                r = c.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s)", (schema, name)).fetchone()
            else:
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
                 time_start: str | None = None, status: str = "planned",
                 source: str = "manual", external_ref: str | None = None,
                 metadata: dict | None = None, affects_training: bool = False,
                 affects_nutrition: bool = False, affects_health: bool = False) -> dict:
    with _conn() as c:
        c.execute(
            """INSERT INTO days (date, has_calendar)
               VALUES (%s, true)
               ON CONFLICT (date) DO UPDATE SET
               has_calendar = true,
               updated_at = now()""",
            (date_start,),
        )
        r = c.execute(
            """INSERT INTO calendar_events (date_start, date_end, time_start, event_type, title,
               status, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (date_start, date_end, time_start, event_type, title, status, source),
        ).fetchone()
        c.commit()
    return {k: _s(v) for k, v in dict(r).items()}


def qcal_event_add_controlled(
    date_start: str,
    title: str,
    date_end: str | None = None,
    time_start: str | None = None,
    event_type: str = "custom",
    description: str | None = None,
    source: str = "chatgpt_mcp",
    idempotency_key: str | None = None,
    confirm: bool = False,
    affects_training: bool = False,
    affects_nutrition: bool = False,
) -> dict:
    """Unified QCal event writer — used by CLI, MCP, action_execute.

    Returns structured result:
      status: ok | duplicate | refused | error
      created: bool
      event_id: int | None
      record: dict | None
      snapshot_rebuilt: bool
      message: str
    """
    import datetime
    import json as _json
    from psycopg.rows import dict_row

    if not confirm:
        return {"status": "refused", "event_id": None, "record": None, "snapshot_rebuilt": False,
                "created": False, "message": "confirm must be true to write."}

    if not idempotency_key:
        return {"status": "refused", "event_id": None, "record": None, "snapshot_rebuilt": False,
                "created": False, "message": "idempotency_key required."}

    # ── Duplicate / stale audit check ──
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute("SELECT entity_id FROM qcal_write_audit WHERE idempotency_key=%s", (idempotency_key,))
        row = cur.fetchone()
        if row:
            existing_id = row["entity_id"]
            # Validate linked record
            cur.execute("SELECT * FROM calendar_events WHERE id=%s", (existing_id,))
            ev = cur.fetchone()
            if ev and ev.get("status") not in ("cancelled", "deleted"):
                ev_dict = {k: str(v) if hasattr(v, "isoformat") else v for k, v in dict(ev).items()}
                c.close()
                return {"status": "duplicate", "created": False, "event_id": existing_id, "record": ev_dict,
                        "message": f"Event already exists (id={existing_id}).", "snapshot_rebuilt": False}
            # Stale audit: clean up
            cur.execute("DELETE FROM qcal_write_audit WHERE idempotency_key=%s", (idempotency_key,))
            c.commit()
        c.close()
    except Exception:
        pass

    # ── Natural-key duplicate fallback ──
    # Check calendar_events by date_start + date_end + time_start + event_type + normalized title
    try:
        c = _conn()
        cur = c.cursor()
        norm_title = title.strip().lower()
        cur.execute(
            "SELECT * FROM calendar_events WHERE date_start=%s::date AND date_end IS NOT DISTINCT FROM %s::date AND time_start IS NOT DISTINCT FROM %s::time AND event_type=%s AND LOWER(TRIM(title))=%s AND status NOT IN ('cancelled','deleted') ORDER BY id",
            (date_start, date_end, time_start, event_type, norm_title))
        matches = cur.fetchall()
        if matches:
            if len(matches) == 1:
                ev = matches[0]
                eid = ev["id"]
                ev_dict = {k: str(v) if hasattr(v, "isoformat") else v for k, v in dict(ev).items()}
                # Update audit to point to this existing event
                if idempotency_key:
                    cur.execute(
                        "INSERT INTO qcal_write_audit (idempotency_key, operation, entity_type, entity_id, date, source, payload_json, result_json) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (idempotency_key) DO UPDATE SET entity_id=EXCLUDED.entity_id",
                        (idempotency_key, "event_add", "event", eid, date_start, source,
                         _json.dumps({"title": title, "date_start": date_start}, default=str),
                         _json.dumps({"id": eid}, default=str)))
                    c.commit()
                c.close()
                return {"status": "duplicate", "created": False, "event_id": eid, "record": ev_dict,
                        "message": f"Event already exists (id={eid}, natural key match).", "snapshot_rebuilt": False,
                        "idempotency_key": idempotency_key}
            else:
                eids = [r["id"] for r in matches]
                c.close()
                return {"status": "conflict_duplicate", "created": False, "event_id": None, "record": None,
                        "message": f"Multiple active events match natural key: {eids}. Suggested cleanup.",
                        "event_ids": eids, "suggested_cleanup": "Use qcal event-cancel to keep only one."}
        c.close()
    except Exception:
        pass

    # ── Create event ──
    try:
        ev = event_create(
            date_start=date_start, title=title, event_type=event_type,
            description=description, date_end=date_end, time_start=time_start,
            status="planned", source=source,
            affects_training=affects_training, affects_nutrition=affects_nutrition,
        )
    except Exception as e:
        return {"status": "error", "created": False, "event_id": None, "record": None,
                "message": str(e)[:200], "snapshot_rebuilt": False}

    eid = ev.get("id")

    # ── Audit ──
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute(
            "INSERT INTO qcal_write_audit (idempotency_key, operation, entity_type, entity_id, date, source, payload_json, result_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (idempotency_key, "event_add", "event", eid, date_start, source,
             _json.dumps({"title": title, "date_start": date_start}, default=str),
             _json.dumps({"id": eid}, default=str)))
        c.commit()
        c.close()
    except Exception:
        pass

    # ── Snapshot ──
    snap_ok = False
    try:
        build_snapshot(date_start)
        snap_ok = True
    except Exception:
        pass

    # ── Serialize record ──
    record = {k: str(v) if hasattr(v, "isoformat") or isinstance(v, type) else v for k, v in ev.items()}

    return {
        "status": "ok", "created": True, "event_id": eid, "record": record,
        "idempotency_key": idempotency_key, "snapshot_rebuilt": snap_ok,
        "message": f"Utworzono wydarzenie: {title} (id={eid}, {date_start})",
    }


def qcal_event_update_controlled(
    event_id: int | None = None,
    match: dict | None = None,
    updates: dict | None = None,
    idempotency_key: str | None = None,
    confirm: bool = False,
    source: str = "chatgpt_mcp",
) -> dict:
    """Update an existing QCal event. Only allowlisted fields can be changed.

    Allowlisted fields: date_start, date_end, time_start, event_type, title,
    description, affects_training, affects_nutrition.

    Returns structured result:
      status: ok | duplicate | refused | not_found | ambiguous_match | error
      event_id: int | None
      updated: bool
      before: dict | None
      after: dict | None
    """
    import datetime, json as _json
    if not confirm:
        return {"status": "refused", "event_id": None, "updated": False, "before": None, "after": None,
                "message": "confirm must be true."}

    if not updates:
        return {"status": "refused", "event_id": None, "updated": False, "before": None, "after": None,
                "message": "No updates provided."}

    _ALLOWED_UPDATE_FIELDS = {"date_start", "date_end", "time_start", "event_type", "title",
                              "description", "affects_training", "affects_nutrition"}

    # Resolve event
    eid = event_id
    if not eid and match:
        try:
            c = _conn()
            cur = c.cursor()
            where = []
            params = []
            if match.get("title"):
                where.append("LOWER(TRIM(title))=LOWER(TRIM(%s))")
                params.append(match["title"])
            if match.get("date_start"):
                where.append("date_start=%s::date")
                params.append(match["date_start"])
            if match.get("date_end"):
                where.append("date_end=%s::date")
                params.append(match["date_end"])
            if match.get("event_type"):
                where.append("event_type=%s")
                params.append(match["event_type"])
            where.append("status NOT IN ('cancelled','deleted')")
            cur.execute(f"SELECT id FROM calendar_events WHERE {' AND '.join(where)} ORDER BY id", params)
            rows = cur.fetchall()
            c.close()
            if len(rows) == 0:
                return {"status": "not_found", "event_id": None, "updated": False,
                        "before": None, "after": None, "message": "No matching active event found."}
            if len(rows) > 1:
                return {"status": "ambiguous_match", "event_id": None, "updated": False,
                        "before": None, "after": None, "message": "Multiple matching events.",
                        "candidates": [r["id"] for r in rows]}
            eid = rows[0]["id"]
        except Exception as e:
            return {"status": "error", "event_id": None, "updated": False,
                    "before": None, "after": None, "message": str(e)[:200]}

    if not eid:
        return {"status": "refused", "event_id": None, "updated": False,
                "before": None, "after": None, "message": "event_id or match required."}

    # Fetch before
    try:
        c = _conn()
        cur = c.cursor()
        cur.execute("SELECT * FROM calendar_events WHERE id=%s", (eid,))
        before = cur.fetchone()
        if not before:
            c.close()
            return {"status": "not_found", "event_id": eid, "updated": False,
                    "before": None, "after": None, "message": f"Event id={eid} not found."}
    except Exception as e:
        return {"status": "error", "event_id": eid, "updated": False,
                "before": None, "after": None, "message": str(e)[:200]}

    # Build SET clause
    set_parts = []
    set_vals = []
    for field in _ALLOWED_UPDATE_FIELDS:
        if field in updates:
            val = updates[field]
            if val is None:
                set_parts.append(f"{field}=NULL")
            elif field in ("affects_training", "affects_nutrition"):
                set_parts.append(f"{field}=%s")
                set_vals.append(bool(val))
            else:
                cast = "::date" if field in ("date_start", "date_end") else ""
                set_parts.append(f"{field}=%s{cast}")
                set_vals.append(val)
    if not set_parts:
        c.close()
        return {"status": "refused", "event_id": eid, "updated": False,
                "before": before, "after": None, "message": "No updateable fields changed."}

    try:
        set_parts.append("updated_at=now()")
        sql = f"UPDATE calendar_events SET {', '.join(set_parts)} WHERE id=%s RETURNING *"
        cur.execute(sql, set_vals + [eid])
        after = cur.fetchone()
        c.commit()
        c.close()
    except Exception as e:
        try: c.close()
        except: pass
        return {"status": "error", "event_id": eid, "updated": False,
                "before": _serialize_dict(before), "after": None, "message": str(e)[:200]}

    before_s = _serialize_dict(before)
    after_s = _serialize_dict(after) if after else None

    # Audit
    try:
        c2 = _conn()
        cur2 = c2.cursor()
        cur2.execute(
            "INSERT INTO qcal_write_audit (idempotency_key, operation, entity_type, entity_id, date, source, payload_json, result_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (idempotency_key, "event_update", "event", eid,
             after_s.get("date_start", "") if after_s else "",
             source, _json.dumps({"updates": updates}, default=str),
             _json.dumps({"before": before_s, "after": after_s}, default=str)))
        c2.commit()
        c2.close()
    except Exception:
        pass

    # Snapshot
    try:
        build_snapshot(after_s.get("date_start", ""))
    except Exception:
        pass

    return {"status": "ok", "event_id": eid, "updated": True, "before": before_s, "after": after_s,
            "idempotency_key": idempotency_key,
            "message": f"Updated event id={eid}: {', '.join(updates.keys())}"}


def qcal_event_cancel_controlled(
    event_id: int | None = None,
    match: dict | None = None,
    reason: str | None = None,
    idempotency_key: str | None = None,
    confirm: bool = False,
    source: str = "chatgpt_mcp",
) -> dict:
    """Cancel an event. Sets status=cancelled.

    Returns structured result:
      status: ok | duplicate | refused | not_found | ambiguous_match | error
      event_id: int | None
      cancelled: bool
      before: dict | None
      after: dict | None
    """
    import datetime, json as _json
    if not confirm:
        return {"status": "refused", "event_id": None, "cancelled": False,
                "before": None, "after": None, "message": "confirm must be true."}

    # Resolve event
    eid = event_id
    if not eid and match:
        try:
            c = _conn()
            cur = c.cursor()
            where = []
            params = []
            if match.get("title"):
                where.append("LOWER(TRIM(title))=LOWER(TRIM(%s))")
                params.append(match["title"])
            if match.get("date_start"):
                where.append("date_start=%s::date")
                params.append(match["date_start"])
            if match.get("event_type"):
                where.append("event_type=%s")
                params.append(match["event_type"])
            where.append("status NOT IN ('cancelled','deleted')")
            cur.execute(f"SELECT id FROM calendar_events WHERE {' AND '.join(where)} ORDER BY id", params)
            rows = cur.fetchall()
            c.close()
            if len(rows) == 0:
                return {"status": "not_found", "event_id": None, "cancelled": False,
                        "before": None, "after": None, "message": "No matching active event found."}
            if len(rows) > 1:
                return {"status": "ambiguous_match", "event_id": None, "cancelled": False,
                        "before": None, "after": None, "message": "Multiple matching events.",
                        "candidates": [r["id"] for r in rows]}
            eid = rows[0]["id"]
        except Exception as e:
            return {"status": "error", "event_id": None, "cancelled": False,
                    "before": None, "after": None, "message": str(e)[:200]}

    if not eid:
        return {"status": "refused", "event_id": None, "cancelled": False,
                "before": None, "after": None, "message": "event_id or match required."}

    try:
        c = _conn()
        cur = c.cursor()
        cur.execute("SELECT * FROM calendar_events WHERE id=%s", (eid,))
        before = cur.fetchone()
        if not before:
            c.close()
            return {"status": "not_found", "event_id": eid, "cancelled": False,
                    "before": None, "after": None, "message": f"Event id={eid} not found."}
        if before["status"] == "cancelled":
            c.close()
            before_s = _serialize_dict(before)
            return {"status": "duplicate", "event_id": eid, "cancelled": False,
                    "before": before_s, "after": before_s, "message": "Event is already cancelled."}
        cur.execute("UPDATE calendar_events SET status='cancelled', updated_at=now() WHERE id=%s RETURNING *", (eid,))
        after = cur.fetchone()
        c.commit()
        c.close()
    except Exception as e:
        return {"status": "error", "event_id": eid, "cancelled": False,
                "before": None, "after": None, "message": str(e)[:200]}

    before_s = _serialize_dict(before)
    after_s = _serialize_dict(after) if after else None

    # Audit
    try:
        c2 = _conn()
        cur2 = c2.cursor()
        cur2.execute(
            "INSERT INTO qcal_write_audit (idempotency_key, operation, entity_type, entity_id, date, source, payload_json, result_json) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (idempotency_key, "event_cancel", "event", eid,
             after_s.get("date_start", "") if after_s else "",
             source, _json.dumps({"reason": reason}, default=str),
             _json.dumps({"before": before_s, "after": after_s}, default=str)))
        c2.commit()
        c2.close()
    except Exception:
        pass

    # Snapshot
    try:
        build_snapshot(after_s.get("date_start", "") if after_s else "")
    except Exception:
        pass

    return {"status": "ok", "event_id": eid, "cancelled": True, "before": before_s, "after": after_s,
            "idempotency_key": idempotency_key,
            "message": f"Cancelled event id={eid}: {before.get('title','?')}"}


def _serialize_dict(d: dict) -> dict:
    """Convert non-serializable types to strings in a dict."""
    if not d:
        return {}
    out = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (int, float, str, bool, type(None))):
            out[k] = v
        else:
            out[k] = str(v)
    return out


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

    # Weight history
    if _table_exists("weight_history"):
        wh = _safe_query("SELECT * FROM weight_history WHERE date=%s ORDER BY measured_at DESC LIMIT 1", (date_str,))
        snap["weight"] = wh[0] if wh else None
        source_tables.append("weight_history")
        total_fields += 1
        if wh: found_fields += 1
    else:
        missing_tables.append("weight_history")

    # Body composition
    # Primary: qbot_v2.body_measurements (Garmin canonical, INDEX_SCALE full body comp)
    if _table_exists("body_measurements", schema="qbot_v2"):
        bm = _safe_query(
            "SELECT date AS date, source_system || '/' || source_type AS source, "
            "weight_kg, bmi, body_fat_pct, body_water_pct, muscle_mass_kg, "
            "bone_mass_kg, quality_status, completeness_score, imported_at "
            "FROM qbot_v2.body_measurements WHERE date=%s "
            "ORDER BY completeness_score DESC, imported_at DESC LIMIT 1",
            (date_str,))
        snap["body_composition"] = bm[0] if bm else None
        if bm:
            source_tables.append("qbot_v2.body_measurements")
    # Fallback: legacy body_daily
    if not snap.get("body_composition") and _table_exists("body_daily", schema="qbot_v2"):
        bd = _safe_query(
            "SELECT * FROM qbot_v2.body_daily WHERE date=%s "
            "ORDER BY CASE source WHEN 'garmin_index_scale' THEN 1 "
            "WHEN 'garmin_mfp' THEN 2 ELSE 3 END, "
            "imported_at DESC LIMIT 1",
            (date_str,))
        snap["body_composition"] = bd[0] if bd else None
        if bd:
            source_tables.append("qbot_v2.body_daily (legacy fallback)")
    if not snap.get("body_composition"):
        if not _table_exists("body_measurements", schema="qbot_v2"):
            missing_tables.append("qbot_v2.body_measurements")
        if not _table_exists("body_daily", schema="qbot_v2"):
            missing_tables.append("qbot_v2.body_daily (legacy)")

    # Training sessions
    if _table_exists("training_sessions"):
        ts = _safe_query("SELECT * FROM training_sessions WHERE date=%s ORDER BY started_at", (date_str,))
        snap["training"] = ts if ts else None
        source_tables.append("training_sessions")
        total_fields += 1
        if ts: found_fields += 1

    # Xert metrics
    if _table_exists("xert_metrics"):
        xm = _safe_query("SELECT * FROM xert_metrics WHERE date=%s ORDER BY imported_at DESC LIMIT 1", (date_str,))
        snap["xert"] = xm[0] if xm else None
        source_tables.append("xert_metrics")
        total_fields += 1
        if xm: found_fields += 1
    else:
        missing_tables.append("xert_metrics")

    # Calendar day metadata
    day = day_get(date_str)
    if day:
        snap["day_type"] = day.get("day_type")
        snap["day_notes"] = day.get("notes")
    source_tables.append("calendar_days")

    # Xert — only if table missing, else just missing_field
    if not _table_exists("xert_metrics"):
        missing_tables.append("xert_metrics")
    if not _table_exists("weight_history"):
        missing_tables.append("weight_history")
    if not _table_exists("body_composition"):
        missing_tables.append("body_composition")

    # Per-date missing fields (table exists but no data for this date)
    if _table_exists("weight_history") and not snap.get("weight"):
        missing_fields.append("weight_kg")
    if _table_exists("body_composition") and not snap.get("body_composition"):
        missing_fields.append("body_fat_pct")
    if _table_exists("training_sessions") and not snap.get("training"):
        missing_fields.append("training_load")
    if _table_exists("qbot_sleep_daily") and not snap.get("sleep"):
        missing_fields.extend(["sleep_duration", "sleep_score", "hrv_ms", "resting_hr"])
    if _table_exists("qbot_wellness_daily") and not snap.get("training"):
        missing_fields.append("hrv_ms")
    if _table_exists("xert_metrics"):
        missing_fields.append("threshold_power_w")  # table exists but never gets xert data yet

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


def import_history_per_source(source: str, date_from: str, date_to: str, dry_run: bool = True) -> dict:
    """Per-source import audit or execution. Fetches live data for Garmin sources."""
    result: dict[str, Any] = {
        "source": source, "date_from": date_from, "date_to": date_to,
        "dry_run": dry_run, "sections": {}, "errors": [],
    }

    if source == "garmin":
        try:
            from qbot_garmin_history import read_weight_history, read_body_composition, read_training_sessions

            # Weight
            weight = read_weight_history(date_from, date_to)
            if weight and "error" in weight[0]:
                result["errors"].append(f"weight: {weight[0]['error']}")
            else:
                result["sections"]["weight_history"] = {"count": len(weight), "sample": weight[:2] if weight else [], "all": weight, "table": "weight_history"}

            # Body composition
            bc = read_body_composition(date_from, date_to)
            if bc and "error" in bc[0]:
                result["errors"].append(f"body_comp: {bc[0]['error']}")
            else:
                result["sections"]["body_composition"] = {"count": len(bc), "sample": bc[:2] if bc else [], "all": bc, "table": "body_composition"}

            # Training
            train = read_training_sessions(date_from, date_to)
            if train and "error" in train[0]:
                result["errors"].append(f"training: {train[0]['error']}")
            else:
                result["sections"]["training_sessions"] = {"count": len(train), "sample": train[:2] if train else [], "all": train, "table": "training_sessions"}

            # Sleep/wellness (already in DB — just count)
            try:
                with _conn() as c:
                    for tbl, col in [("qbot_sleep_daily","date"),("qbot_wellness_daily","date")]:
                        r = c.execute(f"SELECT COUNT(*) c FROM {tbl} WHERE {col} BETWEEN %s AND %s", (date_from, date_to)).fetchone()
                        result["sections"][tbl] = {"count": r["c"], "already_imported": True}
            except Exception:
                pass

            if not dry_run and not result.get("errors"):
                _import_garmin_data(result["sections"])
                result["imported"] = True
            else:
                result["imported"] = False

        except Exception as e:
            result["errors"].append(f"garmin reader failed: {e}")

    elif source == "intervals-comments":
        try:
            from qbot_garmin_history import read_intervals_comments
            comments = read_intervals_comments(date_from, date_to)
            if comments and "error" in comments[0]:
                result["errors"].append(comments[0]["error"])
            else:
                high = [c for c in comments if c.get("confidence") == "high"]
                manual = [c for c in comments if c.get("manual_review_required")]
                result["sections"]["intervals_nutrition_comments"] = {
                    "total": len(comments),
                    "high_confidence": len(high),
                    "needs_manual_review": len(manual),
                    "sample": comments[:3],
                }
            result["imported"] = False
        except Exception as e:
            result["errors"].append(f"intervals-comments failed: {e}")

    elif source == "xert":
        try:
            import httpx, base64
            xert_email = os.getenv("XERT_EMAIL", "")
            xert_pw = os.getenv("XERT_PASSWORD", "")
            if not xert_email or not xert_pw:
                result["sections"]["xert_metrics"] = {"count": 0, "status": "credentials_missing"}
            else:
                with httpx.Client(timeout=15) as client:
                    token_r = client.post(
                        "https://www.xertonline.com/oauth/token",
                        auth=("xert_public", "xert_public"),
                        data={"grant_type": "password", "username": xert_email, "password": xert_pw},
                    )
                    token_r.raise_for_status()
                    token = token_r.json()["access_token"]
                    training_r = client.get(
                        "https://www.xertonline.com/oauth/training",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    training_r.raise_for_status()
                    training_data = training_r.json()
                    advice = training_data.get("advice", {})
                    sig = advice.get("signature", {})
                    ts = advice.get("training_status", {})

                    today = date.today().isoformat()
                    entry = {
                        "date": today,
                        "source": "xert",
                        "threshold_power_w": round(sig.get("ftp", 0), 1) if sig.get("ftp") else None,
                        "high_intensity_energy_kj": round((sig.get("atc", 0) or 0) / 1000, 1),
                        "peak_power_w": round(sig.get("pp", 0), 1) if sig.get("pp") else None,
                        "form_score": None,
                        "freshness": ts.get("freshness"),
                        "fatigue": ts.get("fatigue"),
                        "fitness": ts.get("fitness"),
                        "strain": ts.get("strain"),
                        "difficulty_score": ts.get("difficulty_score"),
                        "focus": ts.get("focus_name"),
                        "status": ts.get("status"),
                        "training_load": ts.get("load"),
                        "raw_json": training_data,
                    }

                    result["sections"]["xert_metrics"] = {"count": 1, "sample": [entry], "all": [entry], "table": "xert_metrics"}

                    if not dry_run:
                        with _conn() as conn:
                            conn.execute(
                                """INSERT INTO xert_metrics (date, source, threshold_power_w,
                                   high_intensity_energy_kj, peak_power_w, training_load,
                                   freshness, fatigue, fitness, strain, difficulty_score,
                                   focus, status, raw_json)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                                (today, "xert", entry["threshold_power_w"], entry["high_intensity_energy_kj"],
                                 entry["peak_power_w"], entry["training_load"], entry["freshness"],
                                 entry["fatigue"], entry["fitness"], entry["strain"],
                                 entry["difficulty_score"], entry["focus"], entry["status"],
                                 json.dumps(entry["raw_json"])),
                            )
                            conn.commit()
                        result["imported"] = True
                        result["sections"]["xert_metrics"]["note"] = "Xert daily snapshot imported"
                    else:
                        result["sections"]["xert_metrics"]["note"] = "Xert API ok — current-day form data. No historical API available."
                        result["imported"] = False
        except Exception as e:
            result["errors"].append(f"Xert API: {str(e)[:200]}")
            result["sections"]["xert_metrics"] = {"count": 0, "status": "api_error", "detail": str(e)[:100]}
        result["imported"] = result.get("imported", False)

    elif source == "intervals-comments":
        try:
            from qbot_garmin_history import read_intervals_comments
            comments = read_intervals_comments(date_from, date_to)
            if comments and "error" in comments[0]:
                result["errors"].append(comments[0]["error"])
            else:
                high = [c for c in comments if c.get("confidence") == "high"]
                manual = [c for c in comments if c.get("manual_review_required")]
                result["sections"]["intervals_nutrition_comments"] = {
                    "total": len(comments),
                    "high_confidence": len(high),
                    "needs_manual_review": len(manual),
                    "sample": comments[:3] if comments else [],
                }
                # Import high-confidence entries into nutrition_daily_summary
                if not dry_run and high:
                    imported = 0
                    for c in high:
                        d = c["date"]
                        kcal = c.get("calories_kcal")
                        prot = c.get("protein_g")
                        carbs = c.get("carbs_g")
                        fat = c.get("fat_g")
                        if kcal is not None:
                            with _conn() as conn:
                                conn.execute(
                                    """INSERT INTO nutrition_daily_summary (date, source, kcal_total,
                                       protein_total, carbs_total, fat_total)
                                       VALUES (%s,%s,%s,%s,%s,%s)
                                       ON CONFLICT (date, source) DO NOTHING""",
                                    (d, "intervals_comment_import", kcal, prot, carbs, fat),
                                )
                                conn.commit()
                            imported += 1
                    result["sections"]["intervals_nutrition_comments"]["imported"] = imported
                    result["imported"] = True
            result["imported"] = result.get("imported", False)
        except Exception as e:
            result["errors"].append(f"intervals-comments failed: {e}")

    elif source == "cronometer":
        crono_e = os.getenv("CRONOMETER_EMAIL", "")
        crono_p = os.getenv("CRONOMETER_PASSWORD", "")
        if not crono_e or not crono_p:
            result["sections"]["cronometer"] = {"count": 0, "status": "credentials_missing", "note": "CRONOMETER_EMAIL/CRONOMETER_PASSWORD not configured."}
        else:
            try:
                os.environ['CRONOMETER_USERNAME'] = crono_e
                os.environ['CRONOMETER_PASSWORD'] = crono_p
                from cronometer_mcp import CronometerClient
                c = CronometerClient()
                c.authenticate()
                sd = date.fromisoformat(date_from)
                ed = date.fromisoformat(date_to)
                daily = c.get_daily_summary(sd, ed)
                total = len(daily) if daily else 0
                result["sections"]["cronometer"] = {
                    "count": total,
                    "status": "ok" if total > 0 else "no_data",
                    "sample": daily[:2] if daily else [],
                }
                if not dry_run and daily:
                    for row in daily:
                        d = str(row.get("date", ""))[:10]
                        if d:
                            with _conn() as conn:
                                conn.execute(
                                    """INSERT INTO nutrition_daily_summary (date, source, kcal_total,
                                       protein_total, carbs_total, fat_total, fiber_total, sodium_mg, fluids_total)
                                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                       ON CONFLICT (date, source) DO NOTHING""",
                                    (d, "cronometer_import",
                                     float(row.get("Energy (kcal)", 0) or 0),
                                     float(row.get("Carbs (g)", 0) or 0),
                                     float(row.get("Protein (g)", 0) or 0),
                                     float(row.get("Fat (g)", 0) or 0),
                                     float(row.get("Fiber (g)", 0) or 0),
                                     float(row.get("Sodium (mg)", 0) or 0),
                                     float(row.get("Water (ml)", 0) or 0)),
                                )
                                conn.commit()
                    result["imported"] = True
            except Exception as e:
                err_str = str(e)[:200]
                if "GWT" in err_str or "RPC" in err_str:
                    result["sections"]["cronometer"] = {"count": 0, "status": "gwt_rpc_version_mismatch", "note": "Cronometer API GWT-RPC version mismatch — library outdated. Działa przez import CSV manualnie."}
                else:
                    result["sections"]["cronometer"] = {"count": 0, "status": "api_error", "detail": err_str}
        result["imported"] = result.get("imported", False)

    elif source == "routes":
        # Check route_artifacts and training_sessions for route_ref
        try:
            with _conn() as c:
                r = c.execute("SELECT COUNT(*) c FROM route_artifacts WHERE created_at::date BETWEEN %s AND %s", (date_from, date_to)).fetchone()
                t = c.execute("SELECT COUNT(*) c FROM training_sessions WHERE date BETWEEN %s AND %s AND route_ref IS NOT NULL", (date_from, date_to)).fetchone()
                sample = _safe_query("SELECT id, route_id, created_at FROM route_artifacts WHERE created_at::date BETWEEN %s AND %s LIMIT 5", (date_from, date_to))
                result["sections"]["routes"] = {
                    "route_artifacts": r["c"],
                    "training_sessions_with_routes": t["c"],
                    "sample": sample,
                }
        except Exception as e:
            result["sections"]["routes"] = {"count": 0, "status": "error", "detail": str(e)[:100]}
        result["imported"] = False

    return result


def _import_garmin_data(sections: dict) -> None:
    """Import Garmin data into target tables. Iterates over 'all' entries."""
    # Weight
    w = sections.get("weight_history", {})
    for entry in w.get("all", []):
        try:
            with _conn() as conn:
                conn.execute(
                    """INSERT INTO weight_history (date, weight_kg, source, external_id, raw_json)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (entry["date"], entry["weight_kg"], "garmin", entry.get("external_id"), json.dumps(entry.get("raw_json"))),
                )
                conn.commit()
        except Exception:
            pass

    # Body composition
    bc = sections.get("body_composition", {})
    for entry in bc.get("all", []):
        try:
            with _conn() as conn:
                conn.execute(
                    """INSERT INTO body_composition (date, weight_kg, body_fat_pct, bmi, lean_mass_kg,
                       muscle_mass_kg, body_water_pct, bone_mass_kg, source, external_id, raw_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (entry["date"], entry.get("weight_kg"), entry.get("body_fat_pct"), entry.get("bmi"),
                     entry.get("lean_mass_kg"), entry.get("muscle_mass_kg"), entry.get("body_water_pct"),
                     entry.get("bone_mass_kg"), "garmin", entry.get("external_id"), json.dumps(entry.get("raw_json"))),
                )
                conn.commit()
        except Exception:
            pass

    # Training
    t = sections.get("training_sessions", {})
    for entry in t.get("all", []):
        try:
            with _conn() as conn:
                conn.execute(
                    """INSERT INTO training_sessions (date, started_at, ended_at, source, external_id,
                       activity_type, title, duration_sec, elapsed_duration_sec,
                       distance_km, elevation_gain_m,
                       calories_kcal, avg_hr, max_hr, avg_power_w, max_power_w,
                       training_load, training_effect, anaerobic_training_effect,
                       route_ref, raw_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (entry["date"], entry.get("started_at"), entry.get("ended_at"), "garmin", entry.get("external_id"),
                     entry.get("activity_type"), entry.get("title"), entry.get("duration_sec"),
                     entry.get("elapsed_duration_sec"),
                     entry.get("distance_km"), entry.get("elevation_gain_m"),
                     entry.get("calories_kcal"), entry.get("avg_hr"), entry.get("max_hr"),
                     entry.get("avg_power_w"), entry.get("max_power_w"),
                     entry.get("training_load"), entry.get("training_effect"),
                     entry.get("anaerobic_training_effect"),
                     entry.get("route_ref"), json.dumps(entry.get("raw_json"))),
                )
                conn.commit()
        except Exception:
            pass
