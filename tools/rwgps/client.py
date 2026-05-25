from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import httpx

import db
from qbot_config import APP_DIR, env, env_float


RWGPS_TIMEOUT_SEC = env_float("RWGPS_TIMEOUT_SEC", 20.0)
RWGPS_API_BASE = (env("RWGPS_API_BASE", "https://ridewithgps.com") or "https://ridewithgps.com").rstrip("/")
RWGPS_AUTH_TOKEN = env("RWGPS_AUTH_TOKEN", "").strip() or None
RWGPS_API_KEY = env("RWGPS_API_KEY", "").strip() or None
RWGPS_USER_ID = env("RWGPS_USER_ID", "").strip() or None
RWGPS_PLANNED_COLLECTION_ID = env("RWGPS_PLANNED_COLLECTION_ID", "").strip() or None

# TODO: verify these RWGPS endpoint templates against the account/API variant in use.
RWGPS_ROUTES_PATH = env("RWGPS_ROUTES_PATH", "/api/v1/routes.json")
RWGPS_ROUTE_PATH = env("RWGPS_ROUTE_PATH", "/api/v1/routes/{route_id}.json")
RWGPS_COLLECTIONS_PATH = env("RWGPS_COLLECTIONS_PATH", "/api/v1/collections.json")
RWGPS_COLLECTION_ROUTES_PATH = env("RWGPS_COLLECTION_ROUTES_PATH", "/api/v1/collections/{collection_id}.json")

RWGPS_MANIFEST_PATH = Path(env("RWGPS_MANIFEST_PATH", str(APP_DIR / "data/routes/rwgps_manifest.json")))
RWGPS_ROUTE_CACHE_PATH = Path(env("RWGPS_ROUTE_CACHE_PATH", str(APP_DIR / "data/routes/rwgps_route_cache.json")))

ARTIFACT_RWGPS_EXPORT_DIR = Path("/opt/qbot/artifacts/exports/rwgps")
ARTIFACT_RWGPS_RELATIVE_PREFIX = "exports/rwgps"
ALLOWED_EXPORT_FORMATS = frozenset({"gpx", "tcx", "json"})


@dataclass
class RWGPSError(Exception):
    kind: str
    message: str
    status_code: int | None = None
    url: str | None = None
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


def _integration_hint() -> str:
    return "Set RWGPS_AUTH_TOKEN and RWGPS_USER_ID in environment/.env and restart q-bot.service"


def _fallback_warning(remote_error: str | None = None) -> str:
    if remote_error:
        return f"RWGPS remote lookup failed; returning local_manifest fallback ({remote_error})"
    return "RWGPS not configured; returning local_manifest fallback"


def _route_origin_for_source(source: str) -> str:
    if source == "cache":
        return "rwgps_api"
    return source


def _missing_required_env() -> list[str]:
    missing: list[str] = []
    if not RWGPS_AUTH_TOKEN:
        missing.append("RWGPS_AUTH_TOKEN")
    if not RWGPS_USER_ID:
        missing.append("RWGPS_USER_ID")
    return missing


def _has_route_payload_capabilities() -> dict[str, bool]:
    configured = not _missing_required_env()
    return {
        "configured": configured,
        "has_api_key": bool(RWGPS_API_KEY),
        "has_auth_token": bool(RWGPS_AUTH_TOKEN),
        "has_user_id": bool(RWGPS_USER_ID),
        "has_planned_collection_id": bool(RWGPS_PLANNED_COLLECTION_ID),
        "can_list_routes": configured,
        "can_get_route": configured,
        "can_list_collections": configured,
        "can_get_planned_collection": configured and bool(RWGPS_PLANNED_COLLECTION_ID),
        "can_get_geometry": True,
        "can_get_cue_sheet": True,
        "can_export_gpx": True,
        "can_export_tcx": True,
        "can_export_fit": False,
    }


def _integration_status() -> dict[str, Any]:
    missing = _missing_required_env()
    return {
        "configured": not missing,
        "missing": missing,
        "hint": _integration_hint(),
        "api_base": RWGPS_API_BASE,
        "has_api_key": bool(RWGPS_API_KEY),
        "has_auth_token": bool(RWGPS_AUTH_TOKEN),
        "has_user_id": bool(RWGPS_USER_ID),
        "has_planned_collection_id": bool(RWGPS_PLANNED_COLLECTION_ID),
        "planned_collection_id": RWGPS_PLANNED_COLLECTION_ID,
        "capabilities": _has_route_payload_capabilities(),
    }


def _integration_payload(
    source: str,
    *,
    remote_error: str | None = None,
    missing_features: list[str] | None = None,
    warning: str | None = None,
) -> dict[str, Any]:
    integration = _integration_status()
    integration["source"] = source
    if source == "local_manifest":
        integration["mode"] = "fallback"
        integration["warning"] = warning or _fallback_warning(remote_error)
    elif source == "cache":
        integration["mode"] = "cache"
        integration["warning"] = warning or _fallback_warning(remote_error)
    else:
        integration["mode"] = "rwgps_api"
        if remote_error:
            integration["remote_error"] = remote_error
    if missing_features:
        integration["missing_features"] = missing_features
    if warning and source == "rwgps_api":
        integration["warning"] = warning
    elif remote_error and source == "rwgps_api":
        integration["remote_error"] = remote_error
    return integration


def _error_payload(
    message: str,
    *,
    source: str = "fallback",
    missing: list[str] | None = None,
    details: Any | None = None,
) -> dict[str, Any]:
    payload = {
        "ok": False,
        "source": source,
        "origin": _route_origin_for_source(source),
        "error": message,
    }
    if missing:
        payload["missing"] = missing
        payload["hint"] = _integration_hint()
    if details is not None:
        payload["details"] = details
    return payload


def _remote_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if RWGPS_AUTH_TOKEN:
        headers["x-rwgps-auth-token"] = RWGPS_AUTH_TOKEN
    if RWGPS_API_KEY:
        headers["x-rwgps-api-key"] = RWGPS_API_KEY
    return headers


def _routes_path() -> str:
    return RWGPS_ROUTES_PATH.format(user_id=RWGPS_USER_ID or "")


def _route_path(route_id: str) -> str:
    return RWGPS_ROUTE_PATH.format(route_id=route_id, user_id=RWGPS_USER_ID or "")


def _collections_path() -> str:
    return RWGPS_COLLECTIONS_PATH.format(user_id=RWGPS_USER_ID or "")


def _collection_routes_path(collection_id: str) -> str:
    return RWGPS_COLLECTION_ROUTES_PATH.format(collection_id=collection_id, user_id=RWGPS_USER_ID or "")


def _request_json(path: str, params: dict[str, Any] | None = None) -> Any:
    if _missing_required_env():
        raise RWGPSError("not_configured", "RWGPS integration not configured")

    url = f"{RWGPS_API_BASE}{path}"
    try:
        with httpx.Client(timeout=RWGPS_TIMEOUT_SEC) as client:
            response = client.get(url, headers=_remote_headers(), params={k: v for k, v in (params or {}).items() if v is not None})
    except httpx.TimeoutException as exc:
        raise RWGPSError("timeout", "RWGPS request timed out", url=url) from exc
    except httpx.RequestError as exc:
        raise RWGPSError("network_error", f"RWGPS network error: {exc.__class__.__name__}", url=url) from exc

    if response.status_code in (401, 403):
        raise RWGPSError("auth_error", f"RWGPS auth failed (HTTP {response.status_code})", status_code=response.status_code, url=url)
    if response.status_code == 404:
        raise RWGPSError("not_found", "RWGPS resource not found", status_code=response.status_code, url=url)
    if response.status_code == 429:
        raise RWGPSError("rate_limited", "RWGPS rate limited (HTTP 429)", status_code=response.status_code, url=url)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:400]
        raise RWGPSError("http_error", f"RWGPS API error (HTTP {response.status_code})", status_code=response.status_code, url=url, details={"body": body}) from exc
    try:
        return response.json()
    except ValueError as exc:
        raise RWGPSError("malformed_response", "RWGPS returned invalid JSON", url=url) from exc


