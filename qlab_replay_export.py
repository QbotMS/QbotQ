#!/usr/bin/env python3
"""Export local FIT files to QLab passthrough replay JSON."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fitparse import FitFile


DEFAULT_SEARCH_DIRS = [Path("/opt/qbot/app/data"), Path("/opt/qbot/app")]
DEFAULT_OUTPUT = Path("/opt/qbot/app/data/qbot_replay_log.json")
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules"}

REPLAY_TICK_FIELDS = [
    "activity_id",
    "source_file",
    "record_index",
    "timestamp",
    "t_s",
    "position_lat",
    "position_long",
    "distance_m",
    "altitude_m",
    "speed_mps",
    "heart_rate_bpm",
    "power_w",
    "cadence_rpm",
    "temperature_c",
    "grade",
]


def _iso_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _seconds_since(value: Any, start: Any) -> float | None:
    if value is None or start is None:
        return None
    try:
        return round((value - start).total_seconds(), 3)
    except Exception:
        return None


def _semicircles_to_degrees(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value) * (180 / 2**31), 7)


def _num(value: Any, digits: int | None = None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if digits is None:
        return int(number) if number.is_integer() else number
    return round(number, digits)


def _field_map(record: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for field in record:
        fields[field.name] = field.value
    return fields


def _speed(fields: dict[str, Any]) -> float | None:
    if fields.get("enhanced_speed") is not None:
        return _num(fields.get("enhanced_speed"), 3)
    if fields.get("speed") is not None:
        return _num(fields.get("speed"), 3)
    return None


def parse_fit_to_replay_ticks(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse a local FIT file into ReplayTick dictionaries.

    Missing FIT fields are emitted as None. No values are inferred from other
    fields; only direct FIT record values are mapped.
    """
    fit = FitFile(str(path))
    records = list(fit.get_messages("record"))
    first_ts = None
    for record in records:
        ts = _field_map(record).get("timestamp")
        if ts is not None:
            first_ts = ts
            break

    activity_id = path.stem
    ticks: list[dict[str, Any]] = []
    present: set[str] = set()

    for idx, record in enumerate(records):
        fields = _field_map(record)
        present.update(k for k, v in fields.items() if v is not None)
        ts = fields.get("timestamp")

        tick = {
            "activity_id": activity_id,
            "source_file": str(path),
            "record_index": idx,
            "timestamp": _iso_timestamp(ts),
            "t_s": _seconds_since(ts, first_ts),
            "position_lat": _semicircles_to_degrees(fields.get("position_lat")),
            "position_long": _semicircles_to_degrees(fields.get("position_long")),
            "distance_m": _num(fields.get("distance"), 3),
            "altitude_m": _num(
                fields.get("enhanced_altitude")
                if fields.get("enhanced_altitude") is not None
                else fields.get("altitude"),
                2,
            ),
            "speed_mps": _speed(fields),
            "heart_rate_bpm": _num(fields.get("heart_rate")),
            "power_w": _num(fields.get("power")),
            "cadence_rpm": _num(fields.get("cadence")),
            "temperature_c": _num(fields.get("temperature")),
            "grade": _num(fields.get("grade"), 3),
        }
        ticks.append(tick)

    metadata = {
        "activity_id": activity_id,
        "source_file": str(path),
        "record_count": len(records),
        "first_timestamp": _iso_timestamp(first_ts),
        "fit_fields_present": sorted(present),
    }
    return ticks, metadata


def _parse_search_dirs(search_dirs: str | None) -> list[Path]:
    raw = search_dirs or os.getenv("QBOT_FIT_DIRS")
    if not raw:
        return DEFAULT_SEARCH_DIRS
    return [Path(item.strip()) for item in raw.split(":") if item.strip()]


def find_fit_files(search_dirs: str | None = None) -> list[Path]:
    roots = _parse_search_dirs(search_dirs)
    found: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".fit":
            found.append(root)
            continue
        if not root.is_dir():
            continue
        for current, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            base = Path(current)
            for filename in filenames:
                path = base / filename
                if path.suffix.lower() == ".fit":
                    found.append(path)
    return sorted(set(found), key=lambda p: str(p))


def build_qlab_replay_payload(fit_files: list[Path]) -> dict[str, Any]:
    activities = []
    ticks: list[dict[str, Any]] = []
    errors = []

    for path in fit_files:
        try:
            file_ticks, metadata = parse_fit_to_replay_ticks(path)
            activities.append(metadata)
            ticks.extend(file_ticks)
        except Exception as exc:
            errors.append({"source_file": str(path), "error": str(exc)})

    return {
        "schema": "qbot.qlab.replay_log",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer": "QBot",
        "consumer": "QLab",
        "transport": "passthrough",
        "replay_tick_type": "ReplayTick[]",
        "tick_fields": REPLAY_TICK_FIELDS,
        "missing_data_policy": "missing FIT fields are null; no inferred values",
        "fit_files": [str(p) for p in fit_files],
        "activities": activities,
        "ticks": ticks,
        "errors": errors,
    }


def export_qlab_replay(
    search_dirs: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    fit_files = find_fit_files(search_dirs)
    payload = build_qlab_replay_payload(fit_files)

    out = Path(output_path or os.getenv("QBOT_QLAB_REPLAY_OUTPUT") or DEFAULT_OUTPUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "output_path": str(out),
        "fit_files_found": len(fit_files),
        "activities": len(payload["activities"]),
        "ticks": len(payload["ticks"]),
        "errors": payload["errors"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--search-dirs", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    print(json.dumps(export_qlab_replay(args.search_dirs, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
