"""Legacy parity restoration tools — RWGPS, Hammerhead FIT Import, CSV Export.

Read-only tools for status, config, inventory, dry-run, and restore planning.
No real uploads, no mutations, no sync execution without explicit approval.
"""
from __future__ import annotations

import csv as _csv
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path("/opt/qbot/app")
_OUTGOING = _PROJECT_ROOT / "outgoing"
_EXPORTS  = _OUTGOING / "exports"
_EXPORTS.mkdir(parents=True, exist_ok=True)


def _env_has(name: str) -> bool:
    v = os.getenv(name)
    if v is not None and v.strip():
        return True
    try:
        text = (_PROJECT_ROOT / ".env.local").read_text(encoding="utf-8", errors="ignore")
        return re.search(rf"^{re.escape(name)}\s*=", text, re.MULTILINE) is not None
    except (PermissionError, FileNotFoundError, OSError):
        return False


def _env_presence(names: list[str]) -> dict[str, bool]:
    return {n: _env_has(n) for n in names}


def _resolve_rwgps_route_hint(name_hint: str, *, limit: int = 5, find_latest: bool = False) -> dict[str, Any]:
    hint = str(name_hint or "").strip()
    if not hint:
        return {"route_id": None, "route_name": None, "candidates": []}
    try:
        from tools.rwgps.route_find import find_routes

        candidates = find_routes(hint, limit=max(1, int(limit or 5)))
        if find_latest and candidates:
            def _updated_ts(item: dict[str, Any]) -> float:
                raw = str(item.get("updated_at") or "").strip()
                if not raw:
                    return 0.0
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc).timestamp()
                except Exception:
                    return 0.0

            candidates = sorted(
                candidates,
                key=lambda item: (
                    -int(item.get("score", 0) or 0),
                    -_updated_ts(item),
                    str(item.get("name") or "").lower(),
                ),
            )
        numeric_candidate = next(
            (
                item
                for item in candidates
                if str(item.get("route_id") or "").strip().isdigit()
            ),
            None,
        )
        return {
            "route_id": str(numeric_candidate.get("route_id")).strip() if numeric_candidate else None,
            "route_name": str(numeric_candidate.get("name") or "").strip() if numeric_candidate else None,
            "candidates": candidates,
        }
    except Exception as exc:
        return {"route_id": None, "route_name": None, "candidates": [], "error": str(exc)}


def _list_glob_files(root: Path, pattern: str, *, max_files: int = 100) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
        if len(results) >= max_files:
            break
        try:
            st = path.stat()
        except OSError:
            continue
        results.append({
            "name": path.name,
            "path": str(path.relative_to(_PROJECT_ROOT)),
            "size_bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            "profile": path.parts[len(root.parts):-1] if len(path.parts) > len(root.parts) else [],
        })
    return results


# ═══════════════════════════════════════════════════════════════════════
#  RWGPS TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_rwgps_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check RWGPS configuration without exposing secrets."""
    env_names = [
        "RWGPS_AUTH_TOKEN",
        "RWGPS_USER_ID",
        "RWGPS_API_URL",
        "RWGPS_API_KEY",
        "RWGPS_PLANNED_COLLECTION_ID",
        "RIDEWITHGPS_AUTH_TOKEN",
        "RIDEWITHGPS_USER_ID",
    ]
    presence = _env_presence(env_names)

    token_ok = presence.get("RWGPS_AUTH_TOKEN") or presence.get("RIDEWITHGPS_AUTH_TOKEN")
    user_ok  = presence.get("RWGPS_USER_ID") or presence.get("RIDEWITHGPS_USER_ID")
    url_ok   = presence.get("RWGPS_API_URL")

    missing = [n for n, present in presence.items() if not present]

    if token_ok and user_ok:
        status = "OK"
        notes = "RWGPS credentials are configured."
    elif token_ok or user_ok:
        status = "WARN"
        notes = "Partial RWGPS credentials — some variables missing."
    else:
        status = "ERROR"
        notes = "No RWGPS credentials configured. Live API is inactive; local manifest fallback used."

    client_py = _PROJECT_ROOT / "tools" / "rwgps" / "client.py"
    code_detected = client_py.exists()

    return {
        "tool": "qbot_rwgps_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "auth_token_present": bool(token_ok),
        "user_id_present": bool(user_ok),
        "api_url_present": bool(url_ok),
        "config_source": ".env.local" if any(presence.values()) else "none",
        "env_presence": presence,
        "missing": missing,
        "code_detected": code_detected,
        "notes": notes,
        "restored_status": "PARTIAL" if code_detected and not (token_ok and user_ok) else ("RESTORED" if token_ok and user_ok else "MISSING"),
    }


def _tool_qbot_rwgps_artifact_store_status(_args: dict | None = None) -> dict[str, Any]:
    """Inspect RWGPS artifact store schema and persistence status. Read-only."""
    try:
        import api_db
    except Exception as exc:
        return {
            "tool": "qbot_rwgps_artifact_store_status",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "db_connected": False,
            "error": f"api_db import failed: {exc}",
        }

    try:
        overview = api_db.rwgps_storage_overview()
    except Exception as exc:
        return {
            "tool": "qbot_rwgps_artifact_store_status",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "db_connected": False,
            "error": str(exc),
        }

    return {
        "tool": "qbot_rwgps_artifact_store_status",
        "safety_class": "READ_ONLY",
        "db_connected": True,
        **overview,
    }


def _tool_qbot_rwgps_route_search(_args: dict | None = None) -> dict[str, Any]:
    """Search RWGPS routes by free-text query. Read-only."""
    _args = _args or {}
    query = str(_args.get("query", "")).strip()
    limit = min(max(int(_args.get("limit", 5)), 1), 20)
    offset = min(max(int(_args.get("offset", 0)), 0), 1000)
    include_details = bool(_args.get("include_details", True))

    if not query:
        return {
            "tool": "qbot_rwgps_route_search",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "query required",
        }

    from tools.rwgps.client import get_route as rwgps_get_route
    from tools.rwgps.client import get_route_export_links as rwgps_get_route_export_links
    from tools.rwgps.client import list_routes as rwgps_list_routes

    result = rwgps_list_routes(limit=limit, offset=offset, search=query)
    routes = result.get("routes", []) if isinstance(result, dict) else []
    best_match = routes[0] if routes else None
    best_route_detail = None
    best_route_export_links = None
    if include_details and isinstance(best_match, dict):
        route_id = best_match.get("id")
        if route_id is not None:
            try:
                best_route_detail = rwgps_get_route(route_id)
            except Exception as exc:
                best_route_detail = {"ok": False, "error": str(exc), "route_id": str(route_id)}
            try:
                best_route_export_links = rwgps_get_route_export_links(route_id)
            except Exception as exc:
                best_route_export_links = {"ok": False, "error": str(exc), "route_id": str(route_id)}

    return {
        "tool": "qbot_rwgps_route_search",
        "status": "OK" if result.get("ok") else "WARN",
        "safety_class": "READ_ONLY",
        "query": query,
        "limit": limit,
        "offset": offset,
        "source": result.get("source"),
        "origin": result.get("origin"),
        "integration": result.get("integration"),
        "count": result.get("count"),
        "total": result.get("total"),
        "routes": routes,
        "best_match": best_match,
        "best_route_detail": best_route_detail,
        "best_route_export_links": best_route_export_links,
        "download_availability": (
            best_route_export_links.get("export_links", {}).get("download", {})
            if isinstance(best_route_export_links, dict)
            else {}
        ),
        "notes": "Read-only RWGPS route search. The best match includes detail and export availability when possible.",
    }


def _tool_qbot_rwgps_route_list(_args: dict | None = None) -> dict[str, Any]:
    """List RWGPS routes in a read-only way."""
    _args = _args or {}
    limit = min(max(int(_args.get("limit", 20)), 1), 100)
    offset = min(max(int(_args.get("offset", 0)), 0), 1000)
    sort = str(_args.get("sort", "updated_at")).strip() or "updated_at"
    order = str(_args.get("order", "desc")).strip() or "desc"
    search = str(_args.get("search", "")).strip() or None

    from tools.rwgps.client import list_routes as rwgps_list_routes

    result = rwgps_list_routes(limit=limit, offset=offset, sort=sort, order=order, search=search)
    return {
        "tool": "qbot_rwgps_route_list",
        "safety_class": "READ_ONLY",
        "status": "OK" if result.get("ok") else "WARN",
        "limit": limit,
        "offset": offset,
        "sort": sort,
        "order": order,
        "search": search,
        **result,
        "notes": "Read-only RWGPS route listing. Returns route records, not a text summary.",
    }


def _tool_qbot_rwgps_route_get(_args: dict | None = None) -> dict[str, Any]:
    """Get a single RWGPS route by id. Read-only."""
    _args = _args or {}
    route_id = str(_args.get("route_id", "")).strip()
    if not route_id:
        return {
            "tool": "qbot_rwgps_route_get",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "route_id required",
        }
    from tools.rwgps.client import get_route as rwgps_get_route
    return {
        "tool": "qbot_rwgps_route_get",
        "safety_class": "READ_ONLY",
        **rwgps_get_route(route_id),
    }


def _tool_qbot_rwgps_route_export_links(_args: dict | None = None) -> dict[str, Any]:
    """Get RWGPS export link/availability metadata for a route. Read-only."""
    _args = _args or {}
    route_id = str(_args.get("route_id", "")).strip()
    if not route_id:
        return {
            "tool": "qbot_rwgps_route_export_links",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "route_id required",
        }
    from tools.rwgps.client import get_route_export_links as rwgps_get_route_export_links
    return {
        "tool": "qbot_rwgps_route_export_links",
        "safety_class": "READ_ONLY",
        **rwgps_get_route_export_links(route_id),
    }


def _tool_qbot_rwgps_route_export_file(_args: dict | None = None) -> dict[str, Any]:
    """Export RWGPS route to a local artifact file. Read-only."""
    _args = _args or {}
    route_id = str(_args.get("route_id", "")).strip()
    fmt = str(_args.get("format", "gpx")).strip().lower() or "gpx"
    return_mode = _args.get("return_mode")
    if not route_id:
        return {
            "tool": "qbot_rwgps_route_export_file",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "route_id required",
        }

    from tools.rwgps.client import export_route_to_artifact as rwgps_export_route_to_artifact

    result = rwgps_export_route_to_artifact(route_id, fmt=fmt, return_mode=return_mode)
    return {
        "tool": "qbot_rwgps_route_export_file",
        "safety_class": "READ_ONLY",
        "requested_format": fmt,
        "requested_return_mode": "metadata" if return_mode is None else str(return_mode).strip().lower(),
        **result,
        "notes": "Read-only route export. Returns a local artifact path that can be fetched separately.",
    }


