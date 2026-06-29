from __future__ import annotations

import base64
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
RWGPS_PARSE_VERSION = "gpx-summary-v1"
RWGPS_SURFACE_ENRICHMENT_VERSION = "surface-profile-v1"

_ARTIFACT_PROJECT_NAME_MAP: dict[str, str] = {
    "toskania": "tuscany_2026",
    "tuscany": "tuscany_2026",
}


def _resolve_project_id_from_name(route_name: str) -> str | None:
    name_lower = route_name.lower()
    for keyword, project_id in _ARTIFACT_PROJECT_NAME_MAP.items():
        if keyword in name_lower:
            return project_id
    return None


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


def _surface_profile_quality_score(summary: dict[str, Any] | None) -> dict[str, Any]:
    summary = summary or {}

    def _float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    coverage_pct = _float(summary.get("coverage_pct"))
    unknown_surface_pct = _float(summary.get("unknown_surface_pct"))
    if unknown_surface_pct is None:
        unknown_surface_pct = _float(summary.get("unknown_pct_refined"))
    if unknown_surface_pct is None:
        unknown_surface_pct = _float(summary.get("unknown_pct_raw"))
    quality_status = str(summary.get("quality_status") or summary.get("status") or "").strip().upper()

    overpass_metrics = summary.get("overpass_metrics") if isinstance(summary.get("overpass_metrics"), dict) else {}
    chunks_total = _int(overpass_metrics.get("chunks_total"))
    chunks_ok = _int(overpass_metrics.get("chunks_ok"))
    chunks_failed = _int(overpass_metrics.get("chunks_failed"))

    suspicious_reasons: list[str] = []
    if coverage_pct is not None and coverage_pct < 80.0:
        suspicious_reasons.append("coverage_pct < 80")
    if unknown_surface_pct is not None and unknown_surface_pct > 40.0:
        suspicious_reasons.append("unknown_surface_pct > 40")
    if quality_status == "LOW_CONFIDENCE":
        suspicious_reasons.append("quality_status == LOW_CONFIDENCE")
    if chunks_total > 0 and chunks_failed > 0 and chunks_ok < chunks_total:
        suspicious_reasons.append("overpass partial/failing chunk coverage")

    good = (
        coverage_pct is not None
        and coverage_pct >= 90.0
        and unknown_surface_pct is not None
        and unknown_surface_pct <= 20.0
        and quality_status in {"GOOD_TAGGED", "GOOD_INFERRED"}
    )
    suspicious = bool(suspicious_reasons)

    score = 0
    if coverage_pct is not None:
        score += int(round(max(0.0, min(coverage_pct, 100.0))))
    if unknown_surface_pct is not None:
        score -= int(round(max(0.0, min(unknown_surface_pct, 100.0))))
    if quality_status in {"GOOD_TAGGED", "GOOD_INFERRED"}:
        score += 25
    elif quality_status == "LOW_CONFIDENCE":
        score -= 25
    if chunks_total > 0 and chunks_failed > 0 and chunks_ok < chunks_total:
        score -= 15

    return {
        "score": score,
        "coverage_pct": coverage_pct,
        "unknown_surface_pct": unknown_surface_pct,
        "quality_status": quality_status or "UNKNOWN",
        "chunks_total": chunks_total,
        "chunks_ok": chunks_ok,
        "chunks_failed": chunks_failed,
        "suspicious": suspicious,
        "good": good,
        "suspicious_reasons": suspicious_reasons,
    }


def _is_suspicious_surface_profile(summary: dict[str, Any] | None) -> bool:
    return bool(_surface_profile_quality_score(summary).get("suspicious"))


