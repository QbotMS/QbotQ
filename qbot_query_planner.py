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
    "body_daily",
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
    "body_comp":    ("qbot_v2.body_daily",),
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

    # ── Domain flags ──
    has_nutrition = "nutrition" in domains
    has_training = "training" in domains
    has_weight = "weight" in domains
    has_body = "body_comp" in domains

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

    # ── Latest training session ──
    if "training" in domains and not has_nutrition and not has_weight:
        from datetime import date as dt_date
        plan_obj["queries"].append({
            "domain": "latest_training",
            "sql": """SELECT date, title, activity_type, distance_km, duration_sec,
               calories_kcal, avg_hr, max_hr, avg_power_w, max_power_w,
               training_load, training_effect, elevation_gain_m
               FROM (
                 SELECT *, ROW_NUMBER() OVER (
                   PARTITION BY COALESCE(external_id, date::text || '|' || title || '|' || activity_type || '|' || COALESCE(distance_km::text, '') || '|' || COALESCE(duration_sec::text, ''))
                   ORDER BY id DESC
                 ) AS rn
                 FROM training_sessions
               ) sub
               WHERE rn = 1
               ORDER BY date DESC LIMIT 3""",
            "params": {},
        })
        # Also check today's snapshot for context
        plan_obj["queries"].append({
            "domain": "today_snapshot",
            "sql": "SELECT * FROM calendar_daily_snapshots WHERE date=%(df)s",
            "params": {"df": dt_date.today().isoformat()},
        })
        return plan_obj

    # ── Food product catalog ──
    if "food_catalog" in domains:
        plan_obj["queries"].append({
            "domain": "food_catalog",
            "sql": "SELECT id, name, brand, default_unit, kcal_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g, fiber_per_100g, source, verified FROM food_items ORDER BY name",
            "params": {},
        })
        plan_obj["queries"].append({
            "domain": "unlinked_summary",
            "sql": "SELECT COUNT(*) AS total FROM meal_log_items WHERE food_item_id IS NULL",
            "params": {},
        })
        return plan_obj

    # ── Saved meals ──
    if "meal_templates" in domains:
        plan_obj["queries"].append({
            "domain": "saved_meals",
            "sql": "SELECT id, name, serving_label, kcal, protein_g, carbs_g, fat_g, fiber_g, sodium_mg, source, confidence, notes FROM meal_templates ORDER BY name",
            "params": {},
        })
        return plan_obj

    # ── Meal log inventory (not when data_quality audit is requested) ──
    if "meal_logs" in domains and "nutrition" in domains and "data_quality" not in domains:
        plan_obj["queries"].append({
            "domain": "meal_log_inventory",
            "sql": """SELECT ml.id, ml.eaten_at::date AS date, ml.note, ml.context,
               COUNT(mli.id) AS items_count,
               COUNT(mli.food_item_id) AS items_linked,
               SUM(COALESCE(mli.kcal,0)) AS total_kcal
               FROM meal_logs ml LEFT JOIN meal_log_items mli ON mli.meal_log_id=ml.id
               GROUP BY ml.id ORDER BY ml.eaten_at DESC LIMIT 50""",
            "params": {},
        })
        return plan_obj

    # ── Food link audit ──
    if "data_quality" in domains:
        plan_obj["queries"].append({
            "domain": "food_link_audit",
            "sql": """SELECT (SELECT COUNT(*) FROM meal_log_items) AS total_items,
               (SELECT COUNT(*) FROM meal_log_items WHERE food_item_id IS NOT NULL) AS items_linked,
               (SELECT COUNT(*) FROM meal_log_items WHERE food_item_id IS NULL) AS items_unlinked""",
            "params": {},
        })
        plan_obj["queries"].append({
            "domain": "unlinked_candidates",
            "sql": """SELECT LOWER(TRIM(mli.food_name)) AS name, COUNT(*) AS cnt,
               ROUND(AVG(mli.kcal)::numeric,0) AS avg_kcal,
               ROUND(AVG(mli.protein_g)::numeric,1) AS avg_protein,
               ROUND(AVG(mli.carbs_g)::numeric,1) AS avg_carbs,
               ROUND(AVG(mli.fat_g)::numeric,1) AS avg_fat,
               STRING_AGG(DISTINCT LEFT(COALESCE(ml.note,'?'),40), ', ') AS example_notes
               FROM meal_log_items mli
               LEFT JOIN meal_logs ml ON ml.id = mli.meal_log_id
               WHERE mli.food_item_id IS NULL
               GROUP BY 1 ORDER BY cnt DESC""",
            "params": {},
        })
        plan_obj["queries"].append({
            "domain": "source_distribution",
            "sql": """
               SELECT 'food_items' AS tbl, source, COUNT(*) AS cnt FROM food_items GROUP BY source
               UNION ALL
               SELECT 'meal_templates', source, COUNT(*) FROM meal_templates GROUP BY source
               UNION ALL
               SELECT 'nutrition_write_audit', COALESCE(source,'?'), COUNT(*) FROM nutrition_write_audit GROUP BY source
               ORDER BY tbl, cnt DESC""",
            "params": {},
        })
        return plan_obj

    # ── Daily table: only when nutrition or training involved ──
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
                       SUM(carbs_g) AS carbs_g, SUM(fat_g) AS fat_g, SUM(fluid_ml) AS fluids_ml, 'intervals_comment_import' AS nut_source
                       FROM qbot_nutrition_daily WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) n ON d.date = n.date""")
            else:
                joins.append(
                    """LEFT JOIN (SELECT date, SUM(kcal_total) AS kcal_in, SUM(protein_total) AS protein_g,
                       SUM(carbs_total) AS carbs_g, SUM(fat_total) AS fat_g, SUM(fluids_total) AS fluids_ml, MAX(source) AS nut_source
                       FROM nutrition_daily_summary WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) n ON d.date = n.date""")
            select_extras.extend(["COALESCE(n.kcal_in,0) AS kcal_in","n.protein_g","n.carbs_g","n.fat_g","n.fluids_ml",
                                  "COALESCE(n.nut_source,'qbot') AS source_in"])

        # Daily energy expenditure (kcal out of day)
        has_energy = _count_nonzero("daily_energy_expenditure", "total_kcal_out", df, dt) > 0
        if has_energy:
            joins.append(
                """LEFT JOIN (SELECT date, total_kcal_out, resting_kcal_out, active_kcal_out, kcal_burned_total, source AS energy_source
                   FROM daily_energy_expenditure WHERE date BETWEEN %(df)s AND %(dt)s) e ON d.date = e.date""")
            select_extras.extend(["e.total_kcal_out","e.resting_kcal_out","e.active_kcal_out",
                                  "ROUND((n.kcal_in - e.total_kcal_out)::numeric,0) AS kcal_balance",
                                  "e.energy_source AS source_out"])

        # Training sessions
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

        # Body comp (primary: qbot_v2.body_daily, fallback: public.body_composition)
        if has_body:
            joins.append(
                """LEFT JOIN (SELECT DISTINCT ON (date) date, body_fat_pct, bmi, muscle_mass_kg, bone_mass_kg, body_water_pct, source
                   FROM qbot_v2.body_daily WHERE date BETWEEN %(df)s AND %(dt)s
                   ORDER BY date, CASE source WHEN 'garmin_index_scale' THEN 1 WHEN 'garmin_mfp' THEN 2 ELSE 3 END, imported_at DESC) bd ON d.date = bd.date""")
            select_extras.extend(["bd.body_fat_pct", "bd.bmi", "bd.muscle_mass_kg", "bd.bone_mass_kg", "bd.body_water_pct"])

        # Missing flags
        mf_parts = []
        if has_training:
            mf_parts.append("CASE WHEN t.workouts IS NULL OR t.workouts=0 THEN 'no_training' END")
            mf_parts.append("CASE WHEN t.workouts > 0 AND t.kcal_burned_training IS NULL THEN 'missing_training_calories' END")
        if has_nutrition: mf_parts.append("CASE WHEN n.kcal_in IS NULL OR n.kcal_in=0 THEN 'no_nutrition' END")
        if has_energy: mf_parts.append("CASE WHEN e.total_kcal_out IS NULL THEN 'no_daily_expenditure' END")
        if has_weight: mf_parts.append("CASE WHEN w.weight_kg IS NULL THEN 'no_weight' END")
        if mf_parts:
            select_extras.append(f"ARRAY_REMOVE(ARRAY[{','.join(mf_parts)}], NULL) AS missing_flags")

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
            bj = "LEFT JOIN (SELECT DISTINCT ON (date) date, body_fat_pct, bmi, muscle_mass_kg, bone_mass_kg, body_water_pct, source FROM qbot_v2.body_daily WHERE date BETWEEN %(df)s AND %(dt)s ORDER BY date, CASE source WHEN 'garmin_index_scale' THEN 1 WHEN 'garmin_mfp' THEN 2 ELSE 3 END, imported_at DESC) bd ON d.date = bd.date"
            bsel = ["bd.body_fat_pct","bd.bmi","bd.muscle_mass_kg","bd.bone_mass_kg","bd.body_water_pct"]
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

        if domain in ("calendar_snapshot", "today_snapshot") and rows:
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

        if domain == "latest_training" and rows:
            latest = rows[0] if rows else None
            today_name = str(df)[:10]
            if latest:
                _cal = latest.get("calories_kcal")
                cal_str = f"{_cal:.0f}kcal" if _cal is not None else "kcal: brak danych"

            if latest and latest.get("date") != today_name:
                date_str = str(latest.get("date","?"))[:10]
                title = latest.get("title","?")
                dist = (latest.get("distance_km") or 0)
                elev = latest.get("elevation_gain_m") or 0
                dur = (latest.get("duration_sec") or 0) / 60
                load = latest.get("training_load") or 0
                eff = latest.get("training_effect") or 0
                hr = latest.get("avg_hr") or "?"
                parts.append(
                    f"Nie widzę jeszcze dzisiejszej aktywności w QBot DB. "
                    f"Ostatnia dostępna: {date_str} — {title} ({dist:.1f}km, {cal_str}, {dur:.0f}min, "
                    f"load={load:.0f}, effect={eff:.1f}, HR={hr}bpm). "
                    f"Dane z zaimportowanych treningów Garmin."
                )
            elif latest:
                title = latest.get("title","?")
                dist = (latest.get("distance_km") or 0)
                parts.append(f"Dzisiejsza aktywność: {title} ({dist:.1f}km, {cal_str})")
            else:
                parts.append("Brak danych treningowych w QBot DB.")
            tables.append({"domain": "latest_training", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
            continue

        if domain == "food_catalog" and rows:
            unlinked_rows = None
            for qd in plan_obj.get("queries", []):
                if qd.get("domain") == "unlinked_summary":
                    unlinked = execute_sql(qd["sql"], qd["params"])
                    unlinked_rows = unlinked[0]["total"] if unlinked else 0
            msg = f"Katalog produktów: {len(rows)} pozycji."
            if unlinked_rows and unlinked_rows > 0:
                msg += f" Dodatkowo {unlinked_rows} wpisów posiłków bez powiązania z katalogiem — użyj audytu/kandydatów."
            parts.append(msg)
            tables.append({"domain": "food_catalog", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
            continue

        if domain == "saved_meals" and rows:
            sources = set(r.get("source","?") for r in rows)
            raw_q = plan_obj.get("task_type","")  # not ideal, use canonical
            is_crono = any(w in str(plan_obj.get("domains",[])).lower() for w in ("cronometer","crono"))
            src_detail = f" (źródła: {', '.join(sorted(sources))})" if sources else ""
            parts.append(f"Zdefiniowane posiłki/templates: {len(rows)} pozycji{src_detail}.")
            if is_crono and "manual_cronometer_migration" in sources:
                parts.append(f"Wszystkie template pochodzą z migracji Cronometer (manual_cronometer_migration).")
            tables.append({"domain": "saved_meals", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
            continue

        if domain == "meal_log_inventory" and rows:
            linked = sum(1 for r in rows if r.get("items_linked",0) > 0)
            parts.append(f"Wpisy posiłków: {len(rows)} logów, {linked} z powiązaniem do katalogu produktów.")
            tables.append({"domain": "meal_log_inventory", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
            continue

        if domain == "food_link_audit" and rows:
            audit = rows[0]
            total = audit.get("total_items",0)
            linked = audit.get("items_linked",0)
            unlinked = audit.get("items_unlinked",0)
            parts.append(f"Audyt połączeń: {total} wpisów, {linked} połączonych z katalogiem, {unlinked} niepołączonych.")
            tables.append({"domain": "food_link_audit", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
            continue

        if domain == "unlinked_candidates" and rows:
            candidates = []
            for r in rows:
                name = r.get("name","?")
                cnt = r.get("cnt",0)
                kcal = r.get("avg_kcal")
                candidates.append(f"{name} (×{cnt}, ~{kcal}kcal)" if kcal else f"{name} (×{cnt})")
            parts.append(f"Kandydaci z logów ({len(rows)} grup): {'; '.join(candidates[:8])}{'...' if len(rows)>8 else ''}.")
            tables.append({"domain": "unlinked_candidates", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
            continue

        if domain == "source_distribution" and rows:
            srcs = "; ".join(f"{r['tbl']}: {r['source']} (x{r['cnt']})" for r in rows)
            parts.append(f"Źródła danych: {srcs}.")
            tables.append({"domain": "source_distribution", "columns": list(rows[0].keys()) if rows else [], "rows": rows})
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
            n = sum(1 for r in rows if (r.get("kcal_in",0) or 0) > 0)
            e = sum(1 for r in rows if r.get("total_kcal_out") is not None)
            complete = sum(1 for r in rows if (r.get("kcal_in",0) or 0) > 0 and r.get("total_kcal_out") is not None)
            nk = sum(r.get("kcal_in",0) or 0 for r in rows)
            ek = sum(r.get("total_kcal_out") or 0 for r in rows if r.get("total_kcal_out") is not None)
            bk = sum(r.get("kcal_balance") or 0 for r in rows if r.get("kcal_balance") is not None)
            avg_bal = bk / max(complete, 1)

            w = sum(1 for r in rows if (r.get("workouts",0) or 0) > 0)
            has_t = plan_obj.get("domains", []) and "training" in plan_obj.get("domains", [])

            train_part = f", {w} z treningiem" if has_t else ""
            parts.append(
                f"Zakres {df}–{dt}: {days} dni, {n} z żywieniem, {e} z wydatkiem, {complete} kompletne. "
                f"kcal_in={nk:.0f}, kcal_out={ek:.0f}, bilans={bk:.0f} kcal, średnio={avg_bal:.0f} kcal/dzień{train_part}. "
                f"Szczegóły w tabeli."
            )
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
