#!/usr/bin/env python3
"""Internal adapter for daily_report.py — maps legacy tool names to direct calls.

No public MCP tools added. All calls are direct internal imports.
Replaces the broken mcp_call("get_events") etc. after QBot3 cutover.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from qbot3.errors import OK, DATA_MISSING, CONNECTOR_MISSING, error_result, success_result


def get_events(oldest: str | None = None, newest: str | None = None) -> list[dict[str, Any]]:
    """Internal replacement for mcp_call('get_events')."""
    try:
        from qbot_calendar_core import event_list
        today_s = oldest or date.today().isoformat()
        end_s = newest or (date.fromisoformat(today_s) + timedelta(days=4)).isoformat()
        events = event_list(date_from=today_s, date_to=end_s, limit=50)
        return events or []
    except ImportError:
        print("  ⚠️  get_events: qbot_calendar_core not available")
        return []
    except Exception as exc:
        print(f"  ⚠️  get_events: {exc}")
        return []


def get_weather(days: int = 2, location: str = "Marki") -> dict[str, Any]:
    """Internal replacement for mcp_call('get_weather')."""
    try:
        from qbot_integration_tools import _tool_qbot_weather_daily_report
        result = _tool_qbot_weather_daily_report({"location": location, "days": days})
        if isinstance(result, dict) and result.get("status") == "OK":
            return result
        return {"error": result.get("error", "unknown") if isinstance(result, dict) else "empty"}
    except ImportError:
        print("  ⚠️  get_weather: qbot_integration_tools not available")
        return {"error": "connector_missing"}
    except Exception as exc:
        print(f"  ⚠️  get_weather: {exc}")
        return {"error": str(exc)[:200]}


def get_xert_status() -> dict[str, Any]:
    """Internal replacement for mcp_call('get_xert_status')."""
    try:
        from qbot_integration_tools import _tool_qbot_xert_readiness_status
        result = _tool_qbot_xert_readiness_status({})
        if isinstance(result, dict) and result.get("status") == "OK":
            return {
                "tp_ftp_watts": result.get("ftp_watts"),
                "tl": None,
                "form_score": None,
                "training_load": None,
                "forma": {
                    "form_score": None,
                    "status": result.get("form_status"),
                    "training_load": None,
                },
                "trening_dziś": {"zalecany_typ": None},
            }
        return {"error": result.get("error", "unknown") if isinstance(result, dict) else "empty"}
    except ImportError:
        print("  ⚠️  get_xert_status: qbot_integration_tools not available")
        return {"error": "connector_missing"}
    except Exception as exc:
        print(f"  ⚠️  get_xert_status: {exc}")
        return {"error": str(exc)[:200]}


def get_xert_activities(limit: int = 10) -> list[dict[str, Any]]:
    """Pobiera ostatnie aktywnosci z Xert.

    Loguje sie password-grant (klient xert_public) tak samo jak
    qbot_xert_readiness_status -- statyczny XERT_ACCESS_TOKEN nie istnieje.
    Mapuje activities.data[] -> [{date, threshold_power, ...}] dla
    tp_z_aktywnosci() w daily_report.py.
    """
    try:
        import httpx
        import os
        import qbot_config  # noqa: F401 - upewnia sie, ze .env(.local) zaladowany
        email = os.getenv("XERT_EMAIL", "")
        password = os.getenv("XERT_PASSWORD", "")
        if not (email and password):
            print("  [WARN] get_xert_activities: brak XERT_EMAIL/XERT_PASSWORD")
            return []
        with httpx.Client(timeout=15) as client:
            tok_r = client.post(
                "https://www.xertonline.com/oauth/token",
                auth=("xert_public", "xert_public"),
                data={"grant_type": "password", "username": email, "password": password},
            )
            tok_r.raise_for_status()
            token = tok_r.json().get("access_token", "")
            if not token:
                print("  [WARN] get_xert_activities: brak access_token z logowania")
                return []
            r = client.get(
                "https://www.xertonline.com/oauth/activities",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            payload = r.json()
        rows = payload.get("activities", {}).get("data", []) if isinstance(payload, dict) else []
        out: list[dict[str, Any]] = []
        for it in rows[:limit]:
            sess = (it.get("sessions") or [{}])[0]
            tp = sess.get("threshold_power") or it.get("threshold_power")
            start = it.get("start_date") or ""
            out.append({
                "date": start[:10] if start else None,
                "start_date": start,
                "threshold_power": tp,
                "name": it.get("name"),
            })
        return out
    except Exception as exc:
        print(f"  [WARN] get_xert_activities: {exc}")
        return []

def get_garmin_wellness(date_str: str | None = None) -> dict[str, Any]:
    """Internal replacement for mcp_call('get_garmin_wellness')."""
    try:
        from qbot_wellness_store import _tool_qbot_wellness_day_get
        ds = date_str or date.today().isoformat()
        result = _tool_qbot_wellness_day_get({"date": ds})
        if not isinstance(result, dict):
            return {}
        if result.get("status") in ("OK", "NO_DATA"):
            data = result.get("data") or {}
            return {
                "sen": {
                    "czas_h": round(data.get("sleep_duration_min", 0) / 60, 1) if data.get("sleep_duration_min") else None,
                    "score": data.get("sleep_score"),
                    "ocena": None,
                    "gleboki_min": None,
                    "rem_min": None,
                },
                "hrv": {
                    "srednia_tygodnia": data.get("hrv_ms"),
                    "status": None,
                },
                "body_battery": {
                    "max_rano": data.get("body_battery_start"),
                    "min_wieczor": None,
                },
                "tetno_spoczynkowe": data.get("resting_hr_bpm"),
            }
        return {}
    except ImportError:
        print("  ⚠️  get_garmin_wellness: qbot_wellness_store not available")
        return {}
    except Exception as exc:
        print(f"  ⚠️  get_garmin_wellness: {exc}")
        return {}
