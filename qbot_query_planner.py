#!/usr/bin/env python3
"""QBot Semantic Query Planner v3 — consumes canonical query object from context resolver."""

from __future__ import annotations

import json, os, re
from datetime import date, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
    )

SAFE_TABLES = {
    "nutrition_daily_summary", "qbot_nutrition_daily", "meal_logs",
    "training_sessions", "weight_history", "body_composition",
    "qbot_sleep_daily", "qbot_wellness_daily",
    "xert_metrics", "calendar_daily_snapshots", "calendar_events",
    "health_events", "health_risk_notes", "health_goals",
    "supplement_inventory", "supplement_protocols", "supplement_intake_log",
}

# ── Domain → table mapping (planner only — no keyword logic) ──

_DOMAIN_TABLE = {
    "nutrition":    ("nutrition_daily_summary", "qbot_nutrition_daily"),
    "training":     ("training_sessions",),
    "weight":       ("weight_history",),
    "body_comp":    ("body_composition",),
    "sleep":        ("qbot_sleep_daily",),
    "recovery":     ("qbot_wellness_daily",),
    "xert":         ("xert_metrics",),
    "health_events":("health_events",),
    "supplements":  ("supplement_inventory",),
    "routes":       ("route_artifacts",),
}


def _safe_val(v: Any) -> Any:
    if isinstance(v, (date,)): return v.isoformat()[:10]
    if isinstance(v, (float,)):
        if v != v: return None
        return round(v, 1) if abs(v) < 100000 else round(v)
    return v


def execute_sql(sql: str, params: dict) -> list[dict]:
    if not sql.strip().upper().startswith("SELECT"): return []
    try:
        with _conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [{k: _safe_val(v) for k, v in dict(r).items()} for r in rows]
    except Exception as e:
        return [{"error": str(e)[:200]}]


# ── Planner ──