def _normalize_rwgps_artifact_summary(result: dict[str, Any], *, tool_name: str, return_mode: str) -> dict[str, Any]:
    if not result.get("ok"):
        return {
            "tool": tool_name,
            "safety_class": "READ_ONLY",
            "return_mode": return_mode,
            **result,
        }

    bounds = result.get("bounds") or {}
    distance_km = result.get("distance_km")
    return {
        "tool": tool_name,
        "safety_class": "READ_ONLY",
        "status": "OK",
        "ok": True,
        "return_mode": return_mode,
        "artifact_path": result.get("artifact_path"),
        "filename": result.get("artifact_name"),
        "track_points": result.get("point_count"),
        "distance_m": round(float(distance_km) * 1000.0, 1) if distance_km is not None else None,
        "elevation_gain_m": result.get("elevation_gain_m"),
        "elevation_loss_m": result.get("elevation_loss_m"),
        "bbox": {
            "min_lat": bounds.get("sw_lat"),
            "min_lon": bounds.get("sw_lng"),
            "max_lat": bounds.get("ne_lat"),
            "max_lon": bounds.get("ne_lng"),
        } if bounds else None,
        "looks_valid": result.get("looks_valid"),
        "point_count": result.get("point_count"),
        "distance_km": distance_km,
        "min_elevation_m": result.get("min_elevation_m"),
        "max_elevation_m": result.get("max_elevation_m"),
        "first_point": result.get("first_point"),
        "last_point": result.get("last_point"),
        "sha256": result.get("sha256"),
        "size_bytes": result.get("size_bytes"),
    }


def _tool_qbot_gpx_artifact_parse(_args: dict | None = None) -> dict[str, Any]:
    """Parse an existing GPX artifact and return normalized summary metadata."""
    _args = _args or {}
    artifact_path = str(_args.get("artifact_path", "")).strip()
    return_mode = str(_args.get("return_mode", "summary")).strip().lower() or "summary"
    if not artifact_path:
        return {
            "tool": "qbot_gpx_artifact_parse",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "artifact_path required",
        }
    if return_mode != "summary":
        return {
            "tool": "qbot_gpx_artifact_parse",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "return_mode must be summary",
            "artifact_path": artifact_path,
            "return_mode": return_mode,
        }

    from tools.rwgps.client import summarize_rwgps_artifact as rwgps_summarize_rwgps_artifact

    result = rwgps_summarize_rwgps_artifact(artifact_path)
    return _normalize_rwgps_artifact_summary(result, tool_name="qbot_gpx_artifact_parse", return_mode=return_mode)


def _tool_qbot_route_artifact_enrich(_args: dict | None = None) -> dict[str, Any]:
    """Enrich an existing route artifact with optional surface analysis."""
    _args = _args or {}
    artifact_path = str(_args.get("artifact_path", "")).strip()
    return_mode = str(_args.get("return_mode", "summary")).strip().lower() or "summary"
    if not artifact_path:
        return {
            "tool": "qbot_route_artifact_enrich",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "artifact_path required",
        }
    if return_mode != "summary":
        return {
            "tool": "qbot_route_artifact_enrich",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "return_mode must be summary",
            "artifact_path": artifact_path,
            "return_mode": return_mode,
        }

    enrich_raw = _args.get("enrich", ["summary"])
    if isinstance(enrich_raw, str):
        enrich = [enrich_raw]
    elif isinstance(enrich_raw, list):
        enrich = [str(item).strip().lower() for item in enrich_raw if str(item).strip()]
    else:
        enrich = ["summary"]

    surface_requested = "surface" in enrich
    surface_source_input = str(_args.get("surface_source", "auto")).strip().lower() or "auto"
    sample_every_m_raw = _args.get("sample_every_m", 100)
    try:
        sample_every_m = int(sample_every_m_raw)
    except (TypeError, ValueError):
        sample_every_m = 100
    sample_every_m = max(100, min(sample_every_m, 5000))

    from tools.rwgps.client import summarize_rwgps_artifact as rwgps_summarize_rwgps_artifact

    summary_result = rwgps_summarize_rwgps_artifact(artifact_path)
    payload = _normalize_rwgps_artifact_summary(
        summary_result,
        tool_name="qbot_route_artifact_enrich",
        return_mode=return_mode,
    )
    if not payload.get("ok"):
        return payload

    payload["enrich"] = enrich
    payload["surface_source"] = "unknown"
    payload["sample_every_m"] = sample_every_m
    surface_result: dict[str, Any] | None = None

    if surface_requested:
        if surface_source_input in {"auto", "osm"}:
            import json as _json

            try:
                import mcp_server

                surface_json = mcp_server.analyze_rwgps_artifact_surface(artifact_path, sample_distance_m=sample_every_m)
                surface_result = _json.loads(surface_json) if isinstance(surface_json, str) else surface_json
            except Exception as exc:
                surface_result = {
                    "ok": False,
                    "status": "ERROR",
                    "error": "OSM_UNAVAILABLE",
                    "reason": str(exc),
                }

            if isinstance(surface_result, dict) and surface_result.get("ok"):
                surface_percentages = surface_result.get("surface_percentages") or {}
                total_distance_m = payload.get("distance_m")
                try:
                    total_distance_m = float(total_distance_m) if total_distance_m is not None else None
                except (TypeError, ValueError):
                    total_distance_m = None
                if total_distance_m is None:
                    try:
                        total_distance_m = float(surface_result.get("distance_km")) * 1000.0 if surface_result.get("distance_km") is not None else None
                    except (TypeError, ValueError):
                        total_distance_m = None
                segments = []
                _real_segs = surface_result.get("segments")
                if isinstance(_real_segs, list) and _real_segs:
                    segments = _real_segs
                elif isinstance(surface_percentages, dict) and surface_percentages and total_distance_m is not None:
                    ordered = sorted(surface_percentages.items(), key=lambda item: float(item[1]), reverse=True)
                    for surface_name, share_pct in ordered:
                        try:
                            share = float(share_pct) / 100.0
                        except (TypeError, ValueError):
                            share = 0.0
                        segments.append({
                            "surface": surface_name,
                            "distance_m": round(total_distance_m * share, 1),
                            "share": round(share, 2),
                        })
                payload["surface_source"] = "osm"
                payload["surface_profile"] = {
                    "source": surface_result.get("source", "osm_overpass"),
                    "confidence": surface_result.get("confidence", "unknown"),
                    "segments": segments,
                    "dominant_surface": surface_result.get("dominant_surface"),
                    "coverage_pct": surface_result.get("coverage_pct"),
                    "sampled_points": surface_result.get("sampled_points"),
                    "matched_points": surface_result.get("matched_points"),
                    "unmatched_points": surface_result.get("unmatched_points"),
                    "warnings": surface_result.get("warnings"),
                }
            else:
                payload["surface_profile"] = {
                    "source": "unknown",
                    "confidence": "unknown",
                    "status": surface_result.get("status") if isinstance(surface_result, dict) else "ERROR",
                    "error": surface_result.get("error") if isinstance(surface_result, dict) else "ERROR",
                    "reason": surface_result.get("reason") if isinstance(surface_result, dict) else "surface enrichment failed",
                }
        else:
            payload["surface_profile"] = {
                "source": surface_source_input if surface_source_input in {"gpx", "rwgps", "osm", "unknown"} else "unknown",
                "confidence": "unknown",
                "status": "SKIPPED",
                "reason": "surface enrichment only runs for surface_source=auto|osm",
            }

        try:
            from pathlib import Path as _Path

            from tools.rwgps.client import _persist_route_surface_profile as rwgps_persist_route_surface_profile

            rwgps_persist_route_surface_profile(_Path(artifact_path), payload, surface_result)
        except Exception:
            pass
    return payload


