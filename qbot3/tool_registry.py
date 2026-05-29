#!/usr/bin/env python3
"""QBot3 Tool Registry — pure tool definitions, zero legacy imports.

Each tool is a dict: {callable, category, description, args_schema, safety}
Albert discovers tools through this registry, not through legacy routers.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_TOOL_REGISTRY: dict[str, dict[str, Any]] = {}
_READ_ONLY_TOOLS: dict[str, dict[str, Any]] = {}
_WRITE_TOOLS: dict[str, dict[str, Any]] = {}


def _safe_call(func: Any, args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = func(args)
        if isinstance(result, dict):
            return result
        return {"status": "OK", "data": result}
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)[:500]}


# ── helpers ────────────────────────────────────────────────────────────

def _today() -> str:
    return date.today().isoformat()


def _resolve_date(question: str, base: date | None = None) -> tuple[date, str]:
    base = base or date.today()
    ql = question.lower()
    if any(k in ql for k in ("jutro", "tomorrow", "jutrze")):
        return base + timedelta(days=1), "tomorrow"
    if any(k in ql for k in ("pojutrze", "pojutrz")):
        return base + timedelta(days=2), "day_after_tomorrow"
    if any(k in ql for k in ("wczoraj", "yesterday")):
        return base - timedelta(days=1), "yesterday"
    m = re.search(r'(\d{4}-\d{2}-\d{2})', question)
    if m:
        try:
            return date.fromisoformat(m.group(1)), "explicit"
        except ValueError:
            pass
    return base, "today"


def _idempotency_key(prefix: str, question: str) -> str:
    import uuid
    key = uuid.uuid5(uuid.NAMESPACE_DNS, f"{prefix}:{question.strip().lower()}")
    return f"{prefix}_{str(key)[:16]}"


# ── tool loaders ───────────────────────────────────────────────────────

def _load_status_tool() -> dict[str, Any]:
    from qbot_tools import _tool_qbot_status
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_status,
        "category": "system",
        "description": "QBot process status — hostname, pid, python version",
        "args_schema": {},
        "safety": "read",
    }


def _load_readiness_tool() -> dict[str, Any]:
    from qbot_operator_tools import _tool_qbot_readiness_report
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_readiness_report,
        "category": "system",
        "description": "QBot readiness assessment: resources, blockers, overall status",
        "args_schema": {},
        "safety": "read",
    }


def _load_calendar_snapshot_tool() -> dict[str, Any]:
    from qbot_calendar_core import build_snapshot
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        date_str = args.get("date", _today())
        q = args.get("_question", "")
        if not args.get("date"):
            d, _ = _resolve_date(q)
            date_str = d.isoformat()
        snap = build_snapshot(date_str)
        return snap
    return {
        "callable": _wrapper,
        "category": "calendar",
        "description": "Dashboard dnia: calendar events, reminders, meals, wellness, health data. Use only for explicit day-summary / dashboard / snapshot / status-day requests.",
        "args_schema": {"date": {"type": "string", "description": "ISO date (optional, default: today or resolved from question)"}},
        "safety": "read",
    }


def _load_planning_facts_tool() -> dict[str, Any]:
    from qbot_planning_memory import list_planning_facts
    return {
        "callable": lambda args: {
            "status": "OK",
            "facts": list_planning_facts(
                fact_date=args.get("date"),
                status=args.get("status"),
            ),
            "count": len(list_planning_facts(fact_date=args.get("date"), status=args.get("status"))),
        },
        "category": "planning",
        "description": "List planning facts (notes, decisions) optionally filtered by date or status",
        "args_schema": {"date": {"type": "string"}, "status": {"type": "string"}},
        "safety": "read",
    }


def _load_weather_forecast_tool() -> dict[str, Any]:
    from qbot_integration_tools import _tool_qbot_weather_forecast
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        q = args.get("_question", "")
        period = args.get("period", "")
        if not period:
            d, resolved = _resolve_date(q)
            period = "jutro" if resolved == "tomorrow" else "today"
        return _tool_qbot_weather_forecast({
            "location": args.get("location", "Marki"),
            "period": period,
            "hours": args.get("hours", 48),
        })
    return {
        "callable": _wrapper,
        "category": "weather",
        "description": "Weather forecast — location (city name), period (today/jutro), hours (1-48)",
        "args_schema": {"location": {"type": "string"}, "period": {"type": "string"}, "hours": {"type": "integer"}},
        "safety": "read",
    }


def _load_nutrition_templates_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_template_list
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_template_list,
        "category": "nutrition",
        "description": "List all saved meal templates with nutritional values (kcal, protein, carbs, fat)",
        "args_schema": {"limit": {"type": "integer"}},
        "safety": "read",
    }


def _load_nutrition_template_get_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_template_get
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_template_get,
        "category": "nutrition",
        "description": "Get one saved meal template by name or id",
        "args_schema": {"name": {"type": "string"}},
        "safety": "read",
    }


def _load_nutrition_day_summary_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_day_summary
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_day_summary,
        "category": "nutrition",
        "description": "Daily nutrition summary — total kcal, macros, meals for a given date",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
    }


def _load_nutrition_meal_list_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_meal_list
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_meal_list,
        "category": "nutrition",
        "description": "List meals logged for a date",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
    }


def _load_wellness_day_tool() -> dict[str, Any]:
    from qbot_wellness_store import _tool_qbot_wellness_day_get
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_wellness_day_get,
        "category": "wellness",
        "description": "Wellness data for a date (HRV, resting HR, sleep duration)",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
    }


def _load_sleep_day_tool() -> dict[str, Any]:
    from qbot_wellness_store import _tool_qbot_sleep_day_get
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_sleep_day_get,
        "category": "wellness",
        "description": "Sleep data for a date (duration, score, start/end time, source)",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
    }


def _load_xert_readiness_tool() -> dict[str, Any]:
    from qbot_integration_tools import _tool_qbot_xert_readiness_status
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_xert_readiness_status,
        "category": "fitness",
        "description": "Xert training readiness: FTP, form, W', fatigue, freshness",
        "args_schema": {},
        "safety": "read",
    }


def _load_rwgps_list_tool() -> dict[str, Any]:
    from qbot_route_tools import _tool_qbot_rwgps_route_list
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_rwgps_route_list,
        "category": "routes",
        "description": "List RWGPS routes with metadata (count, names, ids)",
        "args_schema": {},
        "safety": "read",
    }


def _load_garage_status_tool() -> dict[str, Any]:
    from qbot_garage_tools import _tool_qbot_garage_raw_status
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_garage_raw_status,
        "category": "garage",
        "description": "Garage DB status — tables, counters, seed status",
        "args_schema": {},
        "safety": "read",
    }


def _load_canonical_docs_tool() -> dict[str, Any]:
    _DOCS_DIR = Path("/opt/qbot/docs")
    _DOCS = {
        "QBOT_BIBLE": _DOCS_DIR / "QBOT_BIBLE.md",
        "QBOT_KNOWHOW": _DOCS_DIR / "QBOT_KNOWHOW.md",
        "QBOT_PROJECT_INSTRUCTION": _DOCS_DIR / "QBOT_PROJECT_INSTRUCTION_LOCAL.md",
    }

    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        q = args.get("query", args.get("_question", "")).lower()
        results = []
        for label, path in _DOCS.items():
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            lines = text.splitlines()
            headings = [l.strip().lstrip("#").strip() for l in lines if l.strip().startswith("#")][:8]
            summary = "; ".join(headings[:4]) if headings else ""
            excerpts = []
            if q:
                terms = [w for w in re.findall(r'\w+', q) if len(w) >= 4]
                for term in terms:
                    for line in lines:
                        if term in line.lower():
                            excerpts.append(line.strip()[:240])
                            if len(excerpts) >= 5:
                                break
            results.append({
                "label": label,
                "path": str(path),
                "exists": True,
                "headings": headings,
                "summary": summary,
                "matched_excerpts": excerpts[:5],
            })
        return {
            "status": "OK",
            "documents": results,
            "count": len(results),
            "answer": "\n".join(
                f"- {r['label']}: {r['summary']}"
                + (("\n  excerpt: " + r['matched_excerpts'][0][:200]) if r['matched_excerpts'] else "")
                for r in results
            ) if results else "Brak dokumentów kanonicznych.",
        }

    return {
        "callable": _wrapper,
        "category": "docs",
        "description": "Read canonical QBot documents (QBOT_BIBLE, QBOT_KNOWHOW) with excerpt matching",
        "args_schema": {"query": {"type": "string", "description": "Search terms for excerpt matching"}},
        "safety": "read",
    }


# ── Garmin diagnostics ─────────────────────────────────────────────────

def _load_garmin_diagnostics_tool() -> dict[str, Any]:
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
        q = args.get("_question", "")
        try:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='qbot_wellness_daily')")
            table_exists = cur.fetchone()["exists"]
            if not table_exists:
                c.close()
                return error_result(CONNECTOR_MISSING, "Tabela qbot_wellness_daily nie istnieje w DB.")
            today = date.today().isoformat()
            cur.execute("SELECT source, hrv_ms, resting_hr_bpm, sleep_duration_min FROM qbot_wellness_daily WHERE date=%s ORDER BY source_priority LIMIT 5", (today,))
            today_rows = cur.fetchall()
            cur.execute("SELECT MAX(date) as last_date FROM qbot_wellness_daily")
            last_row = cur.fetchone()
            last_date = last_row["last_date"] if last_row else None
            cur.execute("SELECT COUNT(*) as cnt FROM qbot_wellness_daily WHERE date >= %s", ((date.today() - timedelta(days=30)).isoformat(),))
            count_30d = cur.fetchone()["cnt"]
            c.close()
            details = {
                "table_exists": True,
                "today_data_count": len(today_rows),
                "last_import_date": str(last_date) if last_date else None,
                "records_last_30d": count_30d,
            }
            if today_rows:
                details["sources"]: list[str] = list(set(r["source"] for r in today_rows if r.get("source")))
            return success_result(details)
        except ImportError:
            return error_result(CONNECTOR_MISSING, "psycopg not available")
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"DB check failed: {str(exc)[:200]}")
    return {
        "callable": _wrapper,
        "category": "garmin",
        "description": "Garmin diagnostics: check DB tables, last import date, today's data presence, 30-day record count",
        "args_schema": {},
        "safety": "read",
    }


def _load_nutrition_range_summary_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, error_result, success_result
    from qbot_nutrition_tools import _tool_qbot_nutrition_day_summary
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        date_from = args.get("date_from", date.today().isoformat())
        date_to = args.get("date_to", date_from)
        days = []
        try:
            d = date.fromisoformat(date_from)
            end = date.fromisoformat(date_to)
            while d <= end:
                day_result = _tool_qbot_nutrition_day_summary({"date": d.isoformat()})
                if isinstance(day_result, dict) and day_result.get("total_kcal"):
                    days.append({"date": d.isoformat(), "summary": day_result})
                d += timedelta(days=1)
        except Exception as exc:
            return {"status": "ERROR", "error": f"Range iteration error: {str(exc)[:200]}"}
        if not days:
            return error_result(DATA_MISSING, f"Brak danych żywieniowych dla zakresu {date_from}–{date_to}")
        total_kcal = sum(d["summary"].get("total_kcal", 0) for d in days)
        total_protein = sum(d["summary"].get("total_protein_g", 0) for d in days)
        total_carbs = sum(d["summary"].get("total_carbs_g", 0) for d in days)
        total_fat = sum(d["summary"].get("total_fat_g", 0) for d in days)
        return success_result({
            "date_from": date_from, "date_to": date_to,
            "days_with_data": len(days), "total_kcal": total_kcal,
            "total_protein_g": round(total_protein, 1),
            "total_carbs_g": round(total_carbs, 1),
            "total_fat_g": round(total_fat, 1),
        })
    return {
        "callable": _wrapper,
        "category": "nutrition",
        "description": "Nutrition summary for a date range — total kcal, macros, meal count. Parameters: date_from (ISO), date_to (ISO)",
        "args_schema": {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
        "safety": "read",
    }


def _load_qcal_events_range_tool() -> dict[str, Any]:
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, SCHEMA_MISMATCH, error_result, success_result
        import psycopg
        from psycopg.rows import dict_row
        try:
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            date_from = args.get("date_from", date.today().isoformat())
            date_to = args.get("date_to", date_from)
            # Discover actual columns to avoid schema mismatch
            try:
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='calendar_events' AND table_schema='public'")
                actual_cols = {r["column_name"] for r in cur.fetchall()}
            except Exception:
                actual_cols = set()
            safe_cols = ["id", "date_start", "date_end", "time_start", "title", "event_type", "status"]
            available = [c for c in safe_cols + ["all_day"] if c in actual_cols] or safe_cols
            cols_sql = ", ".join(available)
            cur.execute(
                f"SELECT {cols_sql} FROM calendar_events WHERE date_start >= %s AND date_start <= %s ORDER BY date_start",
                (date_from, date_to),
            )
            rows = cur.fetchall()
            c.close()
            if not rows:
                return error_result(DATA_MISSING, f"Brak wydarzeń w okresie {date_from}–{date_to}")
            return success_result({"events": rows, "count": len(rows), "date_from": date_from, "date_to": date_to, "columns_used": available})
        except psycopg.errors.UndefinedColumn as exc:
            return error_result(SCHEMA_MISMATCH, f"Reader query references non-existent column: {exc}. Use db_table_describe to discover actual columns.")
        except Exception as exc:
            return error_result(READER_ERROR, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "calendar",
        "description": "Raw QCal event rows for a date range. Prefer db_schema_list / db_table_describe / db_select_readonly for ordinary calendar questions. Parameters: date_from (ISO), date_to (ISO)",
        "args_schema": {"date_from": {"type": "string"}, "date_to": {"type": "string"}},
        "safety": "read",
    }


def _load_qcal_reminders_upcoming_tool() -> dict[str, Any]:
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
        try:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            today = date.today().isoformat()
            cur.execute(
                "SELECT id, date, time, title, message, status, reminder_type FROM reminders WHERE date >= %s AND status='pending' ORDER BY date, time LIMIT 20",
                (today,),
            )
            rows = cur.fetchall()
            c.close()
            if not rows:
                return error_result(DATA_MISSING, "Brak nadchodzących przypomnień.")
            return success_result({"reminders": rows, "count": len(rows)})
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "calendar",
        "description": "Upcoming pending reminders. No parameters required.",
        "args_schema": {},
        "safety": "read",
    }


def _load_rwgps_route_fetch_tool() -> dict[str, Any]:
    from qbot_route_tools import _tool_qbot_rwgps_route_get
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_rwgps_route_get,
        "category": "routes",
        "description": "Fetch a specific RWGPS route by ID. Parameter: route_id (string or number)",
        "args_schema": {"route_id": {"type": "string"}},
        "safety": "read",
    }


def _load_system_env_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, AUTH_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        checks = {
            "openai_key": bool(os.getenv("OPENAI_API_KEY") or os.getenv("QGPT_API_KEY")),
            "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")),
            "deepseek_key": bool(os.getenv("DEEPSEEK_API_KEY")),
            "telegram_token": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "xert_email": bool(os.getenv("XERT_EMAIL")),
            "garmin_email": bool(os.getenv("GARMIN_EMAIL")),
            "rwgps_token": bool(os.getenv("RWGPS_AUTH_TOKEN")),
            "intervals_key": bool(os.getenv("INTERVALS_API_KEY")),
            "postgres_host": os.getenv("PGHOST", "not set"),
            "db_connected": False,
            "albert_provider": os.getenv("ALBERT_LLM_PROVIDER", "openai"),
        }
        try:
            import psycopg
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), connect_timeout=3,
            )
            c.close()
            checks["db_connected"] = True
        except Exception:
            pass
        return success_result(checks)
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "System environment status: check which API keys and connectors are configured, DB connectivity",
        "args_schema": {},
        "safety": "read",
    }


# ── Daily report status (internal capability wrapper) ──────────────────

def _load_daily_report_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, TOOL_ERROR, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from qbot3.capabilities import find_capability
            cap = find_capability("daily_report_status")
            if not cap:
                return error_result(CONNECTOR_MISSING, "daily_report_status capability not loaded")
            result = cap.run({"question": args.get("_question", "")})
            if isinstance(result, dict):
                data = result.get("data", result)
                summary = data.get("summary", str(data)[:300]) if isinstance(data, dict) else str(data)
                return success_result(data, summary=summary)
            return error_result(TOOL_ERROR, "capability returned non-dict")
        except ImportError as exc:
            return error_result(CONNECTOR_MISSING, f"capabilities module: {exc}")
        except Exception as exc:
            return error_result(TOOL_ERROR, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Daily report pipeline status: pipeline stage, channel delivery (telegram/email), data source errors, legacy tool errors, sleep data wait status. Używaj gdy pytanie dotyczy raportu dziennego, emaila, Telegram pipeline.",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Internal capability — nie jest publicznym MCP tool. Wrapper dla qbot3.capabilities.system.daily_report_status.",
    }


# ── Gate status (internal capability wrapper) ─────────────────────────

def _load_gate_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, CONNECTOR_MISSING, TOOL_ERROR, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from qbot3.capabilities import find_capability
            cap = find_capability("gate_status")
            if not cap:
                return error_result(CONNECTOR_MISSING, "gate_status capability not loaded")
            result = cap.run({"question": args.get("_question", "")})
            if isinstance(result, dict):
                data = result.get("data", result)
                summary = data.get("summary", str(data)[:300]) if isinstance(data, dict) else str(data)
                return success_result(data, summary=summary)
            return error_result(TOOL_ERROR, "capability returned non-dict")
        except ImportError as exc:
            return error_result(CONNECTOR_MISSING, f"capabilities module: {exc}")
        except Exception as exc:
            return error_result(TOOL_ERROR, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Gate (HikConnect) configuration and last-success status. Tylko odczyt — nie otwiera furtki.",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Internal capability — nie jest publicznym MCP tool. Wrapper dla qbot3.capabilities.system.gate_status.",
    }


# ── Hammerhead sync status (internal capability wrapper) ──────────────

def _load_hammerhead_sync_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, CONNECTOR_MISSING, TOOL_ERROR, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from qbot3.capabilities import find_capability
            cap = find_capability("hammerhead_sync_status")
            if not cap:
                return error_result(CONNECTOR_MISSING, "hammerhead_sync_status capability not loaded")
            result = cap.run({"question": args.get("_question", "")})
            if isinstance(result, dict):
                data = result.get("data", result)
                summary = data.get("summary", str(data)[:300]) if isinstance(data, dict) else str(data)
                return success_result(data, summary=summary)
            return error_result(TOOL_ERROR, "capability returned non-dict")
        except ImportError as exc:
            return error_result(CONNECTOR_MISSING, f"capabilities module: {exc}")
        except Exception as exc:
            return error_result(TOOL_ERROR, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Hammerhead→Garmin sync pipeline status: config, dedup state, last log, outgoing files. Tylko odczyt — nie wykonuje transferu.",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Internal capability — nie jest publicznym MCP tool. Wrapper dla qbot3.capabilities.system.hammerhead_sync_status.",
    }


# ── LLM status (internal capability wrapper) ──────────────────────────

def _load_llm_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, CONNECTOR_MISSING, TOOL_ERROR, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            from qbot3.capabilities import find_capability
            cap = find_capability("llm_status")
            if not cap:
                return error_result(CONNECTOR_MISSING, "llm_status capability not loaded")
            result = cap.run({"question": args.get("_question", "")})
            if isinstance(result, dict):
                data = result.get("data", result)
                summary = result.get("summary", "") or (data.get("summary", "") if isinstance(data, dict) else "")
                if not summary:
                    inner = data if isinstance(data, dict) else result
                    parts = []
                    parts.append(f"Provider: {inner.get('provider','?')}")
                    parts.append(f"Model: {inner.get('model','?')}")
                    parts.append(f"Fallback: {inner.get('fallback_model','?')}")
                    keys_str = ", ".join(f"{k}={'Y' if v else 'N'}" for k, v in inner.get("providers_configured", {}).items())
                    parts.append(f"Keys: {keys_str}")
                    summary = " | ".join(parts)
                return success_result(data, summary=summary)
            return error_result(TOOL_ERROR, "capability returned non-dict")
        except ImportError as exc:
            return error_result(CONNECTOR_MISSING, f"capabilities module: {exc}")
        except Exception as exc:
            return error_result(TOOL_ERROR, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Status używanego modelu LLM i providera. Zwraca provider, model, fallback_model, providers_configured. Tylko odczyt — bez sekretów.",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Internal capability — nie jest publicznym MCP tool. Wrapper dla qbot3.capabilities.system.llm_status.",
    }


# ── MCP tools list ─────────────────────────────────────────────────────

def _load_mcp_tools_list_tool() -> dict[str, Any]:
    from qbot3.errors import OK, success_result
    return {
        "callable": lambda args: success_result({
            "mcp_tools": [
                {"name": "qbot.query", "description": "Main QBot3 interface — read, plan, draft"},
                {"name": "qbot.action_execute", "description": "Execute write actions after safety validation"},
            ]
        }),
        "category": "system",
        "description": "List all available MCP public tools with descriptions",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Returns the 2 public MCP tools: qbot.query and qbot.action_execute",
    }


def _load_system_logs_recent_tool() -> dict[str, Any]:
    from qbot3.errors import CONNECTOR_MISSING, error_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        log_path = "/opt/qbot/logs/q-bot.log"
        try:
            if not os.path.isfile(log_path):
                return error_result(CONNECTOR_MISSING, f"Log file not found: {log_path}")
            lines = 20
            with open(log_path, "r") as f:
                tail = list(f)[-lines:]
            return {"status": "OK", "logs": tail, "source": log_path, "lines": len(tail)}
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"Cannot read logs: {str(exc)[:200]}")
    return {
        "callable": _wrapper,
        "category": "system",
        "description": "Recent system logs tail (last 20 lines from q-bot.log)",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Reads /opt/qbot/logs/q-bot.log — may not exist if log rotation changed path",
    }


def _load_docs_list_qbot_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DOC_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        docs_dir = Path("/opt/qbot/docs")
        if not docs_dir.is_dir():
            return error_result(DOC_MISSING, "Docs directory /opt/qbot/docs not found")
        files = sorted(f.name for f in docs_dir.iterdir() if f.suffix in (".md", ".txt"))
        if not files:
            return error_result(DOC_MISSING, "No documentation files found")
        return success_result({"docs": files, "count": len(files), "path": str(docs_dir)})
    return {
        "callable": _wrapper,
        "category": "docs",
        "description": "List all QBot documentation files",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Lists .md/.txt files from /opt/qbot/docs",
    }


def _load_nutrition_balance_today_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        today = date.today().isoformat()
        result = {"date": today, "kcal_in": None, "kcal_out": None, "balance": None, "sources": {}}
        try:
            from qbot_nutrition_tools import _tool_qbot_nutrition_day_summary
            nutr = _tool_qbot_nutrition_day_summary({"date": today})
            if isinstance(nutr, dict) and nutr.get("total_kcal"):
                result["kcal_in"] = nutr["total_kcal"]
                result["sources"]["nutrition"] = nutr
        except Exception:
            pass
        try:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            cur.execute("SELECT kcal_burned FROM qbot_wellness_daily WHERE date=%s AND source='garmin' LIMIT 1", (today,))
            row = cur.fetchone()
            if row and row.get("kcal_burned"):
                result["kcal_out"] = row["kcal_burned"]
                result["sources"]["garmin"] = {"kcal_burned": row["kcal_burned"]}
            c.close()
        except Exception:
            pass
        if result["kcal_in"] is not None or result["kcal_out"] is not None:
            if result["kcal_in"] is not None and result["kcal_out"] is not None:
                result["balance"] = round(result["kcal_in"] - result["kcal_out"], 1)
            return success_result(result)
        return error_result(DATA_MISSING, f"Brak danych bilansowych dla {today}. Nutrition: {result['kcal_in']}, Garmin: {result['kcal_out']}")
    return {
        "callable": _wrapper,
        "category": "nutrition",
        "description": "Daily nutrition balance: kcal in vs kcal out (Garmin). Parameters: date (ISO, default today)",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Combines nutrition intake with Garmin energy data",
    }


def _load_garmin_energy_today_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            today = date.today().isoformat()
            cur.execute(
                "SELECT date, source, kcal_burned, hrv_ms, resting_hr_bpm, sleep_duration_min "
                "FROM qbot_wellness_daily WHERE date=%s ORDER BY source_priority LIMIT 5", (today,)
            )
            rows = cur.fetchall()
            c.close()
            if not rows:
                return error_result(DATA_MISSING, f"Brak danych Garmin energy dla {today}")
            return success_result({"date": today, "records": rows, "count": len(rows)})
        except ImportError:
            return error_result(CONNECTOR_MISSING, "psycopg not available")
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"DB error: {str(exc)[:200]}")
    return {
        "callable": _wrapper,
        "category": "garmin",
        "description": "Garmin energy data for today: kcal_burned, HRV, resting HR, sleep",
        "args_schema": {"date": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Queries qbot_wellness_daily for Garmin data",
    }


def _load_garmin_sync_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            # Use imported_at (real column name) instead of updated_at (doesn't exist)
            cur.execute("SELECT MAX(date) as last_date, MAX(imported_at) as last_sync FROM qbot_wellness_daily")
            row = cur.fetchone()
            cur.execute("SELECT COUNT(*) as cnt FROM qbot_wellness_daily WHERE date >= %s", ((date.today() - timedelta(days=7)).isoformat(),))
            count_7d = cur.fetchone()["cnt"]
            # Check import_runs for additional sync metadata
            last_import = None
            try:
                cur.execute("SELECT status, created_at FROM qbot_import_runs WHERE import_type='garmin' ORDER BY created_at DESC LIMIT 1")
                ir = cur.fetchone()
                if ir:
                    last_import = {"status": ir["status"], "created_at": str(ir["created_at"]) if ir["created_at"] else None}
            except Exception:
                pass
            c.close()
            if not row or not row.get("last_date"):
                return error_result(DATA_MISSING, "Brak danych Garmin w DB")
            return success_result({
                "last_data_date": str(row["last_date"]),
                "last_sync": str(row.get("last_sync", "")),
                "records_last_7d": count_7d,
                "has_recent_data": count_7d > 0,
                "last_import_run": last_import,
            })
        except ImportError:
            return error_result(CONNECTOR_MISSING, "psycopg not available")
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, f"DB error: {str(exc)[:200]}")
    return {
        "callable": _wrapper,
        "category": "garmin",
        "description": "Garmin sync status: last data date, last sync time, records in last 7 days",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Queries qbot_wellness_daily metadata",
    }


def _load_qcal_events_upcoming_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, SCHEMA_MISMATCH, error_result, success_result
    import psycopg
    from psycopg.rows import dict_row
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            c = psycopg.connect(
                host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
                dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
                password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5,
            )
            cur = c.cursor()
            today = date.today().isoformat()
            limit = int(args.get("limit", 30))
            # Discover actual columns to avoid schema mismatch
            try:
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='calendar_events' AND table_schema='public'")
                actual_cols = {r["column_name"] for r in cur.fetchall()}
            except Exception:
                actual_cols = set()
            safe_cols = ["id", "date_start", "date_end", "time_start", "title", "event_type", "status", "all_day"]
            available = [c for c in safe_cols if c in actual_cols] or [c for c in safe_cols if c not in ("all_day",)]
            cols_sql = ", ".join(available)
            cur.execute(
                f"SELECT {cols_sql} FROM calendar_events "
                f"WHERE date_start >= %s AND status NOT IN ('cancelled', 'deleted') "
                f"ORDER BY date_start LIMIT %s",
                (today, limit),
            )
            rows = cur.fetchall()
            c.close()
            if not rows:
                return error_result(DATA_MISSING, "Brak nadchodzących wydarzeń")
            return success_result({"events": rows, "count": len(rows), "columns_used": available})
        except psycopg.errors.UndefinedColumn as exc:
            return error_result(SCHEMA_MISMATCH, f"Reader query references non-existent column: {exc}. Use db_table_describe to discover actual columns.")
        except Exception as exc:
            return error_result(CONNECTOR_MISSING, str(exc)[:200])
    return {
        "callable": _wrapper,
        "category": "calendar",
        "description": (
            "Upcoming calendar events from today forward. "
            "Returns events with status 'planned', 'active', 'confirmed' (excludes 'cancelled'/'deleted'). "
            "Parameters: limit (default 30, max 100). "
            "Use qcal_events_range for a specific date range."
        ),
        "args_schema": {
            "limit": {"type": "integer", "default": 30, "description": "Max events to return (default 30)"},
        },
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Queries calendar_events table for non-cancelled future events",
    }


def _load_rwgps_route_last_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, error_result, success_result
    try:
        from qbot_route_tools import _tool_qbot_rwgps_route_list
        def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
            result = _tool_qbot_rwgps_route_list({})
            if isinstance(result, dict):
                routes = result.get("data", result.get("routes", []))
                if not routes:
                    return error_result(DATA_MISSING, "Brak tras RWGPS")
                last = routes[0] if isinstance(routes, list) else routes
                return success_result({"last_route": last})
            return error_result(DATA_MISSING, "No RWGPS route data")
        return {
            "callable": _wrapper,
            "category": "routes",
            "description": "Get the most recent RWGPS route",
            "args_schema": {},
            "safety": "read",
            "mode": "read_only",
            "status": "implemented",
            "notes": "Calls rwgps_route_list and returns first (latest) entry",
        }
    except ImportError:
        def _stub(args: dict[str, Any]) -> dict[str, Any]:
            from qbot3.errors import CONNECTOR_MISSING
            return error_result(CONNECTOR_MISSING, "RWGPS route tools not available")
        return {
            "callable": _stub,
            "category": "routes",
            "description": "Get the most recent RWGPS route",
            "args_schema": {},
            "safety": "read",
            "mode": "read_only",
            "status": "adapter_missing",
        }


def _load_rwgps_artifact_status_tool() -> dict[str, Any]:
    from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        route_id = str(args.get("route_id", "")).strip()
        if not route_id:
            return error_result(CONNECTOR_MISSING, "route_id required")
        artifacts_dir = Path("/opt/qbot/artifacts")
        if not artifacts_dir.is_dir():
            return error_result(CONNECTOR_MISSING, "Artifact directory not found")
        patterns = [f"*{route_id}*", f"*{route_id}.*"]
        found = []
        for p in patterns:
            for f in artifacts_dir.rglob(p):
                if f.is_file():
                    found.append(str(f.relative_to(artifacts_dir)))
        if found:
            return success_result({"route_id": route_id, "artifacts": found, "count": len(found)})
        return error_result(DATA_MISSING, f"Brak artifactów dla trasy {route_id}")
    return {
        "callable": _wrapper,
        "category": "routes",
        "description": "Check if route artifacts (GPX/JSON) exist for a given route_id. Parameters: route_id (required string)",
        "args_schema": {"route_id": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "status": "implemented",
        "notes": "Searches /opt/qbot/artifacts for files matching route_id",
    }


# ── write tools ────────────────────────────────────────────────────────

def _load_nutrition_log_add_tool() -> dict[str, Any]:
    from qbot_nutrition_tools import _tool_qbot_nutrition_meal_from_template, _tool_qbot_nutrition_intake_log
    return {
        "callable": _safe_call,
        "wrapped": _tool_qbot_nutrition_intake_log,
        "category": "nutrition",
        "description": "Log a meal entry. Parameters: date (ISO), meal_name, kcal_total, protein_g, carbs_g, fat_g, template_id (optional)",
        "args_schema": {
            "date": {"type": "string"}, "meal_name": {"type": "string"},
            "kcal_total": {"type": "number"}, "protein_g": {"type": "number"},
            "carbs_g": {"type": "number"}, "fat_g": {"type": "number"},
            "template_id": {"type": "integer"},
        },
        "safety": "write",
    }


def _load_calendar_event_add_tool() -> dict[str, Any]:
    TOOL_FUNC = None
    try:
        from qbot_mcp_adapter import _action_exec_event
        TOOL_FUNC = _action_exec_event
    except ImportError:
        def _fallback(args: dict[str, Any]) -> dict[str, Any]:
            return {"status": "BLOCKED", "error": "calendar event writer not available"}
        TOOL_FUNC = _fallback
    return {
        "callable": lambda args: _safe_call(TOOL_FUNC, args),
        "category": "calendar",
        "description": "Add a calendar event. Parameters: date_start (ISO), time_start, title, description, event_type, date_end, all_day",
        "args_schema": {
            "date_start": {"type": "string"}, "time_start": {"type": "string"},
            "title": {"type": "string"}, "description": {"type": "string"},
            "event_type": {"type": "string"}, "date_end": {"type": "string"},
            "all_day": {"type": "boolean"},
        },
        "safety": "write",
    }


def _load_reminder_add_tool() -> dict[str, Any]:
    TOOL_FUNC = None
    try:
        from qbot_mcp_adapter import _action_exec_reminder
        TOOL_FUNC = _action_exec_reminder
    except ImportError:
        def _fallback(args: dict[str, Any]) -> dict[str, Any]:
            return {"status": "BLOCKED", "error": "reminder writer not available"}
        TOOL_FUNC = _fallback
    return {
        "callable": lambda args: _safe_call(TOOL_FUNC, args),
        "category": "calendar",
        "description": "Add a reminder. Parameters: date (ISO), time, title, message",
        "args_schema": {
            "date": {"type": "string"}, "time": {"type": "string"},
            "title": {"type": "string"}, "message": {"type": "string"},
        },
        "safety": "write",
    }


def _load_planning_fact_add_tool() -> dict[str, Any]:
    from qbot_planning_memory import save_planning_fact
    def _wrapper(args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = save_planning_fact(
                fact_type=str(args.get("fact_type", "custom")),
                date=str(args.get("date", _today())),
                title=str(args.get("title", "")),
                fact_json=args.get("fact_json", {}),
            )
            return {"status": "OK", "fact": result}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc)[:300]}
    return {
        "callable": _wrapper,
        "category": "planning",
        "description": "Save a planning fact. Parameters: title (required), fact_type (default: custom), date (ISO), fact_json (optional dict)",
        "args_schema": {
            "title": {"type": "string"}, "fact_type": {"type": "string"},
            "date": {"type": "string"}, "fact_json": {"type": "object"},
        },
        "safety": "write",
    }


def _load_memory_write_tool() -> dict[str, Any]:
    from qbot3.memory import write_memory
    return {
        "callable": lambda args: (write_memory(
            str(args.get("memory_type", "confirmed_fact")),
            {"key": args.get("key", ""), "value": args.get("value", ""), "source": args.get("source", "qbot3")},
            source="qbot3",
        ), {"status": "OK", "memory_type": args.get("memory_type", "confirmed_fact")})[1],
        "category": "memory",
        "description": "Save a confirmed fact to memory. Parameters: memory_type (confirmed_fact|conversation_summary), key, value",
        "args_schema": {
            "memory_type": {"type": "string"}, "key": {"type": "string"}, "value": {"type": "string"},
        },
        "safety": "write",
    }


# ── DB introspection tool loaders ──────────────────────────────────────

def _load_db_schema_list_tool() -> dict[str, Any]:
    from qbot3.db_introspection import db_schema_list
    return {
        "callable": lambda args: db_schema_list(args),
        "category": "db",
        "description": "List all database schemas and their tables. No args needed.",
        "args_schema": {},
        "safety": "read",
        "mode": "read_only",
        "notes": "Transparent DB introspection — Albert should use this when the target table is unknown.",
    }

def _load_db_table_describe_tool() -> dict[str, Any]:
    from qbot3.db_introspection import db_table_describe
    return {
        "callable": lambda args: db_table_describe(args),
        "category": "db",
        "description": "Describe columns of a table: name, type, nullable, default, is_pk. Parameters: table (required), schema (default: public)",
        "args_schema": {"table": {"type": "string"}, "schema": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "notes": "Use this to discover actual column names and types when the schema is unknown or a reader failed.",
    }

def _load_db_sample_rows_tool() -> dict[str, Any]:
    from qbot3.db_introspection import db_sample_rows
    return {
        "callable": lambda args: db_sample_rows(args),
        "category": "db",
        "description": "Sample rows from a table. Parameters: table (required), schema (default: public), limit (default: 5, max: 50)",
        "args_schema": {"table": {"type": "string"}, "schema": {"type": "string"}, "limit": {"type": "integer"}},
        "safety": "read",
        "mode": "read_only",
        "notes": "Use to inspect actual row shape after db_table_describe or when rows are needed for orientation.",
    }

def _load_db_select_readonly_tool() -> dict[str, Any]:
    from qbot3.db_introspection import db_select_readonly
    return {
        "callable": lambda args: db_select_readonly(args),
        "category": "db",
        "description": "Execute a read-only SELECT query. This is the default source of truth for ordinary data questions. Only SELECT allowed, LIMIT enforced. Parameters: sql (required)",
        "args_schema": {"sql": {"type": "string"}},
        "safety": "read",
        "mode": "read_only",
        "notes": "Primary transparent read path for ordinary questions; use db_schema_list / db_table_describe first when schema is unknown.",
    }


# ── init ───────────────────────────────────────────────────────────────

def _init_registry():
    if _TOOL_REGISTRY:
        return

    loaders = [
        ("status", _load_status_tool),
        ("readiness", _load_readiness_tool),
        ("system_env_status", _load_system_env_status_tool),
        ("calendar_snapshot", _load_calendar_snapshot_tool),
        ("planning_facts", _load_planning_facts_tool),
        ("weather_forecast", _load_weather_forecast_tool),
        ("nutrition_template_list", _load_nutrition_templates_tool),
        ("nutrition_template_get", _load_nutrition_template_get_tool),
        ("nutrition_day_summary", _load_nutrition_day_summary_tool),
        ("nutrition_meal_list", _load_nutrition_meal_list_tool),
        ("nutrition_range_summary", _load_nutrition_range_summary_tool),
        ("wellness_day", _load_wellness_day_tool),
        ("sleep_day", _load_sleep_day_tool),
        ("xert_readiness", _load_xert_readiness_tool),
        ("garmin_diagnostics", _load_garmin_diagnostics_tool),
        ("rwgps_route_list", _load_rwgps_list_tool),
        ("rwgps_route_fetch", _load_rwgps_route_fetch_tool),
        ("qcal_events_range", _load_qcal_events_range_tool),
        ("qcal_reminders_upcoming", _load_qcal_reminders_upcoming_tool),
        ("garage_status", _load_garage_status_tool),
        ("canonical_docs", _load_canonical_docs_tool),
        ("mcp_tools_list", _load_mcp_tools_list_tool),
        ("daily_report_status", _load_daily_report_status_tool),
        ("gate_status", _load_gate_status_tool),
        ("hammerhead_sync_status", _load_hammerhead_sync_status_tool),
        ("llm_status", _load_llm_status_tool),
        ("system_logs_recent", _load_system_logs_recent_tool),
        ("docs_list_qbot", _load_docs_list_qbot_tool),
        ("nutrition_balance_today", _load_nutrition_balance_today_tool),
        ("garmin_energy_today", _load_garmin_energy_today_tool),
        ("garmin_sync_status", _load_garmin_sync_status_tool),
        ("qcal_events_upcoming", _load_qcal_events_upcoming_tool),
        ("rwgps_route_last", _load_rwgps_route_last_tool),
        ("rwgps_artifact_status", _load_rwgps_artifact_status_tool),
        # DB introspection tools (transparent read-only for Albert)
        ("db_schema_list", _load_db_schema_list_tool),
        ("db_table_describe", _load_db_table_describe_tool),
        ("db_sample_rows", _load_db_sample_rows_tool),
        ("db_select_readonly", _load_db_select_readonly_tool),
        # Write tools
        ("nutrition_log_add", _load_nutrition_log_add_tool),
        ("calendar_event_add", _load_calendar_event_add_tool),
        ("reminder_add", _load_reminder_add_tool),
        ("planning_fact_add", _load_planning_fact_add_tool),
        ("memory_confirmed_fact_add", _load_memory_write_tool),
    ]

    for name, loader in loaders:
        try:
            spec = loader()
            _TOOL_REGISTRY[name] = spec
            if spec.get("safety") == "write":
                _WRITE_TOOLS[name] = spec
            else:
                _READ_ONLY_TOOLS[name] = spec
        except Exception as exc:
            _TOOL_REGISTRY[name] = {
                "error": str(exc)[:200],
                "safety": "error",
                "category": "error",
            }


def lookup(name: str) -> dict[str, Any] | None:
    _init_registry()
    return _TOOL_REGISTRY.get(name)


def list_read_tools() -> dict[str, dict[str, Any]]:
    _init_registry()
    return dict(_READ_ONLY_TOOLS)


def list_write_tools() -> dict[str, dict[str, Any]]:
    _init_registry()
    return dict(_WRITE_TOOLS)


def list_all_tools() -> dict[str, dict[str, Any]]:
    _init_registry()
    return dict(_TOOL_REGISTRY)


def tool_descriptions() -> list[dict[str, Any]]:
    _init_registry()
    return [
        {
            "name": name,
            "category": spec.get("category", ""),
            "description": spec.get("description", ""),
            "args_schema": spec.get("args_schema", {}),
            "safety": spec.get("safety", "read"),
            "mode": spec.get("mode", "read_only"),
            "status": spec.get("status", "implemented"),
            "notes": spec.get("notes", ""),
        }
        for name, spec in sorted(_TOOL_REGISTRY.items())
        if "error" not in spec
    ]
