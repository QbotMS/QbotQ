#!/usr/bin/env python3
"""QBot Planning Memory — detect, store, list, reconcile planning facts."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any


# ── Table schema ─────────────────────────────────────────────────────────────
# CREATE TABLE IF NOT EXISTS qbot_planning_facts (
#     id SERIAL PRIMARY KEY,
#     date DATE NOT NULL,
#     channel TEXT NOT NULL DEFAULT 'unknown',
#     source_query_text TEXT,
#     source_query_hash TEXT,
#     fact_type TEXT NOT NULL,
#     status TEXT NOT NULL DEFAULT 'proposed',
#     confidence TEXT NOT NULL DEFAULT 'medium',
#     title TEXT NOT NULL,
#     fact_json JSONB DEFAULT '{}'::jsonb,
#     related_event_id INTEGER,
#     related_training_session_id INTEGER,
#     valid_from DATE,
#     valid_until DATE,
#     created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
#     updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
# );
# CREATE INDEX IF NOT EXISTS idx_pf_date ON qbot_planning_facts(date);
# CREATE INDEX IF NOT EXISTS idx_pf_type ON qbot_planning_facts(fact_type);
# CREATE INDEX IF NOT EXISTS idx_pf_status ON qbot_planning_facts(status);
# CREATE INDEX IF NOT EXISTS idx_pf_hash ON qbot_planning_facts(source_query_hash);


def _ensure_table():
    try:
        c = _db()
        cur = c.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS qbot_planning_facts (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                channel TEXT NOT NULL DEFAULT 'unknown',
                source_query_text TEXT,
                source_query_hash TEXT,
                fact_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed',
                confidence TEXT NOT NULL DEFAULT 'medium',
                title TEXT NOT NULL,
                fact_json JSONB DEFAULT '{}'::jsonb,
                related_event_id INTEGER,
                related_training_session_id INTEGER,
                valid_from DATE,
                valid_until DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pf_date ON qbot_planning_facts(date)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pf_type ON qbot_planning_facts(fact_type)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pf_status ON qbot_planning_facts(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pf_hash ON qbot_planning_facts(source_query_hash)")
        c.commit()
        c.close()
    except Exception:
        pass


def _db():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"),
        user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""),
        row_factory=dict_row,
        connect_timeout=5,
    )

import os


def _resolve_date(query: str, context: dict | None = None) -> str:
    """Resolve date from query (dziś/jutro/today/tomorrow/Y-m-d) or default today."""
    q = query.lower()
    today = date.today()
    if re.search(r'\b(pojutrze|pojutrzu)\b', q):
        return (today + timedelta(days=2)).isoformat()
    if re.search(r'\b(jutro|tomorrow)\b', q):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r'\b(dziś|dzisiaj|today)\b', q):
        return today.isoformat()
    m = re.search(r'(\d{4}-\d{2}-\d{2})', query)
    if m:
        try:
            return date.fromisoformat(m.group(1)).isoformat()
        except ValueError:
            pass
    if context:
        for k in ('date', 'date_from', 'single_date'):
            v = context.get(k)
            if v:
                try:
                    return date.fromisoformat(str(v)[:10]).isoformat()
                except (ValueError, TypeError):
                    pass
    return today.isoformat()


def _hash_query(q: str) -> str:
    import hashlib
    return hashlib.sha256(q.encode()).hexdigest()[:16]


# ── Detection patterns ───────────────────────────────────────────────────────

_TRAINING_PATTERNS = [
    r'przed\s+treningiem',
    r'po\s+treningu',
    r'na\s+trening',
    r'planuj[ęe]\s+trening',
    r'jad[ęe]\s+na\s+trening',
    r'(dziś|dzisiaj|jutro)\s+trening',
    r'(dziś|dzisiaj|jutro)\s+mam\s+trening',
    r'godzin[ęa]\s+w\s+Z[12]',
    r'\d+\s*min\s+Z[12]',
    r'luźn[ey]ch?\s+Z[12]',
    r'długi\s+trening',
    r'trasa\s+dziś',
    r'(jad[ęe]|lecę|id[ęe])\s+(dzisiaj|dziś|jutro)\s+(luźn[eaoxy]|spokojn[eaoxy]|Z[12])',
]

_REST_PATTERNS = [
    r'(dziś|dzisiaj|jutro)\s+(rest|odpoczywam|odpoczynek|wolne|bez\s+treningu)',
    r'rest\s+(day|dziś|dzisiaj|jutro)',
    r'odpoczynek\s+(dziś|dzisiaj|jutro)',
]

_NUTRITION_PLAN_PATTERNS = [
    r'co.*zjeść.*przed\s+treningiem',
    r'co.*zjeść.*po\s+treningu',
    r'ile\s+(węgl|kcal|białk|tłuszcz).*(przed|po)\s+trening',
    r'co.*(zjeść|wypić).*(przed|po)\s+trening',
    r'posiłek\s+(przed|po)\s+treningowy',
]


def _extract_training_params(q: str) -> dict:
    """Extract duration_min, intensity, zones from query text."""
    params: dict = {"sport": "cycling", "duration_min": 60, "planned_zones": ["Z2"]}

    # Duration
    dm = re.search(r'(\d+)\s*min', q)
    if dm:
        params["duration_min"] = int(dm.group(1))
    hm = re.search(r'(\d+)\s*(h|godzin)', q)
    if hm:
        params["duration_min"] = int(hm.group(1)) * 60
    hm2 = re.search(r'(\d+)\s*h\s*(\d+)\s*min', q)
    if hm2:
        params["duration_min"] = int(hm2.group(1)) * 60 + int(hm2.group(2))

    # Intensity zones (case-insensitive for lowered queries)
    zones = re.findall(r'[Zz](\d)', q)
    if zones:
        params["planned_zones"] = [f"Z{z}" for z in sorted(set(zones))]
        params["intensity"] = "/".join(params["planned_zones"])
    else:
        if re.search(r'luźn', q):
            params["intensity"] = "Z1/Z2"
            params["planned_zones"] = ["Z1", "Z2"]
        elif re.search(r'(spokojn|easy|endurance)', q):
            params["intensity"] = "Z2"
            params["planned_zones"] = ["Z2"]
        else:
            params["intensity"] = "Z2"
            params["planned_zones"] = ["Z2"]

    # Purpose
    if re.search(r'przed\s+treningiem|co.*zjeść', q):
        params["purpose"] = "nutrition_planning"
        params["affects_nutrition"] = True
        params["affects_energy_balance"] = True
    else:
        params["purpose"] = "general_training"
        params["affects_nutrition"] = False
        params["affects_energy_balance"] = True

    return params


def detect_planning_facts(query_text: str, context: dict | None = None) -> list[dict]:
    """Detect planning facts from query text. Returns list of draft dicts, never writes."""
    q = query_text.lower()
    resolved_date = _resolve_date(query_text, context)
    drafts: list[dict] = []

    # ── A. Planned training ─────────────────────────────────────────────
    is_training = False
    for pat in _TRAINING_PATTERNS:
        if re.search(pat, q):
            is_training = True
            break

    if is_training:
        params = _extract_training_params(q)
        dur = params["duration_min"]
        zones = "/".join(params.get("planned_zones", ["Z2"]))
        title = f"Planowany trening rowerowy {dur} min {zones}"
        fact_json = {
            "sport": params.get("sport", "cycling"),
            "duration_min": dur,
            "intensity": params.get("intensity", "Z2"),
            "planned_zones": params.get("planned_zones", ["Z2"]),
            "purpose": params.get("purpose", "general_training"),
            "affects_nutrition": params.get("affects_nutrition", False),
            "affects_energy_balance": params.get("affects_energy_balance", True),
        }
        drafts.append({
            "fact_type": "planned_training",
            "date": resolved_date,
            "title": title,
            "confidence": "high" if dur else "medium",
            "fact_json": fact_json,
        })

    # ── B. Rest day ──────────────────────────────────────────────────────
    for pat in _REST_PATTERNS:
        if re.search(pat, q):
            drafts.append({
                "fact_type": "rest_day",
                "date": resolved_date,
                "title": "Dzień odpoczynku / rest day",
                "confidence": "high",
                "fact_json": {
                    "rest_day": True,
                    "affects_nutrition": True,
                    "affects_energy_balance": True,
                },
            })
            break

    # ── C. Nutrition plan assumption (only if training also detected) ────
    is_nutrition_plan = False
    for pat in _NUTRITION_PLAN_PATTERNS:
        if re.search(pat, q):
            is_nutrition_plan = True
            break

    if is_nutrition_plan and is_training:
        # Add a nutrition_plan_assumption linked to the training draft
        drafts.append({
            "fact_type": "nutrition_plan_assumption",
            "date": resolved_date,
            "title": "Plan żywieniowy pod trening",
            "confidence": "medium",
            "fact_json": {
                "related_to": "planned_training",
                "purpose": "pre_training_fueling",
                "affects_nutrition": True,
                "affects_energy_balance": True,
            },
        })
    elif is_nutrition_plan:
        drafts.append({
            "fact_type": "nutrition_plan_assumption",
            "date": resolved_date,
            "title": "Założenie planu żywieniowego",
            "confidence": "low",
            "fact_json": {
                "affects_nutrition": True,
                "affects_energy_balance": False,
            },
        })

    return drafts


# ── CRUD ──────────────────────────────────────────────────────────────────────

def save_planning_fact(draft: dict, channel: str = "unknown", confirm: bool = False) -> dict:
    """Save a planning fact. Only writes if confirm=True."""
    if not confirm:
        return {"status": "draft", "note": "confirm=True required to save", "draft": draft}

    _ensure_table()
    ftype = draft.get("fact_type", "custom")
    fd = draft.get("date", date.today().isoformat())
    title = draft.get("title", "Bez tytułu")
    conf = draft.get("confidence", "medium")
    fact_json = draft.get("fact_json", {})
    valid_until = draft.get("valid_until")

    try:
        c = _db()
        cur = c.cursor()
        cur.execute(
            """INSERT INTO qbot_planning_facts
               (date, channel, fact_type, status, confidence, title, fact_json, valid_until)
               VALUES (%s,%s,%s,'confirmed',%s,%s,%s,%s) RETURNING id""",
            (fd, channel, ftype, conf, title, json.dumps(fact_json, default=str), valid_until),
        )
        fid = cur.fetchone()["id"]
        c.commit()
        c.close()
        return {"status": "OK", "planning_fact_id": fid, "title": title, "fact_type": ftype}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)[:200]}


def list_planning_facts(
    fact_date: str | None = None,
    status: str | None = None,
    fact_type: str | None = None,
    title: str | None = None,
) -> list[dict]:
    """List planning facts, optionally filtered by date, status, fact_type and/or title."""
    _ensure_table()
    where = []
    params = []
    if fact_date:
        where.append("date = %s")
        params.append(fact_date)
    if status:
        where.append("status = %s")
        params.append(status)
    if fact_type:
        where.append("fact_type = %s")
        params.append(fact_type)
    if title:
        where.append("title ILIKE %s")
        params.append(f"%{title}%")

    sql = "SELECT * FROM qbot_planning_facts"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"

    try:
        c = _db()
        cur = c.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        c.close()
        result = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("fact_json"), str):
                try:
                    d["fact_json"] = json.loads(d["fact_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result
    except Exception:
        return []


def reconcile_plans(fact_date: str, dry_run: bool = True) -> list[dict]:
    """Reconcile planned_training facts against actual training sessions for date."""
    facts = list_planning_facts(fact_date=fact_date, status="confirmed")
    training_facts = [f for f in facts if f["fact_type"] == "planned_training"]

    if not training_facts:
        return [{"date": fact_date, "reconciliation_type": "no_plans", "summary": "Brak planowanych treningów do reconciliacji."}]

    actual_sessions = []
    try:
        c = _db()
        cur = c.cursor()
        cur.execute(
            """SELECT id, date, title, activity_type, duration_min, training_load, training_effect, avg_hr
               FROM training_sessions WHERE date = %s ORDER BY created_at DESC""",
            (fact_date,),
        )
        actual_sessions = cur.fetchall()
        c.close()
    except Exception:
        pass

    reconciliations = []
    for pf in training_facts:
        fj = pf.get("fact_json", {})
        if isinstance(fj, str):
            try:
                fj = json.loads(fj)
            except (json.JSONDecodeError, TypeError):
                fj = {}
        planned_dur = fj.get("duration_min", 60)

        if not actual_sessions:
            reconciliations.append({
                "planning_fact_id": pf["id"],
                "date": fact_date,
                "reconciliation_type": "missed",
                "summary": f"Brak aktywności — planowany trening ({pf['title']}) nie został odnotowany.",
                "details_json": {"planned_duration_min": planned_dur, "actual_sessions": 0},
            })
        else:
            for act in actual_sessions:
                actual_dur = act.get("duration_min") or 0
                dur_diff = abs(actual_dur - planned_dur) if actual_dur else planned_dur
                intensity_mismatch = False
                planned_zones = fj.get("planned_zones", [])
                if planned_zones and act.get("training_effect"):
                    te = float(act["training_effect"]) if act["training_effect"] else 0
                    if te > 3.0 and all(z in ("Z1", "Z2") for z in planned_zones):
                        intensity_mismatch = True

                if dur_diff > 30 and actual_dur > 0:
                    reconciliations.append({
                        "planning_fact_id": pf["id"],
                        "date": fact_date,
                        "reconciliation_type": "duration_mismatch",
                        "summary": f"Planowano {planned_dur} min, wykonano {actual_dur} min (różnica {dur_diff} min).",
                        "details_json": {"planned_duration_min": planned_dur, "actual_duration_min": actual_dur, "intensity_mismatch": intensity_mismatch},
                    })
                elif intensity_mismatch:
                    reconciliations.append({
                        "planning_fact_id": pf["id"],
                        "date": fact_date,
                        "reconciliation_type": "intensity_mismatch",
                        "summary": f"Planowano {'/'.join(planned_zones)}, ale trening miał wyższe obciążenie (TE={act.get('training_effect')})",
                        "details_json": {"planned_zones": planned_zones, "training_effect": act.get("training_effect")},
                    })
                else:
                    reconciliations.append({
                        "planning_fact_id": pf["id"],
                        "date": fact_date,
                        "reconciliation_type": "matched",
                        "summary": f"Plan ({pf['title']}) — znaleziono aktywność (id={act['id']}, {actual_dur} min).",
                        "details_json": {"actual_session_id": act["id"], "actual_duration_min": actual_dur, "planned_duration_min": planned_dur},
                    })

    return reconciliations if reconciliations else [{"date": fact_date, "reconciliation_type": "no_actual_data", "summary": "Brak danych treningowych do porównania."}]
