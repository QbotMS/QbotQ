#!/usr/bin/env python3
"""QBot Health DB — CRUD for goals, supplements, protocols, intake, reports."""
from __future__ import annotations

import os
import json as _json
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=5,
    )


def _ser(row: dict | None) -> dict | None:
    if not row:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, (date, datetime)):
            d[k] = v.isoformat()
    return d


def _sers(rows: list[dict]) -> list[dict]:
    return [_ser(r) for r in rows]


# ── Goals ──

def goal_create(name: str, goal_type: str = "weight_loss",
                start_weight: float | None = None, target_weight: float | None = None,
                target_date: str | None = None, next_target_weight: float | None = None,
                next_target_date: str | None = None, priority: str = "balanced",
                notes: str | None = None) -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO health_goals (goal_name,goal_type,start_weight_kg,target_weight_kg,
               target_date,next_target_weight_kg,next_target_date,priority,notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (name, goal_type, start_weight, target_weight, target_date,
             next_target_weight, next_target_date, priority, notes),
        ).fetchone()
        c.commit()
    return _ser(dict(r))


def goal_list(status: str | None = "active") -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM health_goals WHERE status=%s ORDER BY created_at DESC", (status,)).fetchall()
    return _sers(rows)


def goal_get(gid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM health_goals WHERE id=%s", (gid,)).fetchone()
    return _ser(dict(r)) if r else None


def goal_update_status(gid: int, status: str) -> dict | None:
    with _conn() as c:
        c.execute("UPDATE health_goals SET status=%s, updated_at=now() WHERE id=%s", (status, gid))
        c.commit()
    return goal_get(gid)


def goal_delete(gid: int) -> dict | None:
    g = goal_get(gid)
    if not g:
        return None
    with _conn() as c:
        c.execute("DELETE FROM health_goals WHERE id=%s", (gid,))
        c.commit()
    return g


# ── Supplement Inventory ──

def supp_create(name: str, brand: str | None = None, form: str = "capsule",
                dose_per_unit: float | None = None, dose_unit: str = "mg",
                units_total: float | None = None, units_remaining: float | None = None,
                purchase_date: str | None = None, expiry_date: str | None = None,
                source_shop: str | None = None, notes: str | None = None) -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO supplement_inventory (name,brand,form,dose_per_unit,dose_unit,
               units_total,units_remaining,purchase_date,expiry_date,source_shop,notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (name, brand, form, dose_per_unit, dose_unit, units_total, units_remaining,
             purchase_date, expiry_date, source_shop, notes),
        ).fetchone()
        c.commit()
    return _ser(dict(r))


def supp_list(status: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as c:
        if status:
            rows = c.execute("SELECT * FROM supplement_inventory WHERE status=%s ORDER BY name LIMIT %s", (status, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM supplement_inventory ORDER BY name LIMIT %s", (limit,)).fetchall()
    return _sers(rows)


def supp_get(sid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM supplement_inventory WHERE id=%s", (sid,)).fetchone()
    return _ser(dict(r)) if r else None


def supp_update(sid: int, units_remaining: float | None = None, status: str | None = None) -> dict | None:
    with _conn() as c:
        if units_remaining is not None:
            c.execute("UPDATE supplement_inventory SET units_remaining=%s, updated_at=now() WHERE id=%s", (units_remaining, sid))
        if status:
            c.execute("UPDATE supplement_inventory SET status=%s, updated_at=now() WHERE id=%s", (status, sid))
        c.commit()
    return supp_get(sid)


def supp_delete(sid: int) -> dict | None:
    s = supp_get(sid)
    if not s:
        return None
    with _conn() as c:
        c.execute("DELETE FROM supplement_inventory WHERE id=%s", (sid,))
        c.commit()
    return s


# ── Protocols ──

def prot_create(supplement_name: str, dose: float = 1, dose_unit: str = "mg",
                frequency: str = "daily", timing: str = "morning",
                with_food: bool | None = None, goal: str = "general_health",
                start_date: str | None = None, notes: str | None = None,
                supplement_id: int | None = None) -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO supplement_protocols (supplement_id,supplement_name,dose,dose_unit,
               frequency,timing,with_food,goal,start_date,reason)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (supplement_id, supplement_name, dose, dose_unit, frequency, timing,
             with_food, goal, start_date, notes),
        ).fetchone()
        c.commit()
    return _ser(dict(r))


def prot_list(status: str | None = "active", limit: int = 50) -> list[dict]:
    with _conn() as c:
        if status:
            rows = c.execute("SELECT * FROM supplement_protocols WHERE status=%s ORDER BY id LIMIT %s", (status, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM supplement_protocols ORDER BY id LIMIT %s", (limit,)).fetchall()
    return _sers(rows)


def prot_get(pid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM supplement_protocols WHERE id=%s", (pid,)).fetchone()
    return _ser(dict(r)) if r else None


def prot_update_status(pid: int, status: str) -> dict | None:
    with _conn() as c:
        c.execute("UPDATE supplement_protocols SET status=%s, updated_at=now() WHERE id=%s", (status, pid))
        c.commit()
    return prot_get(pid)


# ── Intake Log ──

def intake_log(supplement_name: str, date_str: str, dose: float = 1, dose_unit: str = "mg",
               taken: bool = True, source: str = "manual", notes: str | None = None,
               supplement_id: int | None = None, protocol_id: int | None = None) -> dict:
    # Resolve supplement_id from name if not given
    if not supplement_id:
        try:
            for s in supp_list():
                if s.get("name", "").lower() == supplement_name.lower():
                    supplement_id = s["id"]
                    break
        except Exception:
            pass
    with _conn() as c:
        r = c.execute(
            """INSERT INTO supplement_intake_log (supplement_id,protocol_id,date,dose,dose_unit,taken,source,notes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (supplement_id, protocol_id, date_str, dose, dose_unit, taken, source, notes),
        ).fetchone()
        c.commit()
    d = _ser(dict(r))
    d["supplement_name"] = supplement_name
    return d


def intake_list(date_str: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as c:
        if date_str:
            rows = c.execute("SELECT * FROM supplement_intake_log WHERE date=%s ORDER BY created_at DESC LIMIT %s", (date_str, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM supplement_intake_log ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
    result = []
    for r in rows:
        d = _ser(dict(r))
        if not d.get("supplement_name") and d.get("supplement_id"):
            try:
                s = supp_get(d["supplement_id"])
                if s:
                    d["supplement_name"] = s.get("name", "?")
            except Exception:
                pass
        if not d.get("supplement_name"):
            d["supplement_name"] = "?"
        result.append(d)
    return result


# ── Advice Reports ──

def report_create(topic: str, date_str: str,
                  recommendations: dict | None = None,
                  warnings: dict | None = None,
                  assumptions: dict | None = None,
                  missing_fields: dict | None = None,
                  confidence: str = "medium",
                  period_from: str | None = None,
                  period_to: str | None = None) -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO health_advice_reports (date,topic,period_from,period_to,
               recommendations_json,warnings_json,assumptions_json,missing_fields_json,confidence)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (date_str, topic, period_from, period_to,
             _json.dumps(recommendations) if recommendations else None,
             _json.dumps(warnings) if warnings else None,
             _json.dumps(assumptions) if assumptions else None,
             _json.dumps(missing_fields) if missing_fields else None,
             confidence),
        ).fetchone()
        c.commit()
    r2 = _ser(dict(r))
    for k in ("recommendations_json","warnings_json","assumptions_json","missing_fields_json"):
        if r2.get(k) and isinstance(r2[k], str):
            try: r2[k] = _json.loads(r2[k])
            except Exception: pass
    return r2


# ── Health Events ──

def health_event_create(
    date_start: str, title: str, event_type: str = "illness",
    severity: str = "mild", description: str | None = None,
    date_end: str | None = None, symptoms: list[str] | None = None,
    constraints: dict | None = None, source: str = "manual",
    confidence: str = "high", affects_training: bool = True,
    affects_nutrition: bool = True, affects_recovery: bool = True,
) -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO health_events (date_start,date_end,event_type,title,description,
               severity,symptoms_json,constraints_json,source,confidence,
               affects_training,affects_nutrition,affects_recovery)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (date_start, date_end, event_type, title, description, severity,
             _json.dumps(symptoms) if symptoms else None,
             _json.dumps(constraints) if constraints else None,
             source, confidence, affects_training, affects_nutrition, affects_recovery),
        ).fetchone()
        c.commit()
    return _ser(dict(r))


def health_event_list(status: str | None = "active", event_type: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      limit: int = 50) -> list[dict]:
    with _conn() as c:
        conds = []
        params = []
        if status: conds.append("status=%s"); params.append(status)
        if event_type: conds.append("event_type=%s"); params.append(event_type)
        if date_from: conds.append("date_start>=%s"); params.append(date_from)
        if date_to: conds.append("date_start<=%s"); params.append(date_to)
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        rows = c.execute(f"SELECT * FROM health_events {where} ORDER BY date_start DESC LIMIT %s", params + [limit]).fetchall()
    return _sers(rows)


def health_event_get(eid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM health_events WHERE id=%s", (eid,)).fetchone()
    return _ser(dict(r)) if r else None


def health_event_resolve(eid: int, date_end: str) -> dict | None:
    with _conn() as c:
        c.execute("UPDATE health_events SET status='resolved', date_end=%s, updated_at=now() WHERE id=%s",
                  (date_end, eid))
        c.commit()
    return health_event_get(eid)


def health_event_delete(eid: int) -> dict | None:
    ev = health_event_get(eid)
    if not ev: return None
    with _conn() as c:
        c.execute("DELETE FROM health_events WHERE id=%s", (eid,))
        c.commit()
    return ev


def active_health_events() -> list[dict]:
    return health_event_list(status="active")


# ── Observations ──

def observation_create(event_id: int | None, date_str: str, observation_type: str,
                        value_text: str | None = None, value_number: float | None = None,
                        unit: str | None = None, source: str = "manual") -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO health_event_observations (event_id,date,observation_type,value_text,value_number,unit,source)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (event_id, date_str, observation_type, value_text, value_number, unit, source),
        ).fetchone()
        c.commit()
    return _ser(dict(r))


# ── Health Risk Notes ──

def risk_create(title: str, risk_type: str = "other", description: str | None = None,
                constraints: dict | None = None, evidence: dict | None = None) -> dict:
    with _conn() as c:
        r = c.execute(
            """INSERT INTO health_risk_notes (title,risk_type,description,constraints_json,evidence_json)
               VALUES (%s,%s,%s,%s,%s) RETURNING *""",
            (title, risk_type, description,
             _json.dumps(constraints) if constraints else None,
             _json.dumps(evidence) if evidence else None),
        ).fetchone()
        c.commit()
    return _ser(dict(r))


def risk_list(status: str | None = "active", limit: int = 50) -> list[dict]:
    with _conn() as c:
        if status:
            rows = c.execute("SELECT * FROM health_risk_notes WHERE status=%s ORDER BY created_at DESC LIMIT %s", (status, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM health_risk_notes ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
    return _sers(rows)


def risk_get(rid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM health_risk_notes WHERE id=%s", (rid,)).fetchone()
    d = _ser(dict(r)) if r else None
    if d:
        for k in ("constraints_json", "evidence_json"):
            if d.get(k) and isinstance(d[k], str):
                try: d[k] = _json.loads(d[k])
                except Exception: pass
    return d


def risk_update_status(rid: int, status: str) -> dict | None:
    with _conn() as c:
        c.execute("UPDATE health_risk_notes SET status=%s, updated_at=now() WHERE id=%s", (status, rid))
        c.commit()
    return risk_get(rid)


def risk_delete(rid: int) -> dict | None:
    r = risk_get(rid)
    if not r: return None
    with _conn() as c:
        c.execute("DELETE FROM health_risk_notes WHERE id=%s", (rid,))
        c.commit()
    return r


def active_constraints() -> list[dict]:
    """Return all active risk constraints from health_risk_notes."""
    notes = risk_list("active")
    all_constraints: list[dict] = []
    for n in notes:
        cj = n.get("constraints_json")
        if isinstance(cj, dict):
            all_constraints.append(cj)
    return all_constraints