def _extract_items(payload: Any, item_keys: tuple[str, ...] = ("routes", "collections", "items", "results", "data")) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in item_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = value.get("items") or value.get("routes") or value.get("results") or value.get("data")
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
    return []


def _distance_km(route: dict[str, Any]) -> float | None:
    if route.get("distance_km") is not None:
        try:
            return round(float(route["distance_km"]), 3)
        except (TypeError, ValueError):
            return None
    if route.get("distance") is not None:
        try:
            return round(float(route["distance"]) / 1000.0, 3)
        except (TypeError, ValueError):
            return None
    return None


def _route_object(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        route = payload.get("route")
        if isinstance(route, dict):
            return route
        return payload
    return None


def _route_summary(route: dict[str, Any]) -> dict[str, Any]:
    source = route.get("source", "rwgps_api")
    description = route.get("description") if route.get("description") is not None else route.get("notes")
    return {
        "id": route.get("id"),
        "name": route.get("name"),
        "description": description,
        "distance_km": _distance_km(route),
        "elevation_m": route.get("elevation_m") or route.get("elevation_gain"),
        "created_at": route.get("created_at"),
        "updated_at": route.get("updated_at"),
        "locality": route.get("locality"),
        "region": route.get("region"),
        "country": route.get("country") or route.get("country_code"),
        "url": route.get("url"),
        "privacy": route.get("privacy") or route.get("visibility") or route.get("status"),
        "status": route.get("status"),
        "source": source,
        "origin": source,
    }


def _normalize_collection(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    collection = dict(item)
    collection.setdefault("source", source)
    collection.setdefault("origin", source)
    return collection


def _route_export_links_from_route(route: dict[str, Any]) -> dict[str, Any]:
    origin = route.get("origin") or _route_origin_for_source(route.get("source", "rwgps_api"))
    gpx_url = route.get("gpx_url") or route.get("gpxUrl")
    tcx_url = route.get("tcx_url") or route.get("tcxUrl")
    fit_url = route.get("fit_url") or route.get("fitUrl")
    download_capabilities = {
        "gpx": {
            "available": bool(route.get("track_points")),
            "source": "built_from_track_points" if route.get("track_points") else None,
            "reason": None if route.get("track_points") else "track_points are not available",
        },
        "tcx": {
            "available": bool(route.get("track_points")),
            "source": "built_from_track_points" if route.get("track_points") else None,
            "reason": None if route.get("track_points") else "track_points are not available",
        },
        "fit": {
            "available": False,
            "source": "unsupported",
            "reason": "RWGPS FIT export is not exposed by the current client; binary FIT build is not implemented",
        },
    }
    missing_features = []
    if not gpx_url:
        missing_features.append("gpx_url")
    if not tcx_url:
        missing_features.append("tcx_url")
    if not fit_url:
        missing_features.append("fit_url")
    if not route.get("track_points"):
        missing_features.append("track_points")
    return {
        "gpx_url": gpx_url,
        "tcx_url": tcx_url,
        "fit_url": fit_url,
        "source": route.get("source", "rwgps_api"),
        "origin": origin,
        "download": download_capabilities,
        "missing_features": missing_features,
    }


def _route_geometry_from_route(route: dict[str, Any]) -> dict[str, Any]:
    origin = route.get("origin") or _route_origin_for_source(route.get("source", "rwgps_api"))
    track_points = [item for item in (route.get("track_points") or []) if isinstance(item, dict)]
    coords: list[list[float]] = []
    elevations: list[float] = []
    for point in track_points:
        x = point.get("x")
        y = point.get("y")
        if x is None or y is None:
            continue
        coord = [float(x), float(y)]
        if point.get("e") is not None:
            coord.append(float(point["e"]))
            elevations.append(float(point["e"]))
        coords.append(coord)
    if not coords:
        return {
            "available": False,
            "source": route.get("source", "rwgps_api"),
            "origin": origin,
            "format": None,
            "reason": "track_points are not available",
            "geojson": None,
            "point_count": 0,
            "missing_features": ["geometry"],
        }
    bounds = {
        "sw_lat": route.get("sw_lat"),
        "sw_lng": route.get("sw_lng"),
        "ne_lat": route.get("ne_lat"),
        "ne_lng": route.get("ne_lng"),
        "first_lat": route.get("first_lat"),
        "first_lng": route.get("first_lng"),
        "last_lat": route.get("last_lat"),
        "last_lng": route.get("last_lng"),
    }
    return {
        "available": True,
        "source": route.get("source", "rwgps_api"),
        "origin": origin,
        "format": "geojson",
        "point_count": len(coords),
        "distance_km": round(float(route.get("distance_km") or (route.get("distance") or 0) / 1000.0), 3) if route.get("distance_km") or route.get("distance") else None,
        "elevation_m": route.get("elevation_m") or route.get("elevation_gain"),
        "bounds": bounds,
        "geojson": {
            "type": "LineString",
            "coordinates": coords,
        },
        "samples": {
            "first": coords[0],
            "last": coords[-1],
        },
        "elevation_sample_count": len(elevations),
    }


def _route_cue_sheet_from_route(route: dict[str, Any]) -> dict[str, Any]:
    origin = route.get("origin") or _route_origin_for_source(route.get("source", "rwgps_api"))
    course_points = [item for item in (route.get("course_points") or []) if isinstance(item, dict)]
    if not course_points:
        return {
            "available": False,
            "source": route.get("source", "rwgps_api"),
            "origin": origin,
            "reason": "course_points are not available",
            "items": [],
            "count": 0,
            "missing_features": ["cue_sheet"],
        }
    items = []
    for point in course_points:
        items.append({
            "index": point.get("i"),
            "type": point.get("t"),
            "name": point.get("n"),
            "distance_km": round(float(point["d"]) / 1000.0, 3) if point.get("d") is not None else None,
            "location": {
                "lat": point.get("y"),
                "lng": point.get("x"),
            },
            "raw": {
                "d": point.get("d"),
                "i": point.get("i"),
                "t": point.get("t"),
                "n": point.get("n"),
            },
        })
    return {
        "available": True,
        "source": route.get("source", "rwgps_api"),
        "origin": origin,
        "count": len(items),
        "items": items,
    }


def _route_raw_meta(route: dict[str, Any], *, source: str, cache_hit: bool = False, cached_at: str | None = None) -> dict[str, Any]:
    origin = _route_origin_for_source(source)
    collections = [item for item in (route.get("collections") or []) if isinstance(item, dict)]
    points_of_interest = [item for item in (route.get("points_of_interest") or []) if isinstance(item, dict)]
    course_points = [item for item in (route.get("course_points") or []) if isinstance(item, dict)]
    track_points = [item for item in (route.get("track_points") or []) if isinstance(item, dict)]
    return {
        "source": source,
        "origin": origin,
        "cache_hit": cache_hit,
        "cached_at": cached_at,
        "route_keys": sorted(route.keys()),
        "counts": {
            "track_points": len(track_points),
            "course_points": len(course_points),
            "points_of_interest": len(points_of_interest),
            "collections": len(collections),
            "photos": len([item for item in (route.get("photos") or []) if isinstance(item, dict)]),
        },
        "activity_types": [str(item) for item in (route.get("activity_types") or []) if item is not None],
    }


def _cache_path() -> Path:
    return RWGPS_ROUTE_CACHE_PATH


def _load_route_cache() -> dict[str, Any]:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_route_cache(route_id: str, route: dict[str, Any]) -> None:
    path = _cache_path()
    cache = _load_route_cache()
    cache[str(route_id)] = {
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "route": route,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _get_cached_route(route_id: str) -> dict[str, Any] | None:
    entry = _load_route_cache().get(str(route_id))
    if isinstance(entry, dict) and isinstance(entry.get("route"), dict):
        return entry
    return None


def _build_route_detail(
    route: dict[str, Any],
    *,
    source: str,
    cached_at: str | None = None,
    cache_hit: bool = False,
    remote_error: str | None = None,
) -> dict[str, Any]:
    route_view = dict(route)
    route_view.setdefault("source", source)
    route_origin = _route_origin_for_source(source)
    route_view.setdefault("origin", route_origin)
    geometry = _route_geometry_from_route(route_view)
    cue_sheet = _route_cue_sheet_from_route(route_view)
    export_links = _route_export_links_from_route(route_view)
    missing_features = sorted(set(export_links.get("missing_features", [])) | set(geometry.get("missing_features", [])) | set(cue_sheet.get("missing_features", [])))
    warnings = []
    if remote_error:
        warnings.append(remote_error)
    if not geometry.get("available"):
        warnings.append(geometry.get("reason", "geometry unavailable"))
    if not cue_sheet.get("available"):
        warnings.append(cue_sheet.get("reason", "cue sheet unavailable"))
    if export_links.get("missing_features"):
        warnings.append("direct export links are not exposed by this RWGPS response")

    detail = {
        "id": route_view.get("id"),
        "name": route_view.get("name"),
        "description": route_view.get("description") if route_view.get("description") is not None else route_view.get("notes"),
        "distance_km": _distance_km(route_view),
        "elevation_m": route_view.get("elevation_m") or route_view.get("elevation_gain"),
        "created_at": route_view.get("created_at"),
        "updated_at": route_view.get("updated_at"),
        "locality": route_view.get("locality"),
        "region": route_view.get("region") or route_view.get("administrative_area"),
        "country": route_view.get("country") or route_view.get("country_code"),
        "url": route_view.get("url"),
        "html_url": route_view.get("html_url"),
        "privacy": route_view.get("privacy") or route_view.get("visibility") or route_view.get("status"),
        "status": route_view.get("status"),
        "surface": route_view.get("surface"),
        "terrain": route_view.get("terrain"),
        "difficulty": route_view.get("difficulty"),
        "track_type": route_view.get("track_type"),
        "unpaved_pct": route_view.get("unpaved_pct"),
        "source": source,
        "origin": route_origin,
        "geometry": geometry,
        "cue_sheet": cue_sheet,
        "gpx_url": export_links.get("gpx_url"),
        "tcx_url": export_links.get("tcx_url"),
        "fit_url": export_links.get("fit_url"),
        "export_links": export_links,
        "tags": [str(tag) for tag in (route_view.get("tags") or []) if tag is not None],
        "collections": route_view.get("collections") or [],
        "points_of_interest": route_view.get("points_of_interest") or [],
        "course_points": route_view.get("course_points") or [],
        "activity_types": [str(item) for item in (route_view.get("activity_types") or []) if item is not None],
        "raw": _route_raw_meta(route_view, source=source, cache_hit=cache_hit, cached_at=cached_at),
        "meta": {
            "cache_hit": cache_hit,
            "cached_at": cached_at,
            "source": source,
            "origin": route_origin,
        },
        "warnings": [warning for warning in warnings if warning],
        "missing_features": missing_features,
    }
    return detail


def _normalize_route(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    route = item.get("route") if isinstance(item.get("route"), dict) else item
    normalized = {
        "id": route.get("id") or route.get("route_id") or route.get("routeId"),
        "name": route.get("name") or route.get("title"),
        "description": route.get("description") if route.get("description") is not None else route.get("notes"),
        "distance_km": _distance_km(route),
        "elevation_m": route.get("elevation_m") or route.get("elevation") or route.get("elevation_gain"),
        "created_at": route.get("created_at") or route.get("createdAt"),
        "updated_at": route.get("updated_at") or route.get("updatedAt") or route.get("modified_at"),
        "locality": route.get("locality") or route.get("city"),
        "region": route.get("region") or route.get("state") or route.get("province") or route.get("administrative_area"),
        "country": route.get("country") or route.get("country_code"),
        "url": route.get("url") or route.get("route_url"),
        "privacy": route.get("privacy") or route.get("visibility") or route.get("status"),
        "status": route.get("status"),
        "geometry": route.get("geometry") or route.get("polyline") or route.get("track"),
        "cue_sheet": route.get("cue_sheet") or route.get("cueSheet") or route.get("cue_sheet_url"),
        "gpx_url": route.get("gpx_url") or route.get("gpxUrl"),
        "tcx_url": route.get("tcx_url") or route.get("tcxUrl"),
        "fit_url": route.get("fit_url") or route.get("fitUrl"),
        "tags": route.get("tags") or [],
        "collections": route.get("collections") or [],
        "event": route.get("event") or route.get("event_kind"),
        "source": route.get("source", "rwgps_api"),
        "origin": route.get("source", "rwgps_api"),
    }
    if normalized["id"] is None:
        return None
    return normalized


def _seed_manifest_from_trips() -> dict[str, Any]:
    trips = db.get_trips(status="planned") or []
    routes: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for trip in trips:
        route_id = f"local-trip-{trip.get('id')}"
        route = {
            "id": route_id,
            "name": trip.get("name"),
            "description": trip.get("notes"),
            "notes": trip.get("notes"),
            "distance_km": trip.get("distance_km"),
            "elevation_m": trip.get("elevation_m"),
            "created_at": trip.get("created_at"),
            "updated_at": trip.get("created_at"),
            "locality": None,
            "region": None,
            "country": trip.get("country"),
            "url": None,
            "privacy": "local_manifest",
            "status": trip.get("status") or "planned",
            "source": "local_manifest",
            "origin": "local_manifest",
            "source_system": "garage.trips",
            "source_trip_id": trip.get("id"),
            "collections": [{"id": "planned", "name": "Planned routes"}],
            "event": {
                "kind": trip.get("event_kind"),
                "start_date": trip.get("start_date"),
                "end_date": trip.get("end_date"),
            },
        }
        routes.append(route)
        events.append(
            {
                "id": f"event-{route_id}",
                "route_id": route_id,
                "name": trip.get("name"),
                "start_date": trip.get("start_date"),
                "end_date": trip.get("end_date"),
                "kind": trip.get("event_kind"),
                "status": trip.get("status"),
            }
        )

    manifest = {
        "routes": routes,
        "collections": [
            {
                "id": "planned",
                "name": "Planned routes",
                "route_count": len(routes),
                "source": "local_manifest",
                "origin": "local_manifest",
            }
        ],
        "events": events,
        "metadata": {
            "source": "garage.trips",
            "generated_at": None,
        },
    }
    RWGPS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    RWGPS_MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def load_manifest() -> dict[str, Any]:
    if not RWGPS_MANIFEST_PATH.exists():
        return _seed_manifest_from_trips()
    try:
        data = json.loads(RWGPS_MANIFEST_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("manifest is not a dict")
    except Exception:
        return _seed_manifest_from_trips()

    data.setdefault("routes", [])
    data.setdefault("collections", [])
    data.setdefault("events", [])
    data.setdefault("metadata", {})
    return data


def _manifest_routes() -> list[dict[str, Any]]:
    manifest = load_manifest()
    routes = []
    for item in manifest.get("routes", []):
        normalized = _normalize_route(item)
        if normalized:
            routes.append(normalized)
    return routes


def _filter_routes(routes: list[dict[str, Any]], search: str | None = None) -> list[dict[str, Any]]:
    if not search:
        return routes
    needle = search.strip().lower()
    if not needle:
        return routes

    def hay(route: dict[str, Any]) -> str:
        parts = [
            route.get("id"),
            route.get("name"),
            route.get("description"),
            route.get("locality"),
            route.get("region"),
            route.get("country"),
            route.get("privacy"),
            route.get("status"),
        ]
        return " ".join(str(part) for part in parts if part is not None).lower()

    return [route for route in routes if needle in hay(route)]


def _sort_routes(routes: list[dict[str, Any]], sort: str, order: str) -> list[dict[str, Any]]:
    reverse = (order or "desc").lower() != "asc"
    key_name = sort if sort in {"updated_at", "created_at", "name"} else "updated_at"

    def sort_key(route: dict[str, Any]) -> Any:
        value = route.get(key_name)
        return value or ""

    return sorted(routes, key=sort_key, reverse=reverse)


def _paginate(routes: list[dict[str, Any]], limit: int, offset: int) -> list[dict[str, Any]]:
    start = max(0, offset)
    stop = start + max(0, limit)
    return routes[start:stop]


def list_routes(
    limit: int = 20,
    offset: int = 0,
    sort: str = "updated_at",
    order: str = "desc",
    search: str | None = None,
) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    remote_error: str | None = None
    used_manifest = False
    if not _missing_required_env():
        try:
            remote_payload = _request_json(
                _routes_path(),
                params={
                    "limit": limit,
                    "offset": offset,
                    "sort": sort,
                    "order": order,
                    "search": search,
                },
            )
            for item in _extract_items(remote_payload):
                normalized = _normalize_route(item)
                if normalized:
                    routes.append(normalized)
        except Exception as exc:
            remote_error = str(exc)

    if not routes and (remote_error or _missing_required_env()):
        routes = _manifest_routes()
        used_manifest = True
    routes = _filter_routes(routes, search=search)
    routes = _sort_routes(routes, sort=sort, order=order)
    selected = _paginate(routes, limit=limit, offset=offset)

    if not selected and not routes and _missing_required_env():
        return _error_payload(
            "RWGPS integration not configured",
            missing=_missing_required_env(),
        )

    source = "local_manifest" if used_manifest else "rwgps_api"

    return {
        "ok": True,
        "source": source,
        "origin": source,
        "integration": _integration_payload(source, remote_error=remote_error if used_manifest else None),
        "count": len(selected),
        "total": len(routes),
        "limit": limit,
        "offset": offset,
        "sort": sort,
        "order": order,
        "search": search,
        "routes": [_route_summary(route) for route in selected],
    }


def _resolve_route_record(route_id: str | int) -> dict[str, Any]:
    route_id_str = str(route_id)
    remote_error: str | None = None

    if not _missing_required_env():
        try:
            remote_payload = _request_json(_route_path(route_id_str))
            route = _route_object(remote_payload)
            if not route:
                raise RWGPSError("malformed_response", "RWGPS route payload missing route object", details={"route_id": route_id_str})
            _save_route_cache(route_id_str, route)
            return {
                "source": "rwgps_api",
                "route": route,
                "cache_hit": False,
                "cached_at": None,
                "warning": None,
                "remote_error": None,
            }
        except RWGPSError as exc:
            remote_error = exc.message
            if exc.kind in {"timeout", "network_error", "rate_limited", "malformed_response", "http_error"}:
                cached = _get_cached_route(route_id_str)
                if cached:
                    return {
                        "source": "cache",
                        "route": cached["route"],
                        "cache_hit": True,
                        "cached_at": cached.get("cached_at"),
                        "warning": exc.message,
                        "remote_error": exc.message,
                    }
    else:
        remote_error = "RWGPS integration not configured"

    for route in _manifest_routes():
        if str(route.get("id")) == route_id_str or str(route.get("source_trip_id")) == route_id_str:
            return {
                "source": "local_manifest",
                "route": route,
                "cache_hit": False,
                "cached_at": None,
                "warning": remote_error,
                "remote_error": remote_error,
            }

    return {
        "source": "fallback",
        "route": None,
        "cache_hit": False,
        "cached_at": None,
        "warning": remote_error or "Route not found",
        "remote_error": remote_error,
    }


def get_route(route_id: str | int) -> dict[str, Any]:
    route_id_str = str(route_id)
    resolved = _resolve_route_record(route_id_str)
    route = resolved.get("route")
    if not isinstance(route, dict):
        if _missing_required_env() and not _manifest_routes():
            return _error_payload(
                "RWGPS integration not configured",
                source="fallback",
                missing=_missing_required_env(),
            )
        warning = resolved.get("warning") or "Route not found"
        if warning == "Route not found" or resolved.get("source") == "fallback":
            return _error_payload(
                warning,
                source="fallback",
                details={"route_id": route_id_str, "remote_error": resolved.get("remote_error")},
            )
        return _error_payload(
            warning,
            source="fallback",
            details={"route_id": route_id_str, "remote_error": resolved.get("remote_error")},
        )

    source = resolved["source"]
    detail = _build_route_detail(
        route,
        source=source,
        cached_at=resolved.get("cached_at"),
        cache_hit=bool(resolved.get("cache_hit")),
        remote_error=resolved.get("warning"),
    )
    route_origin = detail.get("origin") or _route_origin_for_source(source)
    return {
        "ok": True,
        "source": source,
        "origin": route_origin,
        "integration": _integration_payload(
            source,
            remote_error=resolved.get("remote_error") if source == "cache" else None,
            warning=resolved.get("warning") if source == "cache" else None,
            missing_features=detail.get("missing_features"),
        ),
        "route": detail,
    }


def list_collections() -> dict[str, Any]:
    collections: list[dict[str, Any]] = []
    remote_error: str | None = None
    used_manifest = False
    if not _missing_required_env():
        try:
            remote_payload = _request_json(_collections_path())
            collections = _extract_items(remote_payload, item_keys=("collections", "items", "results", "data"))
        except Exception as exc:
            remote_error = str(exc)

    if not collections and (remote_error or _missing_required_env()):
        manifest = load_manifest()
        collections = [item for item in manifest.get("collections", []) if isinstance(item, dict)]
        used_manifest = True
    if not collections:
        collections = [
            {
                "id": "planned",
                "name": "Planned routes",
                "route_count": len([route for route in _manifest_routes() if route.get("status") == "planned"]),
                "source": "local_manifest",
                "origin": "local_manifest",
            }
    ]

    source = "local_manifest" if used_manifest else "rwgps_api"
    payload = {
        "ok": True,
        "source": source,
        "origin": source,
        "integration": _integration_payload(source, remote_error=remote_error if used_manifest else None),
        "count": len(collections),
        "collections": [_normalize_collection(item, source=source) for item in collections],
    }
    return payload


def list_planned_routes(limit: int = 4) -> dict[str, Any]:
    manifest_routes = _manifest_routes()
    collection_id = RWGPS_PLANNED_COLLECTION_ID
    planned_strategy = "remote_recent_routes"
    planned: list[dict[str, Any]] = []
    remote_error: str | None = None
    used_manifest = False

    if not _missing_required_env():
        try:
            if collection_id:
                remote_payload = _request_json(_collection_routes_path(collection_id), params={"include": "routes"})
                planned = []
                for item in _extract_items(remote_payload):
                    normalized = _normalize_route(item)
                    if normalized:
                        planned.append(normalized)
                if planned:
                    planned_strategy = "remote_collection"
            if not planned:
                remote_payload = _request_json(_routes_path(), params={"limit": limit, "sort": "updated_at", "order": "desc"})
                for item in _extract_items(remote_payload):
                    normalized = _normalize_route(item)
                    if normalized:
                        planned.append(normalized)
                if planned:
                    planned_strategy = "remote_recent_routes"
        except Exception as exc:
            remote_error = str(exc)

    if not planned and (remote_error or _missing_required_env()):
        used_manifest = True
        if collection_id:
            planned = [
                route
                for route in manifest_routes
                if any(
                    isinstance(item, dict) and str(item.get("id")) == collection_id
                    for item in (route.get("collections") or [])
                )
            ]
            if planned:
                planned_strategy = "local_manifest_collection"
        if not planned:
            planned = [route for route in manifest_routes if route.get("status") == "planned"]
            if planned:
                planned_strategy = "local_manifest_planned"
        if not planned:
            planned = manifest_routes
            if planned:
                planned_strategy = "local_manifest_all"

    planned = _sort_routes(planned, sort="updated_at", order="desc")
    planned = _paginate(planned, limit=limit, offset=0)

    if not planned and _missing_required_env() and not manifest_routes:
        return _error_payload(
            "RWGPS integration not configured",
            missing=_missing_required_env(),
        )

    source = "local_manifest" if used_manifest else "rwgps_api"

    return {
        "ok": True,
        "source": source,
        "origin": source,
        "integration": _integration_payload(source, remote_error=remote_error if used_manifest else None),
        "planned_strategy": planned_strategy,
        "count": len(planned),
        "limit": limit,
        "routes": [_route_summary(route) for route in planned],
    }


def planned_route_ids(limit: int = 4) -> list[str]:
    result = list_planned_routes(limit=limit)
    if not result.get("ok"):
        return []
    return [str(route.get("id")) for route in result.get("routes", []) if route.get("id") is not None]


def get_route_export_links(route_id: str | int) -> dict[str, Any]:
    resolved = _resolve_route_record(route_id)
    route = resolved.get("route")
    if not isinstance(route, dict):
        source = resolved.get("source", "fallback")
        return {
            "ok": False,
            "source": source,
            "origin": _route_origin_for_source(source),
            "route_id": str(route_id),
            "integration": _integration_payload(source, warning=resolved.get("warning")),
            "missing_features": ["route"],
            "warning": resolved.get("warning"),
        }
    source = resolved["source"]
    route_view = dict(route)
    route_view.setdefault("source", source)
    route_view.setdefault("origin", _route_origin_for_source(source))
    links = _route_export_links_from_route(route_view)
    return {
        "ok": True,
        "source": source,
        "origin": route_view.get("origin"),
        "route_id": str(route_id),
        "integration": _integration_payload(
            source,
            warning=resolved.get("warning") if source == "cache" else None,
            missing_features=links.get("missing_features"),
        ),
        "export_links": links,
        "missing_features": links.get("missing_features", []),
        "warning": resolved.get("warning") if source == "cache" else None,
    }


def get_route_geometry(route_id: str | int) -> dict[str, Any]:
    resolved = _resolve_route_record(route_id)
    route = resolved.get("route")
    source = resolved.get("source", "fallback")
    if not isinstance(route, dict):
        return {
            "ok": False,
            "source": source,
            "origin": _route_origin_for_source(source),
            "route_id": str(route_id),
            "integration": _integration_payload(source, warning=resolved.get("warning")),
            "geometry": None,
            "missing_features": ["geometry"],
            "warning": resolved.get("warning"),
        }
    route_view = dict(route)
    route_view.setdefault("source", source)
    route_view.setdefault("origin", _route_origin_for_source(source))
    geometry = _route_geometry_from_route(route_view)
    return {
        "ok": geometry.get("available", False),
        "source": source,
        "origin": route_view.get("origin"),
        "route_id": str(route_id),
        "integration": _integration_payload(
            source,
            warning=resolved.get("warning") if source == "cache" else None,
            missing_features=geometry.get("missing_features"),
        ),
        "geometry": geometry if geometry.get("available") else None,
        "geometry_detail": geometry,
        "missing_features": geometry.get("missing_features", []),
        "warning": resolved.get("warning") if source == "cache" else geometry.get("reason"),
    }


def get_route_cue_sheet(route_id: str | int) -> dict[str, Any]:
    resolved = _resolve_route_record(route_id)
    route = resolved.get("route")
    source = resolved.get("source", "fallback")
    if not isinstance(route, dict):
        return {
            "ok": False,
            "source": source,
            "origin": _route_origin_for_source(source),
            "route_id": str(route_id),
            "integration": _integration_payload(source, warning=resolved.get("warning")),
            "cue_sheet": None,
            "missing_features": ["cue_sheet"],
            "warning": resolved.get("warning"),
        }
    route_view = dict(route)
    route_view.setdefault("source", source)
    route_view.setdefault("origin", _route_origin_for_source(source))
    cue_sheet = _route_cue_sheet_from_route(route_view)
    return {
        "ok": cue_sheet.get("available", False),
        "source": source,
        "origin": route_view.get("origin"),
        "route_id": str(route_id),
        "integration": _integration_payload(
            source,
            warning=resolved.get("warning") if source == "cache" else None,
            missing_features=cue_sheet.get("missing_features"),
        ),
        "cue_sheet": cue_sheet if cue_sheet.get("available") else None,
        "cue_sheet_detail": cue_sheet,
        "missing_features": cue_sheet.get("missing_features", []),
        "warning": resolved.get("warning") if source == "cache" else cue_sheet.get("reason"),
    }


def _build_gpx(route: dict[str, Any]) -> str | None:
    geometry = _route_geometry_from_route(route)
    if not geometry.get("available"):
        return None
    coords = geometry["geojson"]["coordinates"]
    route_name = escape(str(route.get("name") or f"RWGPS route {route.get('id')}"))
    route_link = escape(str(route.get("html_url") or route.get("url") or ""))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="QBot RWGPS client" xmlns="http://www.topografix.com/GPX/1/1">',
        "  <metadata>",
        f"    <name>{route_name}</name>",
    ]
    if route_link:
        lines.append(f'    <link href="{route_link}"/>')
    lines.extend([
        "  </metadata>",
        "  <trk>",
        f"    <name>{route_name}</name>",
        "    <trkseg>",
    ])
    for coord in coords:
        lon = coord[0]
        lat = coord[1]
        lines.append(f'      <trkpt lat="{lat}" lon="{lon}">')
        if len(coord) > 2:
            lines.append(f"        <ele>{coord[2]}</ele>")
        lines.append("      </trkpt>")
    lines.extend([
        "    </trkseg>",
        "  </trk>",
        "</gpx>",
    ])
    return "\n".join(lines)


def _build_tcx(route: dict[str, Any]) -> str | None:
    geometry = _route_geometry_from_route(route)
    if not geometry.get("available"):
        return None
    coords = geometry["geojson"]["coordinates"]
    route_name = escape(str(route.get("name") or f"RWGPS route {route.get('id')}"))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">',
        "  <Courses>",
        "    <Course>",
        f"      <Name>{route_name}</Name>",
        "      <Track>",
    ]
    for coord in coords:
        lon = coord[0]
        lat = coord[1]
        lines.append("        <Trackpoint>")
        lines.append(f"          <Position><LatitudeDegrees>{lat}</LatitudeDegrees><LongitudeDegrees>{lon}</LongitudeDegrees></Position>")
        if len(coord) > 2:
            lines.append(f"          <AltitudeMeters>{coord[2]}</AltitudeMeters>")
        lines.append("        </Trackpoint>")
    lines.extend([
        "      </Track>",
        "    </Course>",
        "  </Courses>",
        "</TrainingCenterDatabase>",
    ])
    return "\n".join(lines)


def download_route_gpx(route_id: str | int) -> dict[str, Any]:
    resolved = _resolve_route_record(route_id)
    route = resolved.get("route")
    source = resolved.get("source", "fallback")
    if not isinstance(route, dict):
        return {
            "ok": False,
            "source": source,
            "origin": _route_origin_for_source(source),
            "route_id": str(route_id),
            "format": "gpx",
            "content": None,
            "missing_features": ["route"],
            "warning": resolved.get("warning"),
        }
    route_view = dict(route)
    route_view.setdefault("source", source)
    route_view.setdefault("origin", _route_origin_for_source(source))
    content = _build_gpx(route_view)
    if content is None:
        return {
            "ok": False,
            "source": source,
            "origin": route_view.get("origin"),
            "route_id": str(route_id),
            "format": "gpx",
            "content": None,
            "missing_features": ["geometry"],
            "warning": "track_points are not available",
        }
    return {
        "ok": True,
        "source": source,
        "origin": route_view.get("origin"),
        "route_id": str(route_id),
        "format": "gpx",
        "filename": f"rwgps-route-{route_id}.gpx",
        "content_type": "application/gpx+xml",
        "content": content,
        "byte_length": len(content.encode("utf-8")),
        "integration": _integration_payload(source, warning=resolved.get("warning") if source == "cache" else None),
    }


def download_route_tcx(route_id: str | int) -> dict[str, Any]:
    resolved = _resolve_route_record(route_id)
    route = resolved.get("route")
    source = resolved.get("source", "fallback")
    if not isinstance(route, dict):
        return {
            "ok": False,
            "source": source,
            "origin": _route_origin_for_source(source),
            "route_id": str(route_id),
            "format": "tcx",
            "content": None,
            "missing_features": ["route"],
            "warning": resolved.get("warning"),
        }
    route_view = dict(route)
    route_view.setdefault("source", source)
    route_view.setdefault("origin", _route_origin_for_source(source))
    content = _build_tcx(route_view)
    if content is None:
        return {
            "ok": False,
            "source": source,
            "origin": route_view.get("origin"),
            "route_id": str(route_id),
            "format": "tcx",
            "content": None,
            "missing_features": ["geometry"],
            "warning": "track_points are not available",
        }
    return {
        "ok": True,
        "source": source,
        "origin": route_view.get("origin"),
        "route_id": str(route_id),
        "format": "tcx",
        "filename": f"rwgps-route-{route_id}.tcx",
        "content_type": "application/vnd.garmin.tcx+xml",
        "content": content,
        "byte_length": len(content.encode("utf-8")),
        "integration": _integration_payload(source, warning=resolved.get("warning") if source == "cache" else None),
    }


def download_route_fit(route_id: str | int) -> dict[str, Any]:
    resolved = _resolve_route_record(route_id)
    source = resolved.get("source", "fallback")
    return {
        "ok": False,
        "source": source,
        "origin": _route_origin_for_source(source),
        "route_id": str(route_id),
        "format": "fit",
        "content": None,
        "missing_features": ["fit_export"],
        "warning": "RWGPS FIT export is not implemented because the API does not expose a safe binary FIT export path in this client",
        "integration": _integration_payload(source, warning=resolved.get("warning") if source == "cache" else None, missing_features=["fit_export"]),
    }


def _valid_route_id(route_id_str: str) -> str:
    route_id_str = str(route_id_str).strip()
    if not route_id_str:
        raise RWGPSError("INVALID_ROUTE_ID", "route_id must not be empty")
    if not re.fullmatch(r"^[a-zA-Z0-9_\-]+$", route_id_str):
        raise RWGPSError("INVALID_ROUTE_ID", f"route_id contains invalid characters: {route_id_str}")
    return route_id_str


def _valid_export_format(fmt: str) -> str:
    fmt = str(fmt).strip().lower()
    if fmt not in ALLOWED_EXPORT_FORMATS:
        raise RWGPSError("INVALID_FORMAT", f"format must be one of: {', '.join(sorted(ALLOWED_EXPORT_FORMATS))}")
    return fmt


def export_route_to_artifact(route_id: str | int, fmt: str = "gpx") -> dict[str, Any]:
    route_id_str = _valid_route_id(str(route_id))
    fmt = _valid_export_format(fmt)

    try:
        resolved = _resolve_route_record(route_id_str)
    except RWGPSError as exc:
        return {
            "ok": False,
            "status": "RWGPS_EXPORT_FAILED",
            "route_id": route_id_str,
            "format": fmt,
            "artifact_path": None,
            "size_bytes": 0,
            "sha256": None,
            "point_count": None,
            "distance_km": None,
            "elevation_gain_m": None,
            "reason": exc.message,
            "error": "RWGPS_EXPORT_FAILED",
            "source": "fallback",
            "integration": _integration_payload("fallback", remote_error=exc.message),
        }

    route = resolved.get("route")
    source = resolved.get("source", "fallback")

    if not isinstance(route, dict):
        return {
            "ok": False,
            "status": "ROUTE_NOT_FOUND",
            "route_id": route_id_str,
            "format": fmt,
            "artifact_path": None,
            "size_bytes": 0,
            "sha256": None,
            "point_count": None,
            "distance_km": None,
            "elevation_gain_m": None,
            "reason": resolved.get("warning") or "Route not found",
            "error": "ROUTE_NOT_FOUND",
            "source": source,
            "integration": _integration_payload(source, warning=resolved.get("warning")),
        }

    route_view = dict(route)
    route_view.setdefault("source", source)
    route_view.setdefault("origin", _route_origin_for_source(source))

    content: str | None = None
    if fmt == "gpx":
        content = _build_gpx(route_view)
    elif fmt == "tcx":
        content = _build_tcx(route_view)
    elif fmt == "json":
        geometry = _route_geometry_from_route(route_view)
        if geometry.get("available"):
            detail = _build_route_detail(
                route_view,
                source=source,
                cached_at=resolved.get("cached_at"),
                cache_hit=bool(resolved.get("cache_hit")),
                remote_error=resolved.get("warning"),
            )
            content = json.dumps(detail, ensure_ascii=False, indent=2)

    if content is None:
        missing = "geometry/track_points"
        return {
            "ok": False,
            "status": "RWGPS_EXPORT_FAILED",
            "route_id": route_id_str,
            "format": fmt,
            "artifact_path": None,
            "size_bytes": 0,
            "sha256": None,
            "point_count": None,
            "distance_km": _distance_km(route_view),
            "elevation_gain_m": route_view.get("elevation_gain") or route_view.get("elevation_m"),
            "reason": f"Cannot build {fmt}: {missing} not available",
            "error": "RWGPS_EXPORT_FAILED",
            "source": source,
            "integration": _integration_payload(source, warning=resolved.get("warning"), missing_features=[missing]),
        }

    content_bytes = content.encode("utf-8")
    sha256_hash = hashlib.sha256(content_bytes).hexdigest()

    ARTIFACT_RWGPS_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"rwgps_{route_id_str}.{fmt}"
    artifact_path = ARTIFACT_RWGPS_EXPORT_DIR / filename
    artifact_path.write_text(content, encoding="utf-8")

    geometry = _route_geometry_from_route(route_view)
    point_count = geometry.get("point_count", 0)
    dist_m = route_view.get("distance")
    if dist_m is not None:
        dist_km = round(float(dist_m) / 1000.0, 3)
    else:
        dist_km = _distance_km(route_view)
    elev_gain = route_view.get("elevation_gain") or route_view.get("elevation_m")

    relative_path = f"{ARTIFACT_RWGPS_RELATIVE_PREFIX}/rwgps_{route_id_str}.{fmt}"

    return {
        "ok": True,
        "status": "OK",
        "route_id": route_id_str,
        "route_name": route_view.get("name"),
        "format": fmt,
        "artifact_path": str(artifact_path),
        "artifact_relative_path": relative_path,
        "size_bytes": len(content_bytes),
        "sha256": sha256_hash,
        "point_count": point_count,
        "distance_km": dist_km,
        "elevation_gain_m": elev_gain,
        "source": source,
        "origin": route_view.get("origin"),
        "integration": _integration_payload(source, warning=resolved.get("warning") if source == "cache" else None),
    }


def _parse_gpx_for_summary(file_path: Path) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    tree = ET.parse(str(file_path))
    root = tree.getroot()
    ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
    for trkpt in root.iter("{http://www.topografix.com/GPX/1/1}trkpt"):
        lat = trkpt.get("lat")
        lon = trkpt.get("lon")
        ele_el = trkpt.find("{http://www.topografix.com/GPX/1/1}ele")
        ele = float(ele_el.text) if ele_el is not None and ele_el.text else None
        try:
            point = {"lat": float(lat) if lat else 0, "lon": float(lon) if lon else 0}
            if ele is not None:
                point["elevation"] = ele
            points.append(point)
        except (TypeError, ValueError):
            continue
    return _compute_summary_from_points(points)


def _parse_tcx_for_summary(file_path: Path) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    tree = ET.parse(str(file_path))
    root = tree.getroot()
    ns = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    for tp in root.iter(f"{{{ns}}}Trackpoint"):
        pos = tp.find(f"{{{ns}}}Position")
        if pos is None:
            continue
        lat_el = pos.find(f"{{{ns}}}LatitudeDegrees")
        lon_el = pos.find(f"{{{ns}}}LongitudeDegrees")
        alt_el = tp.find(f"{{{ns}}}AltitudeMeters")
        try:
            point = {}
            if lat_el is not None and lon_el is not None:
                point["lat"] = float(lat_el.text or 0)
                point["lon"] = float(lon_el.text or 0)
            else:
                continue
            if alt_el is not None and alt_el.text:
                point["elevation"] = float(alt_el.text)
            points.append(point)
        except (TypeError, ValueError):
            continue
    return _compute_summary_from_points(points)


def _parse_json_for_summary(file_path: Path) -> dict[str, Any]:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    points: list[dict[str, Any]] = []

    geometry = data.get("geometry", {}) if isinstance(data, dict) else {}
    geojson = geometry.get("geojson")
    if isinstance(geojson, dict) and isinstance(geojson.get("coordinates"), list):
        for coord in geojson["coordinates"]:
            if isinstance(coord, list) and len(coord) >= 2:
                p = {"lat": float(coord[1]), "lon": float(coord[0])}
                if len(coord) >= 3 and coord[2] is not None:
                    p["elevation"] = float(coord[2])
                points.append(p)

    summary = _compute_summary_from_points(points)
    if isinstance(data, dict):
        dist = data.get("distance_km") or (
            round(float(data.get("distance", 0)) / 1000.0, 3) if data.get("distance") else None
        )
        summary["distance_km"] = dist or summary["distance_km"]
        summary["elevation_gain_m"] = data.get("elevation_m") or data.get("elevation_gain") or summary["elevation_gain_m"]
        summary["elevation_loss_m"] = data.get("elevation_loss") or summary["elevation_loss_m"]
        summary["cue_count"] = len(data.get("course_points") or [])
    return summary


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _compute_summary_from_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        return {
            "point_count": 0,
            "bounds": None,
            "distance_km": None,
            "elevation_gain_m": None,
            "elevation_loss_m": None,
            "min_elevation_m": None,
            "max_elevation_m": None,
            "first_point": None,
            "last_point": None,
            "looks_valid": False,
        }

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    bounds = {
        "sw_lat": min(lats),
        "sw_lng": min(lons),
        "ne_lat": max(lats),
        "ne_lng": max(lons),
    }

    total_dist_m = 0.0
    for i in range(1, len(points)):
        total_dist_m += _haversine_m(
            points[i - 1]["lat"], points[i - 1]["lon"],
            points[i]["lat"], points[i]["lon"],
        )

    elevations = [p["elevation"] for p in points if "elevation" in p]
    elev_gain = 0.0
    elev_loss = 0.0
    for i in range(1, len(elevations)):
        delta = elevations[i] - elevations[i - 1]
        if delta > 0:
            elev_gain += delta
        elif delta < 0:
            elev_loss += abs(delta)

    return {
        "point_count": len(points),
        "bounds": bounds,
        "distance_km": round(total_dist_m / 1000.0, 3),
        "elevation_gain_m": round(elev_gain, 1) if elevations else None,
        "elevation_loss_m": round(elev_loss, 1) if elevations else None,
        "min_elevation_m": round(min(elevations), 1) if elevations else None,
        "max_elevation_m": round(max(elevations), 1) if elevations else None,
        "first_point": {"lat": points[0]["lat"], "lon": points[0]["lon"]},
        "last_point": {"lat": points[-1]["lat"], "lon": points[-1]["lon"]},
        "looks_valid": len(points) > 1,
    }


def _resolve_artifact_for_summary(artifact_path_or_name: str) -> Path:
    if not isinstance(artifact_path_or_name, str):
        raise RWGPSError("INVALID_PATH", "artifact_path_or_name must be a string")
    raw = artifact_path_or_name.strip()
    if not raw:
        raise RWGPSError("INVALID_PATH", "artifact_path_or_name must not be empty")

    export_dir = ARTIFACT_RWGPS_EXPORT_DIR

    if raw.startswith("/"):
        abs_path = Path(raw).resolve(strict=False)
        if abs_path.exists() and abs_path.is_file():
            return abs_path
        raise RWGPSError("NOT_FOUND", f"Artifact not found: {raw}")

    artifact_root = Path("/opt/qbot/artifacts")
    if "/" in raw:
        rel_path = artifact_root / raw
        rel_path = rel_path.resolve(strict=False)
        if rel_path.exists() and rel_path.is_file():
            return rel_path

    from_export = export_dir / raw
    from_export = from_export.resolve(strict=False)
    if from_export.exists() and from_export.is_file():
        return from_export

    if export_dir.exists():
        all_files = sorted(export_dir.glob("*"))
        for fpath in all_files:
            if fpath.is_file() and fpath.name == raw:
                return fpath
        for fpath in all_files:
            if fpath.is_file() and fpath.name.casefold() == raw.casefold():
                return fpath

    raise RWGPSError("NOT_FOUND", f"Artifact not found: {raw}")


def extract_artifact_points(artifact_path_or_name: str) -> list[list[float]]:
    """Extract [lat, lon] or [lat, lon, elevation] points from a GPX/TCX/JSON artifact."""
    file_path = _resolve_artifact_for_summary(artifact_path_or_name)
    suffix = file_path.suffix.lower()

    if suffix == ".gpx":
        return _extract_gpx_points(file_path)
    elif suffix == ".tcx":
        return _extract_tcx_points(file_path)
    elif suffix == ".json":
        return _extract_json_artifact_points(file_path)
    else:
        raise RWGPSError("INVALID_FORMAT", f"Unsupported format for point extraction: {suffix}")


def _extract_gpx_points(file_path: Path) -> list[list[float]]:
    tree = ET.parse(str(file_path))
    root_ns = tree.getroot()
    points: list[list[float]] = []
    ns = "http://www.topografix.com/GPX/1/1"
    for trkpt in root_ns.iter(f"{{{ns}}}trkpt"):
        lat = trkpt.get("lat")
        lon = trkpt.get("lon")
        if lat is None or lon is None:
            continue
        ele_el = trkpt.find(f"{{{ns}}}ele")
        point = [float(lat), float(lon)]
        if ele_el is not None and ele_el.text:
            try:
                point.append(float(ele_el.text))
            except (TypeError, ValueError):
                pass
        points.append(point)
    return points


def _extract_tcx_points(file_path: Path) -> list[list[float]]:
    tree = ET.parse(str(file_path))
    root_ns = tree.getroot()
    points: list[list[float]] = []
    ns = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    for tp in root_ns.iter(f"{{{ns}}}Trackpoint"):
        pos = tp.find(f"{{{ns}}}Position")
        if pos is None:
            continue
        lat_el = pos.find(f"{{{ns}}}LatitudeDegrees")
        lon_el = pos.find(f"{{{ns}}}LongitudeDegrees")
        if lat_el is None or lon_el is None:
            continue
        try:
            point = [float(lat_el.text or 0), float(lon_el.text or 0)]
            alt_el = tp.find(f"{{{ns}}}AltitudeMeters")
            if alt_el is not None and alt_el.text:
                point.append(float(alt_el.text))
            points.append(point)
        except (TypeError, ValueError):
            continue
    return points


def _extract_json_artifact_points(file_path: Path) -> list[list[float]]:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    points: list[list[float]] = []
    geometry = data.get("geometry", {}) if isinstance(data, dict) else {}
    geojson = geometry.get("geojson")
    if isinstance(geojson, dict) and isinstance(geojson.get("coordinates"), list):
        for coord in geojson["coordinates"]:
            if isinstance(coord, list) and len(coord) >= 2:
                pt = [float(coord[1]), float(coord[0])]  # lat, lon
                if len(coord) >= 3 and coord[2] is not None:
                    pt.append(float(coord[2]))
                points.append(pt)
    return points

    # Relative path from artifact root (e.g. "exports/rwgps/rwgps_55256628.gpx")
    artifact_root = Path("/opt/qbot/artifacts")
    if "/" in raw:
        rel_path = artifact_root / raw
        rel_path = rel_path.resolve(strict=False)
        if rel_path.exists() and rel_path.is_file():
            return rel_path

    # Relative path from export dir (e.g. "rwgps_55256628.gpx" or "rwgps/55256628.gpx")
    from_export = export_dir / raw
    from_export = from_export.resolve(strict=False)
    if from_export.exists() and from_export.is_file():
        return from_export

    # Filename-only lookup in export dir
    if export_dir.exists():
        all_files = sorted(export_dir.glob("*"))
        for fpath in all_files:
            if fpath.is_file() and fpath.name == raw:
                return fpath
        for fpath in all_files:
            if fpath.is_file() and fpath.name.casefold() == raw.casefold():
                return fpath

    raise RWGPSError("NOT_FOUND", f"Artifact not found: {raw}")


def summarize_rwgps_artifact(artifact_path_or_name: str) -> dict[str, Any]:
    try:
        file_path = _resolve_artifact_for_summary(artifact_path_or_name)
    except RWGPSError as exc:
        return {
            "ok": False,
            "status": "NOT_FOUND",
            "error": exc.kind,
            "reason": exc.message,
            "artifact_path_or_name": artifact_path_or_name,
        }

    try:
        size_bytes = file_path.stat().st_size
        sha256_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    except OSError as exc:
        return {
            "ok": False,
            "status": "WRITE_FAILED",
            "error": "WRITE_FAILED",
            "reason": str(exc),
            "artifact_path": str(file_path),
        }

    suffix = file_path.suffix.lower()
    try:
        if suffix == ".gpx":
            summary = _parse_gpx_for_summary(file_path)
        elif suffix == ".tcx":
            summary = _parse_tcx_for_summary(file_path)
        elif suffix == ".json":
            summary = _parse_json_for_summary(file_path)
        else:
            return {
                "ok": False,
                "status": "INVALID_FORMAT",
                "error": "INVALID_FORMAT",
                "reason": f"Unsupported file format: {suffix}",
                "artifact_path": str(file_path),
                "size_bytes": size_bytes,
                "sha256": sha256_hash,
            }
    except ET.ParseError as exc:
        return {
            "ok": False,
            "status": "RWGPS_EXPORT_FAILED",
            "error": "RWGPS_EXPORT_FAILED",
            "reason": f"XML parsing failed: {exc}",
            "artifact_path": str(file_path),
            "size_bytes": size_bytes,
            "sha256": sha256_hash,
        }
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "status": "RWGPS_EXPORT_FAILED",
            "error": "RWGPS_EXPORT_FAILED",
            "reason": f"JSON parsing failed: {exc}",
            "artifact_path": str(file_path),
            "size_bytes": size_bytes,
            "sha256": sha256_hash,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "RWGPS_EXPORT_FAILED",
            "error": "RWGPS_EXPORT_FAILED",
            "reason": str(exc),
            "artifact_path": str(file_path),
            "size_bytes": size_bytes,
            "sha256": sha256_hash,
        }

    return {
        "ok": True,
        "status": "OK",
        "artifact_path": str(file_path),
        "artifact_name": file_path.name,
        "size_bytes": size_bytes,
        "sha256": sha256_hash,
        **summary,
    }
