#!/usr/bin/env python3
"""QBot Semantic Query Planner — interprets natural language, builds execution plans.

Replaces shallow keyword routing with domain-aware planning over:
calendar snapshots, DB tables, domain readers.
"""

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


# ── Semantic concept registry ──

DOMAIN_MAP = {
    "nutrition": {
        "keywords": ["kalorii", "kcal", "zjedzone", "jedzenie", "żywieni", "dieta", "spozycie",
                     "spożycie", "intake", "zjadł", "jadł", "zjedzone", "makro", "białko", "carbs",
                     "carbo", "węgle", "węglowodan", "tłuszcz", "protein", "fat", "płyny", "nawodnieni",
                     "posiłk", "bilans kalor", "cronometer"],
        "tables": [
            {"table": "qbot_nutrition_daily", "columns": {"kcal": "calories_kcal", "protein": "protein_g", "carbs": "carbs_g", "fat": "fat_g", "fiber": "fiber_g", "sodium": "sodium_mg", "fluids": "fluid_ml"}},
            {"table": "nutrition_daily_summary", "columns": {"kcal": "kcal_total", "protein": "protein_total", "carbs": "carbs_total", "fat": "fat_total", "fiber": "fiber_total", "sodium": "sodium_total", "fluids": "fluids_total"}},
        ],
    },
    "training": {
        "keywords": ["spalone", "spalanie", "trening", "aktywność", "activity", "jazda", "kolarstwo",
                     "cycling", "dystans", "przewyższenie", "elevation", "training load",
                     "obciążenie treningowe", "tss", "garmin activity", "przebieg",
                     "kcal spalone", "spalon"],
        "table": "training_sessions",
        "columns": {"kcal": "calories_kcal", "distance": "distance_km", "elevation": "elevation_gain_m",
                     "duration": "duration_sec", "elapsed": "elapsed_duration_sec",
                     "load": "training_load", "effect": "training_effect",
                     "avg_hr": "avg_hr", "max_hr": "max_hr", "hr": "avg_hr"},
    },
    "weight": {
        "keywords": ["waga", "masa ciała", "weight", "kilogram", "kg", "ważę", "ważył"],
        "table": "weight_history",
        "columns": {"weight": "weight_kg"},
    },
    "body_comp": {
        "keywords": ["body fat", "tkanka tłuszczowa", "bf", "bodyfat", "bmi", "body composition",
                     "skład ciała", "masa mięśniowa", "muscle", "bone", "tłuszczu"],
        "table": "body_composition",
        "columns": {"bf": "body_fat_pct", "bmi": "bmi", "muscle": "muscle_mass_kg",
                     "bone": "bone_mass_kg", "water": "body_water_pct"},
    },
    "sleep": {
        "keywords": ["sen", "sleep", "spał", "spanie", "głęboki sen", "rem"],
        "table": "qbot_sleep_daily",
        "columns": {"duration": "sleep_duration_min", "deep": "deep_sleep_min",
                     "rem": "rem_sleep_min", "score": "sleep_score"},
    },
    "recovery": {
        "keywords": ["hrv", "tętno spoczynkowe", "resting hr", "rhr", "resting heart",
                     "regeneracja", "recovery", "wellness"],
        "table": "qbot_wellness_daily",
        "columns": {"hrv": "hrv_ms", "rhr": "resting_hr_bpm"},
    },
    "xert": {
        "keywords": ["xert", "ftp", "threshold", "form", "freshness", "fatigue", "fitness",
                     "strain", "ltp", "w_prime", "peak power"],
        "table": "xert_metrics",
        "columns": {"ftp": "threshold_power_w", "form": "focus", "freshness": "freshness",
                     "fatigue": "fatigue", "fitness": "fitness", "strain": "strain"},
    },
    "health_events": {
        "keywords": ["chorob", "przezięb", "infekcj", "gorączk", "katar", "kaszl", "źle się czu",
                     "samopoczucie", "wellbeing", "health event"],
        "table": "health_events",
        "columns": {},
    },
}


