#!/usr/bin/env python3
"""Data validation for QBot reports before generation/sending.

Defines:
  - DATA_OK:       all required data fresh and present
  - DATA_PARTIAL:  partial data — report must show explicit missing sections
  - DATA_MISSING:  critical data absent — do NOT generate normal report

Usage:
    status, details = validate_daily_report_data(data_sources, date)
    status, details = validate_ride_report_data(activity_data, activity_id)
"""

from __future__ import annotations

from datetime import date
from typing import Any

# ── Status constants ────────────────────────────────────────────────────────

DATA_OK = "DATA_OK"
DATA_PARTIAL = "DATA_PARTIAL"
DATA_MISSING = "DATA_MISSING"

# ── Source freshness ────────────────────────────────────────────────────────

MAX_SLEEP_AGE_HOURS = 18
MAX_WELLNESS_AGE_HOURS = 24
MAX_ACTIVITY_AGE_HOURS = 48
MAX_NUTRITION_AGE_HOURS = 48


def _source_freshness(
    source_date: date | str | None,
    today: date,
    max_age_hours: int = 48,
) -> str:
    """Return 'fresh', 'stale' or 'missing' for a source."""
    if source_date is None:
        return "missing"
    if isinstance(source_date, str):
        try:
            source_date = date.fromisoformat(source_date[:10])
        except (ValueError, TypeError):
            return "missing"
    delta = (today - source_date).days
    if delta < 0:
        return "fresh"
    if delta == 0:
        hours_old = 0
        if hours_old <= max_age_hours:
            return "fresh"
        return "stale"
    if delta == 1 and max_age_hours >= 24:
        return "stale"
    return "missing"


# ── Daily report validation ─────────────────────────────────────────────────


REQUIRED_DAILY_FIELDS = [
    "date",
    "sleep_wellness",
    "calories_expenditure",
    "nutrition",
    "activity_summary",
]