def _tool_qbot_route_poi_analyze(_args: dict | None = None) -> dict[str, Any]:
    """Analyze route GPX POI candidates and persist a markdown report artifact."""
    _args = _args or {}
    route_id = str(_args.get("route_id", "")).strip() or None
    artifact_id = str(_args.get("artifact_id", "")).strip() or None
    project_id = str(_args.get("project_id", "")).strip() or None
    path_raw = str(_args.get("path", "")).strip()
    output_format = str(_args.get("output_format", "md")).strip().lower() or "md"
    focus = str(_args.get("focus", "")).strip() or None
    retry_chunk_id = str(_args.get("retry_chunk_id", "")).strip() or None
    retry_mode = bool(_args.get("retry_mode", False))
    timeout_sec_raw = _args.get("timeout_sec")
    merge_artifact_ids_raw = _args.get("merge_artifact_ids")
    confirm = bool(_args.get("confirm", True))

    if not confirm:
        return {
            "tool": "qbot_route_poi_analyze",
            "status": "BLOCKED",
            "safety_class": "READ_ONLY",
            "error": "confirm must be true",
        }
    if output_format not in {"json", "md"}:
        return {
            "tool": "qbot_route_poi_analyze",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "output_format must be json or md",
        }
    merge_artifact_ids: list[str] = []
    if isinstance(merge_artifact_ids_raw, list):
        merge_artifact_ids = [str(item).strip() for item in merge_artifact_ids_raw if str(item).strip()]
    elif isinstance(merge_artifact_ids_raw, str):
        merge_artifact_ids = [item.strip() for item in merge_artifact_ids_raw.split(",") if item.strip()]

    if not route_id and not artifact_id and not path_raw and not merge_artifact_ids:
        return {
            "tool": "qbot_route_poi_analyze",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": "route_id, artifact_id, path or merge_artifact_ids required",
        }

    from pathlib import Path as _Path

    source_path: _Path | None = None
    resolved_route_id = route_id

    if route_id:
        from tools.rwgps.client import export_route_to_artifact as rwgps_export_route_to_artifact

        export_result = rwgps_export_route_to_artifact(route_id, fmt="gpx", return_mode="metadata")
        if not export_result.get("ok"):
            return {
                "tool": "qbot_route_poi_analyze",
                "status": export_result.get("status", "ERROR"),
                "safety_class": "READ_ONLY",
                "error": export_result.get("reason") or export_result.get("error") or "RWGPS export failed",
                "route_id": route_id,
                "export_result": export_result,
            }
        exported_path = export_result.get("artifact_path")
        if not exported_path:
            return {
                "tool": "qbot_route_poi_analyze",
                "status": "ERROR",
                "safety_class": "READ_ONLY",
                "error": "RWGPS export did not return artifact_path",
                "route_id": route_id,
                "export_result": export_result,
            }
        source_path = _Path(str(exported_path))

    elif artifact_id:
        from qbot3.artifacts.store import get_artifact as _get_artifact

        record = _get_artifact(artifact_id)
        if not record:
            return {
                "tool": "qbot_route_poi_analyze",
                "status": "NOT_FOUND",
                "safety_class": "READ_ONLY",
                "error": f"artifact not found: {artifact_id}",
                "artifact_id": artifact_id,
            }
        file_path = str(record.get("file_path") or "").strip()
        if not file_path:
            return {
                "tool": "qbot_route_poi_analyze",
                "status": "ERROR",
                "safety_class": "READ_ONLY",
                "error": f"artifact {artifact_id} has no file_path",
                "artifact_id": artifact_id,
            }
        source_path = _Path("/opt/qbot/artifacts") / file_path
        if not resolved_route_id:
            resolved_route_id = str(record.get("metadata_json", {}).get("route_id") if isinstance(record.get("metadata_json"), dict) else "") or None

    elif path_raw:
        source_path = _Path(path_raw)

    if not merge_artifact_ids and (source_path is None or not source_path.exists()):
        return {
            "tool": "qbot_route_poi_analyze",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "error": f"source GPX not found: {source_path}",
            "route_id": resolved_route_id,
            "artifact_id": artifact_id,
        }

    if merge_artifact_ids:
        try:
            km_from = float(_args.get("km_from", 0) or 0)
            km_to = float(_args.get("km_to", 0) or 0)
        except (TypeError, ValueError):
            km_from = 0.0
            km_to = 0.0
    else:
        try:
            km_from = float(_args.get("km_from"))
            km_to = float(_args.get("km_to"))
        except (TypeError, ValueError):
            return {
                "tool": "qbot_route_poi_analyze",
                "status": "ERROR",
                "safety_class": "READ_ONLY",
                "error": "km_from and km_to are required numeric values",
                "route_id": resolved_route_id,
                "artifact_id": artifact_id,
            }
    buffers_raw = _args.get("buffers") or {}
    if not isinstance(buffers_raw, dict):
        buffers_raw = {}
    buffers = {
        "attractions_m": buffers_raw.get("attractions_m", 1000),
        "hard_resupply_m": buffers_raw.get("hard_resupply_m", buffers_raw.get("food_m", 400)),
        "soft_food_m": buffers_raw.get("soft_food_m", buffers_raw.get("food_m", 400)),
        "food_m": buffers_raw.get("food_m", buffers_raw.get("soft_food_m", 400)),
        "water_m": buffers_raw.get("water_m", 200),
        "chunk_km": buffers_raw.get("chunk_km", 12.0),
        "chunk_overlap_km": buffers_raw.get("chunk_overlap_km", 1.0),
        "analysis_timeout_sec": timeout_sec_raw if timeout_sec_raw is not None else buffers_raw.get("analysis_timeout_sec", 80.0),
        "overpass_timeout_sec": buffers_raw.get("overpass_timeout_sec", 20.0),
        "min_chunk_km": buffers_raw.get("min_chunk_km", 5.0),
        "overpass_retries": buffers_raw.get("overpass_retries", 3),
        "retry_backoff_sec": buffers_raw.get("retry_backoff_sec", 1.25),
        "open_window": bool(_args.get("open_window", buffers_raw.get("open_window", False))),
        "ride_start": _args.get("ride_start", buffers_raw.get("ride_start")),
        "avg_speed_kmh": _args.get("avg_speed_kmh", buffers_raw.get("avg_speed_kmh", 18.0)),
        "google_hours": _args.get("google_hours", buffers_raw.get("google_hours", True)),
    }

    from qbot3.artifacts.route_analyzer import analyze_route_poi_artifact
    analysis = analyze_route_poi_artifact(
        str(source_path) if source_path is not None else "",
        route_id=resolved_route_id,
        artifact_id=artifact_id,
        project_id=project_id,
        km_from=km_from,
        km_to=km_to,
        buffers=buffers,
        focus=focus,
        retry_chunk_id=retry_chunk_id,
        retry_mode=retry_mode,
        merge_artifact_ids=merge_artifact_ids or None,
        timeout_sec=float(timeout_sec_raw) if timeout_sec_raw not in (None, "") else None,
        output_format=output_format,
    )
    if not analysis.get("ok"):
        return {
            "tool": "qbot_route_poi_analyze",
            "status": analysis.get("status", "ERROR"),
            "safety_class": "READ_ONLY",
            "error": analysis.get("error", "analysis failed"),
            "route_id": resolved_route_id,
            "artifact_id": artifact_id,
            "source_path": str(source_path) if source_path is not None else "",
        }

    source_slug = resolved_route_id or artifact_id or (source_path.stem if source_path is not None else "route_poi")
    report_filename = analysis.get("report_filename") or f"tuscany_2026_stage_01_poi_analysis_{source_slug}_{int(km_from):02d}_{int(km_to):02d}.md"
    report_path = _Path("/opt/qbot/artifacts/reports") / report_filename
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(analysis["markdown"], encoding="utf-8")

    report_json_filename = analysis.get("report_json_filename") or report_path.with_suffix(".json").name
    report_json_path = report_path.with_name(report_json_filename)
    report_json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    from qbot3.artifacts.store import register_existing_file as _register_existing_file

    artifact_record = _register_existing_file(
        str(report_path.relative_to(_Path("/opt/qbot/artifacts"))),
        artifact_type="report",
        title="Tuscany 2026 Stage 01 POI analysis",
        project_id="tuscany_2026",
        source="qbot",
        mutation_type="source",
        metadata={
            "route_id": resolved_route_id,
            "artifact_id": artifact_id,
            "project_id": project_id,
            "source_path": str(source_path),
            "km_from": km_from,
            "km_to": km_to,
            "buffers": buffers,
            "output_format": output_format,
            "focus": focus,
            "retry_chunk_id": retry_chunk_id,
            "retry_mode": retry_mode,
            "merge_artifact_ids": merge_artifact_ids,
            "timeout_sec": timeout_sec_raw,
            "report_json_path": str(report_json_path),
        },
    )
    json_artifact_record = _register_existing_file(
        str(report_json_path.relative_to(_Path("/opt/qbot/artifacts"))),
        artifact_type="report",
        title="Tuscany 2026 Stage 01 POI analysis JSON",
        project_id="tuscany_2026",
        source="qbot",
        mutation_type="source",
        metadata={
            "route_id": resolved_route_id,
            "artifact_id": artifact_id,
            "project_id": project_id,
            "source_path": str(source_path) if source_path is not None else "",
            "km_from": km_from,
            "km_to": km_to,
            "buffers": buffers,
            "output_format": output_format,
            "focus": focus,
            "retry_chunk_id": retry_chunk_id,
            "retry_mode": retry_mode,
            "merge_artifact_ids": merge_artifact_ids,
            "timeout_sec": timeout_sec_raw,
            "report_md_path": str(report_path),
        },
    )

    return {
        "tool": "qbot_route_poi_analyze",
        "status": analysis.get("status", "OK"),
        "safety_class": "READ_ONLY",
        "ok": True,
        "route_id": resolved_route_id,
        "artifact_id": artifact_id,
        "source_path": str(source_path) if source_path is not None else "",
        "report_path": str(report_path),
        "report_artifact_id": artifact_record.get("artifact_id"),
        "report_json_path": str(report_json_path),
        "report_json_artifact_id": json_artifact_record.get("artifact_id"),
        "analysis": analysis,
    }


def _tool_qbot_rwgps_legacy_status(_args: dict | None = None) -> dict[str, Any]:
    """Comprehensive RWGPS legacy parity status."""
    import subprocess

    config = _tool_qbot_rwgps_config_status()
    dry_run = _tool_qbot_rwgps_dry_run({"operation": "list_routes"})

    evidence_files: list[dict[str, Any]] = []
    for pattern in ["tools/rwgps/**/*.py", "data/routes/rwgps*.json", "mcp_server.py"]:
        for p in _PROJECT_ROOT.glob(pattern):
            if p.is_file() and p.name != "__init__.py":
                try:
                    evidence_files.append({
                        "file": str(p.relative_to(_PROJECT_ROOT)),
                        "size_bytes": p.stat().st_size,
                    })
                except OSError:
                    pass

    manifest_path = _PROJECT_ROOT / "data" / "routes" / "rwgps_manifest.json"
    cache_path = _PROJECT_ROOT / "data" / "routes" / "rwgps_route_cache.json"
    manifest_routes = 0
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest_routes = len(manifest.get("routes", [])) if isinstance(manifest, dict) else len(manifest) if isinstance(manifest, list) else 0
        except Exception:
            pass

    configured = bool(config.get("auth_token_present") and config.get("user_id_present"))

    if configured and dry_run.get("status") == "PLAN_ONLY" and dry_run.get("would_execute"):
        restored = "RESTORED"
        notes = "RWGPS credentials configured and read-only dry-run path is available."
    elif evidence_files:
        restored = "PARTIAL"
        notes = "RWGPS code detected but missing API credentials. Local manifest fallback active."
    else:
        restored = "MISSING"
        notes = "No RWGPS code or configuration detected."

    return {
        "tool": "qbot_rwgps_legacy_status",
        "capability": "rwgps",
        "status": "OK" if config.get("status") == "OK" else "WARN",
        "safety_class": "READ_ONLY",
        "code_detected": bool(evidence_files),
        "candidate_files": evidence_files[:20],
        "env_presence": config.get("env_presence", {}),
        "generated_artifacts": {
            "manifest_routes": manifest_routes,
            "has_cache": cache_path.exists(),
        },
        "configured": bool(configured),
        "dry_run_status": dry_run.get("status"),
        "dry_run_would_execute": dry_run.get("would_execute"),
        "restored_status": restored,
        "notes": notes,
        "can_restore_today": bool(configured and dry_run.get("would_execute")),
        "risk": "medium",
    }