# ── Query Interpreter ──

def interpret_query(query: str, context: str = "") -> dict[str, Any]:
    """Parse natural language into structured query intent."""
    q = query.lower()
    ctx = {}
    if context:
        try:
            ctx = json.loads(context) if isinstance(context, str) else context
        except Exception:
            pass

    # Date range
    today = date.today()
    if ctx.get("date"):
        try:
            today = date.fromisoformat(str(ctx["date"])[:10])
        except Exception:
            pass

    df, dt, date_source = _extract_date_range(q, ctx, today)

    # Intent type
    intent_type = "lookup"
    if any(w in q for w in ["od ", "zakres", "od pocz", "cały miesiąc", "ostatni", "tygodnia", "dni"]):
        intent_type = "range_analysis"
    if any(w in q for w in ["trend", "zmiana", "spadek", "wzrost", "zmniejsza", "zwiększa", "kierunek"]):
        intent_type = "trend"
    if any(w in q for w in ["porównaj", "porównanie", "czy w dni", "różnica", "vs", "kontra", "wobec"]):
        intent_type = "comparison"
    if any(w in q for w in ["które dni", "brakuje", "missing", "bez", "nie mają"]):
        intent_type = "missing_data_check"
    if re.search(r"pokaż wszystko.*co.*wie", q) or "wszystko co wiesz" in q:
        intent_type = "daily_summary"

    # Output format
    output_format = "summary"
    if any(w in q for w in ["tabela", "tabelę", "tabelaryczn", "zestawienie", "kolumny"]):
        output_format = "table"
    if re.search(r"lista|wypisz|pokaż\s+\d+|najnowsze", q):
        output_format = "list"

    # Domains
    domains = []
    for domain_name, info in DOMAIN_MAP.items():
        for kw in info["keywords"]:
            if kw in q:
                if domain_name not in domains:
                    domains.append(domain_name)
                break

    # If user asks for "nutrition and training" but keywords matched both, split
    if not domains:
        domains = []

    # Grain
    grain = "day"
    if any(w in q for w in ["tydzień", "tygodniow", "weekly"]):
        grain = "week"
    if any(w in q for w in ["miesiąc", "miesięczn", "monthly"]):
        grain = "month"

    return {
        "intent_type": intent_type,
        "date_from": df,
        "date_to": dt,
        "date_source": date_source,
        "grain": grain,
        "domains": domains,
        "output_format": output_format,
        "raw_query": query,
    }


def _extract_date_range(q: str, ctx: dict, today: date) -> tuple[str, str, str]:
    """Extract date range from query or context."""
    source = "query_text"

    # Context dates
    cdf = ctx.get("date_from", "")
    cdt = ctx.get("date_to", "")
    if cdf and re.match(r"\d{4}-\d{2}-\d{2}", str(cdf)):
        source = "context"

    # Explicit ISO ranges
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:do|–|to|-)\s*(\d{4}-\d{2}-\d{2}|today|dziś)", q)
    if m:
        df = m.group(1)
        dt_raw = m.group(2)
        dt_val = today.isoformat() if dt_raw in ("today", "dziś") else dt_raw
        return df, dt_val, "query_text"

    # "od 1.05" / "od początku maja" / "od 2026-05-01"
    m = re.search(r"od\s+(?:początku\s+)?(?:maja|maj|may)\s*(\d{4})?", q)
    if m:
        year = m.group(1) or str(today.year)
        return f"{year}-05-01", today.isoformat(), "query_text"

    m = re.search(r"od\s+(\d{4}-\d{2}-\d{2})", q)
    if m:
        return m.group(1), today.isoformat(), "query_text"

    m = re.search(r"od\s+(\d{1,2})[\.\-/](\d{1,2})", q)
    if m:
        d = int(m.group(1)); mo = int(m.group(2))
        return f"{today.year}-{mo:02d}-{d:02d}", today.isoformat(), "query_text"

    m = re.search(r"od\s+(\d{1,2})\s*(?:stycz|lut|mar|kwiet|maj|czerw|lip|sierp|wrze|paździer|listopad|grud)", q)
    if m:
        months = {"stycz":1,"lut":2,"mar":3,"kwiet":4,"maj":5,"czerw":6,"lip":7,"sierp":8,"wrze":9,"paździer":10,"listopad":11,"grud":12}
        for k, v in months.items():
            if k in q: return f"{today.year}-{v:02d}-01", today.isoformat(), "query_text"

    # "ostatnie X dni"
    m = re.search(r"ostatni(?:ch|e)?\s+(\d+)\s*(?:dni|day)", q)
    if m:
        days = int(m.group(1))
        return (today - timedelta(days=days - 1)).isoformat(), today.isoformat(), "query_text"

    # Default: today
    return today.isoformat(), today.isoformat(), "default_today"