def plan(canonical: dict) -> dict[str, Any]:
    """Build execution plan from canonical query object."""
    t = canonical.get("resolved_time", {})
    task = canonical.get("task", {})
    df, dt = t.get("date_from", ""), t.get("date_to", "")
    domains = canonical.get("domains", [])
    negs = canonical.get("negative_constraints", [])
    itype = task.get("type", "lookup")

    plan_obj = {
        "task_type": itype, "date_from": df, "date_to": dt,
        "domains": domains, "negations": negs,
        "queries": [], "rejected": [], "warnings": [],
    }

    if not df or not dt:
        plan_obj["warnings"].append("No date range resolved")
        return plan_obj

    # ── Calendar day context ──
    if itype == "calendar_day_context":
        plan_obj["queries"].append({
            "domain": "calendar_snapshot",
            "sql": "SELECT * FROM calendar_daily_snapshots WHERE date=%(df)s",
            "params": {"df": df},
        })
        return plan_obj

    # ── Route list ──
    if itype == "route_list" or ("routes" in domains and negs and any(n in negs for n in ("no_export","no_gpx","list_only"))):
        limit = 10
        m = re.search(r"(\d+)\s+najnowsze", canonical.get("raw_query", "").lower())
        if m: limit = int(m.group(1))

        try:
            from qbot_route_tools import _tool_qbot_rwgps_route_list
            api_result = _tool_qbot_rwgps_route_list({"limit": max(limit, 10)})
            api_routes = api_result.get("routes", [])

            rows = []
            for r in api_routes[:limit]:
                rid = str(r.get("id", ""))
                name = r.get("name", "")
                dkm = r.get("distance_km") or 0
                elev = r.get("elevation_m") or 0
                # Fallback: local cache if API has 0 distance
                if dkm == 0:
                    try:
                        with _conn() as c:
                            local = c.execute(
                                "SELECT (metadata_json->>'distance_km')::float AS dkm, (metadata_json->>'elevation_gain_m')::float AS elev FROM route_artifacts WHERE route_id=%s AND (metadata_json->>'distance_km')::float > 0 LIMIT 1",
                                (rid,),
                            ).fetchone()
                            if local:
                                dkm = local.get("dkm", 0) or dkm
                                elev = local.get("elev", 0) or elev
                    except Exception:
                        pass

                rows.append({
                    "route_id": rid,
                    "name": name,
                    "distance_km": dkm,
                    "elevation_gain_m": elev,
                    "updated_at": r.get("updated_at", ""),
                    "origin": r.get("origin", ""),
                })
            plan_obj["queries"].append({"domain": "route_list", "limit": limit, "sql": "rwgps_api", "params": {}, "rows": rows})
        except Exception as e:
            plan_obj["warnings"].append(f"RWGPS API failed: {str(e)[:100]}")

        return plan_obj

    # ── Daily table: only when nutrition or training involved ──
    has_nutrition = "nutrition" in domains
    has_training = "training" in domains
    has_weight = "weight" in domains
    has_body = "body_comp" in domains

    if itype in ("range_analysis", "comparison", "trend") and (has_nutrition or has_training):
        joins, select_extras = [], []
        select_extras.append("d.date::date AS date")

        # Nutrition — prefer table with more non-zero data
        if has_nutrition:
            ns_count = _count_nonzero("nutrition_daily_summary", "kcal_total", df, dt)
            qb_count = _count_nonzero("qbot_nutrition_daily", "calories_kcal", df, dt)
            if qb_count > ns_count * 2:
                joins.append(
                    """LEFT JOIN (SELECT date, SUM(calories_kcal) AS kcal_in, SUM(protein_g) AS protein_g,
                       SUM(carbs_g) AS carbs_g, SUM(fat_g) AS fat_g, SUM(fluid_ml) AS fluids_ml
                       FROM qbot_nutrition_daily WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) n ON d.date = n.date""")
            else:
                joins.append(
                    """LEFT JOIN (SELECT date, SUM(kcal_total) AS kcal_in, SUM(protein_total) AS protein_g,
                       SUM(carbs_total) AS carbs_g, SUM(fat_total) AS fat_g, SUM(fluids_total) AS fluids_ml
                       FROM nutrition_daily_summary WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) n ON d.date = n.date""")
            select_extras.extend(["COALESCE(n.kcal_in,0) AS kcal_in","n.protein_g","n.carbs_g","n.fat_g","n.fluids_ml"])

        # Training
        if has_training:
            joins.append(
                """LEFT JOIN (SELECT date, COUNT(*) AS workouts, SUM(calories_kcal) AS kcal_burned_training,
                   SUM(distance_km) AS distance_km, SUM(duration_sec)/60.0 AS moving_min,
                   SUM(elapsed_duration_sec)/60.0 AS elapsed_min
                   FROM training_sessions WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) t ON d.date = t.date""")
            select_extras.extend(["COALESCE(t.workouts,0) AS workouts","t.kcal_burned_training","t.distance_km",
                                  "ROUND(COALESCE(t.moving_min,0)::numeric,0) AS moving_min",
                                  "ROUND(COALESCE(t.elapsed_min,0)::numeric,0) AS elapsed_min"])

        # Weight
        if has_weight:
            joins.append(
                "LEFT JOIN (SELECT DISTINCT ON (date) date, weight_kg FROM weight_history WHERE date BETWEEN %(df)s AND %(dt)s ORDER BY date, measured_at DESC) w ON d.date = w.date")
            select_extras.append("w.weight_kg")

        # Body comp
        if has_body:
            joins.append(
                "LEFT JOIN (SELECT DISTINCT ON (date) date, body_fat_pct, bmi FROM body_composition WHERE date BETWEEN %(df)s AND %(dt)s ORDER BY date, measured_at DESC) bc ON d.date = bc.date")
            select_extras.append("bc.body_fat_pct")

        # Missing flags
        mf_parts = []
        if has_training:
            mf_parts.append("CASE WHEN t.workouts IS NULL OR t.workouts=0 THEN 'no_training' END")
            mf_parts.append("CASE WHEN t.workouts > 0 AND t.kcal_burned_training IS NULL THEN 'missing_training_calories' END")
        if has_nutrition: mf_parts.append("CASE WHEN n.kcal_in IS NULL OR n.kcal_in=0 THEN 'no_nutrition' END")
        if has_weight: mf_parts.append("CASE WHEN w.weight_kg IS NULL THEN 'no_weight' END")
        if mf_parts:
            select_extras.append(f"ARRAY_REMOVE(ARRAY[{','.join(mf_parts)}], NULL) AS missing_flags")

        # Kcal balance
        if has_nutrition and has_training:
            select_extras.append("ROUND((COALESCE(n.kcal_in,0) - COALESCE(t.kcal_burned_training,0))::numeric,0) AS kcal_balance")

        sql = f"""SELECT {', '.join(select_extras)}
FROM generate_series(%(df)s::date, %(dt)s::date, '1 day'::interval) AS d(date)
{' '.join(joins)}
ORDER BY d.date"""

        plan_obj["queries"].append({
            "domain": "daily_table",
            "sql": sql,
            "params": {"df": df, "dt": dt},
        })

    # ── Comparison ──
    if itype == "comparison" and has_training and has_nutrition:
        ns_c = _count_nonzero("nutrition_daily_summary", "kcal_total", df, dt)
        qb_c = _count_nonzero("qbot_nutrition_daily", "calories_kcal", df, dt)
        nut_table = "qbot_nutrition_daily" if qb_c > ns_c * 2 else "nutrition_daily_summary"
        nut_col = "calories_kcal" if nut_table == "qbot_nutrition_daily" else "kcal_total"
        comp_sql = (
            "SELECT CASE WHEN t.workouts>0 THEN 'treningowe' ELSE 'nietreningowe' END AS grp, "
            f"ROUND(AVG(n.kcal_in)::numeric,0) AS avg_kcal_in, COUNT(*) AS days "
            "FROM (SELECT date, COUNT(*) AS workouts FROM training_sessions "
            "WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) t "
            f"FULL JOIN (SELECT date, SUM({nut_col}) AS kcal_in FROM {nut_table} "
            "WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) n ON t.date=n.date "
            "WHERE n.kcal_in IS NOT NULL AND n.kcal_in > 0 "
            "GROUP BY 1 ORDER BY 1"
        )
        plan_obj["queries"].append({
            "domain": "comparison",
            "sql": comp_sql,
            "params": {"df": df, "dt": dt},
        })

    # ── Missing data: training without nutrition ──
    if itype == "missing_data_check" and has_training and has_nutrition:
        plan_obj["queries"].append({
            "domain": "training_without_nutrition",
            "sql": """SELECT t.date, t.workouts, t.kcal_burned_training,
               COALESCE(n.kcal_in, 0) AS kcal_in,
               ARRAY_REMOVE(ARRAY[
                 CASE WHEN n.kcal_in IS NULL THEN 'no_nutrition' END,
                 CASE WHEN n.kcal_in = 0 THEN 'possible_empty_nutrition' END
               ], NULL) AS missing_flags
               FROM (SELECT date, COUNT(*) AS workouts, SUM(calories_kcal) AS kcal_burned_training
                     FROM training_sessions WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) t
               LEFT JOIN (SELECT date, SUM(kcal_total) AS kcal_in
                          FROM nutrition_daily_summary WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) n ON t.date=n.date
               WHERE t.workouts > 0 AND (n.kcal_in IS NULL OR n.kcal_in = 0)
               ORDER BY t.date""",
            "params": {"df": df, "dt": dt},
        })

    # ── Weight/body only ──
    if (has_weight or has_body) and not has_training and not has_nutrition:
        wj, bj = "", ""
        wsel, bsel = [], []
        if has_weight:
            wj = "LEFT JOIN (SELECT DISTINCT ON (date) date, weight_kg FROM weight_history WHERE date BETWEEN %(df)s AND %(dt)s ORDER BY date, measured_at DESC) w ON d.date = w.date"
            wsel = ["w.weight_kg"]
        if has_body:
            bj = "LEFT JOIN (SELECT DISTINCT ON (date) date, body_fat_pct, bmi FROM body_composition WHERE date BETWEEN %(df)s AND %(dt)s ORDER BY date, measured_at DESC) bc ON d.date = bc.date"
            bsel = ["bc.body_fat_pct","bc.bmi"]
        all_sel = ["d.date::date AS date"] + wsel + bsel
        plan_obj["queries"].append({
            "domain": "weight_body_table",
            "sql": f"""SELECT {', '.join(all_sel)}
FROM generate_series(%(df)s::date, %(dt)s::date, '1 day'::interval) AS d(date)
{wj} {bj} ORDER BY d.date""",
            "params": {"df": df, "dt": dt},
        })

    return plan_obj


