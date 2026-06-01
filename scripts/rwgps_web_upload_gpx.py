#!/usr/bin/env python3
"""Manual RWGPS web upload helper for full GPX route import.

This script uses the captured RWGPS web import endpoint:
POST /trips?import_type=route
multipart field: data_file

It uploads one GPX file, then finds the resulting route by created_at/name and
validates geometry plus imported native points_of_interest.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))

GPX_NAME_PREFIXES = ("Puznówka", "Puznowka", "Puznówka 31.05")


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _count_gpx_stats(path: Path) -> dict[str, int]:
    tree = ET.parse(path)
    root = tree.getroot()
    counts = {"trk": 0, "trkseg": 0, "trkpt": 0, "rte": 0, "rtept": 0, "wpt": 0}
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag in counts:
            counts[tag] += 1
    return counts


def _gpx_waypoint_names(path: Path) -> list[str]:
    tree = ET.parse(path)
    root = tree.getroot()
    names: list[str] = []
    for wpt in root.iter():
        tag = wpt.tag.rsplit("}", 1)[-1]
        if tag != "wpt":
            continue
        name_el = None
        for child in wpt:
            if child.tag.rsplit("}", 1)[-1] == "name":
                name_el = child
                break
        if name_el is not None and (name := (name_el.text or "").strip()):
            names.append(name)
    return names


def _route_points_of_interest(route: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (route.get("points_of_interest") or []) if isinstance(item, dict)]


def _route_poi_names(route: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for poi in _route_points_of_interest(route):
        name = str(poi.get("name") or poi.get("title") or "").strip()
        if name:
            names.append(name)
    return names


def _print_json(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _print_route_table(routes: list[dict[str, Any]]) -> None:
    table = []
    for route in routes:
        table.append(
            {
                "route_id": route.get("id"),
                "name": route.get("name"),
                "created_at": route.get("created_at"),
                "distance_km": route.get("distance_km"),
                "elevation_m": route.get("elevation_m"),
                "url": route.get("url") or route.get("html_url") or (f"https://ridewithgps.com/routes/{route.get('id')}" if route.get("id") else None),
            }
        )
    _print_json({"candidate_routes": table})


def _find_recent_route(route_list: list[dict[str, Any]], upload_started_at: datetime) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for route in route_list:
        created_at = _parse_iso8601(str(route.get("created_at") or ""))
        if created_at is None or created_at < upload_started_at:
            continue
        name = str(route.get("name") or "").strip()
        distance_km = route.get("distance_km")
        try:
            distance_val = float(distance_km) if distance_km is not None else None
        except (TypeError, ValueError):
            distance_val = None
        prefix_match = any(name.startswith(prefix) for prefix in GPX_NAME_PREFIXES)
        distance_match = distance_val is not None and 80.0 <= distance_val <= 83.5
        if prefix_match or distance_match:
            candidate = dict(route)
            candidate["_created_at_dt"] = created_at
            candidate["_prefix_match"] = prefix_match
            candidate["_distance_match"] = distance_match
            candidates.append(candidate)
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item.get("_created_at_dt") or datetime.min.replace(tzinfo=timezone.utc),
            bool(item.get("_prefix_match")),
            bool(item.get("_distance_match")),
        ),
        reverse=True,
    )
    return candidates[0]


def _fetch_route(route_id: str) -> dict[str, Any]:
    from tools.rwgps.client import get_route

    result = get_route(route_id)
    if isinstance(result, dict) and isinstance(result.get("route"), dict):
        return result["route"]
    return {}


def _validate_route(route_id: str, gpx_path: Path) -> dict[str, Any]:
    from tools.rwgps.client import _fetch_track_points, export_route_to_artifact

    route = _fetch_route(route_id)
    track_points = _fetch_track_points(route_id)
    validation: dict[str, Any] = {
        "route_id": route_id,
        "route_name": route.get("name"),
        "route_url": route.get("html_url") or route.get("url") or f"https://ridewithgps.com/routes/{route_id}",
        "distance": route.get("distance_km"),
        "track_points": len(track_points),
        "points_of_interest_count": len(_route_points_of_interest(route)),
        "points_of_interest_names": _route_poi_names(route),
        "source_gpx_waypoint_names": _gpx_waypoint_names(gpx_path),
    }

    export_result = export_route_to_artifact(route_id, fmt="gpx", return_mode="metadata")
    validation["export_status"] = export_result.get("status")
    export_path = export_result.get("artifact_path")
    validation["export_path"] = export_path

    if export_path:
        export_file = Path(str(export_path))
        if export_file.exists():
            text = export_file.read_text(encoding="utf-8")
            validation["export_trkpt"] = text.count("<trkpt ")
            validation["export_wpt"] = text.count("<wpt ")

    distance_value = validation.get("distance")
    try:
        distance_numeric = float(distance_value) if distance_value is not None else 0.0
    except (TypeError, ValueError):
        distance_numeric = 0.0

    source_waypoints = validation["source_gpx_waypoint_names"]
    poi_names = validation["points_of_interest_names"]
    validation["distance_gt_0"] = distance_numeric > 0
    validation["track_points_gt_0"] = validation["track_points"] > 0
    validation["source_waypoints_present"] = all(name in poi_names for name in source_waypoints)
    validation["validation_ok"] = (
        validation["distance_gt_0"]
        and validation["track_points_gt_0"]
        and validation["source_waypoints_present"]
    )
    return validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpx", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--description", default=None)
    parser.add_argument("--privacy", default=None)
    args = parser.parse_args()

    gpx_path = Path(args.gpx)
    if not gpx_path.exists():
        _print_json({"ok": False, "status": "NOT_FOUND", "path": str(gpx_path)})
        return 2

    stats = _count_gpx_stats(gpx_path)
    waypoint_names = _gpx_waypoint_names(gpx_path)
    _print_json(
        {
            "gpx": str(gpx_path),
            "stats": stats,
            "wpt_names": waypoint_names,
        }
    )

    upload_started_at = datetime.now(timezone.utc)

    from tools.rwgps.client import import_route_via_trips_upload_gpx, list_routes

    result = import_route_via_trips_upload_gpx(
        gpx_path,
        name=args.name,
        description=args.description,
        privacy=args.privacy,
    )
    _print_json(
        {
            key: result.get(key)
            for key in (
                "ok",
                "status",
                "task_id",
                "response_status",
                "response_content_type",
                "response_location",
                "response_body_preview",
                "response_json_keys",
                "response_fields",
                "endpoint",
                "method",
                "content_type",
                "multipart",
                "auth_mode",
                "missing_auth_requirement",
                "required_auth_env",
            )
            if key in result
        }
    )

    if result.get("status") == "RWGPS_WEB_UPLOAD_REQUIRES_SESSION_COOKIE":
        return 0

    routes_result = list_routes(limit=100, offset=0, sort="created_at", order="desc")
    routes = list(routes_result.get("routes") or [])
    recent_routes = []
    for route in routes:
        created_at = _parse_iso8601(str(route.get("created_at") or ""))
        if created_at is not None and created_at >= upload_started_at:
            recent_routes.append(route)
    _print_route_table(recent_routes[:10])

    candidate = _find_recent_route(recent_routes, upload_started_at)
    if not candidate:
        _print_json({"ok": False, "status": "TASK_ACCEPTED_ROUTE_NOT_FOUND_YET"})
        return 0

    route_id = str(candidate.get("id"))
    validation: dict[str, Any] | None = None
    route_url = candidate.get("url") or candidate.get("html_url") or f"https://ridewithgps.com/routes/{route_id}"
    try:
        validation = _validate_route(route_id, gpx_path)
    except Exception as exc:
        _print_json(
            {
                "ok": False,
                "status": "UPLOAD_SENT_VISUAL_CHECK_REQUIRED",
                "route_id": route_id,
                "route_url": route_url,
                "error": str(exc),
            }
        )
        return 0

    if validation.get("validation_ok"):
        _print_json(
            {
                "ok": True,
                "status": "NEW_GPX_WPT_IMPORTED_AS_RWGPS_POI",
                "route_id": route_id,
                "route_url": route_url,
                "poi_names": validation.get("points_of_interest_names"),
                "validation": {
                    "distance_gt_0": validation.get("distance_gt_0"),
                    "track_points_gt_0": validation.get("track_points_gt_0"),
                    "source_waypoints_present": validation.get("source_waypoints_present"),
                    "export_trkpt": validation.get("export_trkpt"),
                    "export_wpt": validation.get("export_wpt"),
                },
            }
        )
    else:
        _print_json(
            {
                "ok": False,
                "status": "RWGPS_IMPORTED_ONLY_FIRST_5_WPT_OR_FILTERED_NEW_WPT",
                "route_id": route_id,
                "route_url": route_url,
                "poi_names": validation.get("points_of_interest_names"),
                "source_waypoint_names": validation.get("source_gpx_waypoint_names"),
                "validation": {
                    "distance_gt_0": validation.get("distance_gt_0"),
                    "track_points_gt_0": validation.get("track_points_gt_0"),
                    "source_waypoints_present": validation.get("source_waypoints_present"),
                    "export_trkpt": validation.get("export_trkpt"),
                    "export_wpt": validation.get("export_wpt"),
                },
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