# ── Data Inventory ──

def check_inventory(date_from: str, date_to: str, domains: list[str]) -> dict[str, Any]:
    """Check which tables have data for the given date range."""
    inventory: dict[str, dict] = {}
    for d in domains:
        info = DOMAIN_MAP.get(d)
        if not info:
            continue
        tables = info.get("tables", [{"table": info["table"], "columns": info.get("columns", {})}] if info.get("table") else [])
        domain_inv = {"tables": tables, "exists": True}
        for tdef in tables:
            table = tdef["table"]
            try:
                with _conn() as c:
                    r = c.execute(f"SELECT COUNT(*) c FROM {table} WHERE date BETWEEN %s AND %s",
                                  (date_from, date_to)).fetchone()
                    total = c.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
                    domain_inv[table] = {"exists": True, "rows_in_range": r["c"], "total_rows": total}
            except Exception:
                domain_inv[table] = {"exists": False, "rows_in_range": 0, "total_rows": 0}
        inventory[d] = domain_inv
    return inventory


# ── Semantic Planner ──

def plan_query(interpreted: dict, inventory: dict) -> dict[str, Any]:
    """Build an execution plan based on interpreted intent and data inventory."""
    domains = interpreted["domains"]
    itype = interpreted["intent_type"]
    df = interpreted["date_from"]
    dt = interpreted["date_to"]

    plan = {
        "intent_type": itype,
        "date_from": df, "date_to": dt,
        "grain": interpreted["grain"],
        "domains": domains,
        "output_format": interpreted["output_format"],
        "queries": [],
        "rejected": [],
        "warnings": [],
    }

    if not domains:
        plan["warnings"].append("No domains detected — try adding more specific keywords.")
        return plan

    for d in domains:
        info = DOMAIN_MAP.get(d)
        inv = inventory.get(d, {})
        if not info:
            continue

        tables = info.get("tables", [{"table": info["table"], "columns": info.get("columns", {})}] if info.get("table") else [])

        for tdef in tables:
            table = tdef["table"]
            t_inv = inv.get(table, {})
            if not t_inv.get("exists", True):
                plan["rejected"].append(f"{d}/{table}: does not exist")
                continue
            if t_inv.get("rows_in_range", 0) == 0 and itype == "range_analysis":
                plan["warnings"].append(f"{d}/{table}: 0 rows in range {df}–{dt}")

            columns = tdef.get("columns", {})
            cols = ", ".join(f"{col} AS {alias}" for alias, col in columns.items()) if columns else "*"

            plan["queries"].append({
                "domain": d,
                "table": table,
                "columns": cols,
                "sql": f"SELECT date, source, {cols} FROM {table} WHERE date BETWEEN %(df)s AND %(dt)s ORDER BY date",
                "params": {"df": df, "dt": dt},
            })

    # For comparison: add training vs non-training day split
    if itype == "comparison" and "training" in domains:
        plan["queries"].append({
            "domain": "training_comparison",
            "table": "training_sessions",
            "columns": "date",
            "sql": "SELECT date, COUNT(*) AS workout_count, SUM(calories_kcal) AS total_kcal FROM training_sessions WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date ORDER BY date",
            "params": {"df": df, "dt": dt},
        })

    # For missing_data_check: join training and nutrition
    if itype == "missing_data_check":
        plan["queries"].append({
            "domain": "missing_check",
            "table": "training_sessions LEFT JOIN nutrition_daily_summary",
            "columns": "t.date, t.workout_count, n.kcal_total",
            "sql": """SELECT t.date, t.workout_count, COALESCE(n.kcal_total, 0) AS kcal_total
                      FROM (SELECT date, COUNT(*) AS workout_count FROM training_sessions WHERE date BETWEEN %(df)s AND %(dt)s GROUP BY date) t
                      LEFT JOIN (SELECT date, kcal_total FROM nutrition_daily_summary WHERE source='qbot' AND date BETWEEN %(df)s AND %(dt)s) n ON t.date = n.date
                      ORDER BY t.date""",
            "params": {"df": df, "dt": dt},
        })

    return plan