def validate_daily_from_provider(
    provider_result: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Validate daily report data from ReportDataProvider output.

    Args:
        provider_result: the dict returned by ReportDataProvider.get_daily_report_data()

    Returns:
        (status, details) same as validate_daily_report_data()
    """
    val = provider_result.get("validation", {})
    val_status = val.get("status", "DATA_MISSING")
    missing = val.get("missing_fields", [])

    if val_status == "DATA_MISSING":
        alert = (
            "Raport nie zosta\u0142 wygenerowany \u2014 brak danych krytycznych: "
            + ", ".join(missing)
            + ". Sprawd\u017a synchronizacj\u0119 Garmin i Intervals.icu."
        )
        return DATA_MISSING, {
            "required_fields": {k: provider_result.get(k, {}).get("status") for k in
                                ["sleep", "wellness", "energy", "nutrition", "activity_summary", "body_composition", "xert"]},
            "missing": missing,
            "partial": [],
            "present": [],
            "garmin_sync_failed": any("sync" in m for m in missing),
            "alert_message": alert,
        }

    if val_status == "DATA_PARTIAL":
        alert = "Raport cz\u0119\u015bciowy \u2014 brakuj\u0105ce: " + ", ".join(missing)
        return DATA_PARTIAL, {
            "required_fields": {},
            "missing": [m for m in missing if "(partial)" not in m],
            "partial": [m.replace("(partial)", "") for m in missing if "(partial)" in m],
            "present": [k for k in ["sleep", "wellness", "energy", "nutrition", "activity_summary", "body_composition"] if provider_result.get(k, {}).get("status") == "ok"],
            "garmin_sync_failed": False,
            "alert_message": alert,
        }

    return DATA_OK, {
        "required_fields": {},
        "missing": [],
        "partial": [],
        "present": [k for k in ["sleep", "wellness", "energy", "nutrition", "activity_summary", "body_composition"]
                    if provider_result.get(k, {}).get("status") == "ok"],
        "garmin_sync_failed": False,
        "alert_message": None,
    }


def validate_ride_from_provider(
    provider_result: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Validate ride report data from ReportDataProvider output.

    Args:
        provider_result: the dict returned by ReportDataProvider.get_ride_report_data()

    Returns:
        (status, details) same as validate_ride_report_data()
    """
    val = provider_result.get("validation", {})
    val_status = val.get("status", "DATA_MISSING")
    missing = val.get("missing_fields", [])
    alert = val.get("alert")

    if val_status == "DATA_MISSING":
        return DATA_MISSING, {
            "missing": missing or ["activity_data"],
            "partial": [],
            "present": [],
            "alert_message": alert or "Raport nie zosta\u0142 wygenerowany \u2014 brak danych aktywno\u015bci.",
        }

    if val_status == "DATA_PARTIAL":
        act = provider_result.get("aktywnosc", {})
        return DATA_PARTIAL, {
            "missing": missing,
            "partial": act.get("missing_fields", []),
            "present": [],
            "alert_message": alert or "Raport cz\u0119\u015bciowy.",
        }

    return DATA_OK, {
        "missing": [],
        "partial": [],
        "present": ["activity_id", "czas_trwania", "dystans", "przewy\u017cszenie", "moc", "t\u0119tno"],
        "alert_message": None,
    }


def validate_daily_report_data(
    data_sources: dict[str, str | None],
    report_date: date | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate data completeness for daily report.

    Args:
        data_sources: dict with keys:
            - sleep_wellness: status ('ok', 'empty', 'error', or None)
            - calories_expenditure: status
            - nutrition: status
            - activity_summary: status
            - garmin_sync: status ('ok', 'failed', or None)
            - intervals_wellness: status
        report_date: the date being reported on

    Returns:
        (status, details) where:
          status = DATA_OK | DATA_PARTIAL | DATA_MISSING
          details = {
            "required_fields": {...},
            "missing": [...],
            "partial": [...],
            "present": [...],
            "garmin_sync_failed": bool,
            "alert_message": str | None,
          }
    """
    today = report_date or date.today()

    required_fields = {
        "date": today.isoformat(),
        "sleep_wellness": data_sources.get("sleep_wellness"),
        "calories_expenditure": data_sources.get("calories_expenditure"),
        "nutrition": data_sources.get("nutrition"),
        "activity_summary": data_sources.get("activity_summary"),
    }

    garmin_sync = data_sources.get("garmin_sync")
    garmin_sync_failed = garmin_sync in ("failed", "error", None)

    missing = [k for k, v in required_fields.items() if v in (None, "missing", "error")]
    partial = [k for k, v in required_fields.items() if v == "empty"]
    present = [k for k, v in required_fields.items() if v == "ok"]

    # Decide status
    # DATA_MISSING: no real data at all, or garmin sync failed AND nothing present
    if garmin_sync_failed and not present:
        alert = (
            "Raport nie zosta\u0142 wygenerowany \u2014 brak danych: "
            "synchronizacja Garmin nie powiod\u0142a si\u0119, "
            "brak danych wellness, sleep, nutrition i aktywno\u015bci. "
            "Sprawd\u017a status synchronizacji Garmin i spr\u00f3buj ponownie."
        )
        return DATA_MISSING, {
            "required_fields": required_fields,
            "missing": missing + partial,
            "partial": [],
            "present": present,
            "garmin_sync_failed": True,
            "alert_message": alert,
        }

    # Blokuj tylko gdy brakuje nutrition - reszta to PARTIAL
    _hard_missing = [f for f in missing if "nutrition" in f]
    if _hard_missing:
        alert = "Raport nie zostal wygenerowany - brak danych zywieniowych: " + ", ".join(_hard_missing)
        return DATA_MISSING, {"required_fields": required_fields, "missing": missing, "partial": partial, "present": present, "garmin_sync_failed": garmin_sync_failed, "alert_message": alert}

    # DATA_PARTIAL: some data present but some missing
    if missing or partial:
        parts = []
        if missing:
            parts.append("Brakuj\u0105ce: " + ", ".join(missing))
        if partial:
            parts.append("Niekompletne: " + ", ".join(partial))
        alert = "Raport cz\u0119\u015bciowy \u2014 " + "; ".join(parts)
        return DATA_PARTIAL, {
            "required_fields": required_fields,
            "missing": missing,
            "partial": partial,
            "present": present,
            "garmin_sync_failed": garmin_sync_failed,
            "alert_message": alert,
        }

    return DATA_OK, {
        "required_fields": required_fields,
        "missing": [],
        "partial": [],
        "present": present,
        "garmin_sync_failed": False,
        "alert_message": None,
    }


# ── Ride report validation ──────────────────────────────────────────────────


REQUIRED_RIDE_FIELDS = [
    "activity_id",
    "duration",
    "distance",
    "elevation",
    "source",
]


def validate_ride_report_data(
    activity_data: dict[str, Any] | None,
    activity_id: str | int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Validate data completeness for ride report.

    Args:
        activity_data: the dict returned by fetch_activity_data()
        activity_id: activity identifier for the report

    Returns:
        (status, details) tuple (same pattern as validate_daily_report_data)
    """
    if not activity_data:
        return DATA_MISSING, {
            "missing": ["activity_data"],
            "partial": [],
            "present": [],
            "alert_message": (
                "Raport nie zosta\u0142 wygenerowany \u2014 "
                "brak danych aktywno\u015bci. "
                "Nie uda\u0142o si\u0119 pobra\u0107 \u017cadnych danych aktywno\u015bci."
            ),
        }

    act = activity_data.get("aktywnosc") or {}

    # Check critical fields
    has_id = activity_id is not None or act.get("id") is not None
    duration_s = act.get("moving_time") or act.get("duration") or 0
    has_duration = float(duration_s or 0) > 0
    distance_m = act.get("distance") or 0
    has_distance = float(distance_m or 0) > 0
    elevation = act.get("elevation_gain") or act.get("total_elevation_gain") or 0
    has_elevation = float(elevation or 0) > 0

    # Determine source
    fit_streams = act.get("fit_streams")
    source = activity_data.get("source") or "intervals_icu"
    if fit_streams:
        source = "FIT"
    elif activity_data.get("nawierzchnia"):
        source = "Strava/Intervals"
    elif activity_data.get("xert", {}).get("tp_ftp_w"):
        source = "Xert"

    # Power/HR availability
    avg_watts = act.get("icu_average_watts") or act.get("avg_power")
    np_watts = act.get("icu_weighted_avg_watts") or act.get("norm_power")
    has_power = avg_watts is not None or np_watts is not None
    has_hr = act.get("average_heartrate") or act.get("avg_hr") is not None

    missing = []
    if not has_id:
        missing.append("activity_id")
    if not has_duration:
        missing.append("czas_trwania")
    if not has_distance:
        missing.append("dystans")
    if not has_elevation:
        missing.append("przewy\u017cszenie")

    partial = []
    available_fields = []
    if has_id:
        available_fields.append("activity_id")
    if has_duration:
        available_fields.append("czas_trwania")
    if has_distance:
        available_fields.append("dystans")
    if has_elevation:
        available_fields.append("przewy\u017cszenie")

    freshness_info = {
        "source": source,
        "fit_available": bool(fit_streams),
        "power_available": has_power,
        "hr_available": has_hr,
        "has_id": has_id,
        "has_duration": has_duration,
        "has_distance": has_distance,
        "has_elevation": has_elevation,
    }

    # DATA_MISSING: no core ride data
    if not has_id or (not has_duration and not has_distance):
        alert = (
            "Raport nie zosta\u0142 wygenerowany \u2014 brak danych aktywno\u015bci: "
            "nie znaleziono identyfikatora, czasu lub dystansu przejazdu. "
            "Aktywno\u015b\u0107 mo\u017ce nie by\u0107 w pe\u0142ni zsynchronizowana z Garmin/Intervals."
        )
        return DATA_MISSING, {
            "activity_id": str(activity_id) if activity_id else None,
            "missing": missing,
            "partial": partial,
            "present": available_fields,
            "freshness": freshness_info,
            "alert_message": alert,
        }

    # DATA_PARTIAL: core data present but some metrics missing
    missing_optional = []
    if not has_power:
        missing_optional.append("moc (HR/power)")
    if not has_hr:
        missing_optional.append("t\u0119tno")
    if missing_optional:
        partial.extend(missing_optional)

    if missing or partial:
        parts = []
        if missing:
            parts.append("Brakuj\u0105ce: " + ", ".join(missing))
        if partial:
            parts.append("Niekompletne: " + ", ".join(partial))
        alert = "Raport cz\u0119\u015bciowy \u2014 " + "; ".join(parts)
        return DATA_PARTIAL, {
            "activity_id": str(activity_id) if activity_id else None,
            "missing": missing,
            "partial": partial,
            "present": available_fields,
            "freshness": freshness_info,
            "alert_message": alert,
        }

    return DATA_OK, {
        "activity_id": str(activity_id) if activity_id else None,
        "missing": [],
        "partial": [],
        "present": available_fields,
        "freshness": freshness_info,
        "alert_message": None,
    }