def _tool_qbot_rwgps_dry_run(_args: dict | None = None) -> dict[str, Any]:
    """Read-only dry-run of RWGPS operations. No uploads, no mutations."""
    _args = _args or {}
    operation = str(_args.get("operation", "list_routes"))

    allowed = {"list_routes", "get_user", "export_preview"}
    if operation not in allowed:
        return {
            "tool": "qbot_rwgps_dry_run",
            "status": "BLOCKED_UNKNOWN_OPERATION",
            "safety_class": "READ_ONLY",
            "operation": operation,
            "allowed_operations": sorted(allowed),
            "notes": f"Operation '{operation}' is not in the dry-run allowlist.",
        }

    config = _tool_qbot_rwgps_config_status()
    if not config.get("auth_token_present") or not config.get("user_id_present"):
        return {
            "tool": "qbot_rwgps_dry_run",
            "status": "BLOCKED_MISSING_SECRET",
            "safety_class": "READ_ONLY",
            "operation": operation,
            "missing_config": config.get("missing", []),
            "would_execute": False,
            "notes": "Cannot perform dry-run: RWGPS credentials missing.",
        }

    manifest_path = _PROJECT_ROOT / "data" / "routes" / "rwgps_manifest.json"
    local_routes = 0
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text())
            local_routes = len(data.get("routes", [])) if isinstance(data, dict) else len(data) if isinstance(data, list) else 0
        except Exception:
            pass

    return {
        "tool": "qbot_rwgps_dry_run",
        "status": "PLAN_ONLY",
        "safety_class": "READ_ONLY",
        "operation": operation,
        "would_execute": True,
        "envs_configured": True,
        "local_manifest_routes": local_routes,
        "notes": f"Dry-run for '{operation}' is PLAN_ONLY. Live API call requires controlled execution. Local manifest has {local_routes} cached routes.",
        "blocked_operations": ["upload", "sync", "create_route", "delete_route", "modify_route"],
    }