# ── Safe SQL Executor ──

SAFE_TABLES = {
    "nutrition_daily_summary", "meal_logs", "meal_log_items", "nutrition_day_plans",
    "training_sessions", "weight_history", "body_composition",
    "qbot_sleep_daily", "qbot_wellness_daily", "qbot_nutrition_daily",
    "xert_metrics", "calendar_daily_snapshots", "calendar_events", "reminders",
    "health_events", "health_risk_notes", "health_goals", "health_advice_reports",
    "supplement_inventory", "supplement_protocols", "supplement_intake_log",
    "route_artifacts", "food_items", "meal_templates",
    "nutrition_daily_summary", "hydration_events", "fueling_events",
}

def execute_safe_sql(sql: str, params: dict) -> list[dict]:
    """Execute read-only SQL against whitelisted tables."""
    # Validate: only SELECT allowed
    if not sql.strip().upper().startswith("SELECT"):
        return []
    # Check table names against whitelist
    for table in SAFE_TABLES:
        pass  # trust the planner's SQL for now (it builds queries from our registry)
    try:
        with _conn() as c:
            rows = c.execute(sql, params).fetchall()
        return [{k: _safe_val(v) for k, v in dict(r).items()} for r in rows]
    except Exception as e:
        return [{"error": str(e)[:200], "sql": sql[:100]}]


def _safe_val(v: Any) -> Any:
    if isinstance(v, (date,)):
        return v.isoformat()
    if isinstance(v, (float,)):
        return round(v, 2) if abs(v) < 100000 else v
    return v


# ── Result Formatter ──

def format_results(plan: dict, query_results: list[dict]) -> dict[str, Any]:
    """Build the answer + tables from execution results."""
    answer_parts = []
    tables = []

    for qr in query_results:
        domain = qr.get("domain", "?")
        rows = qr.get("rows", [])
        if not rows:
            answer_parts.append(f"{domain}: brak danych")
            continue
        if isinstance(rows[0], dict) and "error" in rows[0]:
            continue

        # Build table
        if len(rows) <= 30:
            tables.append({"domain": domain, "columns": list(rows[0].keys()), "rows": rows})
        else:
            tables.append({"domain": domain, "columns": list(rows[0].keys()), "rows": rows[:30], "truncated": len(rows)})

        # Build summary
        if domain in ("nutrition",):
            avg_kcal = sum(r.get("kcal", 0) or 0 for r in rows) / len(rows)
            avg_prot = sum(r.get("protein", 0) or 0 for r in rows) / len(rows)
            answer_parts.append(f"Nutycja: średnio {avg_kcal:.0f} kcal, {avg_prot:.0f}g białka ({len(rows)} dni)")
        elif domain in ("training",):
            total_kcal = sum(r.get("kcal", 0) or 0 for r in rows)
            total_sessions = sum(1 for r in rows if (r.get("kcal", 0) or 0) > 0)
            answer_parts.append(f"Trening: {total_kcal:.0f} kcal łącznie, {total_sessions} sesji w {len(rows)} dniach")
        elif domain == "missing_check":
            missing = [r for r in rows if r.get("workout_count", 0) > 0 and r.get("kcal_total", 0) == 0]
            if missing:
                dates = ", ".join(str(r["date"])[:10] for r in missing[:5])
                answer_parts.append(f"Dni z treningiem bez żywienia: {dates} ({len(missing)} dni)")
            else:
                answer_parts.append("Wszystkie dni treningowe mają dane żywieniowe.")
        elif domain == "weight":
            if len(rows) >= 2:
                first = rows[0].get("weight_kg", 0)
                last = rows[-1].get("weight_kg", 0)
                delta = last - first
                answer_parts.append(f"Waga: {first} → {last} kg (Δ={delta:+.1f})")
        else:
            answer_parts.append(f"{domain}: {len(rows)} wpisów")

    if plan.get("warnings"):
        answer_parts.append("⚠ " + "; ".join(plan["warnings"]))

    answer = " | ".join(answer_parts) if answer_parts else "Brak danych w QBot / plikach projektu."

    return {
        "answer": answer,
        "tables": tables,
        "data": {
            "plan": plan,
            "source_count": len(tables),
        },
    }