def _has_better_existing_surface_profile(route_id: str | None, summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not route_id or not _is_suspicious_surface_profile(summary):
        return None
    try:
        import os as _os
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(
            host=_os.getenv("PGHOST", "127.0.0.1"),
            port=_os.getenv("PGPORT", "5432"),
            dbname=_os.getenv("PGDATABASE", "qbot"),
            user=_os.getenv("PGUSER", "qbot"),
            password=_os.getenv("PGPASSWORD", ""),
            row_factory=dict_row,
            connect_timeout=5,
        )
        row = conn.execute(
            """
            SELECT
                p.id,
                p.route_artifact_id,
                a.route_id::text AS route_id,
                p.enriched_at,
                p.coverage_pct,
                COALESCE(NULLIF(p.surface_summary_json->>'quality_status', ''), p.status) AS quality_status,
                COALESCE(
                    NULLIF(p.surface_summary_json->>'unknown_surface_pct', '')::double precision,
                    NULLIF(p.surface_summary_json->>'unknown_pct_refined', '')::double precision,
                    NULLIF(p.surface_summary_json->>'unknown_pct_raw', '')::double precision
                ) AS unknown_surface_pct
            FROM qbot_v2.route_surface_profiles p
            JOIN qbot_v2.route_artifacts a ON a.id = p.route_artifact_id
            WHERE a.route_id::text = %s
              AND p.coverage_pct >= 90
              AND COALESCE(
                    NULLIF(p.surface_summary_json->>'unknown_surface_pct', '')::double precision,
                    NULLIF(p.surface_summary_json->>'unknown_pct_refined', '')::double precision,
                    NULLIF(p.surface_summary_json->>'unknown_pct_raw', '')::double precision
                  ) <= 20
              AND UPPER(COALESCE(NULLIF(p.surface_summary_json->>'quality_status', ''), p.status, '')) IN ('GOOD_TAGGED', 'GOOD_INFERRED')
            ORDER BY p.coverage_pct DESC, unknown_surface_pct ASC NULLS LAST, p.enriched_at DESC NULLS LAST, p.id DESC
            LIMIT 1
            """,
            (str(route_id),),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


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


def _artifact_route_id_from_path(file_path: Path) -> str:
    stem = file_path.stem
    if stem.startswith("rwgps_"):
        candidate = stem.split("rwgps_", 1)[1].strip()
        if candidate:
            return candidate
    return stem


def _artifact_relative_path(file_path: Path) -> str | None:
    try:
        return str(file_path.resolve(strict=False).relative_to(Path("/opt/qbot/artifacts")))
    except Exception:
        return None


def _persist_route_artifact_record(
    file_path: Path,
    *,
    route_id: str | None = None,
    export_format: str | None = None,
    status: str = "ok",
    parser_version: str | None = None,
    source_artifact_sha256: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        import api_db

        st = file_path.stat()
        sha256_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        payload = {
            "route_id": route_id or _artifact_route_id_from_path(file_path),
            "source": "rwgps",
            "export_format": export_format or (f"{file_path.suffix.lstrip('.')}_track" if file_path.suffix else "gpx_track"),
            "artifact_path": str(file_path),
            "artifact_relative_path": _artifact_relative_path(file_path),
            "filename": file_path.name,
            "file_size_bytes": st.st_size,
            "sha256": sha256_hash,
            "parser_version": parser_version,
            "source_artifact_sha256": source_artifact_sha256 or sha256_hash,
            "status": status,
            "metadata_json": metadata_json or {},
        }
        return api_db.upsert_route_artifact(payload)
    except Exception:
        return None


def _persist_route_parse_result(file_path: Path, summary: dict[str, Any]) -> dict[str, Any] | None:
    try:
        import api_db

        route_artifact = _persist_route_artifact_record(
            file_path,
            route_id=_artifact_route_id_from_path(file_path),
            export_format=f"{file_path.suffix.lstrip('.')}_track" if file_path.suffix else "gpx_track",
            parser_version=RWGPS_PARSE_VERSION,
            metadata_json={"kind": "parse_source"},
        )
        if not route_artifact:
            return None

        bounds = summary.get("bounds") or {}
        first_point = summary.get("first_point") or {}
        last_point = summary.get("last_point") or {}
        record = {
            "route_artifact_id": route_artifact["id"],
            "parser_version": RWGPS_PARSE_VERSION,
            "source_artifact_sha256": route_artifact.get("sha256"),
            "track_points": summary.get("point_count"),
            "distance_m": round(float(summary.get("distance_km")) * 1000.0, 1) if summary.get("distance_km") is not None else None,
            "distance_km": summary.get("distance_km"),
            "elevation_gain_m": summary.get("elevation_gain_m"),
            "elevation_loss_m": summary.get("elevation_loss_m"),
            "bbox_min_lat": bounds.get("sw_lat"),
            "bbox_min_lon": bounds.get("sw_lng"),
            "bbox_max_lat": bounds.get("ne_lat"),
            "bbox_max_lon": bounds.get("ne_lng"),
            "start_lat": first_point.get("lat"),
            "start_lon": first_point.get("lon"),
            "end_lat": last_point.get("lat"),
            "end_lon": last_point.get("lon"),
            "min_ele": summary.get("min_elevation_m"),
            "max_ele": summary.get("max_elevation_m"),
            "looks_valid": summary.get("looks_valid"),
            "summary_json": summary,
        }
        return api_db.upsert_route_parse_result(record)
    except Exception:
        return None


def _persist_route_surface_profile(file_path: Path, payload: dict[str, Any], surface_result: dict[str, Any] | None) -> dict[str, Any] | None:
    try:
        import api_db

        route_id = _artifact_route_id_from_path(file_path)
        _rname = None
        try:
            import re as _re
            _gpx_txt = file_path.read_text(encoding="utf-8", errors="ignore")
            _nm = _re.search(r"<name>(.*?)</name>", _gpx_txt)
            if _nm:
                _rname = _nm.group(1).strip()
        except Exception:
            _rname = None

        surface_profile = payload.get("surface_profile") or {}
        surface_summary = dict(surface_profile)
        if isinstance(surface_result, dict) and surface_result:
            surface_summary.update(surface_result)
        gate = _surface_profile_quality_score(surface_summary)
        existing_good_profile = _has_better_existing_surface_profile(route_id, surface_summary)
        if gate.get("suspicious") and existing_good_profile:
            return {
                "skipped": True,
                "reason": "surface_quality_gate_rejected_partial_result",
                "existing_profile_id": existing_good_profile.get("id"),
                "existing_route_artifact_id": existing_good_profile.get("route_artifact_id"),
                "new_quality_status": gate.get("quality_status"),
                "new_coverage_pct": gate.get("coverage_pct"),
                "new_unknown_surface_pct": gate.get("unknown_surface_pct"),
                "quality_score": gate.get("score"),
                "suspicious_reasons": gate.get("suspicious_reasons"),
            }
        if gate.get("suspicious") and not existing_good_profile:
            warnings = surface_summary.get("warnings")
            if not isinstance(warnings, list):
                warnings = []
            if "LOW_QUALITY_PROFILE_NO_BETTER_EXISTING_PROFILE" not in warnings:
                warnings.append("LOW_QUALITY_PROFILE_NO_BETTER_EXISTING_PROFILE")
            surface_summary["warnings"] = warnings

        route_artifact = _persist_route_artifact_record(
            file_path,
            route_id=route_id,
            export_format=f"{file_path.suffix.lstrip('.')}_track" if file_path.suffix else "gpx_track",
            parser_version=RWGPS_PARSE_VERSION,
            metadata_json={"kind": "enrich_source", "route_name": _rname},
        )
        if not route_artifact:
            return None
        segments = surface_summary.get("segments") or []
        record = {
            "route_artifact_id": route_artifact["id"],
            "enrichment_version": RWGPS_SURFACE_ENRICHMENT_VERSION,
            "source_artifact_sha256": route_artifact.get("sha256"),
            "surface_source": surface_summary.get("surface_source", payload.get("surface_source", "unknown")),
            "sample_every_m": surface_summary.get(
                "sample_every_m",
                surface_summary.get("sample_distance_m", payload.get("sample_every_m")),
            ),
            "confidence": surface_summary.get("confidence", surface_profile.get("confidence")),
            "coverage_pct": surface_summary.get("coverage_pct", surface_profile.get("coverage_pct")),
            "sampled_points": surface_summary.get("sampled_points", surface_profile.get("sampled_points")),
            "matched_points": surface_summary.get("matched_points", surface_profile.get("matched_points")),
            "unmatched_points": surface_summary.get("unmatched_points", surface_profile.get("unmatched_points")),
            "dominant_surface": surface_summary.get("dominant_surface", surface_profile.get("dominant_surface")),
            "status": surface_summary.get(
                "status",
                surface_profile.get("status", "ok" if surface_result and surface_result.get("ok") else "unknown"),
            ),
            "surface_summary_json": surface_summary,
            "surface_segments_json": segments,
            "surface_segments_path": surface_summary.get("surface_segments_path"),
        }
        profile_row = api_db.upsert_route_surface_profile(record)
        if isinstance(segments, list):
            segment_rows = []
            for segment in segments:
                if isinstance(segment, dict):
                    segment_rows.append(segment)
            if segment_rows:
                api_db.replace_route_surface_segments(profile_row["id"], segment_rows)
        return profile_row
    except Exception:
        return None


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


def _valid_export_return_mode(return_mode: str | None) -> str:
    mode = "metadata" if return_mode is None else str(return_mode).strip().lower()
    if mode not in {"metadata", "text", "base64"}:
        raise RWGPSError("INVALID_RETURN_MODE", "return_mode must be one of: metadata, text, base64")
    return mode


def export_route_to_artifact(route_id: str | int, fmt: str = "gpx", return_mode: str | None = None) -> dict[str, Any]:
    route_id_str = _valid_route_id(str(route_id))
    fmt = _valid_export_format(fmt)
    return_mode = _valid_export_return_mode(return_mode)

    try:
        resolved = _resolve_route_record(route_id_str)
    except RWGPSError as exc:
        return {
            "ok": False,
            "status": "RWGPS_EXPORT_FAILED",
            "route_id": route_id_str,
            "format": fmt,
            "return_mode": return_mode,
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
            "return_mode": return_mode,
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
            "return_mode": return_mode,
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
    artifact_file = artifact_path if isinstance(artifact_path, Path) else Path(str(artifact_path))

    geometry = _route_geometry_from_route(route_view)
    point_count = geometry.get("point_count", 0)
    dist_m = route_view.get("distance")
    if dist_m is not None:
        dist_km = round(float(dist_m) / 1000.0, 3)
    else:
        dist_km = _distance_km(route_view)
    elev_gain = route_view.get("elevation_gain") or route_view.get("elevation_m")

    relative_path = f"{ARTIFACT_RWGPS_RELATIVE_PREFIX}/rwgps_{route_id_str}.{fmt}"

    payload = {
        "ok": True,
        "status": "OK",
        "route_id": route_id_str,
        "route_name": route_view.get("name"),
        "format": fmt,
        "return_mode": return_mode,
        "artifact_path": str(artifact_path),
        "artifact_relative_path": relative_path,
        "filename": artifact_file.name,
        "download_ready": artifact_file.exists(),
        "size_bytes": len(content_bytes),
        "sha256": sha256_hash,
        "point_count": point_count,
        "distance_km": dist_km,
        "elevation_gain_m": elev_gain,
        "source": source,
        "origin": route_view.get("origin"),
        "integration": _integration_payload(source, warning=resolved.get("warning") if source == "cache" else None),
    }
    if return_mode == "text":
        payload["content"] = content
    elif return_mode == "base64":
        payload["content_base64"] = base64.b64encode(content_bytes).decode("ascii")

    _persist_route_artifact_record(
        artifact_file,
        route_id=route_id_str,
        export_format=f"{fmt}_track",
        status="ok",
        metadata_json={
            "route_name": route_view.get("name"),
            "route_origin": route_view.get("origin"),
            "route_source": source,
            "distance_km": dist_km,
            "elevation_gain_m": elev_gain,
            "point_count": point_count,
            "return_mode": return_mode,
        },
    )

    # ── Register in qbot_v2.artifacts (Artifact Store) ──
    try:
        from qbot3.artifacts.store import register_existing_file as _register_artifact

        route_name = route_view.get("name") or ""
        project_id = _resolve_project_id_from_name(route_name)

        # Wersjonowany klucz idempotencji — zawiera date updated_at z RWGPS.
        # Zmiana trasy na RWGPS = nowy klucz = nowy rekord; stary -> superseded.
        _rwgps_upd = route_view.get("updated_at") or ""
        _idem_date = (
            _rwgps_upd[:10].replace("-", "")  # "20260610"
            if len(_rwgps_upd) >= 10
            else "unknown"
        )
        idem_key = f"rwgps_export:{route_id_str}:{fmt}:{_idem_date}"
        artifact_record = _register_artifact(
            relative_path,
            artifact_type="route",
            title=route_name or f"Route {route_id_str}",
            project_id=project_id,
            mutation_type="export",
            source="rwgps",
            idempotency_key=idem_key,
            metadata={
                "rwgps_route_id": int(route_id_str),
                "rwgps_url": f"https://ridewithgps.com/routes/{route_id_str}",
                "distance_km": dist_km,
                "elevation_gain_m": elev_gain,
                "point_count": point_count,
                "route_name": route_name,
                "route_source": source,
                "rwgps_updated_at": route_view.get("updated_at") or "",
            },
        )
        if artifact_record and artifact_record.get("artifact_id"):
            payload["artifact_store_id"] = str(artifact_record["artifact_id"])
            payload["artifact_store_status"] = "registered"
            # Freshness invariant: superseduj stare rekordy tej trasy
            try:
                from core.invariants import supersede_stale_route_artifacts as _supersede
                _n_sup = _supersede(route_id_str, fmt, idem_key)
                if _n_sup:
                    payload["freshness_superseded"] = _n_sup
            except Exception as _inv_exc:
                payload["freshness_warning"] = f"supersede failed: {_inv_exc}"
        else:
            payload["artifact_store_warning"] = "Artifact Store returned empty record"
            payload["artifact_store_status"] = "skipped"
    except Exception as _as_exc:
        payload["artifact_store_warning"] = f"Artifact Store registration failed: {_as_exc}"
        payload["artifact_store_status"] = "failed"

    return payload


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

    def _try_resolve(path: Path) -> Path | None:
        try:
            p = path.resolve(strict=False)
            if p.exists() and p.is_file():
                return p
        except (OSError, RuntimeError):
            pass
        return None

    if raw.startswith("/"):
        found = _try_resolve(Path(raw))
        if found:
            return found

    artifact_root = Path("/opt/qbot/artifacts")
    if "/" in raw:
        found = _try_resolve(artifact_root / raw)
        if found:
            return found

    found = _try_resolve(export_dir / raw)
    if found:
        return found

    if export_dir.exists():
        for fpath in sorted(export_dir.glob("*")):
            if fpath.is_file() and (fpath.name == raw or fpath.name.casefold() == raw.casefold()):
                return fpath

    # ── Auto-export on demand: if filename matches rwgps_{route_id}.gpx, try to export ──
    import re as _re
    m = _re.match(r"rwgps_(\d+)\.gpx", Path(raw).name)
    if m:
        route_id = m.group(1)
        export_result = export_route_to_artifact(route_id, fmt="gpx", return_mode="metadata")
        if export_result.get("ok"):
            artifact_path_str = export_result.get("artifact_path")
            if artifact_path_str:
                ap = Path(artifact_path_str).resolve(strict=False)
                if ap.exists() and ap.is_file():
                    return ap

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

    _persist_route_artifact_record(
        file_path,
        route_id=_artifact_route_id_from_path(file_path),
        export_format=f"{file_path.suffix.lstrip('.')}_track" if file_path.suffix else "gpx_track",
        parser_version=RWGPS_PARSE_VERSION,
        source_artifact_sha256=sha256_hash,
        metadata_json={
            "kind": "artifact_summary_source",
            "artifact_name": file_path.name,
            "size_bytes": size_bytes,
        },
    )

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

    payload = {
        "ok": True,
        "status": "OK",
        "artifact_path": str(file_path),
        "artifact_name": file_path.name,
        "size_bytes": size_bytes,
        "sha256": sha256_hash,
        **summary,
    }

    _persist_route_parse_result(file_path, summary)
    return payload


def _sample_points(
    points: list[dict],
    max_points: int = 200,
) -> list[dict[str, Any]]:
    """Downsample a point list to at most max_points (uniform sampling)."""
    if not points:
        return []
    if len(points) <= max_points:
        return [{"lat": p["lat"], "lon": p["lon"], "ele": p.get("ele")} for p in points]
    step = len(points) / max_points
    sampled: list[dict[str, Any]] = []
    for i in range(max_points):
        idx = min(int(i * step), len(points) - 1)
        p = points[idx]
        sampled.append({"lat": p["lat"], "lon": p["lon"], "ele": p.get("ele")})
    return sampled


def parse_gpx_artifact_geometry(
    route_id: str | int | None = None,
    artifact_id: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Deterministic readout of full GPX geometry.

    Exactly one of *route_id*, *artifact_id*, or *path* must be provided.
    Does NOT call RWGPS API — works entirely from local files + qbot_v2.artifacts.
    Does NOT write to database.
    """
    # ── Validate input ──────────────────────────────────────────
    provided = sum(1 for x in (route_id, artifact_id, path) if x is not None)
    if provided != 1:
        return {
            "ok": False,
            "status": "INVALID_ARGS",
            "error": "Provide exactly one of: route_id, artifact_id, path",
        }

    file_path: Path | None = None
    artifact_record: dict | None = None
    resolved_route_id: str | None = None

    # ── Resolve by artifact_id ─────────────────────────────────
    if artifact_id is not None:
        try:
            import os as _os
            from qbot3.artifacts.store import get_artifact as _get_artifact

            artifact_record = _get_artifact(str(artifact_id))
            if artifact_record is None:
                return {
                    "ok": False,
                    "status": "NOT_FOUND",
                    "error": f"Artifact {artifact_id} not found in qbot_v2.artifacts",
                }
            rel = artifact_record.get("file_path")
            if not rel:
                return {
                    "ok": False,
                    "status": "NO_FILE",
                    "error": f"Artifact {artifact_id} has no file_path",
                }
            candidate = Path("/opt/qbot/artifacts") / rel
            if candidate.exists():
                file_path = candidate
        except Exception as exc:
            return {"ok": False, "status": "RESOLVE_ERROR", "error": str(exc)}

    # ── Resolve by route_id ────────────────────────────────────
    elif route_id is not None:
        rid = str(route_id)

        # Always try to find artifact record from store
        try:
            import os as _os
            import psycopg
            from psycopg.rows import dict_row

            conn = psycopg.connect(
                host=_os.getenv("PGHOST", "127.0.0.1"),
                port=_os.getenv("PGPORT", "5432"),
                dbname=_os.getenv("PGDATABASE", "qbot"),
                user=_os.getenv("PGUSER", "qbot"),
                password=_os.getenv("PGPASSWORD", ""),
                row_factory=dict_row,
                connect_timeout=5,
            )
            row = conn.execute(
                "SELECT * FROM qbot_v2.artifacts "
                "WHERE metadata_json->>'rwgps_route_id' = %s "
                "AND status = 'active'::qbot_v2.artifact_status "
                "ORDER BY created_at DESC LIMIT 1",
                (rid,),
            ).fetchone()
            conn.close()
            if row:
                artifact_record = dict(row)
                for key in ("created_at", "updated_at", "expires_at"):
                    if hasattr(artifact_record.get(key), "isoformat"):
                        artifact_record[key] = artifact_record[key].isoformat()
        except Exception:
            pass

        # Determine file path
        std_path = ARTIFACT_RWGPS_EXPORT_DIR / f"rwgps_{rid}.gpx"
        if std_path.exists():
            file_path = std_path
        elif artifact_record:
            rel = artifact_record.get("file_path")
            if rel:
                candidate = Path("/opt/qbot/artifacts") / rel
                if candidate.exists():
                    file_path = candidate

        if file_path is None:
            return {
                "ok": False,
                "status": "NOT_FOUND",
                "error": f"No GPX artifact found for route_id={rid}",
            }
        resolved_route_id = rid

    # ── Resolve by path ────────────────────────────────────────
    elif path is not None:
        raw = str(path).strip()
        candidate = Path(raw)
        if not candidate.exists():
            candidate = Path("/opt/qbot/artifacts") / raw
        if not candidate.exists():
            candidate = ARTIFACT_RWGPS_EXPORT_DIR / raw
        if not candidate.exists():
            # glob-style lookup by filename
            if ARTIFACT_RWGPS_EXPORT_DIR.exists():
                for fp in sorted(ARTIFACT_RWGPS_EXPORT_DIR.glob("*")):
                    if fp.is_file() and (fp.name == raw or fp.name.casefold() == raw.casefold()):
                        candidate = fp
                        break
        if not candidate.exists():
            return {
                "ok": False,
                "status": "NOT_FOUND",
                "error": f"GPX file not found: {path}",
            }
        file_path = candidate.resolve()

    # ── Guard ───────────────────────────────────────────────────
    if file_path is None or not file_path.exists():
        return {"ok": False, "status": "NOT_FOUND", "error": "Could not resolve GPX file"}

    # ── Parse GPX ───────────────────────────────────────────────
    from qbot3.artifacts.route_analyzer import _parse_gpx_file_detailed, _find_point_at_km

    try:
        detailed = _parse_gpx_file_detailed(file_path)
    except Exception as exc:
        return {"ok": False, "status": "PARSE_ERROR", "error": str(exc)}

    if not detailed:
        return {
            "ok": False,
            "status": "PARSE_EMPTY",
            "error": f"No track points in {file_path}",
        }

    # ── Compute summary ─────────────────────────────────────────
    raw_points = [
        {"lat": p["lat"], "lon": p["lon"], "elevation": p.get("ele")}
        for p in detailed
    ]
    summary = _compute_summary_from_points(raw_points)

    total_km = detailed[-1]["cum_km"]
    first = detailed[0]
    last = detailed[-1]

    # ── Control points every 5 km ───────────────────────────────
    control_points: list[dict[str, Any]] = []
    for km in range(0, int(total_km) + 1, 5):
        pt = _find_point_at_km(detailed, float(km))
        control_points.append({
            "km": pt.get("nearest_km", round(float(km), 3)),
            "lat": pt["lat"],
            "lon": pt["lon"],
            "ele": pt.get("ele"),
        })

    # ── Simplified geometry (max 200 points) ────────────────────
    geometry_sample = _sample_points(detailed, max_points=200)

    # ── Build response ──────────────────────────────────────────
    size_bytes = file_path.stat().st_size

    result: dict[str, Any] = {
        "ok": True,
        "status": "OK",
        "analytics_source": "parse_gpx_artifact_geometry v1",
        "artifact_id": str(artifact_record["artifact_id"]) if artifact_record else None,
        "project_id": artifact_record.get("project_id") if artifact_record else None,
        "route_id": resolved_route_id,
        "absolute_path": str(file_path.resolve()),
        "relative_path": str(file_path.relative_to(Path("/opt/qbot/artifacts")))
        if file_path.is_relative_to(Path("/opt/qbot/artifacts"))
        else str(file_path),
        "filename": file_path.name,
        "size_bytes": size_bytes,
        "point_count": summary.get("point_count"),
        "distance_km": summary.get("distance_km"),
        "elevation_gain_m": summary.get("elevation_gain_m"),
        "elevation_loss_m": summary.get("elevation_loss_m"),
        "min_elevation_m": summary.get("min_elevation_m"),
        "max_elevation_m": summary.get("max_elevation_m"),
        "bbox": summary.get("bounds"),
        "start_point": {
            "lat": first["lat"],
            "lon": first["lon"],
            "ele": first.get("ele"),
        },
        "end_point": {
            "lat": last["lat"],
            "lon": last["lon"],
            "ele": last.get("ele"),
        },
        "track_length_km": round(total_km, 3),
        "control_points_every_5km": control_points,
        "geometry_sample": geometry_sample,
    }

    return result


def create_route_from_gpx(
    gpx_path: str | Path,
    name: str,
    description: str = "",
    privacy: str = "private",
) -> dict[str, Any]:
    """Create a new RWGPS route from a local GPX file.

    POST to /routes.json with the GPX file as multipart upload.
    Uses /routes.json (NOT /api/v1/routes.json — that endpoint returns 404 for POST).
    Returns the new route id, html_url, and api_url on success.
    """
    path = Path(gpx_path)
    if not path.exists():
        raise RWGPSError("NOT_FOUND", f"GPX file not found: {path}")
    if path.stat().st_size == 0:
        raise RWGPSError("EMPTY_FILE", f"GPX file is empty: {path}")

    if _missing_required_env():
        raise RWGPSError("not_configured", "RWGPS integration not configured")

    _create_path = env("RWGPS_CREATE_ROUTE_PATH", "/routes.json")
    url = f"{RWGPS_API_BASE}{_create_path}"
    headers = _remote_headers()
    # Do not set Content-Type — httpx will set multipart boundary automatically

    file_content = path.read_bytes()
    files = {
        "file": (path.name, file_content, "application/gpx+xml"),
    }
    data: dict[str, str] = {
        "route[name]": name,
        "route[description]": description,
        "route[privacy]": privacy,
    }

    try:
        with httpx.Client(timeout=RWGPS_TIMEOUT_SEC * 2) as client:
            response = client.post(url, headers=headers, files=files, data=data)
    except httpx.TimeoutException as exc:
        raise RWGPSError("timeout", "RWGPS route creation timed out", url=url) from exc
    except httpx.RequestError as exc:
        raise RWGPSError("network_error", f"RWGPS network error: {exc.__class__.__name__}", url=url) from exc

    if response.status_code in (401, 403):
        raise RWGPSError("auth_error", f"RWGPS auth failed (HTTP {response.status_code})", status_code=response.status_code, url=url)
    if response.status_code == 429:
        raise RWGPSError("rate_limited", "RWGPS rate limited (HTTP 429)", status_code=response.status_code, url=url)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:600]
        raise RWGPSError("http_error", f"RWGPS create route error (HTTP {response.status_code})", status_code=response.status_code, url=url, details={"body": body}) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise RWGPSError("malformed_response", "RWGPS returned invalid JSON", url=url) from exc

    route = _route_object(payload)
    if not route:
        # Fallback: try top-level keys
        route = payload.get("route") or payload

    route_id = str(route.get("id", "")) if isinstance(route, dict) else ""
    return {
        "ok": True,
        "route_id": route_id,
        "html_url": f"https://ridewithgps.com/routes/{route_id}" if route_id else None,
        "api_url": f"{RWGPS_API_BASE}/api/v1/routes/{route_id}.json" if route_id else None,
        "name": name,
        "description": description,
        "privacy": privacy,
        "route": route,
    }


def _parse_cookie_header(cookie_header: str | None) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if not cookie_header:
        return cookies
    for chunk in cookie_header.split(";"):
        part = chunk.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            cookies[key] = value
    return cookies


def _web_upload_session_cookie_source() -> tuple[str, dict[str, str]] | None:
    """Return the explicit browser session cookie source for RWGPS web upload."""
    raw = env("RWGPS_BROWSER_SESSION_COOKIE", "").strip()
    if not raw:
        return None
    parsed = _parse_cookie_header(raw)
    if not parsed:
        return None
    return ("RWGPS_BROWSER_SESSION_COOKIE", parsed)


def _web_upload_preview_payload(
    *,
    path: Path,
    name: str | None,
    description: str | None,
    privacy: str | None,
    auth_mode: str,
    session_cookie_source: str | None = None,
    session_cookie_names: list[str] | None = None,
) -> dict[str, Any]:
    preview: dict[str, Any] = {
        "ok": False,
        "status": "RWGPS_WEB_UPLOAD_REQUIRES_SESSION_COOKIE",
        "endpoint": f"{RWGPS_API_BASE}/trips?import_type=route",
        "method": "POST",
        "content_type": "multipart/form-data",
        "multipart": {
            "file_field_name": "data_file",
            "filename": path.name,
            "file_content_type": "application/octet-stream",
        },
        "auth_mode": auth_mode,
        "auth_headers": {
            "accept": "application/json",
            "origin": "https://ridewithgps.com",
            "referer": "https://ridewithgps.com/upload",
            "x-requested-with": "XMLHttpRequest",
        },
        "route_metadata": {
            "name": name,
            "description": description,
            "privacy": privacy,
        },
        "required_auth_env": "RWGPS_BROWSER_SESSION_COOKIE",
        "missing_auth_requirement": "RWGPS_BROWSER_SESSION_COOKIE environment variable required for RWGPS web upload",
    }
    if session_cookie_source:
        preview["session_cookie_source"] = session_cookie_source
    if session_cookie_names is not None:
        preview["session_cookie_names"] = session_cookie_names
    return preview


def _sanitize_response_text(text: str, limit: int = 2000) -> str:
    snippet = text[:limit]
    replacements = (
        ("_rwgps_3_session", "_REDACTED_SESSION_COOKIE_"),
        ("csrf_token", "csrf_token[redacted]"),
        ("auth_token", "auth_token[redacted]"),
        ("api_key", "api_key[redacted]"),
    )
    for needle, replacement in replacements:
        snippet = snippet.replace(needle, replacement)
    return snippet


def _extract_async_task_fields(payload: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return fields

    direct_keys = (
        "id",
        "task_id",
        "trip_id",
        "route_id",
        "url",
        "redirect",
        "location",
        "status",
        "state",
        "error",
        "message",
        "success",
    )
    for key in direct_keys:
        value = payload.get(key)
        if value is not None:
            fields[key] = value

    for nested_key in ("task", "trip", "route", "errors", "error", "result"):
        nested_value = payload.get(nested_key)
        if isinstance(nested_value, dict):
            for key in ("id", "task_id", "trip_id", "route_id", "url", "redirect", "location", "status", "state", "error", "message"):
                value = nested_value.get(key)
                if value is not None and key not in fields:
                    fields[key] = value
        elif isinstance(nested_value, list) and nested_value and nested_key not in fields:
            fields[nested_key] = nested_value[:10]
    return fields


def _build_web_upload_response_preview(
    *,
    url: str,
    response: httpx.Response,
    file_name: str,
    auth_mode: str,
    session_source_name: str | None,
    session_cookie_names: list[str] | None,
    name: str | None,
    description: str | None,
    privacy: str | None,
) -> dict[str, Any]:
    response_headers = dict(response.headers)
    location = response_headers.get("location")
    response_json: Any = None
    try:
        response_json = response.json()
    except ValueError:
        response_json = None

    payload_preview: dict[str, Any] = {
        "ok": response.status_code < 400,
        "status": "RWGPS_WEB_UPLOAD_REQUEST_SENT",
        "endpoint": url,
        "method": "POST",
        "content_type": "multipart/form-data",
        "multipart": {
            "file_field_name": "data_file",
            "filename": file_name,
            "file_content_type": "application/octet-stream",
        },
        "auth_mode": auth_mode,
        "auth_headers": {
            "accept": "application/json",
            "origin": "https://ridewithgps.com",
            "referer": "https://ridewithgps.com/upload",
            "x-requested-with": "XMLHttpRequest",
        },
        "session_cookie_source": session_source_name,
        "session_cookie_names": session_cookie_names,
        "route_metadata": {
            "name": name,
            "description": description,
            "privacy": privacy,
        },
        "response_status": response.status_code,
        "response_content_type": response_headers.get("content-type"),
        "response_location": location,
        "response_headers": {
            "content_type": response_headers.get("content-type"),
            "location": location,
            "redirect": response_headers.get("location"),
        },
        "response_body_preview": _sanitize_response_text(response.text, 2000),
        "response_json_keys": sorted(response_json.keys()) if isinstance(response_json, dict) else [],
    }
    if isinstance(response_json, dict):
        payload_preview["response_fields"] = _extract_async_task_fields(response_json)
    task_id = None
    if isinstance(response_json, dict):
        task_value = response_json.get("task_id") or response_json.get("id")
        if task_value is not None:
            task_id = str(task_value)
    if task_id:
        payload_preview["task_id"] = task_id
        payload_preview["status"] = "RWGPS_WEB_UPLOAD_ACCEPTED_TASK_CREATED"
    return payload_preview


def import_route_via_trips_upload_gpx(
    path: str | Path,
    name: str | None = None,
    description: str | None = None,
    privacy: str | None = None,
) -> dict[str, Any]:
    """Experimental RWGPS web upload via /trips?import_type=route.

    This uses the browser upload endpoint captured from the RWGPS web UI:
    multipart file field name: data_file.

    The function is intentionally conservative:
    - it will use a browser-session cookie only if the runtime exposes one
    - it will not guess POI architecture or mutate the legacy GPX uploader
    - if no session cookie is available, it returns a sanitized dry-run payload
      with RWGPS_WEB_UPLOAD_REQUIRES_SESSION_COOKIE
    """
    file_path = Path(path)
    if not file_path.exists():
        raise RWGPSError("NOT_FOUND", f"GPX file not found: {file_path}")
    if file_path.stat().st_size == 0:
        raise RWGPSError("EMPTY_FILE", f"GPX file is empty: {file_path}")

    session_source = _web_upload_session_cookie_source()
    if not session_source:
        return _web_upload_preview_payload(
            path=file_path,
            name=name,
            description=description,
            privacy=privacy,
            auth_mode="headers_only",
        )

    session_source_name, session_cookies = session_source
    session_cookie_names = sorted(session_cookies.keys())
    headers = _remote_headers()
    headers.update({
        "Accept": "application/json",
        "Origin": "https://ridewithgps.com",
        "Referer": "https://ridewithgps.com/upload",
        "X-Requested-With": "XMLHttpRequest",
    })
    url = f"{RWGPS_API_BASE}/trips?import_type=route"
    file_content = file_path.read_bytes()
    files = {
        "data_file": (file_path.name, file_content, "application/octet-stream"),
    }

    try:
        with httpx.Client(timeout=RWGPS_TIMEOUT_SEC * 2, follow_redirects=False, cookies=session_cookies) as client:
            response = client.post(url, headers=headers, files=files)
    except httpx.TimeoutException as exc:
        raise RWGPSError("timeout", "RWGPS web upload timed out", url=url) from exc
    except httpx.RequestError as exc:
        raise RWGPSError("network_error", f"RWGPS web upload network error: {exc.__class__.__name__}", url=url) from exc

    response_headers = dict(response.headers)
    location = response_headers.get("location")

    if response.status_code in (401, 403) or (300 <= response.status_code < 400 and location and "login" in location.lower()):
        preview = _web_upload_preview_payload(
            path=file_path,
            name=name,
            description=description,
            privacy=privacy,
            auth_mode="browser_session_cookie",
            session_cookie_source=session_source_name,
            session_cookie_names=session_cookie_names,
        )
        preview.update({
            "ok": False,
            "status": "RWGPS_WEB_UPLOAD_REQUIRES_SESSION_COOKIE",
            "response_status": response.status_code,
            "response_location": location,
        })
        return preview

    if response.status_code in (301, 302, 303, 307, 308) and location:
        preview = _web_upload_preview_payload(
            path=file_path,
            name=name,
            description=description,
            privacy=privacy,
            auth_mode="browser_session_cookie",
            session_cookie_source=session_source_name,
            session_cookie_names=session_cookie_names,
        )
        preview.update({
            "ok": True,
            "status": "RWGPS_WEB_UPLOAD_REDIRECTED",
            "response_status": response.status_code,
            "response_location": location,
        })
        return preview

    response_preview = _build_web_upload_response_preview(
        url=url,
        response=response,
        file_name=file_path.name,
        auth_mode="browser_session_cookie",
        session_source_name=session_source_name,
        session_cookie_names=session_cookie_names,
        name=name,
        description=description,
        privacy=privacy,
    )

    return response_preview


def _fetch_track_points(route_id: str) -> list[dict]:
    """Fetch track_points from an RWGPS route via GET with track_points=1."""
    url = f"{RWGPS_API_BASE}/api/v1/routes/{route_id}.json?track_points=1"
    headers = _remote_headers()
    with httpx.Client(timeout=RWGPS_TIMEOUT_SEC) as client:
        resp = client.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    route = data.get("route") or data
    return list(route.get("track_points") or [])


def _copy_route(source_route_id: str) -> str:
    """Copy a route via POST /routes/{id}/copy.json, return new route id."""
    url = f"{RWGPS_API_BASE}/routes/{source_route_id}/copy.json"
    headers = _remote_headers()
    with httpx.Client(timeout=RWGPS_TIMEOUT_SEC) as client:
        resp = client.post(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    route = data.get("route") or data
    rid = str(route.get("id", ""))
    if not rid:
        raise RWGPSError("copy_failed", f"COPY {source_route_id} returned empty id")
    return rid


def _trim_and_normalize_track_points(
    points: list[dict],
    start_m: float,
    end_m: float,
) -> list[dict]:
    """Trim track_points to d ∈ [start_m, end_m] and rebase d to start at 0.

    RWGPS uses the d field (cumulative distance in meters) to compute route
    distance and profile. If we send points with d starting at e.g. 65000 m,
    the route distance will appear as (max_d - min_d) which is correct for
    length, but the d values themselves will confuse the elevation/distance
    profile display. By rebasing so d[0] = 0, the displayed profile matches
    the stage length.
    """
    trimmed = [
        tp for tp in points
        if isinstance(tp, dict) and start_m <= (tp.get("d") or 0) <= end_m
    ]
    if not trimmed:
        return []
    base = trimmed[0].get("d") or 0
    result = []
    for tp in trimmed:
        r = dict(tp)
        raw_d = r.get("d") or 0
        r["d"] = round(raw_d - base, 1)
        result.append(r)
    return result


def import_stage_from_canonical(
    source_route_id: str,
    *,
    start_km: float,
    end_km: float | None,
    name: str,
) -> dict:
    """Full pipeline: copy canonical route → fetch track_points → trim →
    normalize d → update copy → validate.

    This is the replacement for create_route_from_gpx / GPX upload for the
    Tuscany 2026 import use case.  GPX upload creates empty routes; this
    pipeline creates a correctly-geometried stage route.

    Returns:
        dict with ok, route_id, html_url, distance_m, track_points_count,
        diagnostics_log (list of per-step entries).
    """
    if _missing_required_env():
        raise RWGPSError("not_configured", "RWGPS integration not configured")

    diagnostics: list[dict] = []

    # Step 1 — copy
    copied_id = _copy_route(source_route_id)
    diagnostics.append({"step": "COPY", "route_id": copied_id, "endpoint": f"POST /routes/{source_route_id}/copy.json"})

    # Step 2 — fetch track_points from source
    all_tp = _fetch_track_points(source_route_id)
    diagnostics.append({"step": "FETCH", "count_total": len(all_tp)})
    if not all_tp:
        raise RWGPSError("no_track_points", f"Source route {source_route_id} has no track_points")

    # Step 3 — trim
    start_m = start_km * 1000.0
    end_m = end_km * 1000.0 if end_km is not None else float("inf")
    trimmed = _trim_and_normalize_track_points(all_tp, start_m, end_m)
    diagnostics.append({"step": "TRIM", "trimmed": len(trimmed), "range_m": [start_m, end_m]})
    if not trimmed:
        raise RWGPSError("trim_empty", f"Trim d∈[{start_m:.0f},{end_m:.0f}]m produced zero points (total={len(all_tp)})")

    # Step 4 — update
    update_result = update_route(copied_id, {"name": name, "track_points": trimmed})
    if not update_result.get("ok"):
        raise RWGPSError("update_failed", f"Update route {copied_id} failed")
    diagnostics.append({
        "step": "UPDATE",
        "endpoint": "PUT /routes/{id}.json",
        "payload": {"route": {"name": name, "track_points": len(trimmed)}},
    })

    # Step 5 — validate: re-fetch and check geometry
    updated_tp = _fetch_track_points(copied_id)
    updated_route = update_result.get("route") or {}
    distance_m = updated_route.get("distance") or 0
    html_url = f"https://ridewithgps.com/routes/{copied_id}"

    diagnostics.append({
        "step": "VALIDATE",
        "final_distance_m": distance_m,
        "final_track_points": len(updated_tp),
    })

    return {
        "ok": True,
        "route_id": copied_id,
        "html_url": html_url,
        "distance_m": distance_m,
        "distance_km": round(distance_m / 1000.0, 1) if distance_m else None,
        "track_points_count": len(updated_tp),
        "track_points_trimmed": len(trimmed),
        "track_points_total": len(all_tp),
        "name": name,
        "diagnostics": diagnostics,
    }


def update_route(
    route_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    """Update an existing RWGPS route metadata and/or track_points.

    PUT to the legacy endpoint /routes/{id}.json (not /api/v1/) — this is the
    only path that accepts track_points replacement.

    Use nested {"route": {...}} when sending track_points so the geometry is
    actually replaced; flat payloads only update metadata fields.

    Returns the full route object on success.
    """
    if _missing_required_env():
        raise RWGPSError("not_configured", "RWGPS integration not configured")

    url = f"{RWGPS_API_BASE}/routes/{route_id}.json"
    headers = _remote_headers()

    payload: dict[str, Any]
    if "track_points" in updates:
        payload = {"route": updates}
    else:
        payload = updates

    try:
        with httpx.Client(timeout=RWGPS_TIMEOUT_SEC) as client:
            response = client.put(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise RWGPSError("timeout", "RWGPS update timed out", url=url) from exc
    except httpx.RequestError as exc:
        raise RWGPSError("network_error", f"RWGPS network error: {exc.__class__.__name__}", url=url) from exc

    if response.status_code in (401, 403):
        raise RWGPSError("auth_error", f"RWGPS auth failed (HTTP {response.status_code})", status_code=response.status_code, url=url)
    if response.status_code == 429:
        raise RWGPSError("rate_limited", "RWGPS rate limited (HTTP 429)", status_code=response.status_code, url=url)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = response.text[:600]
        raise RWGPSError("http_error", f"RWGPS update error (HTTP {response.status_code})", status_code=response.status_code, url=url, details={"body": body}) from exc

    try:
        result = response.json()
    except ValueError as exc:
        raise RWGPSError("malformed_response", "RWGPS returned invalid JSON", url=url) from exc

    route = _route_object(result)
    if not route:
        route = result.get("route") or result

    return {
        "ok": True,
        "route_id": route_id,
        "route": route,
    }


# ═════════════════════════════════════════════════════════════════════════════
# RWGPS Custom POI (points_of_interest) — dry-run helper
# ═════════════════════════════════════════════════════════════════════════════

RWGPS_POI_CATEGORY_MAP: dict[str, dict[str, Any]] = {
    "groceries":     {"type": "convenience_store", "type_id": 24},
    "food":          {"type": "food",              "type_id": 3},
    "water":         {"type": "water",             "type_id": 1},
    "bike_service":  {"type": "bike_shop",         "type_id": 8},
    "camping":       {"type": "camping",           "type_id": 6},
    "restroom":      {"type": "restroom",          "type_id": 5},
}

RWGPS_POI_FALLBACK = {"type": "generic", "type_id": 0}


def get_rwgps_raw_route(route_id: str | int) -> dict[str, Any]:
    """Fetch the raw RWGPS route object (not the detailed QBot-wrapped version).

    Returns the raw route dict as returned by RWGPS API (route.points_of_interest
    is present if the route has custom POIs).
    """
    route_id_str = str(route_id)
    if _missing_required_env():
        return {"ok": False, "error": "RWGPS not configured", "missing": _missing_required_env()}

    try:
        remote_payload = _request_json(_route_path(route_id_str))
        route = _route_object(remote_payload)
        if not route:
            return {"ok": False, "error": "No route object in RWGPS response"}
        return {"ok": True, "route_id": route_id_str, "route": route, "source": "rwgps_api"}
    except RWGPSError as exc:
        return {"ok": False, "error": str(exc), "kind": exc.kind}


def _rwgps_poi_category(category_label: str) -> dict[str, Any]:
    """Map a QBot category label to RWGPS POI type/type_id."""
    key = category_label.strip().lower()
    mapped = RWGPS_POI_CATEGORY_MAP.get(key)
    if mapped:
        return dict(mapped)
    return dict(RWGPS_POI_FALLBACK)


def _normalize_poi_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _poi_distance_key(lat: float, lng: float, precision: int = 4) -> str:
    return f"{round(lat, precision)}:{round(lng, precision)}"


def _format_poi_for_rwgps(poi: dict[str, Any]) -> dict[str, Any]:
    """Format a single QBot POI dict into RWGPS points_of_interest format."""
    category_info = _rwgps_poi_category(poi.get("category", ""))
    name = str(poi.get("name", "")).strip() or "unnamed"

    desc_parts = []
    if poi.get("category"):
        desc_parts.append(f"cat:{poi['category']}")
    if poi.get("distance_to_track_m") is not None:
        desc_parts.append(f"dist:{poi['distance_to_track_m']:.0f}m")
    if poi.get("nearest_track_km") is not None:
        desc_parts.append(f"km:{poi['nearest_track_km']:.1f}")
    if poi.get("description"):
        short = str(poi["description"])[:80]
        desc_parts.append(short)

    description = " | ".join(desc_parts) if desc_parts else "QBot/OSM"
    description += " | src:QBot/OSM"

    lng = poi.get("lng") or poi.get("lon") or poi.get("longitude")
    return {
        "type": category_info["type"],
        "type_id": category_info["type_id"],
        "name": name,
        "description": description[:200],
        "url": poi.get("url") or "",
        "lat": float(poi["lat"]),
        "lng": float(lng),
    }



# =============================================================================
# POI selection / filtering before sending to RWGPS
# =============================================================================

def select_best_pois(
    poi_candidates: list[dict],
    km_total: float = 0.0,
) -> list[dict]:
    """Filter and select best POIs from route_poi_analyze output.

    WATER:    max 200m from track, deduplicate < 500m route-distance
    FOOD:     max 500m from track, max 1 per 20km, best shop type priority
    ATTRACT:  max 500m from track, max 4 per 100km, by type priority
    TOWNS:    skipped
    """
    FOOD_PRIORITY = {
        "supermarket": 0, "convenience": 1, "grocery": 2, "bakery": 3,
        "deli": 4, "butcher": 5, "greengrocer": 5, "farm": 6,
        "cafe": 7, "restaurant": 8, "fast_food": 9, "bar": 10, "pub": 11,
    }
    ATTRACTION_PRIORITY = {
        "viewpoint": 0, "museum": 1, "gallery": 1,
        "historic": 2, "artwork": 3, "picnic_site": 4,
    }

    def _km(p):
        return float(p.get("route_km") or p.get("nearest_track_km") or 0.0)

    def _dist(p):
        return float(p.get("distance_to_track_m") or 9999.0)

    def _parse_tags(p):
        st = p.get("source_tags") or {}
        if isinstance(st, str):
            r = {}
            for part in st.split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    r[k.strip()] = v.strip()
            return r
        return st if isinstance(st, dict) else {}

    def _food_prio(p):
        tags = _parse_tags(p)
        amenity = str(tags.get("amenity") or "").lower()
        shop = str(tags.get("shop") or "").lower()
        for label, score in FOOD_PRIORITY.items():
            if label in amenity or label in shop:
                return score
        return 99

    def _attr_prio(p):
        tags = _parse_tags(p)
        tourism = str(tags.get("tourism") or "").lower()
        historic = str(tags.get("historic") or "").lower()
        for label, score in ATTRACTION_PRIORITY.items():
            if label in tourism or label in historic:
                return score
        return 99

    # WATER
    water_raw = sorted(
        [p for p in poi_candidates if p.get("category") == "water" and _dist(p) <= 200.0],
        key=lambda p: (_km(p), _dist(p))
    )
    water_out = []
    last_km = -999.0
    for p in water_raw:
        if _km(p) - last_km >= 0.5:
            water_out.append(p)
            last_km = _km(p)

    # FOOD
    food_raw = sorted(
        [p for p in poi_candidates
         if p.get("category") in ("hard_resupply", "soft_food_stop", "food")
         and _dist(p) <= 500.0],
        key=lambda p: (_km(p), _food_prio(p), _dist(p))
    )
    food_out = []
    last_km = -999.0
    for p in food_raw:
        if _km(p) - last_km >= 20.0:
            food_out.append(p)
            last_km = _km(p)

    # ATTRACTIONS
    attr_raw = sorted(
        [p for p in poi_candidates
         if p.get("category") == "attraction"
         and _dist(p) <= 500.0
         and str(p.get("name") or "").strip()],
        key=lambda p: (_attr_prio(p), _dist(p))
    )
    max_attr = max(4, int(km_total / 100.0) * 4) if km_total > 0 else 4
    attr_out = attr_raw[:max_attr]

    try:
        from tools.rwgps.google_places import enrich_food_pois, filter_local_food
        food_enriched = enrich_food_pois(food_out, radius_m=150.0, min_rating=3.8, max_price_level=2)
        food_out = filter_local_food(food_enriched)
    except Exception:
        pass
    result = sorted(water_out + food_out + attr_out, key=_km)
    return result

def prepare_rwgps_poi_update(
    route_id: str | int,
    new_pois: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Dry-run: prepare a payload to update route.points_of_interest without
    executing the PUT.

    Reads the current route, merges existing + new POIs, deduplicates, and
    returns a preview.  Does NOT call the RWGPS PUT endpoint.

    Parameters
    ----------
    route_id : str | int
        RWGPS route ID.
    new_pois : list[dict]
        List of QBot-format POI dicts.  Each must have at minimum:
          - name (str)
          - category (str) — one of the keys in RWGPS_POI_CATEGORY_MAP or
            fallback to generic
          - lat (float)
          - lng (float)
        Optional:
          - description (str)
          - distance_to_track_m (float)
          - nearest_track_km (float)
          - url (str)
    dry_run : bool
        If True (default), the PUT is skipped.

    Returns
    -------
    dict with keys: ok, route_id, route_name, existing_pois_count,
    new_pois_count, duplicates_skipped, duplicate_keys, final_pois_count,
    no_put_executed, payload_preview, warnings
    """
    route_id_str = str(route_id)
    warnings: list[str] = []
    seen_distance_keys: set[str] = set()
    seen_names: set[str] = set()
    duplicates_skipped = 0
    duplicate_examples: list[str] = []

    # 1. GET current route
    raw = get_rwgps_raw_route(route_id_str)
    if not raw.get("ok"):
        return {
            "ok": False,
            "error": raw.get("error", "failed to fetch route"),
            "route_id": route_id_str,
            "no_put_executed": True,
        }

    route = raw["route"]
    route_name = route.get("name") or route.get("title") or f"Route {route_id_str}"

    # 2. Read existing POIs
    existing = [p for p in (route.get("points_of_interest") or []) if isinstance(p, dict)]
    existing_pois: list[dict[str, Any]] = []
    for p in existing:
        formatted = {
            "type": p.get("type", "generic"),
            "type_id": p.get("type_id", 0),
            "name": str(p.get("name", "")).strip() or "unnamed",
            "description": str(p.get("description", "")),
            "url": str(p.get("url", "")),
            "lat": float(p.get("lat", 0)),
            "lng": float(p.get("lng", 0)),
        }
        existing_pois.append(formatted)
        # Seed dedupe keys from existing
        norm_name = _normalize_poi_name(formatted["name"])
        dist_key = _poi_distance_key(formatted["lat"], formatted["lng"])
        seen_names.add(norm_name)
        seen_distance_keys.add(dist_key)

    # 3. Format new POIs and merge
    formatted_new: list[dict[str, Any]] = []
    for poi in new_pois:
        f = _format_poi_for_rwgps(poi)
        norm_name = _normalize_poi_name(f["name"])
        dist_key = _poi_distance_key(f["lat"], f["lng"])

        # Check duplicate by name
        if norm_name in seen_names:
            duplicates_skipped += 1
            if len(duplicate_examples) < 3:
                duplicate_examples.append(f"name:'{f['name']}' (by normalized name)")
            continue

        # Check duplicate by location (lat/lng tolerance)
        if dist_key in seen_distance_keys:
            duplicates_skipped += 1
            if len(duplicate_examples) < 3:
                duplicate_examples.append(f"lat/lng:{dist_key} (by location)")
            continue

        formatted_new.append(f)
        seen_names.add(norm_name)
        seen_distance_keys.add(dist_key)

    # 4. Build merged list
    merged = existing_pois + formatted_new
    final_count = len(merged)

    # 5. Build preview (limit to avoid huge output)
    preview = {
        "route": {
            "name": route_name,
            "points_of_interest": merged,
        }
    }

    return {
        "ok": True,
        "route_id": route_id_str,
        "route_name": route_name,
        "existing_pois_count": len(existing_pois),
        "new_pois_count": len(formatted_new),
        "duplicates_skipped": duplicates_skipped,
        "duplicate_keys": duplicate_examples,
        "final_pois_count": final_count,
        "no_put_executed": dry_run,
        "payload_preview": preview,
        "warnings": warnings,
        "_dry_run_note": "PUT was NOT executed — this is a dry-run preview only.",
    }


def apply_rwgps_poi_update(
    route_id: str | int,
    new_pois: list[dict[str, Any]],
    confirm: bool = False,
    restore_after_test: bool = False,
    backup_path: str | None = None,
) -> dict[str, Any]:
    """Real writer: update route.points_of_interest via PUT.

    Pipeline:
      1. GET current route (read existing POIs)
      2. Backup existing POIs to JSON artifact
      3. Merge existing + new POIs (via prepare_rwgps_poi_update)
      4. PUT merged POIs to RWGPS
      5. GET verify
      6. Optionally restore original POIs (restore_after_test)

    Never modifies track_points, cuesheet, or other route fields.
    """
    route_id_str = str(route_id)
    if not confirm:
        return {
            "ok": False,
            "error": "confirm=True is required for real PUT. Use prepare_rwgps_poi_update for dry-run.",
            "route_id": route_id_str,
            "put_executed": False,
        }

    # 1. GET current route (raw for POI, detailed for track_points count)
    raw = get_rwgps_raw_route(route_id_str)
    if not raw.get("ok"):
        return {"ok": False, "error": raw.get("error", "failed to fetch route"), "route_id": route_id_str}
    route = raw["route"]
    route_name = route.get("name") or route.get("title") or f"Route {route_id_str}"

    # 2. Backup existing POIs
    existing_pois_raw = [p for p in (route.get("points_of_interest") or []) if isinstance(p, dict)]
    backup_ts = datetime.now(timezone.utc)
    backup_data = {
        "route_id": route_id_str,
        "route_name": route_name,
        "backup_timestamp": backup_ts.isoformat(),
        "existing_points_of_interest": existing_pois_raw,
        "count": len(existing_pois_raw),
        "note": "Backup of route.points_of_interest before PUT smoke test",
    }
    if not backup_path:
        backup_path = str(Path(f"/opt/qbot/artifacts/exports/rwgps/rwgps_{route_id_str}_poi_backup_before_R3_2.json"))
    backup_file = Path(backup_path)
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    backup_file.write_text(json.dumps(backup_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Track point count before
    tp_before = len(route.get("track_points") or [])
    existing_pois_count = len(existing_pois_raw)

    # 3. Prepare merged POI list
    dry_result = prepare_rwgps_poi_update(route_id_str, new_pois, dry_run=True)
    if not dry_result.get("ok"):
        return {
            "ok": False,
            "error": dry_result.get("error", "merge failed"),
            "route_id": route_id_str,
            "put_executed": False,
        }

    merged = dry_result["payload_preview"]["route"]["points_of_interest"]
    new_count = dry_result["new_pois_count"]
    dup_skipped = dry_result["duplicates_skipped"]
    final_count = len(merged)

    # 4. PUT merged POIs
    put_payload = {"route": {"points_of_interest": merged}}
    try:
        put_result = update_route(route_id_str, put_payload)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"PUT failed: {exc}",
            "route_id": route_id_str,
            "put_executed": True,
            "put_may_have_partially_succeeded": True,
            "backup_path": backup_path,
        }

    if not put_result.get("ok"):
        return {
            "ok": False,
            "error": f"PUT returned non-ok: {put_result}",
            "route_id": route_id_str,
            "put_executed": True,
            "backup_path": backup_path,
        }

    # 5. GET verify
    verify_raw = get_rwgps_raw_route(route_id_str)
    verify_ok = verify_raw.get("ok", False)
    verify_route = verify_raw.get("route", {})
    verify_pois = [p for p in (verify_route.get("points_of_interest") or []) if isinstance(p, dict)]
    tp_after = len(verify_route.get("track_points") or [])
    verify_count = len(verify_pois)
    verify_has_test_poi = any("QBot TEST POI" in str(p.get("name", "")) for p in verify_pois)

    result = {
        "ok": True,
        "status": "PUT_OK",
        "route_id": route_id_str,
        "route_name": route_name,
        "put_executed": True,
        "backup_path": backup_path,
        "backup_count": existing_pois_count,
        "existing_pois_count": existing_pois_count,
        "new_pois_count": new_count,
        "duplicates_skipped": dup_skipped,
        "final_pois_count": final_count,
        "verify_get_ok": verify_ok,
        "verify_pois_count": verify_count,
        "verify_has_test_poi": verify_has_test_poi,
        "track_points_count_before": tp_before,
        "track_points_count_after": tp_after,
        "track_points_unchanged": tp_before == tp_after,
        "route_id_unchanged": verify_raw.get("route", {}).get("id") == route.get("id"),
        "restore_attempted": False,
        "restored": False,
    }

    # 6. Restore
    if restore_after_test and existing_pois_count > 0:
        restore_payload = {"route": {"points_of_interest": existing_pois_raw}}
        try:
            restore_result = update_route(route_id_str, restore_payload)
            restore_ok = restore_result.get("ok", False)
        except Exception:
            restore_ok = False

        if restore_ok:
            verify2_raw = get_rwgps_raw_route(route_id_str)
            verify2_pois = [p for p in (verify2_raw.get("route", {}).get("points_of_interest") or []) if isinstance(p, dict)]
            result["restore_attempted"] = True
            result["restored"] = True
            result["after_restore_pois_count"] = len(verify2_pois)
            result["restore_matched_original"] = len(verify2_pois) == existing_pois_count
        else:
            result["restore_attempted"] = True
            result["restored"] = False
            result["restore_error"] = "PUT restore failed"
    elif restore_after_test and existing_pois_count == 0:
        result["restore_attempted"] = True
        result["restored"] = True
        result["after_restore_pois_count"] = 0
        result["restore_matched_original"] = True

    return result


# ═════════════════════════════════════════════════════════════════════════════
# RWGPS course_points — on-route writer (R3.4)
# ═════════════════════════════════════════════════════════════════════════════

RWGPS_CP_TYPE_MAP: dict[str, str] = {
    "water": "Water",
    "food": "Food",
    "groceries": "Food",
    "bike_service": "Waypoint",
    "camping": "Camping",
    "restroom": "Restroom",
    "attractions": "Waypoint",
    "warning": "Waypoint",
    "surface": "Waypoint",
}

RWGPS_CP_FALLBACK_TYPE = "Waypoint"

COURSE_POINTS_DEFAULT_MAX_DISTANCE_M = 100


def _format_qbot_poi_as_course_point(poi: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """Convert a QBot-format POI dict to an RWGPS course_point dict.

    Input fields used: lat, lng/lon, name, category (or type), km_on_route.
    Output: {x, y, n, t, d, i} — d=distance_m, i=index (both required by RWGPS).
    """
    lat = float(poi.get("lat", 0))
    lng = float(poi.get("lng", 0) or poi.get("lon", 0))
    name = str(poi.get("name", "")).strip() or "unnamed"

    category_raw = str(poi.get("category", "") or poi.get("type", "")).strip().lower()
    cp_type = RWGPS_CP_FALLBACK_TYPE
    if category_raw:
        for cat_key, cp_t in RWGPS_CP_TYPE_MAP.items():
            if cat_key in category_raw:
                cp_type = cp_t
                break

    # Compute distance in meters from km_on_route
    km = poi.get("km_on_route")
    d_m = round(float(km) * 1000, 1) if km is not None else 0.0

    return {
        "x": round(lng, 6),
        "y": round(lat, 6),
        "n": name[:60],
        "t": cp_type,
        "d": d_m,
        "i": index,
    }


def _course_point_normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _course_point_loc_key(x: float, y: float, precision: int = 4) -> str:
    return f"{round(y, precision)}:{round(x, precision)}"


def _course_point_lat_from_cp(cp: dict[str, Any]) -> float:
    return float(cp.get("y", 0))


def _course_point_lng_from_cp(cp: dict[str, Any]) -> float:
    return float(cp.get("x", 0))


def prepare_rwgps_course_points_update(
    route_id: str | int,
    new_points: list[dict[str, Any]],
    dry_run: bool = True,
    max_distance_to_track_m: int = COURSE_POINTS_DEFAULT_MAX_DISTANCE_M,
) -> dict[str, Any]:
    """Prepare a course_points update payload — dry-run by default.

    Validates each candidate QBot POI:
      - Must have distance_to_track_m <= max_distance_to_track_m
      - Must have valid lat/lng
      - Deduplicated against existing course_points on the route

    Does NOT execute PUT if dry_run=True.
    """
    route_id_str = str(route_id)
    warnings: list[str] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    duplicates_skipped = 0
    duplicate_examples: list[str] = []

    # 1. GET current route
    raw = get_rwgps_raw_route(route_id_str)
    if not raw.get("ok"):
        return {"ok": False, "error": raw.get("error", "failed to fetch route"), "route_id": route_id_str}

    route = raw["route"]
    route_name = route.get("name") or route.get("title") or f"Route {route_id_str}"

    # 2. Read existing course_points
    existing = [cp for cp in (route.get("course_points") or []) if isinstance(cp, dict)]
    seen_names: set[str] = set()
    seen_locs: set[str] = set()
    for cp in existing:
        norm = _course_point_normalize_name(cp.get("n", ""))
        loc = _course_point_loc_key(float(cp.get("x", 0)), float(cp.get("y", 0)))
        seen_names.add(norm)
        seen_locs.add(loc)

    # 3. Process new points
    for poi in new_points:
        dist = poi.get("distance_to_track_m")
        if dist is None:
            rejected.append({**poi, "_reason": "missing distance_to_track_m"})
            warnings.append(f"Rejected '{poi.get('name', '?')}': missing distance_to_track_m")
            continue

        try:
            dist_f = float(dist)
        except (TypeError, ValueError):
            rejected.append({**poi, "_reason": "invalid distance_to_track_m"})
            continue

        if dist_f > max_distance_to_track_m:
            rejected.append({**poi, "_reason": f"off-route ({dist_f:.0f}m > {max_distance_to_track_m}m)"})
            warnings.append(f"Rejected '{poi.get('name', '?')}': {dist_f:.0f}m > {max_distance_to_track_m}m")
            continue

        cp = _format_qbot_poi_as_course_point(poi, index=len(accepted))
        norm = _course_point_normalize_name(cp["n"])
        loc = _course_point_loc_key(cp["x"], cp["y"])

        if norm in seen_names:
            duplicates_skipped += 1
            if len(duplicate_examples) < 3:
                duplicate_examples.append(f"name:'{cp['n']}' (by normalized name)")
            continue

        if loc in seen_locs:
            duplicates_skipped += 1
            if len(duplicate_examples) < 3:
                duplicate_examples.append(f"x/y:{loc} (by location)")
            continue

        accepted.append(cp)
        seen_names.add(norm)
        seen_locs.add(loc)

    # 4. Build merged list
    merged = existing + accepted

    preview = {
        "route": {
            "name": route_name,
            "course_points": merged,
        }
    }

    return {
        "ok": True,
        "route_id": route_id_str,
        "route_name": route_name,
        "existing_course_points_count": len(existing),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "rejected": rejected,
        "duplicates_skipped": duplicates_skipped,
        "duplicate_keys": duplicate_examples,
        "final_course_points_count": len(merged),
        "max_distance_to_track_m": max_distance_to_track_m,
        "no_put_executed": dry_run,
        "payload_preview": preview,
        "warnings": warnings,
        "_dry_run_note": "PUT was NOT executed — this is a dry-run preview only.",
    }


def apply_rwgps_course_points_update(
    route_id: str | int,
    new_points: list[dict[str, Any]],
    confirm: bool = False,
    restore_after_test: bool = False,
    max_distance_to_track_m: int = COURSE_POINTS_DEFAULT_MAX_DISTANCE_M,
    backup_path: str | None = None,
) -> dict[str, Any]:
    """Real writer: update route.course_points via PUT.

    Only accepts points with distance_to_track_m <= max_distance_to_track_m.
    Backs up existing course_points before PUT.  Optionally restores after test.
    Never modifies track_points or other route fields.
    """
    from datetime import datetime, timezone

    route_id_str = str(route_id)
    if not confirm:
        return {
            "ok": False,
            "error": "confirm=True is required for real PUT.",
            "route_id": route_id_str,
            "put_executed": False,
        }

    # 1. GET current route
    raw = get_rwgps_raw_route(route_id_str)
    if not raw.get("ok"):
        return {"ok": False, "error": raw.get("error", "failed to fetch route"), "route_id": route_id_str}
    route = raw["route"]
    route_name = route.get("name") or route.get("title") or f"Route {route_id_str}"

    # 2. Backup existing course_points
    existing_raw = [cp for cp in (route.get("course_points") or []) if isinstance(cp, dict)]
    backup_ts = datetime.now(timezone.utc)
    backup_data = {
        "route_id": route_id_str,
        "route_name": route_name,
        "backup_timestamp": backup_ts.isoformat(),
        "course_points": existing_raw,
        "count": len(existing_raw),
        "note": "Backup of route.course_points before R3.4 PUT test",
    }
    if not backup_path:
        backup_path = str(Path(f"/opt/qbot/artifacts/exports/rwgps/rwgps_{route_id_str}_course_points_backup_before_R3_4.json"))
    backup_file = Path(backup_path)
    backup_file.parent.mkdir(parents=True, exist_ok=True)
    backup_file.write_text(json.dumps(backup_data, indent=2, ensure_ascii=False), encoding="utf-8")

    tp_before = len(route.get("track_points") or [])
    before_count = len(existing_raw)

    # 3. Prepare via dry-run function
    dry = prepare_rwgps_course_points_update(
        route_id_str, new_points, dry_run=True,
        max_distance_to_track_m=max_distance_to_track_m,
    )
    if not dry.get("ok"):
        return {"ok": False, "error": dry.get("error", "prepare failed"), "route_id": route_id_str, "put_executed": False}

    accepted = dry["accepted_count"]
    rejected = dry["rejected_count"]
    duplicates = dry["duplicates_skipped"]
    merged = dry["payload_preview"]["route"]["course_points"]
    final_count = len(merged)

    if accepted == 0:
        return {
            "ok": False,
            "error": f"No points accepted (0/{len(new_points)}). All rejected or duplicates.",
            "route_id": route_id_str,
            "put_executed": False,
            "accepted": 0,
            "rejected": rejected,
            "duplicates_skipped": duplicates,
            "backup_path": backup_path,
        }

    # 4. PUT merged course_points
    put_payload = {"route": {"course_points": merged}}
    try:
        put_result = update_route(route_id_str, put_payload)
    except Exception as exc:
        return {
            "ok": False, "error": f"PUT failed: {exc}",
            "route_id": route_id_str, "put_executed": True,
            "backup_path": backup_path,
        }

    if not put_result.get("ok"):
        return {
            "ok": False, "error": f"PUT returned non-ok: {put_result}",
            "route_id": route_id_str, "put_executed": True,
            "backup_path": backup_path,
        }

    # 5. GET verify
    verify_raw = get_rwgps_raw_route(route_id_str)
    verify_route = verify_raw.get("route", {})
    verify_cps = [cp for cp in (verify_route.get("course_points") or []) if isinstance(cp, dict)]
    tp_after = len(verify_route.get("track_points") or [])
    verify_count = len(verify_cps)

    # Check if our test CPs are visible (by name prefix)
    test_names = [cp["n"] for cp in merged if cp["n"].startswith("QBot TEST")]
    verify_has_test = all(any(tn in str(vcp.get("n", "")) for vcp in verify_cps) for tn in test_names)

    result = {
        "ok": True,
        "status": "PUT_OK",
        "route_id": route_id_str,
        "route_name": route_name,
        "put_executed": True,
        "backup_path": backup_path,
        "before_course_points_count": before_count,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "duplicates_skipped": duplicates,
        "after_put_course_points_count": verify_count,
        "verify_has_test_points": verify_has_test,
        "track_points_count_before": tp_before,
        "track_points_count_after": tp_after,
        "track_points_unchanged": tp_before == tp_after,
        "route_id_unchanged": verify_route.get("id") == route.get("id"),
        "max_distance_to_track_m": max_distance_to_track_m,
        "restore_attempted": False,
        "restored": False,
    }

    # 6. Restore
    if restore_after_test and before_count == 0 and accepted > 0:
        restore_payload = {"route": {"course_points": []}}
        try:
            rr = update_route(route_id_str, restore_payload)
            restore_ok = rr.get("ok", False)
        except Exception:
            restore_ok = False
        if restore_ok:
            verify2 = get_rwgps_raw_route(route_id_str)
            verify2_cps = [cp for cp in (verify2.get("route", {}).get("course_points") or []) if isinstance(cp, dict)]
            result["restore_attempted"] = True
            result["restored"] = True
            result["after_restore_course_points_count"] = len(verify2_cps)
            result["restore_matched_original"] = len(verify2_cps) == before_count
            result["route_name_after_restore"] = verify2.get("route", {}).get("name")
            result["track_points_after_restore"] = len(verify2.get("route", {}).get("track_points") or [])
    elif restore_after_test and before_count > 0 and accepted > 0:
        restore_payload = {"route": {"course_points": existing_raw}}
        try:
            rr = update_route(route_id_str, restore_payload)
            restore_ok = rr.get("ok", False)
        except Exception:
            restore_ok = False
        if restore_ok:
            verify2 = get_rwgps_raw_route(route_id_str)
            verify2_cps = [cp for cp in (verify2.get("route", {}).get("course_points") or []) if isinstance(cp, dict)]
            result["restore_attempted"] = True
            result["restored"] = True
            result["after_restore_course_points_count"] = len(verify2_cps)
            result["restore_matched_original"] = len(verify2_cps) == before_count
    else:
        result["restore_attempted"] = False
        result["restored"] = False

    return result


# ═════════════════════════════════════════════════════════════════════════════
# RWGPS points_of_interest — off-route writer (R3.4B)
# ═════════════════════════════════════════════════════════════════════════════

POI_OFF_ROUTE_MIN_M = 100
POI_OFF_ROUTE_MAX_M = 1000


def _format_poi_for_rwgps_v2(poi: dict[str, Any]) -> dict[str, Any]:
    """Format a QBot-format POI into RWGPS points_of_interest dict."""
    name = str(poi.get("name", "")).strip() or "unnamed"
    desc_parts = []
    if poi.get("category"):
        desc_parts.append(f"cat:{poi['category']}")
    if poi.get("distance_to_track_m") is not None:
        desc_parts.append(f"dist:{poi['distance_to_track_m']:.0f}m")
    if poi.get("nearest_track_km") is not None:
        desc_parts.append(f"km:{poi['nearest_track_km']:.1f}")
    if poi.get("description"):
        desc_parts.append(str(poi["description"])[:80])
    description = " | ".join(desc_parts) if desc_parts else "src:QBot/OSM"
    description += " | src:QBot/OSM"

    category_info = _rwgps_poi_category(poi.get("category", ""))

    return {
        "type": category_info["type"],
        "type_id": category_info["type_id"],
        "name": name[:80],
        "description": description[:200],
        "url": poi.get("url") or "",
        "lat": float(poi.get("lat", 0)),
        "lng": float(poi.get("lng", 0) or poi.get("lon", 0)),
    }


def prepare_rwgps_points_of_interest_update(
    route_id: str | int,
    new_pois: list[dict[str, Any]],
    dry_run: bool = True,
    min_distance_m: int = POI_OFF_ROUTE_MIN_M,
    max_distance_m: int = POI_OFF_ROUTE_MAX_M,
) -> dict[str, Any]:
    """Prepare a points_of_interest update for off-route POI (100-1000m).

    RWGPS API does NOT accept points_of_interest via PUT (confirmed HTTP 500).
    This function still prepares the merge for:
      - dry-run payload preview
      - fallback GPX <wpt> export

    Points with distance_to_track_m < min_distance_m are rejected
    (they should use course_points instead).
    Points with distance_to_track_m > max_distance_m are warned.
    """
    route_id_str = str(route_id)
    warnings: list[str] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    duplicates_skipped = 0
    duplicate_examples: list[str] = []

    raw = get_rwgps_raw_route(route_id_str)
    if not raw.get("ok"):
        return {"ok": False, "error": raw.get("error", "failed to fetch route"), "route_id": route_id_str}

    route = raw["route"]
    route_name = route.get("name") or route.get("title") or f"Route {route_id_str}"

    existing = [p for p in (route.get("points_of_interest") or []) if isinstance(p, dict)]
    seen_names: set[str] = set()
    seen_locs: set[str] = set()
    for p in existing:
        norm = _normalize_poi_name(p.get("name", ""))
        loc = _poi_distance_key(float(p.get("lat", 0)), float(p.get("lng", 0)))
        seen_names.add(norm)
        seen_locs.add(loc)

    for poi in new_pois:
        dist = poi.get("distance_to_track_m")
        if dist is None:
            rejected.append({**poi, "_reason": "missing distance_to_track_m"})
            warnings.append(f"Rejected '{poi.get('name', '?')}': missing distance")
            continue

        try:
            dist_f = float(dist)
        except (TypeError, ValueError):
            rejected.append({**poi, "_reason": "invalid distance"})
            continue

        if dist_f < min_distance_m:
            rejected.append({**poi, "_reason": f"too close ({dist_f:.0f}m < {min_distance_m}m) — use course_points"})
            warnings.append(f"Rejected '{poi.get('name', '?')}': {dist_f:.0f}m < {min_distance_m}m (use course_points)")
            continue

        if dist_f > max_distance_m:
            warnings.append(f"Warning '{poi.get('name', '?')}': {dist_f:.0f}m > {max_distance_m}m — far from route")

        fp = _format_poi_for_rwgps_v2(poi)
        norm = _normalize_poi_name(fp["name"])
        loc = _poi_distance_key(fp["lat"], fp["lng"])

        if norm in seen_names:
            duplicates_skipped += 1
            if len(duplicate_examples) < 3:
                duplicate_examples.append(f"name:'{fp['name']}'")
            continue
        if loc in seen_locs:
            duplicates_skipped += 1
            if len(duplicate_examples) < 3:
                duplicate_examples.append(f"lat/lng:{loc}")
            continue

        accepted.append(fp)
        seen_names.add(norm)
        seen_locs.add(loc)

    merged = existing + accepted

    return {
        "ok": True,
        "route_id": route_id_str,
        "route_name": route_name,
        "existing_pois_count": len(existing),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "rejected": rejected,
        "duplicates_skipped": duplicates_skipped,
        "duplicate_keys": duplicate_examples,
        "final_pois_count": len(merged),
        "min_distance_m": min_distance_m,
        "max_distance_m": max_distance_m,
        "no_put_executed": True,
        "_rwgps_api_note": "RWGPS API does not accept points_of_interest via PUT (confirmed HTTP 500). "
                           "Use fallback GPX <wpt> export instead.",
        "warnings": warnings,
    }


def generate_poi_gpx_wpt(
    pois: list[dict[str, Any]],
    gpx_path: str | None = None,
) -> str:
    """Generate GPX <wpt> elements for off-route POI points.

    These can be added as separate waypoints file or merged into an existing GPX.
    """
    from xml.sax.saxutils import escape

    lines: list[str] = []
    for i, poi in enumerate(pois, 1):
        lat = poi.get("lat", 0)
        lon = poi.get("lng", 0) or poi.get("lon", 0)
        name = escape(str(poi.get("name", f"POI {i}")))
        desc_lines = []
        if poi.get("category"):
            desc_lines.append(f"Category: {poi['category']}")
        if poi.get("distance_to_track_m") is not None:
            desc_lines.append(f"Distance from track: {poi['distance_to_track_m']:.0f}m")
        if poi.get("nearest_track_km") is not None:
            desc_lines.append(f"Nearest track km: {poi['nearest_track_km']:.1f}")
        if poi.get("description"):
            desc_lines.append(str(poi["description"]))
        desc = escape(" | ".join(desc_lines)) if desc_lines else "QBot POI"
        lines.append(f'  <wpt lat="{lat}" lon="{lon}">')
        lines.append(f"    <name>{name}</name>")
        lines.append(f"    <desc>{desc}</desc>")
        lines.append(f"    <type>{poi.get('category', 'generic')}</type>")
        lines.append(f"  </wpt>")

    return "\n".join(lines)


def export_poi_to_gpx_artifact(
    route_id: str | int,
    pois: list[dict[str, Any]],
    project_id: str = "tuscany_2026",
    fmt: str = "gpx_wpt",
) -> dict[str, Any]:
    """Export off-route POIs as a standalone GPX waypoints artifact.

    File: /opt/qbot/artifacts/projects/<project_id>/rwgps_<route_id>_poi_off_route.gpx
    """
    route_id_str = str(route_id)
    wpt_xml = generate_poi_gpx_wpt(pois)

    gpx = f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="QBot R3.4B POI Export" xmlns="http://www.topografix.com/GPX/1/1">
{wpt_xml}
</gpx>"""

    artifact_path = Path("/opt/qbot/artifacts") / "projects" / project_id / f"rwgps_{route_id_str}_poi_off_route.gpx"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(gpx, encoding="utf-8")

    return {
        "ok": True,
        "route_id": route_id_str,
        "project_id": project_id,
        "artifact_path": str(artifact_path),
        "filename": artifact_path.name,
        "poi_count": len(pois),
        "format": fmt,
        "note": "Off-route POIs exported as GPX waypoints (RWGPS API does not support points_of_interest write).",
    }
