#!/usr/bin/env python3
"""Shared delivery-state helpers for QBot reports."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_CHANNELS = ("telegram", "email")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def channels_complete(channels: dict | None, required: tuple[str, ...] = REQUIRED_CHANNELS) -> bool:
    if not channels:
        return False
    return all(channels.get(ch) == "sent" for ch in required)


def single_report_state_for_date(path: Path, report_date: str) -> dict:
    data = load_json(path, {})
    if not isinstance(data, dict) or data.get("date") != report_date:
        return {}
    return data


def single_report_complete(path: Path, report_date: str) -> bool:
    state = single_report_state_for_date(path, report_date)
    if not state:
        return False
    channels = state.get("channels")
    # Legacy state files only had {"date": "..."} and meant fully sent.
    return True if not channels else channels_complete(channels)


def mark_single_report(path: Path, report_date: str, channels: dict | None = None) -> None:
    payload = {"date": report_date}
    if channels:
        payload["channels"] = channels
    write_json(path, payload)


def activity_report_complete(path: Path, activity_id: str, *, in_progress_ttl_hours: int = 6) -> bool:
    reported = load_json(path, {})
    if not isinstance(reported, dict):
        return False
    item = reported.get(str(activity_id))
    if not isinstance(item, dict):
        return False
    if item.get("status") == "in_progress":
        try:
            started = datetime.fromisoformat(item.get("date", ""))
            age_hours = (datetime.now() - started).total_seconds() / 3600
            if age_hours > in_progress_ttl_hours:
                return False
        except Exception:
            return False
    return item.get("status", "sent") in ("sent", "in_progress")


def mark_activity_report(
    path: Path,
    activity_id: str,
    activity_name: str,
    status: str,
    *,
    error: Exception | str | None = None,
    channels: dict | None = None,
    keep: int = 100,
) -> None:
    reported = load_json(path, {})
    if not isinstance(reported, dict):
        reported = {}
    previous = reported.get(str(activity_id), {})
    entry = {
        "name": activity_name,
        "date": datetime.now().isoformat(),
        "status": status,
        "channels": channels or previous.get("channels", {}),
    }
    if error:
        entry["error"] = str(error)[:500]
    reported[str(activity_id)] = entry
    if len(reported) > keep:
        for key in sorted(reported.keys())[: len(reported) - keep]:
            del reported[key]
    write_json(path, reported)