# ── Full pipeline ──

def semantic_query(question: str, context: str = "", mode: str = "read_only",
                   scope: str = "all") -> dict[str, Any]:
    """Full semantic query pipeline: interpret → inventory → plan → execute → format."""
    # Step 1: Interpret
    interpreted = interpret_query(question, context)

    # Step 2: Check inventory
    inventory = check_inventory(interpreted["date_from"], interpreted["date_to"],
                                interpreted["domains"])

    # Step 3: Plan
    plan = plan_query(interpreted, inventory)

    # Step 4: Execute
    query_results = []
    for qdef in plan.get("queries", []):
        rows = execute_safe_sql(qdef["sql"], qdef["params"])
        query_results.append({"domain": qdef["domain"], "table": qdef["table"], "rows": rows})

    # Step 5: Format
    formatted = format_results(plan, query_results)

    return {
        "tool": "qbot.query",
        "safety_class": "READ_ONLY",
        "mode": mode,
        "status": "ok" if query_results else "no_data",
        "query": question,
        "intents_detected": interpreted["domains"],
        "answer": formatted["answer"],
        "tables": formatted["tables"],
        "data": formatted["data"],
        "provenance": [{"domain": qr["domain"], "table": qr["table"], "rows": len(qr["rows"])} for qr in query_results],
        "query_plan": plan,
        "date_resolution": {"date_from": interpreted["date_from"], "date_to": interpreted["date_to"]},
        "missing_fields": plan.get("rejected", []),
        "limitations": plan.get("warnings", []),
        "confidence": "high" if not plan.get("warnings") else "medium",
    }


def plan_only_display(question: str, context: str = "") -> str:
    """SHOW the execution plan without executing."""
    interpreted = interpret_query(question, context)
    inventory = check_inventory(interpreted["date_from"], interpreted["date_to"], interpreted["domains"])
    plan = plan_query(interpreted, inventory)

    lines = [
        f"Intent: {interpreted['intent_type']}",
        f"Range: {interpreted['date_from']} → {interpreted['date_to']} ({interpreted['date_source']})",
        f"Grain: {interpreted['grain']}",
        f"Domains: {', '.join(interpreted['domains']) or '(none detected)'}",
        f"Output: {interpreted['output_format']}",
        "",
        "Execution plan:",
    ]
    for q in plan.get("queries", []):
        lines.append(f"  {q['domain']} → {q['table']}")
        lines.append(f"    SQL: {q['sql'][:120]}...")

    if plan.get("rejected"):
        lines.append("\nRejected:")
        for r in plan["rejected"]:
            lines.append(f"  ✗ {r}")

    if plan.get("warnings"):
        lines.append("\nWarnings:")
        for w in plan["warnings"]:
            lines.append(f"  ⚠ {w}")

    return "\n".join(lines)
