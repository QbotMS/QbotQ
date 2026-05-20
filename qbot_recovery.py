"""Recovery record selection for Karoo readiness/setup payloads."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds).astimezone()
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _display_dt(value: Any) -> Any:
    parsed = _parse_dt(value)
    return parsed.isoformat() if parsed else value


def _parse_date(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if "T" in raw:
        parsed = _parse_dt(raw)
        return parsed.date().isoformat() if parsed else raw[:10]
    return raw[:10]


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def normalize_sleep_record(record: dict[str, Any]) -> dict[str, Any]:
    start = _first(record, (
        "sleepStartTime",
        "sleepStartTimestampLocal",
        "sleepStartTimestampGMT",
        "startTime",
        "start",
    ))
    end = _first(record, (
        "sleepEndTime",
        "sleepEndTimestampLocal",
        "sleepEndTimestampGMT",
        "wakeTime",
        "endTime",
        "end",
    ))
    duration_min = _number(_first(record, (
        "sleepDurationMin",
        "durationMin",
        "durationMinutes",
    )))
    if duration_min is None:
        duration_seconds = _number(_first(record, (
            "sleepTimeSeconds",
            "sleepSecs",
            "durationSeconds",
        )))
        duration_min = round(duration_seconds / 60, 1) if duration_seconds is not None else None

    end_dt = _parse_dt(end)
    local_date = _parse_date(_first(record, (
        "sleepLocalDate",
        "localDate",
        "calendarDate",
        "id",
        "date",
    ))) or (end_dt.date().isoformat() if end_dt else None)
    is_complete = bool(end_dt and duration_min and duration_min > 0)

    return {
        "localDate": local_date,
        "startTime": _display_dt(start),
        "endTime": _display_dt(end),
        "endDt": end_dt,
        "durationMin": duration_min,
        "source": record.get("source") or "garmin",
        "isComplete": is_complete,
        "raw": record,
    }


def normalize_hrv_record(record: dict[str, Any]) -> dict[str, Any]:
    value = _number(_first(record, (
        "hrv",
        "value",
        "lastNightAvg",
        "srednia_noc",
    )))
    source_time = _first(record, (
        "hrvSourceTime",
        "sourceTime",
        "sleepEndTime",
        "sleepEndTimestampLocal",
        "time",
        "timestamp",
    ))
    source_dt = _parse_dt(source_time)
    local_date = _parse_date(_first(record, (
        "hrvLocalDate",
        "localDate",
        "calendarDate",
        "id",
        "date",
    ))) or (source_dt.date().isoformat() if source_dt else None)
    weekly_avg = _number(_first(record, ("weeklyAvg", "srednia_tygodnia")))

    return {
        "localDate": local_date,
        "sourceTime": _display_dt(source_time),
        "sourceDt": source_dt,
        "value": round(value, 1) if value is not None else None,
        "weeklyAvg": round(weekly_avg, 1) if weekly_avg is not None else None,
        "source": record.get("source") or "garmin",
        "raw": record,
    }


def _hrv_sort_key(record: dict[str, Any]) -> tuple[int, str]:
    source_dt = record.get("sourceDt")
    if source_dt:
        return (1, source_dt.isoformat())
    return (0, record.get("localDate") or "")


def _hrv_matches_sleep(hrv: dict[str, Any], sleep: dict[str, Any]) -> bool:
    if not hrv.get("value"):
        return False
    sleep_date = sleep.get("localDate")
    sleep_end = sleep.get("endDt")
    hrv_date = hrv.get("localDate")
    hrv_dt = hrv.get("sourceDt")
    if sleep_date and hrv_date and sleep_date == hrv_date:
        return True
    if sleep_end and hrv_dt and sleep_end.date() == hrv_dt.date():
        return True
    return False


def select_recovery_records(
    sleep_records: list[dict[str, Any]] | None,
    hrv_records: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    sleep_candidates = [normalize_sleep_record(r) for r in (sleep_records or [])]
    hrv_candidates = [normalize_hrv_record(r) for r in (hrv_records or [])]
    complete_sleep = [r for r in sleep_candidates if r["isComplete"]]
    selected_sleep = max(complete_sleep, key=lambda r: r["endDt"]) if complete_sleep else None

    hrv_with_values = [r for r in hrv_candidates if r.get("value") is not None]
    selected_hrv = None
    hrv_matches_sleep = False
    if selected_sleep:
        matching_hrv = [r for r in hrv_with_values if _hrv_matches_sleep(r, selected_sleep)]
        if matching_hrv:
            selected_hrv = max(matching_hrv, key=_hrv_sort_key)
            hrv_matches_sleep = True
        elif hrv_with_values:
            selected_hrv = max(hrv_with_values, key=_hrv_sort_key)

    sleep_h = (
        round(selected_sleep["durationMin"] / 60, 2)
        if selected_sleep and selected_sleep.get("durationMin") is not None
        else None
    )
    hrv_value = selected_hrv.get("value") if selected_hrv else None
    hrv_baseline = selected_hrv.get("weeklyAvg") if selected_hrv else None

    recovery_source = {
        "sleepLocalDate": selected_sleep.get("localDate") if selected_sleep else None,
        "sleepStartTime": selected_sleep.get("startTime") if selected_sleep else None,
        "sleepEndTime": selected_sleep.get("endTime") if selected_sleep else None,
        "sleepDurationMin": selected_sleep.get("durationMin") if selected_sleep else None,
        "hrvLocalDate": selected_hrv.get("localDate") if selected_hrv else None,
        "hrvSourceTime": selected_hrv.get("sourceTime") if selected_hrv else None,
        "source": selected_sleep.get("source") if selected_sleep else None,
        "hrvSource": selected_hrv.get("source") if selected_hrv else None,
        "hrvMatchesSleep": hrv_matches_sleep,
        "hrvFallback": bool(selected_hrv and not hrv_matches_sleep),
        "isComplete": bool(selected_sleep),
    }

    return {
        "candidates": len(sleep_candidates),
        "completeSleepCandidates": len(complete_sleep),
        "hrvCandidates": len(hrv_candidates),
        "selectedSleepRecord": selected_sleep,
        "selectedHrvRecord": selected_hrv,
        "hrvToday": hrv_value,
        "sleepTodayH": sleep_h,
        "hrvBaseline": hrv_baseline,
        "recoverySource": recovery_source,
    }