def _count_nonzero(table: str, col: str, df: str, dt: str) -> int:
    try:
        with _conn() as c:
            r = c.execute(f"SELECT COUNT(*) c FROM {table} WHERE date BETWEEN %s AND %s AND {col} > 0", (df, dt)).fetchone()
            return r["c"] if r else 0
    except Exception:
        return 0


# ── Executor + Formatter ──

def execute_and_format(plan_obj: dict) -> dict[str, Any]:
    """Execute all queries in plan, format into answer + tables."""
    df, dt = plan_obj.get("date_from", "?"), plan_obj.get("date_to", "?")
    parts, tables = [], []

    for qdef in plan_obj.get("queries", []):
        # Inline rows from planner (e.g. RWGPS API)
        if "rows" in qdef:
            rows = qdef["rows"]
            domain = qdef.get("domain", "?")
        else:
            rows = execute_sql(qdef["sql"], qdef["params"])
            domain = qdef.get("domain", "?")
        if not rows: continue
        if isinstance(rows[0], dict) and "error" in rows[0]: continue

        if domain == "calendar_snapshot" and rows:
            snap = rows[0]
            sd = snap.get("snapshot_json")
            if isinstance(sd, str):
                try: sd = json.loads(sd)
                except: sd = {}
            comp = snap.get("completeness_score", 0) or 0
            sections = [k for k, v in (sd or {}).items() if v and not k.startswith("_")]
            parts.append(f"Dzień {df}: completeness={comp*100:.0f}%, sekcje={', '.join(sections[:8])}")
            tables.append({"domain": "snapshot", "columns": ["date","completeness","sections"],
                           "rows": [{"date": snap.get("date"), "completeness": comp, "sections": sections}]})
            continue

        if domain == "route_list" and rows:
            limit = 10
            for qdef2 in plan_obj.get("queries", []):
                if qdef2.get("domain") == "route_list":
                    limit = qdef2.get("limit", 10)
            rows = rows[:limit]
            previews = []
            for r in rows:
                rid = str(r.get("route_id", "?"))
                name = r.get("name") or rid
                dist = (r.get("distance_km") or 0)
                elev = (r.get("elevation_gain_m") or 0)
                previews.append(f"{name} (ID={rid}, {dist:.1f}km, +{elev:.0f}m)")
            parts.append(f"Trasy: {len(rows)} znalezionych — {'; '.join(previews)}.")
            tables.append({"domain": "route_list", "columns": ["route_id","name","distance_km","elevation_gain_m"], "rows": rows})
            continue

        if domain in ("daily_table",) and rows:
            days = len(rows)
            w = sum(1 for r in rows if (r.get("workouts",0) or 0) > 0)
            n = sum(1 for r in rows if (r.get("kcal_in",0) or 0) > 0)
            tk = sum(r.get("kcal_burned_training") or 0 for r in rows if r.get("kcal_burned_training") is not None)
            nk = sum(r.get("kcal_in",0) or 0 for r in rows)
            missing_cal = sum(1 for r in rows if (r.get("workouts",0) or 0) > 0 and r.get("kcal_burned_training") is None)
            cal_msg = f"kcal treningowe={tk:.0f}" if tk > 0 else (f"kcal treningowe=missing ({missing_cal} dni)" if missing_cal > 0 else "kcal treningowe=0")
            parts.append(f"Zakres {df}–{dt}: {days} dni, {w} z treningiem, {n} z żywieniem, {cal_msg}, kcal spożyte={nk:.0f}. Szczegóły w tabeli.")
            tables.append({"domain": "semantic_daily_table", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
            continue

        if domain == "comparison":
            for r in rows:
                parts.append(f"Dni {r.get('grp','?')}: {r.get('avg_kcal_in','?')} kcal/dzień ({r.get('days','?')} dni)")
            continue

        if domain == "training_without_nutrition" and rows:
            dates = ", ".join(str(r["date"])[:10] for r in rows[:5])
            tail = f" +{len(rows)-5} więcej" if len(rows) > 5 else ""
            parts.append(f"Od {df} do {dt}: {len(rows)} dni z treningiem bez wiarygodnego wpisu żywienia: {dates}{tail}.")
            tables.append({"domain": "training_without_nutrition", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
            continue

        if domain == "weight_body_table" and rows:
            wd = sum(1 for r in rows if r.get("weight_kg") is not None)
            bd = sum(1 for r in rows if r.get("body_fat_pct") is not None or r.get("bmi") is not None)
            parts.append(f"Zakres {df}–{dt}: {wd} pomiarów wagi, {bd} pomiarów body composition. Szczegóły w tabeli.")
            tables.append({"domain": "weight_body_table", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
            continue

    answer = " | ".join(parts) if parts else "Brak danych w QBot / plikach projektu."
    return {"answer": answer, "tables": tables, "data": {"plan": {"task_type": plan_obj.get("task_type"), "date_from": plan_obj.get("date_from"), "date_to": plan_obj.get("date_to"), "domains": plan_obj.get("domains", [])}}}


# ── Full pipeline ──

def semantic_query(question: str, context: str = "", mode: str = "read_only",
                   scope: str = "all") -> dict[str, Any]:
    from qbot_context_resolver import resolve as resolve_context
    canonical = resolve_context(question, context)
    plan_obj = plan(canonical)
    formatted = execute_and_format(plan_obj)

    provenance = []
    for qdef in plan_obj.get("queries", []):
        rows = execute_sql(qdef["sql"], qdef["params"])
        provenance.append({"domain": qdef["domain"], "rows": len(rows)})

    return {
        "tool": "qbot.query", "safety_class": "READ_ONLY", "mode": mode,
        "status": "ok" if plan_obj.get("queries") else "no_data",
        "query": question, "intents_detected": canonical["domains"],
        "answer": formatted["answer"], "tables": formatted["tables"],
        "data": formatted["data"],
        "provenance": provenance,
        "query_plan": plan_obj,
        "canonical": canonical,
        "date_resolution": {"date_from": canonical["resolved_time"]["date_from"],
                            "date_to": canonical["resolved_time"]["date_to"]},
        "confidence": "high" if not plan_obj.get("warnings") else "medium",
    }


def plan_only_display(question: str, context: str = "") -> str:
    from qbot_context_resolver import resolve as resolve_context
    canonical = resolve_context(question, context)
    plan_obj = plan(canonical)
    t = canonical["resolved_time"]
    lines = [
        f"Task: {canonical['task']['type']}",
        f"Output: {canonical['task']['output']}",
        f"Date:   {t['date_from']} → {t['date_to']} ({t.get('relative_expression', t.get('grain',''))})",
        f"Domains: {', '.join(canonical['domains']) or '(none)'}",
        f"Negations: {', '.join(canonical['negative_constraints']) or '(none)'}",
        f"Confidence: {t.get('confidence','')}",
        "", "Queries:",
    ]
    for qdef in plan_obj.get("queries", []):
        lines.append(f"  ✓ {qdef['domain']}")
    if plan_obj.get("rejected"):
        lines.append("\nRejected:"); lines.extend(f"  ✗ {r}" for r in plan_obj["rejected"])
    if plan_obj.get("warnings"):
        lines.append("\nWarnings:"); lines.extend(f"  ⚠ {w}" for w in plan_obj["warnings"])
    return "\n".join(lines)