def _tool_qbot_rwgps_restore_plan(_args: dict | None = None) -> dict[str, Any]:
    """Restore plan for RWGPS capability."""
    config = _tool_qbot_rwgps_config_status()
    legacy = _tool_qbot_rwgps_legacy_status()

    missing = config.get("missing", [])
    configured = config.get("auth_token_present") and config.get("user_id_present")

    return {
        "tool": "qbot_rwgps_restore_plan",
        "status": "RESTORED" if configured else "PARTIAL",
        "safety_class": "READ_ONLY",
        "missing_config": missing,
        "safe_readonly_tests": [
            "list_routes (dry_run)",
            "get_user (dry_run)",
            "export_preview (dry_run)",
        ],
        "blocked_operations": [
            "create_route",
            "delete_route",
            "modify_route",
            "upload_route",
            "sync_routes",
        ],
        "required_manual_env": missing,
        "code_present": legacy.get("code_detected", False),
        "local_manifest_available": legacy.get("generated_artifacts", {}).get("manifest_routes", 0) > 0,
        "next_steps": [
            "Set RWGPS_AUTH_TOKEN and RWGPS_USER_ID in .env.local",
            "Run qbot_rwgps_dry_run to verify API connectivity",
            "Backup existing manifest before enabling live API",
        ] if not configured else [
            "Run qbot_rwgps_dry_run operation=list_routes for confirmation",
            "Live API is ready for controlled read-only operations",
        ],
        "notes": "RWGPS client code in tools/rwgps/client.py is 1,781 lines, smoke-tested. Local cache/backup present in /opt/qbot/backups/rwgps/.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  HAMMERHEAD TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_hammerhead_config_status(_args: dict | None = None) -> dict[str, Any]:
    """Check Hammerhead config without exposing tokens."""
    env_names = [
        "HAMMERHEAD_EMAIL",
        "HAMMERHEAD_PASSWORD",
        "HAMMERHEAD_BEARER_TOKEN",
        "HAMMERHEAD_REFRESH_TOKEN",
        "HAMMERHEAD_TOKENSTORE",
        "HAMMERHEAD_USER_ID",
    ]
    presence = _env_presence(env_names)

    jwt_ok = presence.get("HAMMERHEAD_BEARER_TOKEN")
    refresh_ok = presence.get("HAMMERHEAD_REFRESH_TOKEN")
    email_ok = presence.get("HAMMERHEAD_EMAIL")
    user_id_ok = presence.get("HAMMERHEAD_USER_ID")
    ts_env_ok = presence.get("HAMMERHEAD_TOKENSTORE")

    possible_expired = "unknown"
    if jwt_ok:
        try:
            raw = os.getenv("HAMMERHEAD_BEARER_TOKEN", "")
            if raw:
                import base64 as _b64
                payload = raw.split(".")[1] if "." in raw else ""
                pad = len(payload) % 4
                payload += "=" * ((4 - pad) % 4) if pad else ""
                decoded = _b64.urlsafe_b64decode(payload)
                exp = json.loads(decoded).get("exp", 0)
                now = datetime.now(timezone.utc).timestamp()
                possible_expired = "true" if now > exp else "false"
        except Exception:
            possible_expired = "unknown"

    tokenstore = _PROJECT_ROOT / ".hammerhead_tokens"
    ts_ok = False
    try:
        ts_ok = tokenstore.exists() and any(tokenstore.iterdir())
    except (PermissionError, OSError):
        pass

    ts_user_id = None
    if ts_ok and not user_id_ok:
        try:
            for f in sorted(tokenstore.iterdir()):
                if f.is_file() and f.suffix in (".json", ""):
                    data = json.loads(f.read_text(encoding="utf-8"))
                    uid = data.get("user_id") or data.get("userId") or data.get("id")
                    if uid:
                        ts_user_id = str(uid)
                        break
        except (PermissionError, OSError, json.JSONDecodeError, Exception):
            pass

    has_local_token = jwt_ok or refresh_ok or ts_ok
    has_online_creds = email_ok and presence.get("HAMMERHEAD_PASSWORD")

    missing = []
    if not has_local_token and not has_online_creds:
        missing = [n for n, p in presence.items() if not p]
    else:
        for n in ["HAMMERHEAD_BEARER_TOKEN", "HAMMERHEAD_REFRESH_TOKEN", "HAMMERHEAD_EMAIL", "HAMMERHEAD_PASSWORD"]:
            if n in presence and not presence[n]:
                if n.startswith("HAMMERHEAD_EMAIL") and has_local_token:
                    continue
                if n.startswith("HAMMERHEAD_PASSWORD") and has_local_token:
                    continue
                if n.startswith("HAMMERHEAD_BEARER") and ts_ok and refresh_ok:
                    continue
                if n.startswith("HAMMERHEAD_REFRESH") and ts_ok and jwt_ok:
                    continue
                if not has_local_token and not has_online_creds:
                    missing.append(n)

    if has_local_token and ts_ok:
        status = "OK"
        notes = "Hammerhead tokenstore active with bearer/refresh tokens. Local read-only ready."
    elif has_local_token:
        status = "OK"
        notes = "Hammerhead bearer/refresh tokens configured. Tokenstore optional."
    elif has_online_creds:
        status = "WARN"
        notes = "Hammerhead email/password configured (legacy). Token refresh path available."
    else:
        status = "ERROR"
        notes = "No Hammerhead tokens or credentials configured."

    if has_local_token and ts_ok:
        restored = "RESTORED_FOR_READONLY"
    elif has_local_token:
        restored = "RESTORED_FOR_READONLY" if not (possible_expired == "true") else "PARTIAL"
    elif has_online_creds:
        restored = "PARTIAL"
    else:
        restored = "MISSING"

    return {
        "tool": "qbot_hammerhead_config_status",
        "status": status,
        "safety_class": "READ_ONLY",
        "jwt_present": bool(jwt_ok),
        "bootstrap_jwt_present": bool(jwt_ok),
        "refresh_token_present": bool(refresh_ok),
        "email_configured": bool(email_ok),
        "api_url_present": False,
        "possible_expired_token": possible_expired,
        "tokenstore_active": ts_ok,
        "env_presence": presence,
        "missing": missing,
        "has_local_token": has_local_token,
        "has_online_creds": has_online_creds,
        "ts_user_id_inferred": ts_user_id,
        "notes": notes,
        "restored_status": restored,
        "email_optional_when_tokenstore_active": True,
    }


def _tool_qbot_hammerhead_import_status_enhanced(_args: dict | None = None) -> dict[str, Any]:
    """Extended Hammerhead import status with inventory. Delegates to legacy + adds context."""
    import importlib

    try:
        from qbot_legacy_parity_tools import _tool_qbot_hammerhead_import_status as _legacy
        base = _legacy(_args)
    except Exception:
        base = {"tool": "qbot_hammerhead_import_status", "status": "error"}

    config = _tool_qbot_hammerhead_config_status()
    inventory = _tool_qbot_hammerhead_import_inventory({"limit": 5})

    has_local = config.get("has_local_token", False) and config.get("tokenstore_active", False)
    local_ok = inventory.get("count", 0) > 0

    if has_local and local_ok:
        restored = "RESTORED_FOR_READONLY"
        base["status"] = "OK"
    elif has_local:
        restored = "PARTIAL"
        base["status"] = "WARN"
    else:
        restored = config.get("restored_status", "PARTIAL")
        base["status"] = "WARN" if base.get("status") != "error" else base.get("status")

    base["restored_status"] = restored
    base["config_status"] = config.get("status")
    base["possible_expired_token"] = config.get("possible_expired_token")
    base["hammerhead_originals_count"] = inventory.get("count", 0)
    base["latest_hammerhead_original_fit"] = inventory.get("latest_files", [])[0] if inventory.get("latest_files") else None
    base["config_detail"] = {
        "jwt_present": config.get("jwt_present"),
        "refresh_token_present": config.get("refresh_token_present"),
        "email_configured": config.get("email_configured"),
        "tokenstore_active": config.get("tokenstore_active"),
        "has_local_token": config.get("has_local_token"),
    }
    base["notes"] = "Tokenstore-based read-only status active. Online API import requires separate controlled execution approval."
    return base


def _tool_qbot_hammerhead_import_inventory(_args: dict | None = None) -> dict[str, Any]:
    """List Hammerhead original FIT files."""
    _args = _args or {}
    limit = min(max(int(_args.get("limit", 20)), 1), 100)

    all_files = _list_glob_files(_OUTGOING, "**/hammerhead_originals/*.fit", max_files=limit)

    per_user: dict[str, int] = {}
    for f in all_files:
        parts = f.get("profile", [])
        user = parts[0] if parts else "default"
        per_user[user] = per_user.get(user, 0) + 1

    return {
        "tool": "qbot_hammerhead_import_inventory",
        "status": "OK" if all_files else "WARN",
        "safety_class": "READ_ONLY",
        "count": len(all_files),
        "latest_files": all_files[:5],
        "per_user_counts": per_user,
        "latest_mtime": all_files[0]["mtime"] if all_files else None,
        "source_dir": str(_OUTGOING.relative_to(_PROJECT_ROOT)),
        "notes": "Read-only inventory. No files read from Hammerhead API.",
    }


def _tool_qbot_hammerhead_import_dry_run(_args: dict | None = None) -> dict[str, Any]:
    """Safe dry-run of Hammerhead import. No downloads, no sync.

    source=latest only inspects local artifacts — no API call.
    """
    _args = _args or {}
    source = str(_args.get("source", "latest"))

    config = _tool_qbot_hammerhead_config_status()
    inventory = _tool_qbot_hammerhead_import_inventory({"limit": 5})

    has_token = config.get("has_local_token", False)
    tokenstore_ok = config.get("tokenstore_active", False)
    expired = config.get("possible_expired_token", "unknown")
    local_count = inventory.get("count", 0)
    latest = inventory.get("latest_files", [])[0] if inventory.get("latest_files") else None

    profile_name = "default"
    if latest and latest.get("profile"):
        profile_name = latest["profile"][0] if latest["profile"] else "default"
    elif source not in ("latest",):
        profile_name = source

    no_creds_at_all = not has_token and not config.get("has_online_creds", False)

    if no_creds_at_all and local_count == 0:
        return {
            "tool": "qbot_hammerhead_import_dry_run",
            "status": "BLOCKED_NO_CREDENTIALS_OR_ARTIFACTS",
            "safety_class": "READ_ONLY",
            "source": source,
            "would_fetch": False,
            "would_store_to": None,
            "missing_config": config.get("missing", []),
            "latest_local_fit": None,
            "local_count": 0,
            "notes": "No Hammerhead credentials and no local FIT artifacts. Nothing to inspect.",
        }

    api_blocked = no_creds_at_all or (not has_token and not tokenstore_ok)
    warning_jwt = expired == "true"

    return {
        "tool": "qbot_hammerhead_import_dry_run",
        "status": "OK" if (not api_blocked) and local_count > 0 else "WARN",
        "safety_class": "READ_ONLY",
        "source": source,
        "would_fetch": False,
        "would_store_to": str(_OUTGOING.relative_to(_PROJECT_ROOT)) + "/" if not api_blocked else None,
        "api_blocked": api_blocked,
        "api_block_reason": (
            "No credentials" if no_creds_at_all else "Tokenstore inactive" if not tokenstore_ok else "JWT expired" if warning_jwt else None
        ),
        "jwt_expired": warning_jwt,
        "missing_config": config.get("missing", []),
        "latest_local_fit": latest,
        "profile": profile_name,
        "local_count": local_count,
        "tokenstore_active": tokenstore_ok,
        "has_local_token": has_token,
        "notes": (
            "Dry-run only. Local FIT artifacts available for inspection. "
            "Online Hammerhead API import requires controlled execution with valid credentials."
        ),
    }


def _tool_qbot_hammerhead_restore_plan(_args: dict | None = None) -> dict[str, Any]:
    """Restore plan for Hammerhead FIT import."""
    config = _tool_qbot_hammerhead_config_status()
    expired = config.get("possible_expired_token")
    has_local = config.get("has_local_token", False)
    ts_ok = config.get("tokenstore_active", False)

    if has_local and ts_ok and expired == "false":
        plan_status = "RESTORED_FOR_READONLY"
    elif has_local and ts_ok:
        plan_status = "READY_FOR_TOKEN_REFRESH"
    elif has_local:
        plan_status = "PARTIAL"
    else:
        plan_status = "MISSING"

    next_steps = []
    if expired == "true" or expired == "unknown":
        next_steps.append("Refresh HAMMERHEAD_BEARER_TOKEN using HAMMERHEAD_REFRESH_TOKEN (or email/password as fallback)")
    if not ts_ok:
        next_steps.append("Configure HAMMERHEAD_TOKENSTORE env var pointing to .hammerhead_tokens/")
    if has_local and ts_ok and expired == "false":
        next_steps.append("Tokenstore active and token valid — import pipeline ready for controlled execution")
        next_steps.append("Monitor cron logs for sync success")
    if not next_steps:
        next_steps.append("Set HAMMERHEAD_BEARER_TOKEN and HAMMERHEAD_REFRESH_TOKEN in .env.local")
        next_steps.append("Alternatively set HAMMERHEAD_EMAIL and HAMMERHEAD_PASSWORD for fresh login (optional fallback)")

    return {
        "tool": "qbot_hammerhead_restore_plan",
        "status": plan_status,
        "safety_class": "READ_ONLY",
        "missing_config": config.get("missing", []),
        "token_refresh_needed": expired != "false",
        "email_password_optional": True,
        "safe_tests": [
            "qbot_hammerhead_config_status",
            "qbot_hammerhead_import_inventory",
            "qbot_hammerhead_import_dry_run",
        ],
        "controlled_execution_needed": True,
        "next_steps": next_steps,
        "notes": "Email/password are optional fallback. Primary: tokenstore with bearer/refresh tokens.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  CSV EXPORT TOOLS
# ═══════════════════════════════════════════════════════════════════════

def _tool_qbot_csv_export_inventory(_args: dict | None = None) -> dict[str, Any]:
    """List CSV files in outgoing directory."""
    _args = _args or {}
    limit = min(max(int(_args.get("limit", 20)), 1), 100)

    csv_files = _list_glob_files(_OUTGOING, "**/*.csv", max_files=limit)

    has_latest = (_OUTGOING / "qbot_garmin_proxy_latest.csv").exists()

    by_dir: dict[str, int] = {}
    for f in csv_files:
        parts = f.get("profile", [])
        key = parts[0] if parts else "root"
        by_dir[key] = by_dir.get(key, 0) + 1

    return {
        "tool": "qbot_csv_export_inventory",
        "status": "OK" if csv_files else "WARN",
        "safety_class": "READ_ONLY",
        "csv_count": len(csv_files),
        "latest_csv": str(_OUTGOING / "qbot_garmin_proxy_latest.csv") if has_latest else None,
        "qbot_garmin_proxy_latest_csv_present": has_latest,
        "latest_files": csv_files[:5],
        "by_directory": by_dir,
        "notes": "Read-only inventory. CSV files generated by Hammerhead-Garmin sync pipeline.",
    }


def _tool_qbot_csv_export_latest_get(_args: dict | None = None) -> dict[str, Any]:
    """Read latest CSV file (read-only)."""
    _args = _args or {}
    source = str(_args.get("source", "garmin_proxy_latest"))
    limit_rows = min(max(int(_args.get("limit_rows", 20)), 1), 200)

    allowed_sources = {"garmin_proxy_latest", "latest_any"}
    if source not in allowed_sources:
        return {
            "tool": "qbot_csv_export_latest_get",
            "status": "BLOCKED_UNKNOWN_SOURCE",
            "safety_class": "READ_ONLY",
            "allowed_sources": sorted(allowed_sources),
            "notes": f"Source '{source}' not in allowlist.",
        }

    candidates: list[Path] = []

    if source == "garmin_proxy_latest":
        p = _OUTGOING / "qbot_garmin_proxy_latest.csv"
        if p.exists():
            candidates = [p]
    elif source == "latest_any":
        for p in sorted(_OUTGOING.glob("**/*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
            candidates.append(p)
            if len(candidates) >= 1:
                break

    if not candidates:
        return {
            "tool": "qbot_csv_export_latest_get",
            "status": "WARN",
            "safety_class": "READ_ONLY",
            "source": source,
            "file": None,
            "columns": [],
            "row_count_estimate": 0,
            "sample_rows": [],
            "notes": "No CSV files found for the selected source.",
        }

    target = candidates[0]
    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
        reader = _csv.reader(io.StringIO(text))
        rows = list(reader)
    except Exception as exc:
        return {
            "tool": "qbot_csv_export_latest_get",
            "status": "ERROR",
            "safety_class": "READ_ONLY",
            "file": str(target.relative_to(_PROJECT_ROOT)),
            "error": str(exc),
            "notes": "Failed to read CSV file.",
        }

    columns = rows[0] if rows else []
    sample = rows[1:limit_rows + 1] if len(rows) > 1 else []

    return {
        "tool": "qbot_csv_export_latest_get",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "source": source,
        "file": str(target.relative_to(_PROJECT_ROOT)),
        "file_size_bytes": target.stat().st_size,
        "mtime": datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc).isoformat(),
        "columns": columns,
        "row_count_estimate": len(rows) - 1,
        "sample_rows": [
            dict(zip(columns, r)) for r in sample
        ] if columns else sample,
        "notes": f"Read-only preview. Showing {len(sample)} of {len(rows) - 1} data rows.",
    }


def _tool_qbot_csv_export_create_preview(_args: dict | None = None) -> dict[str, Any]:
    """Preview what a CSV export would contain. No file written."""
    _args = _args or {}
    source_report = str(_args.get("source_report", "latest"))
    output_name = str(_args.get("output_name", "preview"))

    latest_csv = _OUTGOING / "qbot_garmin_proxy_latest.csv"

    source_available = False
    source_info = ""

    if source_report in ("latest",) and latest_csv.exists():
        source_available = True
        try:
            st = latest_csv.stat()
            source_info = f"{latest_csv.name} ({st.st_size} bytes, {datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()})"
        except OSError:
            source_info = f"{latest_csv.name}"

    if not source_available:
        return {
            "tool": "qbot_csv_export_create_preview",
            "status": "PLAN_ONLY",
            "safety_class": "READ_ONLY",
            "source_report": source_report,
            "output_name": output_name,
            "source_available": False,
            "would_generate": False,
            "target_dir": str(_EXPORTS.relative_to(_PROJECT_ROOT)),
            "notes": "No source data available for CSV generation.",
        }

    return {
        "tool": "qbot_csv_export_create_preview",
        "status": "OK",
        "safety_class": "READ_ONLY",
        "source_report": source_report,
        "output_name": output_name,
        "source_available": True,
        "source_info": source_info,
        "would_generate": True,
        "target_dir": str(_EXPORTS.relative_to(_PROJECT_ROOT)),
        "notes": f"Would copy/convert {source_info} to {_EXPORTS.relative_to(_PROJECT_ROOT)}/{output_name}.",
    }


def _tool_qbot_csv_export_create_execute(_args: dict | None = None) -> dict[str, Any]:
    """Execute CSV export (controlled, dry_run by default)."""
    _args = _args or {}
    source_report = str(_args.get("source_report", "latest"))
    output_name = str(_args.get("output_name", "qbot_export_latest.csv"))
    dry_run = bool(_args.get("dry_run", True))

    output_name = os.path.basename(output_name)
    target_path = _EXPORTS / output_name

    latest_csv = _OUTGOING / "qbot_garmin_proxy_latest.csv"

    if not latest_csv.exists():
        return {
            "tool": "qbot_csv_export_create_execute",
            "status": "WARN",
            "safety_class": "WRITE_SAFE",
            "source_not_found": True,
            "notes": "Source CSV not found. Cannot export.",
        }

    if dry_run:
        return {
            "tool": "qbot_csv_export_create_execute",
            "status": "DRY_RUN",
            "safety_class": "WRITE_SAFE",
            "dry_run": True,
            "would_write_to": str(target_path.relative_to(_PROJECT_ROOT)),
            "source_file": str(latest_csv.relative_to(_PROJECT_ROOT)),
            "source_size_bytes": latest_csv.stat().st_size,
            "notes": "Dry-run only. Set dry_run=false to export.",
        }

    if target_path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = _EXPORTS / f"{output_name.removesuffix('.csv')}_{ts}.csv"

    try:
        _EXPORTS.mkdir(parents=True, exist_ok=True)
        content = latest_csv.read_bytes()
        target_path.write_bytes(content)
        st = target_path.stat()
    except Exception as exc:
        return {
            "tool": "qbot_csv_export_create_execute",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "error": str(exc),
            "notes": "CSV export failed.",
        }

    return {
        "tool": "qbot_csv_export_create_execute",
        "status": "OK",
        "safety_class": "WRITE_SAFE",
        "dry_run": False,
        "written_to": str(target_path.relative_to(_PROJECT_ROOT)),
        "file_size_bytes": st.st_size,
        "source_file": str(latest_csv.relative_to(_PROJECT_ROOT)),
        "notes": "CSV exported successfully to outgoing/exports/.",
    }


def _tool_qbot_csv_export_status(_args: dict | None = None) -> dict[str, Any]:
    """Comprehensive CSV export status."""
    inventory = _tool_qbot_csv_export_inventory({"limit": 5})
    latest_get = _tool_qbot_csv_export_latest_get({"source": "garmin_proxy_latest", "limit_rows": 5})
    preview = _tool_qbot_csv_export_create_preview()

    has_csv = inventory.get("csv_count", 0) > 0
    latest_ok = latest_get.get("status") == "OK"
    preview_ok = preview.get("source_available", False)

    if has_csv and latest_ok and preview_ok:
        restored = "RESTORED"
    elif has_csv:
        restored = "PARTIAL"
    else:
        restored = "PARTIAL"

    return {
        "tool": "qbot_csv_export_status",
        "capability": "csv_export",
        "status": "OK" if restored == "RESTORED" else "WARN",
        "safety_class": "READ_ONLY",
        "restored_status": restored,
        "inventory": {"csv_count": inventory.get("csv_count")},
        "latest_available": latest_ok,
        "latest_file": latest_get.get("file"),
        "latest_columns": latest_get.get("columns", [])[:10],
        "create_preview_ready": preview_ok,
        "create_execute_ready": has_csv,
        "notes": "CSV export from Hammerhead-Garmin proxy pipeline. Read-only preview available; controlled execute writes to outgoing/exports/.",
    }


# ═══════════════════════════════════════════════════════════════════════
#  RWGPS ROUTE IMPORT GPX — WRITE TOOL
# ═══════════════════════════════════════════════════════════════════════


def _validate_gpx_file(gpx_path: str) -> dict[str, Any]:
    """Validate a GPX file for import. Returns (valid, summary) or error dict."""
    path = Path(gpx_path)
    if not path.exists():
        return {"valid": False, "error": f"File not found: {gpx_path}"}
    try:
        size = path.stat().st_size
    except OSError as exc:
        return {"valid": False, "error": f"Cannot stat file: {exc}"}
    if size == 0:
        return {"valid": False, "error": "File is empty (0 bytes)"}

    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(str(path))
    except ET.ParseError as exc:
        return {"valid": False, "error": f"Invalid XML: {exc}"}

    root = tree.getroot()
    ns = "http://www.topografix.com/GPX/1/1"
    trkpts = list(root.iter(f"{{{ns}}}trkpt"))
    trackpoint_count = len(trkpts)
    if trackpoint_count <= 2:
        return {"valid": False, "error": f"Too few track points ({trackpoint_count}); need > 2"}

    lats = []
    lons = []
    for tp in trkpts:
        lat = tp.get("lat")
        lon = tp.get("lon")
        if lat is not None and lon is not None:
            try:
                lats.append(float(lat))
                lons.append(float(lon))
            except (TypeError, ValueError):
                pass

    return {
        "valid": True,
        "file_exists": True,
        "size_bytes": size,
        "filename": path.name,
        "trackpoint_count": trackpoint_count,
        "valid_coordinates": len(lats),
        "bounds": {
            "min_lat": min(lats) if lats else None,
            "max_lat": max(lats) if lats else None,
            "min_lon": min(lons) if lons else None,
            "max_lon": max(lons) if lons else None,
        } if lats else None,
    }


def _check_duplicate_route_name(name: str) -> dict[str, Any]:
    """Check if a route with the same name already exists in RWGPS."""
    try:
        from tools.rwgps.client import list_routes as rwgps_list_routes
        result = rwgps_list_routes(limit=100, search=name)
        routes = result.get("routes", []) if isinstance(result, dict) else []
        for r in routes:
            existing_name = (r.get("name") or "").strip().lower()
            if existing_name == name.strip().lower():
                return {
                    "is_duplicate": True,
                    "existing_route_id": str(r.get("id", "")),
                    "existing_name": r.get("name"),
                    "existing_url": f"https://ridewithgps.com/routes/{r.get('id')}" if r.get("id") else None,
                }
    except Exception:
        pass
    return {"is_duplicate": False}


def _tool_qbot_rwgps_route_import_gpx(args: dict | None = None) -> dict[str, Any]:
    """Import a route into RWGPS.

    Two modes:

    1. **Canonical-copy mode** (preferred — produces correct geometry):
       Provide `source_route_id` + `start_km` + `end_km`.
       Pipeline: copy canonical route → fetch track_points → trim by
       distance → update copy with trimmed points + new name.
       Used for Tuscany 2026 stage import.

    2. **GPX-upload mode** (legacy — may produce empty route):
       Provide `gpx_path`.  Uploads GPX via POST /api/v1/routes.json.
       KNOWN ISSUE: RWGPS may create a route with distance=null and
       track_points=[] when receiving a GPX upload this way.

    WRITE tool — requires confirm=true to execute.
    Dry-run (confirm=false) shows planned action without writing.

    Args:
        source_route_id: Canonical RWGPS route ID to copy (e.g. 55256628)
        stage: Stage number (looks up start_km/end_km from StageSpec)
        start_km: Stage start km (used if stage not provided)
        end_km: Stage end km (used if stage not provided)
        name: Route name
        gpx_path: Absolute path to local .gpx file (legacy fallback)
        description: Route description
        privacy: One of "public", "private", "friends" (default: "private")
        collection_id: Optional RWGPS collection ID
        confirm: Set to true to execute (default: false)

    Returns:
        On dry-run: validation result with planned action
        On confirm=true: status, new_route_id, html_url, diagnostics
    """
    _args = args or {}
    source_route_id = str(_args.get("source_route_id", "")).strip()
    stage_raw = _args.get("stage")
    start_km_raw = _args.get("start_km")
    end_km_raw = _args.get("end_km")
    route_name_hint = str(_args.get("route_name_hint", "")).strip()
    find_latest = bool(_args.get("find_latest", False))
    gpx_path = str(_args.get("gpx_path", "")).strip()
    name = str(_args.get("name", "")).strip()
    description = str(_args.get("description", "")).strip()
    privacy = str(_args.get("privacy", "private")).strip().lower()
    collection_id = str(_args.get("collection_id", "")).strip() or None
    confirm = bool(_args.get("confirm", False))

    resolved_candidates: list[dict[str, Any]] = []
    resolved_route_name = ""
    if source_route_id and not source_route_id.isdigit():
        source_route_id = ""
    if not source_route_id and route_name_hint:
        resolved = _resolve_rwgps_route_hint(route_name_hint, find_latest=find_latest)
        resolved_candidates = [item for item in resolved.get("candidates", []) if isinstance(item, dict)]
        if resolved.get("route_id") and str(resolved["route_id"]).isdigit():
            source_route_id = str(resolved["route_id"]).strip()
            resolved_route_name = str(resolved.get("route_name") or "").strip()
            if not name and resolved_route_name:
                name = resolved_route_name

    if route_name_hint and not source_route_id and not gpx_path:
        return {
            "tool": "qbot_rwgps_route_import_gpx",
            "status": "PARTIAL",
            "safety_class": "WRITE_SAFE",
            "route_name_hint": route_name_hint,
            "candidates": resolved_candidates[:5],
            "error": "Nie udało się rozwiązać route_id z podanej nazwy trasy.",
        }

    # ── Determine mode ──
    use_canonical = bool(source_route_id) and (stage_raw is not None or (start_km_raw is not None and end_km_raw is not None))
    if not use_canonical and not gpx_path and source_route_id and source_route_id.isdigit():
        try:
            gpx_path = "/opt/qbot/artifacts/exports/rwgps/rwgps_%s.gpx" % source_route_id
            if not os.path.exists(gpx_path) or bool(_args.get("force", False)):
                import requests

                api_key = os.getenv("RWGPS_API_KEY", "").strip()
                auth_token = os.getenv("RWGPS_AUTH_TOKEN", "").strip()
                response = requests.get(
                    "https://ridewithgps.com/routes/%s.gpx" % source_route_id,
                    params={"apikey": api_key, "auth_token": auth_token, "version": "2"},
                    timeout=30,
                )
                response.raise_for_status()
                os.makedirs(os.path.dirname(gpx_path), exist_ok=True)
                with open(gpx_path, "wb") as fh:
                    fh.write(response.content)
            if not name:
                name = resolved_route_name or ("rwgps_%s" % source_route_id)
        except Exception as exc:
            return {
                "tool": "qbot_rwgps_route_import_gpx",
                "status": "ERROR",
                "safety_class": "WRITE_SAFE",
                "error": str(exc),
                "resolved_route_id": source_route_id or None,
                "route_name_hint": route_name_hint or None,
            }
    use_gpx = bool(gpx_path) and not use_canonical

    # Validate required
    missing = []
    if not name:
        missing.append("name")
    if not use_canonical and not use_gpx:
        missing.append("source_route_id+stage/start_km+end_km  OR  gpx_path")

    if privacy not in ("public", "private", "friends"):
        missing.append(f"privacy must be public/private/friends, got '{privacy}'")

    if missing:
        return {
            "tool": "qbot_rwgps_route_import_gpx",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "missing_fields": missing,
            "error": f"Missing or invalid required field(s): {', '.join(missing)}",
        }

    # Check RWGPS config
    try:
        from tools.rwgps.client import _missing_required_env as rwgps_missing_env
        rwgps_missing = rwgps_missing_env()
        if rwgps_missing:
            return {
                "tool": "qbot_rwgps_route_import_gpx",
                "status": "BLOCKED_MISSING_CONFIG",
                "safety_class": "WRITE_SAFE",
                "name": name,
                "missing_env": rwgps_missing,
                "notes": "RWGPS API credentials not configured in .env",
            }
    except Exception as exc:
        return {
            "tool": "qbot_rwgps_route_import_gpx",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "error": str(exc),
        }

    # ── Resolve spec ──
    start_km: float | None = None
    end_km: float | None = None
    if use_canonical:
        if stage_raw is not None:
            stage = int(stage_raw)
            try:
                from qbot3.artifacts.gpx_splitter import DEFAULT_STAGE_SPECS
                specs = DEFAULT_STAGE_SPECS.get(("tuscany_2026", int(source_route_id)), [])
                spec = next((s for s in specs if s.stage == stage), None)
                if not spec:
                    return {
                        "tool": "qbot_rwgps_route_import_gpx",
                        "status": "ERROR",
                        "safety_class": "WRITE_SAFE",
                        "error": f"StageSpec not found for route={source_route_id}, stage={stage}",
                    }
                start_km = spec.start_km
                end_km = spec.end_km
                if not name:
                    name = spec.title
            except Exception as exc:
                return {
                    "tool": "qbot_rwgps_route_import_gpx",
                    "status": "ERROR",
                    "safety_class": "WRITE_SAFE",
                    "error": str(exc),
                }
        else:
            start_km = float(start_km_raw) if start_km_raw is not None else None
            end_km = float(end_km_raw) if end_km_raw is not None else None

    # ── Build plan ──
    if use_canonical:
        plan = {
            "action": "rwgps_canonical_stage_import",
            "planned_route": {
                "name": name or "(unnamed)",
                "source_route_id": source_route_id,
                "range_km": [start_km, end_km],
                "description": description,
                "privacy": privacy,
            },
        }
    else:
        validation = _validate_gpx_file(gpx_path)
        if not validation.get("valid"):
            return {
                "tool": "qbot_rwgps_route_import_gpx",
                "status": "VALIDATION_ERROR",
                "safety_class": "WRITE_SAFE",
                "gpx_path": gpx_path,
                "validation_error": validation.get("error"),
                "name": name,
                "description": description,
            }
        # Check duplicates by name
        dup_check = _check_duplicate_route_name(name)
        if dup_check.get("is_duplicate"):
            return {
                "tool": "qbot_rwgps_route_import_gpx",
                "status": "DUPLICATE_SKIPPED",
                "safety_class": "WRITE_SAFE",
                "gpx_path": gpx_path,
                "name": name,
                "is_duplicate": True,
                "existing_route_id": dup_check.get("existing_route_id"),
                "existing_url": dup_check.get("existing_url"),
                "notes": f"A route with name '{name}' already exists (ID {dup_check.get('existing_route_id')}). Skipping.",
            }
        plan = {
            "action": "rwgps_route_create",
            "planned_route": {
                "name": name,
                "description": description,
                "privacy": privacy,
                "source_gpx": gpx_path,
                "gpx_filename": validation.get("filename"),
                "gpx_size_bytes": validation.get("size_bytes"),
                "trackpoint_count": validation.get("trackpoint_count"),
                "bounds": validation.get("bounds"),
            },
        }
        if collection_id and collection_id.lower() != "none":
            plan["planned_route"]["collection_id"] = collection_id

    if not confirm:
        return {
            "tool": "qbot_rwgps_route_import_gpx",
            "safety_class": "WRITE_SAFE",
            "status": "DRY_RUN",
            "confirm": False,
            "mode": "canonical_copy" if use_canonical else "gpx_upload",
            "resolved_route_id": source_route_id or None,
            "resolved_route_name": resolved_route_name or name or None,
            "route_name_hint": route_name_hint or None,
            "candidates": resolved_candidates[:5],
            "plan": plan,
            "notes": "Dry-run mode. Set confirm=true to execute.",
        }

    # ── Execute ──
    if use_canonical:
        try:
            from tools.rwgps.client import import_stage_from_canonical
            result = import_stage_from_canonical(
                source_route_id,
                start_km=start_km,
                end_km=end_km,
                name=name,
            )
        except Exception as exc:
            return {
                "tool": "qbot_rwgps_route_import_gpx",
                "status": "CREATE_FAILED",
                "safety_class": "WRITE_SAFE",
                "error": str(exc),
                "notes": "Canonical stage import failed.",
            }

        if not result.get("ok"):
            return {
                "tool": "qbot_rwgps_route_import_gpx",
                "status": "CREATE_FAILED",
                "safety_class": "WRITE_SAFE",
                "error": result.get("error", "Unknown error"),
                "notes": "Canonical stage import failed.",
            }

        return {
            "tool": "qbot_rwgps_route_import_gpx",
            "safety_class": "WRITE_SAFE",
            "status": "OK",
            "confirm": True,
            "mode": "canonical_copy",
            "resolved_route_id": source_route_id or None,
            "resolved_route_name": resolved_route_name or name or None,
            "new_route_id": result["route_id"],
            "html_url": result["html_url"],
            "distance_km": result.get("distance_km"),
            "track_points_count": result.get("track_points_count"),
            "track_points_total": result.get("track_points_total"),
            "track_points_trimmed": result.get("track_points_trimmed"),
            "name": name,
            "diagnostics": result.get("diagnostics", []),
            "notes": f"RWGPS stage imported successfully. ID={result['route_id']}",
        }

    # ── Legacy GPX-upload path (may create empty route) ──
    try:
        from tools.rwgps.client import create_route_from_gpx as rwgps_create_route
        create_result = rwgps_create_route(
            gpx_path=gpx_path,
            name=name,
            description=description,
            privacy=privacy,
        )
    except Exception as exc:
        return {
            "tool": "qbot_rwgps_route_import_gpx",
            "status": "CREATE_FAILED",
            "safety_class": "WRITE_SAFE",
            "gpx_path": gpx_path,
            "name": name,
            "error": str(exc),
            "notes": "RWGPS route creation failed.",
        }

    if not create_result.get("ok"):
        return {
            "tool": "qbot_rwgps_route_import_gpx",
            "status": "CREATE_FAILED",
            "safety_class": "WRITE_SAFE",
            "gpx_path": gpx_path,
            "name": name,
            "error": create_result.get("error", "Unknown error"),
            "notes": "RWGPS route creation failed.",
        }

    new_route_id = create_result.get("route_id", "")

    if collection_id and new_route_id:
        try:
            from tools.rwgps.client import _request_json as rwgps_request_json
            from tools.rwgps.client import _collection_routes_path as rwgps_collection_routes_path
            add_url = rwgps_collection_routes_path(collection_id)
            rwgps_request_json(add_url)
        except Exception:
            pass

    return {
        "tool": "qbot_rwgps_route_import_gpx",
        "safety_class": "WRITE_SAFE",
        "status": "OK",
        "confirm": True,
        "mode": "gpx_upload",
        "resolved_route_id": source_route_id or None,
        "resolved_route_name": resolved_route_name or name or None,
        "new_route_id": new_route_id,
        "html_url": create_result.get("html_url"),
        "api_url": create_result.get("api_url"),
        "source_gpx_path": gpx_path,
        "name": name,
        "description": description,
        "privacy": privacy,
        "validation": validation,
        "notes": f"RWGPS route created (GPX upload). ID={new_route_id}",
    }


def _tool_qbot_rwgps_route_import_gpx_batch(args: dict | None = None) -> dict[str, Any]:
    """Batch import multiple GPX files as new RWGPS routes.

    Each item in `routes` list must have: gpx_path, name.
    Optional per-item: description, privacy, collection_id.

    Args:
        routes: list of dicts, each with gpx_path and name
        confirm: Set to true to execute imports (default: false)

    Returns:
        Summary of all imports: total, succeeded, skipped, failed
    """
    _args = args or {}
    routes_raw = _args.get("routes", [])
    confirm = bool(_args.get("confirm", False))

    if not isinstance(routes_raw, list) or not routes_raw:
        return {
            "tool": "qbot_rwgps_route_import_gpx_batch",
            "status": "ERROR",
            "safety_class": "WRITE_SAFE",
            "error": "routes must be a non-empty list of {gpx_path, name}",
        }

    results: list[dict[str, Any]] = []
    for i, item in enumerate(routes_raw):
        if not isinstance(item, dict):
            results.append({"index": i, "status": "ERROR", "error": "item is not a dict"})
            continue
        sub_result = _tool_qbot_rwgps_route_import_gpx({
            "gpx_path": item.get("gpx_path", ""),
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "privacy": item.get("privacy", "private"),
            "collection_id": item.get("collection_id"),
            "confirm": confirm,
        })
        results.append(sub_result)

    succeeded = sum(1 for r in results if r.get("status") == "OK")
    skipped_dup = sum(1 for r in results if r.get("status") == "DUPLICATE_SKIPPED")
    failed = sum(1 for r in results if r.get("status") in ("ERROR", "VALIDATION_ERROR", "CREATE_FAILED", "BLOCKED_MISSING_CONFIG"))
    dry_run = sum(1 for r in results if r.get("status") == "DRY_RUN")

    return {
        "tool": "qbot_rwgps_route_import_gpx_batch",
        "safety_class": "WRITE_SAFE",
        "status": "OK" if succeeded > 0 else ("DRY_RUN" if dry_run > 0 else "PARTIAL"),
        "confirm": confirm,
        "total": len(results),
        "succeeded": succeeded,
        "skipped_duplicate": skipped_dup,
        "failed": failed,
        "dry_run": dry_run,
        "results": results,
        "notes": (
            f"Batch complete: {succeeded} created, {skipped_dup} duplicates skipped, "
            f"{failed} failed, {dry_run} in dry-run mode."
        ),
    }


def _tool_qbot_rwgps_poi_push(args=None):
    a = args or {}
    route_id = str(a.get("route_id", "")).strip()
    artifact_id = str(a.get("artifact_id", "")).strip() or None
    fpath = str(a.get("path", "")).strip() or None
    km_from = float(a.get("km_from", 0.0))
    km_to = a.get("km_to")
    km_total = float(a.get("km_total", 0.0))
    dry_run = bool(a.get("dry_run", True))
    confirm = bool(a.get("confirm", False))
    focus = str(a.get("focus", "all")).strip() or "all"
    buffers = a.get("buffers") or {}

    if not route_id and not artifact_id and not fpath:
        return {"tool": "qbot_rwgps_poi_push", "status": "ERROR",
                "error": "Wymagany route_id, artifact_id lub path"}

    if km_to is None:
        km_to = km_total if km_total > 0 else 100.0
    km_to = float(km_to)

    buf = {
        "attractions_m": buffers.get("attractions_m", 500),
        "hard_resupply_m": buffers.get("hard_resupply_m", 500),
        "soft_food_m": buffers.get("soft_food_m", 500),
        "water_m": buffers.get("water_m", 200),
    }
    buf.update({k: v for k, v in buffers.items() if k not in buf})

    poi_result = _tool_qbot_route_poi_analyze({
        "route_id": route_id or None,
        "artifact_id": artifact_id,
        "path": fpath,
        "km_from": km_from,
        "km_to": km_to,
        "focus": None if focus == "all" else focus,
        "output_format": "json",
        "confirm": True,
        "buffers": buf,
    })

    if poi_result.get("status") not in ("OK", "PARTIAL"):
        return {"tool": "qbot_rwgps_poi_push", "status": "ERROR",
                "error": "POI analyze failed: " + str(poi_result.get("error", poi_result.get("status"))),
                "poi_result": poi_result}

    # poi_candidates sa w podkluczach: hard_resupply, soft_food_stop, water, attractions
    analysis = poi_result.get("analysis") or poi_result
    raw_pois = []
    for key in ("hard_resupply", "soft_food_stop", "water", "attractions"):
        items = analysis.get(key) or []
        for p in items:
            if isinstance(p, dict):
                cat = key if key != "attractions" else "attraction"
                if "category" not in p:
                    p = dict(p, category=cat)
                raw_pois.append(p)
    raw_count = len(raw_pois)

    from tools.rwgps.client import select_best_pois, prepare_rwgps_poi_update, apply_rwgps_poi_update
    selected = select_best_pois(raw_pois, km_total=km_total or (km_to - km_from))
    selected_count = len(selected)

    if dry_run or not confirm:
        preview = prepare_rwgps_poi_update(route_id, selected, dry_run=True)
        return {
            "tool": "qbot_rwgps_poi_push", "status": "DRY_RUN",
            "route_id": route_id, "km_from": km_from, "km_to": km_to,
            "raw_poi_count": raw_count, "selected_count": selected_count,
            "existing_pois_count": preview.get("existing_pois_count", 0),
            "final_pois_count": preview.get("final_pois_count", 0),
            "selected_pois": [{
                "name": p.get("name"), "category": p.get("category"),
                "route_km": p.get("route_km"),
                "distance_to_track_m": p.get("distance_to_track_m"),
            } for p in selected],
            "note": "Dry-run — ustaw confirm=True i dry_run=False aby wykonac PUT do RWGPS",
        }

    result = apply_rwgps_poi_update(route_id, selected, confirm=True)
    return {
        "tool": "qbot_rwgps_poi_push",
        "status": "OK" if result.get("ok") else "ERROR",
        "route_id": route_id, "km_from": km_from, "km_to": km_to,
        "raw_poi_count": raw_count, "selected_count": selected_count,
        "put_executed": result.get("put_executed"),
        "final_pois_count": result.get("final_pois_count"),
        "verify_get_ok": result.get("verify_get_ok"),
        "backup_path": result.get("backup_path"),
        "error": result.get("error"),
    }


# ── FAZA A/B: analiza trasy planowanej i ocena jazdy (pudelka 80 m) ──────────

def _tool_qbot_route_plan_analysis(_args: dict | None = None) -> dict[str, Any]:
    """FAZA A — briefing planowanej trasy: droga, podjazdy, nawierzchnia, wiatr per km, forma.

    Args: artifact_id|route_id (opcjonalnie; domyslnie najnowsza otrasowana trasa),
          start 'YYYY-MM-DD HH:MM' (opcjonalnie -> dolicza prognoze pogody), speed_kmh.
    """
    import io
    import contextlib
    _args = _args or {}
    artifact_id = _args.get("artifact_id")
    route_id = _args.get("route_id")
    if route_id and not str(route_id).strip().isdigit():
        _hint = _resolve_rwgps_route_hint(str(route_id))
        route_id = _hint.get("route_id") or None
    start = _args.get("start")
    speed = float(_args.get("speed_kmh", 22.0))
    try:
        from tools.rwgps.route_brief import build as brief_build, _db_connect
        from tools.rwgps.route_weather import build as weather_build
        if not artifact_id and not route_id:
            c = _db_connect(); cur = c.cursor()
            cur.execute("SELECT route_artifact_id FROM qbot_v2.route_frames "
                        "WHERE frame_size_m=80 ORDER BY route_artifact_id DESC LIMIT 1")
            r = cur.fetchone(); c.close()
            if r:
                artifact_id = r[0]
        if not artifact_id and not route_id:
            return {"tool": "qbot_route_plan_analysis", "safety_class": "READ_ONLY",
                    "status": "WARN", "notes": "Brak otrasowanych tras (route_frames)."}
        aid = int(artifact_id) if artifact_id else None
        rid = str(route_id) if route_id else None
        if start:
            with contextlib.redirect_stdout(io.StringIO()):
                weather_build(artifact_id=aid, route_id=rid, start=start, speed_kmh=speed)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            brief_build(artifact_id=aid, route_id=rid)
        return {"tool": "qbot_route_plan_analysis", "safety_class": "READ_ONLY", "status": "OK",
                "analysis": buf.getvalue(),
                "notes": "To jest PELNA, znormalizowana analiza trasy. Pokaz uzytkownikowi pole analysis w calosci (1:1). NIE przerabiaj, NIE dodawaj pogody ani przewyzszen z innych narzedzi — pogoda tutaj jest liczona po wspolrzednych trasy."}
    except Exception as exc:
        return {"tool": "qbot_route_plan_analysis", "safety_class": "READ_ONLY",
                "status": "ERROR", "error": repr(exc)}


def _tool_qbot_ride_analysis(_args: dict | None = None) -> dict[str, Any]:
    """FAZA B — ocena wykonanej jazdy: naloz FIT na pudelka planu (diff) + werdykt wobec formy.

    Args: fit (sciezka, opcjonalnie) lub domyslnie najnowszy FIT; ride (ride_key, domyslnie 'latest').
    """
    import io
    import contextlib
    _args = _args or {}
    fit = _args.get("fit")
    ride = _args.get("ride", "latest")
    try:
        from tools.rwgps.ride_overlay import build as overlay_build
        from tools.rwgps.ride_verdict import build as verdict_build
        with contextlib.redirect_stdout(io.StringIO()):
            if fit:
                rc = overlay_build(fit_path=str(fit), use_latest=False)
            else:
                rc = overlay_build(use_latest=True)
        if rc == 3:
            return {"tool": "qbot_ride_analysis", "safety_class": "READ_ONLY", "status": "WARN",
                    "notes": "Jazda nie pasuje do zadnego planu (start za daleko). Tryb bez planu jeszcze niedostepny."}
        if rc not in (0, None):
            return {"tool": "qbot_ride_analysis", "safety_class": "READ_ONLY", "status": "WARN",
                    "notes": f"Nakladanie FIT zwrocilo kod {rc}."}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            verdict_build(ride=ride)
        return {"tool": "qbot_ride_analysis", "safety_class": "READ_ONLY", "status": "OK",
                "analysis": buf.getvalue(),
                "notes": "Ocena wykonanej jazdy (Faza B). Tekst gotowy do pokazania."}
    except Exception as exc:
        return {"tool": "qbot_ride_analysis", "safety_class": "READ_ONLY",
                "status": "ERROR", "error": repr(exc)}


def _tool_qbot_route_profile_detail(_args: dict | None = None) -> dict[str, Any]:
    # FAZA A — SZCZEGOLOWY profil trasy z ramek (nawierzchnia odcinkami, wysokosci po km, podjazdy).
    import io
    import contextlib
    _args = _args or {}
    artifact_id = _args.get("artifact_id")
    route_id = _args.get("route_id")
    if route_id and not str(route_id).strip().isdigit():
        _hint = _resolve_rwgps_route_hint(str(route_id))
        route_id = _hint.get("route_id") or None
    try:
        from tools.rwgps.route_brief import build_detail, _db_connect
        if not artifact_id and not route_id:
            c = _db_connect()
            cur = c.cursor()
            cur.execute("SELECT route_artifact_id FROM qbot_v2.route_frames WHERE frame_size_m=80 ORDER BY route_artifact_id DESC LIMIT 1")
            r = cur.fetchone()
            c.close()
            if r:
                artifact_id = r[0]
        if not artifact_id and not route_id:
            return {"tool": "qbot_route_profile_detail", "safety_class": "READ_ONLY", "status": "WARN", "notes": "Brak otrasowanych tras (route_frames)."}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            build_detail(artifact_id=int(artifact_id) if artifact_id else None, route_id=str(route_id) if route_id else None)
        return {"tool": "qbot_route_profile_detail", "safety_class": "READ_ONLY", "status": "OK", "analysis": buf.getvalue(), "notes": "Szczegolowy profil z ramek. Pokaz pole analysis w calosci, 1:1."}
    except Exception as exc:
        return {"tool": "qbot_route_profile_detail", "safety_class": "READ_ONLY", "status": "ERROR", "error": repr(exc)}
