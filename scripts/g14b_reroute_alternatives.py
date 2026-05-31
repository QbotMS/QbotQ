#!/usr/bin/env python3
"""g14b_reroute_alternatives.py — Real Reroute Alternatives dla Gravel Intelligence (G14B + G14C).

Dla każdego reroute_hint z G14 próbuje znaleźć realną alternatywę
pomiędzy start_anchor i end_anchor przez Brouter lub Valhalla.

Usage:
    python3 scripts/g14b_reroute_alternatives.py --route-id 55401067 --mode dry-run
    python3 scripts/g14b_reroute_alternatives.py --route-id 55401067 --mode build
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path("/opt/qbot/app")
ARTIFACTS_REROUTE = Path("/opt/qbot/artifacts/reroute")
ARTIFACTS_EXPORTS = Path("/opt/qbot/artifacts/exports/rwgps")
CONFIG_FILE = APP_DIR / "config" / "router_endpoints.json"
CONFIG_EXAMPLE = APP_DIR / "config" / "router_endpoints.example.json"

MAX_DETOUR_PCT = 25.0
SUSPICIOUS_SHORT_PCT = -50.0


# ── Config ────────────────────────────────────────────────────────────────

def load_router_config() -> dict:
    """Load router configuration from file and env overrides.

    Priority: env vars > config file > defaults.
    """
    # Default config
    config = {
        "source": "defaults",
        "brouter": {"enabled": False, "base_url": None, "profile": "trekking"},
        "valhalla": {"enabled": False, "base_url": None, "api_key": None, "profile": "bicycle"},
    }

    # Load from config file
    if CONFIG_FILE.exists():
        try:
            file_config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if "brouter" in file_config:
                config["brouter"].update(file_config["brouter"])
            if "valhalla" in file_config:
                config["valhalla"].update(file_config["valhalla"])
            config["source"] = str(CONFIG_FILE)
        except (json.JSONDecodeError, OSError):
            pass

    # Env overrides (highest priority)
    env_brouter = os.getenv("BROUTER_BASE_URL", "").strip()
    if env_brouter:
        config["brouter"]["enabled"] = True
        config["brouter"]["base_url"] = env_brouter

    env_valhalla = os.getenv("VALHALLA_BASE_URL", "").strip()
    if env_valhalla:
        config["valhalla"]["enabled"] = True
        config["valhalla"]["base_url"] = env_valhalla

    env_valhalla_key = os.getenv("VALHALLA_API_KEY", "").strip()
    if env_valhalla_key:
        config["valhalla"]["api_key"] = env_valhalla_key

    if env_brouter or env_valhalla:
        config["source"] = "env (overrides config file)"

    config["any_configured"] = config["brouter"]["enabled"] or config["valhalla"]["enabled"]
    return config


def router_config_status(config: dict | None = None) -> dict:
    """Return human-readable router configuration status."""
    if config is None:
        config = load_router_config()
    return {
        "source": config.get("source", "unknown"),
        "brouter": {
            "configured": config["brouter"]["enabled"],
            "url": config["brouter"]["base_url"],
            "profile": config["brouter"]["profile"],
        },
        "valhalla": {
            "configured": config["valhalla"]["enabled"],
            "url": config["valhalla"]["base_url"],
            "api_key_set": bool(config["valhalla"]["api_key"]),
            "profile": config["valhalla"]["profile"],
        },
        "any_configured": config["any_configured"],
    }


# ── Health Checks ─────────────────────────────────────────────────────────

def check_brouter_health(config: dict) -> dict:
    """Check if Brouter endpoint is reachable."""
    bc = config["brouter"]
    if not bc["enabled"] or not bc["base_url"]:
        return {"router": "brouter", "status": "DISABLED", "detail": "Brouter not configured"}

    try:
        import httpx
        # Use actual reference points (Mazowsze area) for healthcheck
        test_url = bc["base_url"].rstrip("/") + "/brouter?lonlats=21.0,52.0|21.1,52.1&profile=trekking&format=geojson"
        r = httpx.get(test_url, timeout=10)
        r.raise_for_status()
        data = r.json()
        healthy = isinstance(data, dict) and "features" in data and len(data["features"]) > 0
        if healthy:
            tl = _safe_float(data["features"][0].get("properties", {}).get("track-length", 0))
            healthy = tl > 0
        return {
            "router": "brouter",
            "status": "HEALTHY" if healthy else "UNHEALTHY",
            "detail": f"HTTP {r.status_code}, features={len(data.get('features', []))}, track={tl if healthy else '?'}m" if healthy else f"HTTP {r.status_code}, no data",
            "url": bc["base_url"],
        }
    except ImportError:
        return {"router": "brouter", "status": "UNHEALTHY", "detail": "httpx not available"}
    except Exception as exc:
        return {"router": "brouter", "status": "UNHEALTHY", "detail": str(exc)[:200]}


def check_valhalla_health(config: dict) -> dict:
    """Check if Valhalla endpoint is reachable."""
    vc = config["valhalla"]
    if not vc["enabled"] or not vc["base_url"]:
        return {"router": "valhalla", "status": "DISABLED", "detail": "Valhalla not configured"}

    try:
        import httpx
        test_url = vc["base_url"].rstrip("/") + "/health"
        r = httpx.get(test_url, timeout=10)
        r.raise_for_status()
        return {"router": "valhalla", "status": "HEALTHY", "detail": f"HTTP {r.status_code}", "url": vc["base_url"]}
    except ImportError:
        return {"router": "valhalla", "status": "UNHEALTHY", "detail": "httpx not available"}
    except Exception as exc:
        # Valhalla health endpoint might not exist; try a basic GET
        try:
            import httpx
            r = httpx.get(vc["base_url"], timeout=10)
            return {"router": "valhalla", "status": "HEALTHY", "detail": f"HTTP {r.status_code}", "url": vc["base_url"]}
        except Exception as exc2:
            return {"router": "valhalla", "status": "UNHEALTHY", "detail": str(exc2)[:200]}


# ── Router Calls ──────────────────────────────────────────────────────────

def route_with_brouter(
    start_lat: float, start_lng: float,
    end_lat: float, end_lng: float,
    config: dict,
) -> dict:
    """Route via Brouter API between two points."""
    bc = config["brouter"]
    if not bc["enabled"] or not bc["base_url"]:
        return {"router": "brouter", "status": "DISABLED", "error": "Brouter not configured"}

    profile = bc.get("profile", "trekking")
    try:
        import httpx
        base = bc["base_url"].rstrip("/")
        url = (
            f"{base}/brouter"
            f"?lonlats={start_lng},{start_lat}|{end_lng},{end_lat}"
            f"&profile={profile}"
            f"&alternativeidx=0"
            f"&format=geojson"
        )
        r = httpx.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data or "features" not in data:
            return {"router": "brouter", "status": "NOT_FOUND", "error": "Empty Brouter response"}
        return normalize_router_response(data, "brouter")
    except ImportError:
        return {"router": "brouter", "status": "ERROR", "error": "httpx not available"}
    except Exception as exc:
        return {"router": "brouter", "status": "ERROR", "error": str(exc)[:300]}


def route_with_valhalla(
    start_lat: float, start_lng: float,
    end_lat: float, end_lng: float,
    config: dict,
) -> dict:
    """Route via Valhalla API between two points."""
    vc = config["valhalla"]
    if not vc["enabled"] or not vc["base_url"]:
        return {"router": "valhalla", "status": "DISABLED", "error": "Valhalla not configured"}

    try:
        import httpx
        base = vc["base_url"].rstrip("/")
        headers = {"Content-Type": "application/json"}
        if vc.get("api_key"):
            headers["api_key"] = vc["api_key"]

        body = {
            "locations": [
                {"lat": start_lat, "lon": start_lng},
                {"lat": end_lat, "lon": end_lng},
            ],
            "costing": vc.get("profile", "bicycle"),
            "costing_options": {
                "bicycle": {"bicycle_type": "Gravel", "cycling_speed": 20, "use_roads": 0.3}
            },
            "directions_options": {"units": "km"},
        }

        r = httpx.post(f"{base}/route", json=body, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        return normalize_router_response(data, "valhalla")
    except ImportError:
        return {"router": "valhalla", "status": "ERROR", "error": "httpx not available"}
    except Exception as exc:
        return {"router": "valhalla", "status": "ERROR", "error": str(exc)[:300]}


def _safe_float(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0


def normalize_router_response(data: dict, router: str) -> dict:
    """Normalize Brouter/Valhalla response to a standard format."""
    if router == "brouter":
        total_km = 0.0
        coordinates = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            total_km += _safe_float(props.get("track-length", 0)) / 1000.0
            geom = feature.get("geometry", {})
            if geom.get("type") == "LineString":
                coords = geom.get("coordinates", [])
                coordinates.extend([(c[1], c[0]) for c in coords])
        if not coordinates:
            return {"router": "brouter", "status": "ERROR", "error": "Empty geometry in Brouter response"}
        return {
            "router": "brouter",
            "status": "FOUND",
            "distance_km": round(total_km, 4),
            "coordinates": coordinates,
            "point_count": len(coordinates),
            "profile": "gravel",
        }

    if router == "valhalla":
        trip = data.get("trip", {})
        legs = trip.get("legs", [])
        if not legs:
            return {"router": "valhalla", "status": "NOT_FOUND", "error": "No legs in Valhalla response"}
        total_km = 0.0
        coordinates = []
        for leg in legs:
            total_km += leg.get("length", 0)
            shape = leg.get("shape", [])
            coordinates.extend([(pt["lat"], pt["lon"]) for pt in shape])
        if not coordinates:
            return {"router": "valhalla", "status": "ERROR", "error": "Empty shape in Valhalla response"}
        return {
            "router": "valhalla",
            "status": "FOUND",
            "distance_km": round(total_km, 4),
            "coordinates": coordinates,
            "point_count": len(coordinates),
            "profile": "bicycle",
        }

    return {"router": router, "status": "ERROR", "error": f"Unknown router: {router}"}


# ── Helpers ───────────────────────────────────────────────────────────────

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── GPX ───────────────────────────────────────────────────────────────────

def load_gpx_points(route_id: str) -> list:
    gpx_path = ARTIFACTS_EXPORTS / f"rwgps_{route_id}.gpx"
    if not gpx_path.exists():
        return []
    try:
        tree = ET.parse(str(gpx_path))
        root = tree.getroot()
    except Exception:
        return []
    ns = "{http://www.topografix.com/GPX/1/1}"
    ns0 = "{http://www.topografix.com/GPX/1/0}"
    trkpts = root.findall(f".//{ns}trkpt") or root.findall(f".//{ns0}trkpt")
    points = []
    for pt in trkpts:
        lat = pt.get("lat")
        lon = pt.get("lon")
        if lat and lon:
            points.append((float(lat), float(lon)))
    return points


def compute_original_segment(hint: dict, gpx_points: list) -> float:
    s_idx = hint.get("start_anchor_gpx_idx", 0)
    e_idx = hint.get("end_anchor_gpx_idx", 0)
    if not gpx_points:
        return hint.get("length_km", 0)
    s_idx = max(0, min(s_idx, len(gpx_points) - 1))
    e_idx = max(0, min(e_idx, len(gpx_points) - 1))
    if s_idx >= e_idx:
        s_idx, e_idx = e_idx, s_idx
    total = 0.0
    for i in range(s_idx, e_idx):
        total += _haversine_km(gpx_points[i][0], gpx_points[i][1], gpx_points[i + 1][0], gpx_points[i + 1][1])
    return round(total, 4)


# ── Alternative Finder ────────────────────────────────────────────────────

def compare_alternative_to_original(alt_km: float, original_km: float) -> dict:
    """Compare alternative to original and apply safety limits."""
    if original_km <= 0:
        return {"status": "ERROR", "recommendation": "ROUTER_FAILED", "error": "Original segment has zero length"}

    delta_km = alt_km - original_km
    delta_pct = round((delta_km / original_km * 100), 1)
    suspicious = delta_pct < SUSPICIOUS_SHORT_PCT if delta_pct < 0 else False

    if alt_km <= 0:
        return {"delta_km": round(delta_km, 4), "delta_pct": delta_pct, "status": "ERROR", "recommendation": "ROUTER_FAILED", "suspicious": False}
    if delta_pct > MAX_DETOUR_PCT:
        return {"delta_km": round(delta_km, 4), "delta_pct": delta_pct, "status": "TOO_LONG", "recommendation": "MANUAL_REVIEW", "suspicious": suspicious}
    if suspicious:
        return {"delta_km": round(delta_km, 4), "delta_pct": delta_pct, "status": "FOUND", "recommendation": "MANUAL_REVIEW", "suspicious": suspicious}
    if delta_pct <= 5:
        return {"delta_km": round(delta_km, 4), "delta_pct": delta_pct, "status": "FOUND", "recommendation": "USE_CANDIDATE", "suspicious": suspicious}
    if delta_pct <= 15:
        return {"delta_km": round(delta_km, 4), "delta_pct": delta_pct, "status": "FOUND", "recommendation": "KEEP_ORIGINAL", "suspicious": suspicious}
    return {"delta_km": round(delta_km, 4), "delta_pct": delta_pct, "status": "FOUND", "recommendation": "MANUAL_REVIEW", "suspicious": suspicious}


def find_alternative(hint: dict, gpx_points: list, config: dict) -> dict:
    """Find a reroute alternative for a single hint."""
    slat, slng = hint["start_anchor_lat"], hint["start_anchor_lng"]
    elat, elng = hint["end_anchor_lat"], hint["end_anchor_lng"]
    original_km = compute_original_segment(hint, gpx_points)
    straight_km = _haversine_km(slat, slng, elat, elng)

    alt_id = f"alt_{hint['hint_id']}"

    # Try Brouter
    if config["brouter"]["enabled"]:
        result = route_with_brouter(slat, slng, elat, elng, config)
        if result["status"] == "FOUND":
            comp = compare_alternative_to_original(result["distance_km"], original_km)
            return _build_alternative(alt_id, hint, original_km, straight_km, comp, result)

    # Try Valhalla
    if config["valhalla"]["enabled"]:
        result = route_with_valhalla(slat, slng, elat, elng, config)
        if result["status"] == "FOUND":
            comp = compare_alternative_to_original(result["distance_km"], original_km)
            return _build_alternative(alt_id, hint, original_km, straight_km, comp, result)

    # Both failed or disabled
    if not config["any_configured"]:
        return _build_unavailable(alt_id, hint, original_km, straight_km, "ROUTER_UNAVAILABLE", "No router configured. Set BROUTER_BASE_URL or VALHALLA_BASE_URL in .env or config/router_endpoints.json")
    if not config["brouter"]["enabled"] and not config["valhalla"]["enabled"]:
        return _build_unavailable(alt_id, hint, original_km, straight_km, "ROUTER_DISABLED", "Both routers disabled in config")
    return _build_unavailable(alt_id, hint, original_km, straight_km, "NOT_FOUND", "Routers returned no valid alternative")


def _build_alternative(alt_id: str, hint: dict, original_km: float, straight_km: float, comp: dict, router_result: dict) -> dict:
    return {
        "alternative_id": alt_id,
        "hint_id": hint["hint_id"],
        "original_distance_km": round(original_km, 4),
        "straight_line_km": round(straight_km, 4),
        "alternative_distance_km": router_result["distance_km"],
        "delta_km": comp["delta_km"],
        "delta_pct": comp["delta_pct"],
        "router": router_result["router"],
        "status": comp["status"],
        "recommendation": comp["recommendation"],
        "suspicious": comp.get("suspicious", False),
        "coordinates": router_result.get("coordinates", []),
        "point_count": router_result.get("point_count", 0),
    }


def _build_unavailable(alt_id: str, hint: dict, original_km: float, straight_km: float, status: str, error: str) -> dict:
    return {
        "alternative_id": alt_id,
        "hint_id": hint["hint_id"],
        "original_distance_km": round(original_km, 4),
        "straight_line_km": round(straight_km, 4),
        "alternative_distance_km": None,
        "delta_km": None,
        "delta_pct": None,
        "router": "none",
        "status": status,
        "recommendation": "MANUAL_REVIEW",
        "suspicious": False,
        "coordinates": [],
        "point_count": 0,
        "error": error,
    }


# ── Main Pipeline ─────────────────────────────────────────────────────────

def run_alternatives(route_id: str, mode: str = "dry-run") -> dict:
    rid = str(route_id)

    # 1. Load config
    router_config = load_router_config()
    config_status = router_config_status(router_config)
    healthcheck = {}
    if router_config["brouter"]["enabled"]:
        healthcheck["brouter"] = check_brouter_health(router_config)
    else:
        healthcheck["brouter"] = {"router": "brouter", "status": "DISABLED", "detail": "not configured"}
    if router_config["valhalla"]["enabled"]:
        healthcheck["valhalla"] = check_valhalla_health(router_config)
    else:
        healthcheck["valhalla"] = {"router": "valhalla", "status": "DISABLED", "detail": "not configured"}

    print(f"  Router config source: {config_status['source']}")
    print(f"  Brouter: {'✅' if config_status['brouter']['configured'] else '❌'} "
          f"{'HEALTHY' if healthcheck.get('brouter',{}).get('status')=='HEALTHY' else healthcheck.get('brouter',{}).get('status','?')}")
    print(f"  Valhalla: {'✅' if config_status['valhalla']['configured'] else '❌'} "
          f"{'HEALTHY' if healthcheck.get('valhalla',{}).get('status')=='HEALTHY' else healthcheck.get('valhalla',{}).get('status','?')}")

    # 2. Load hints
    hints_path = ARTIFACTS_REROUTE / f"reroute_hints_{rid}.json"
    hints_data = _read_json(hints_path)
    if not hints_data:
        return {"ok": False, "status": "ERROR", "error": f"G14 hints not found: {hints_path}"}
    hints = hints_data.get("hints", [])
    if not hints:
        return {"ok": False, "status": "ERROR", "error": f"No hints in G14 data for {rid}"}

    gpx_points = load_gpx_points(rid)
    print(f"  Hints: {len(hints)}, GPX points: {len(gpx_points)}")

    # 3. Find alternatives
    alternatives = []
    found, unavailable, disabled, too_long, errors = 0, 0, 0, 0, 0

    for hint in hints:
        print(f"  Processing {hint['hint_id']}...", end=" ")
        result = find_alternative(hint, gpx_points, router_config)
        alternatives.append(result)
        s = result["status"]
        print(f"{s} rec={result['recommendation']} "
              + (f"Δ={result['delta_pct']:+.1f}%" if result["delta_pct"] is not None else ""))
        if s == "FOUND": found += 1
        elif s == "ROUTER_UNAVAILABLE": unavailable += 1
        elif s == "ROUTER_DISABLED": disabled += 1
        elif s == "TOO_LONG": too_long += 1
        elif s == "ERROR": errors += 1

    # 4. Build output
    ts = _iso_now()
    json_out = {
        "ok": True,
        "status": "OK",
        "mode": mode,
        "route_id": rid,
        "route_name": hints_data.get("route_name", ""),
        "distance_km": hints_data.get("distance_km", 0),
        "source": "g14c_router_setup",
        "g14_hints_source": hints_path.name,
        "g14b_source": "g14b_reroute_alternatives.py",
        "router_config": config_status,
        "router_config_source": config_status["source"],
        "healthcheck": healthcheck,
        "hint_count": len(hints),
        "found_count": found,
        "unavailable_count": unavailable,
        "disabled_count": disabled,
        "too_long_count": too_long,
        "error_count": errors,
        "alternatives": alternatives,
        "generated_at": ts,
        "generator": "g14b_reroute_alternatives.py (G14C)",
    }

    # 5. Build MD
    md = _build_md(rid, hints_data, config_status, healthcheck, alternatives, ts, mode)

    # 6. Determine final status
    if not config_status["any_configured"]:
        json_out["g14c_status"] = "BLOCKED"
        json_out["g14c_blocked_reason"] = "router endpoint not configured"
    else:
        json_out["g14c_status"] = "DONE"

    # 7. Write output (after status is set)
    if mode == "build":
        json_path = ARTIFACTS_REROUTE / f"g14c_reroute_alternatives_{rid}.json"
        md_path = ARTIFACTS_REROUTE / f"g14c_reroute_alternatives_{rid}.md"
        _write_json(json_path, json_out)
        _write_md(md_path, md)
        print(f"  Output: {json_path.name}")

    print()
    print(f"  Summary: {found} found, {too_long} too_long, {unavailable} unavailable, {disabled} disabled, {errors} errors")

    if not config_status["any_configured"]:
        print(f"\n  ⚠️  G14C BLOCKED: router endpoint not configured")
        print(f"     Set BROUTER_BASE_URL or VALHALLA_BASE_URL in .env or")
        print(f"     create config/router_endpoints.json (see router_endpoints.example.json)")

    return json_out


def _build_md(rid, hints_data, config_status, healthcheck, alternatives, ts, mode):
    lines = []
    lines.append(f"# G14C Real Router Endpoint Setup — {hints_data.get('route_name', '?')}")
    lines.append("")
    lines.append(f"**Route ID:** {rid}")
    lines.append(f"**Distance:** {hints_data.get('distance_km', 0):.2f} km")
    lines.append(f"**Hints:** {len(hints_data.get('hints', []))}")
    lines.append(f"**Mode:** {mode}")
    lines.append(f"**Generated:** {ts}")
    lines.append("")

    lines.append("## 🔧 Router Configuration")
    lines.append("")
    lines.append(f"**Config source:** {config_status['source']}")
    lines.append("")
    lines.append("| Router | Configured | URL | Profile | Health |")
    lines.append("|--------|-----------|-----|---------|--------|")
    b = config_status["brouter"]
    bh = healthcheck.get("brouter", {})
    lines.append(f"| Brouter | {'✅' if b['configured'] else '❌'} | {str(b['url'] or '-')} | {b['profile']} | {bh.get('status','?')} |")
    v = config_status["valhalla"]
    vh = healthcheck.get("valhalla", {})
    lines.append(f"| Valhalla | {'✅' if v['configured'] else '❌'} | {str(v['url'] or '-')} | {v['profile']} | {vh.get('status','?')} |")
    lines.append("")

    if not config_status["any_configured"]:
        lines.append("## ⚠️ BLOCKED — No Router Configured")
        lines.append("")
        lines.append("To enable real reroute alternatives, configure one of:")
        lines.append("")
        lines.append("1. **Brouter** — set `BROUTER_BASE_URL` in `.env` (e.g. `http://127.0.0.1:17777`)")
        lines.append("2. **Valhalla** — set `VALHALLA_BASE_URL` in `.env`")
        lines.append("3. **Config file** — create `config/router_endpoints.json` (see `router_endpoints.example.json`)")
        lines.append("")
        lines.append("Example config file:")
        lines.append("```json")
        ex = _read_json(CONFIG_EXAMPLE)
        if ex:
            lines.append(json.dumps(ex, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")

    # Summary table
    found = sum(1 for a in alternatives if a["status"] == "FOUND")
    too_long = sum(1 for a in alternatives if a["status"] == "TOO_LONG")
    unavailable = sum(1 for a in alternatives if a["status"] in ("ROUTER_UNAVAILABLE", "ROUTER_DISABLED"))
    errors = sum(1 for a in alternatives if a["status"] == "ERROR")

    lines.append("## 📋 Alternatives Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|--------|-------|")
    lines.append(f"| **Total hints** | {len(alternatives)} |")
    lines.append(f"| FOUND | {found} |")
    lines.append(f"| TOO_LONG | {too_long} |")
    lines.append(f"| ROUTER_UNAVAILABLE / DISABLED | {unavailable} |")
    lines.append(f"| ERROR | {errors} |")
    lines.append("")

    for alt in alternatives:
        lines.append(f"## 🚧 {alt['alternative_id']}")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        lines.append(f"| Hint ID | {alt['hint_id']} |")
        lines.append(f"| Status | {alt['status']} |")
        lines.append(f"| Router | {alt['router']} |")
        lines.append(f"| Original (GPX) | {alt['original_distance_km']:.4f} km |")
        lines.append(f"| Straight line | {alt['straight_line_km']:.4f} km |")
        if alt["alternative_distance_km"] is not None:
            lines.append(f"| Alternative | {alt['alternative_distance_km']:.4f} km |")
            lines.append(f"| Delta | {alt['delta_km']:+.4f} km ({alt['delta_pct']:+.1f}%) |")
        lines.append(f"| Recommendation | {alt['recommendation']} |")
        if alt.get("suspicious"):
            lines.append(f"| ⚠️ Suspicious | Alternative suspiciously short ({alt['delta_pct']:+.1f}%) |")
        if alt.get("error"):
            lines.append(f"| Error | {alt['error']} |")
        lines.append("")

    lines.append("## ⚠️ Important")
    lines.append("")
    lines.append("G14C **nie modyfikuje żadnej trasy**. Nie tworzy candidate GPX.")
    lines.append("Nie uploaduje do RWGPS.")
    lines.append("Celem jest wyłącznie weryfikacja endpointu routera i jakości alternatyw.")
    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated by G14C — {ts}*")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="G14B/G14C Real Reroute Alternatives")
    p.add_argument("--route-id", required=True, help="Garmin route ID")
    p.add_argument("--mode", choices=["dry-run", "build"], default="dry-run")
    args = p.parse_args()

    print("=" * 70)
    print("G14C Real Router Endpoint Setup")
    print("=" * 70)
    print(f"  Route ID: {args.route_id}")
    print(f"  Mode:     {args.mode}")
    print()

    result = run_alternatives(args.route_id, mode=args.mode)
    if not result.get("ok"):
        print(f"  ERROR: {result.get('error')}")
        sys.exit(1)
    print()
    print("Done.")


if __name__ == "__main__":
    main()
