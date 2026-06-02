"""Route workflow: RWGPS -> local processing -> confirm -> RWGPS upload.

Katalogowanie: /opt/qbot/artifacts/routes/YYYY-MM-DD/
Nazwa przy upload: [oryginalna] | QBot YYYY-MM-DD HH:MM
"""
from __future__ import annotations
import json, os, sys, httpx
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ARTIFACTS_BASE = Path("/opt/qbot/artifacts/routes")
APP_DIR = Path("/opt/qbot/app")

def _env():
    return dict(l.strip().split("=",1) for l in open(APP_DIR/".env.local") if "=" in l and not l.startswith("#"))

def _rwgps_get(route_id: str) -> dict:
    e = _env()
    url = f"https://ridewithgps.com/routes/{route_id}.json?apikey={e.get('RWGPS_API_KEY','')}&auth_token={e.get('RWGPS_AUTH_TOKEN','')}&version=2"
    r = httpx.get(url, timeout=15.0)
    r.raise_for_status()
    return r.json().get("route", {})

def _work_dir(date_str: str | None = None) -> Path:
    ds = date_str or datetime.now().strftime("%Y-%m-%d")
    d = ARTIFACTS_BASE / ds
    d.mkdir(parents=True, exist_ok=True)
    return d

def fetch_and_process(route_id: str, project_id: str = "tuscany_2026") -> dict:
    """Pobierz trase z RWGPS i przetworz lokalnie.
    
    Zapisuje do /opt/qbot/artifacts/routes/YYYY-MM-DD/
    Zwraca summary z linkami do plikow.
    """
    now = datetime.now()
    ds = now.strftime("%Y-%m-%d")
    ts = now.strftime("%Y-%m-%d_%H-%M")
    work_dir = _work_dir(ds)

    # 1. Pobierz z RWGPS
    route = _rwgps_get(route_id)
    name = route.get("name", f"route_{route_id}")
    tp = route.get("track_points", [])
    dist_km = round(float(route.get("distance", 0)) / 1000, 1)
    ele_gain = route.get("elevation_gain", 0)

    # 2. Zapisz surowy JSON
    raw_file = work_dir / f"{route_id}_raw_{ts}.json"
    raw_file.write_text(json.dumps({
        "route_id": route_id, "name": name, "fetched_at": now.isoformat(),
        "distance_km": dist_km, "elevation_gain_m": ele_gain,
        "track_points_count": len(tp),
        "route": {k: v for k, v in route.items() if k != "track_points"},
    }, ensure_ascii=False), encoding="utf-8")

    # 3. Climbs
    climbs = []
    try:
        sys.path.insert(0, str(APP_DIR))
        from tools.rwgps.climbs import detect_climbs
        climbs = detect_climbs(tp)
    except Exception as e:
        pass

    # 4. POI z cache Geofabrik
    poi_summary = {}
    try:
        from qbot3.artifacts.route_analyzer import _parse_gpx_file_detailed, _track_projection, _track_bbox, _expand_bbox, _geofabrik_cache_candidates, _route_poi_v2_classify, _nearest_track_projection
        projected = _track_projection([{"lat": p["y"], "lon": p["x"], "ele": p.get("e",0), "distance_m": p.get("d",0)} for p in tp])
        bbox = _expand_bbox(_track_bbox(projected), 500.0)
        elements = _geofabrik_cache_candidates(bbox) or []
        cats = {"water": 0, "food": 0, "attraction": 0}
        for el in elements:
            cat, _ = _route_poi_v2_classify(el.get("tags") or {})
            if cat in cats:
                cats[cat] += 1
        poi_summary = cats
    except Exception:
        pass

    # 5. Zapisz processing summary
    summary = {
        "route_id": route_id, "name": name, "project_id": project_id,
        "processed_at": now.isoformat(), "work_dir": str(work_dir),
        "distance_km": dist_km, "elevation_gain_m": ele_gain,
        "track_points": len(tp), "climbs_count": len(climbs),
        "climbs": climbs, "poi_candidates": poi_summary,
        "raw_file": str(raw_file),
        "status": "processed_local",
        "rwgps_upload_name": None,
    }
    summary_file = work_dir / f"{route_id}_summary_{ts}.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, default=str), encoding="utf-8")

    return {
        "ok": True, "route_id": route_id, "name": name,
        "distance_km": dist_km, "elevation_gain_m": ele_gain,
        "climbs_count": len(climbs), "poi_candidates": poi_summary,
        "work_dir": str(work_dir), "summary_file": str(summary_file),
        "status": "processed_local",
        "note": f"Gotowe. Aby wyslac do RWGPS: potwierdz upload trasy {route_id}",
    }

def upload_to_rwgps(route_id: str, summary_file: str | None = None, dry_run: bool = True) -> dict:
    """Wyslij przetworzona trase do RWGPS z nowa nazwa.
    
    Nazwa: [oryginalna] | QBot YYYY-MM-DD HH:MM
    """
    route = _rwgps_get(route_id)
    orig_name = route.get("name", f"route_{route_id}")
    now = datetime.now()
    new_name = f"{orig_name} | QBot {now.strftime('%Y-%m-%d %H:%M')}"

    if dry_run:
        return {
            "ok": True, "dry_run": True, "route_id": route_id,
            "original_name": orig_name, "new_name": new_name,
            "note": "Dry-run. Dodaj 'potwierdz' aby wykonac upload."
        }

    # PUT do RWGPS
    e = _env()
    url = f"https://ridewithgps.com/routes/{route_id}.json?apikey={e.get('RWGPS_API_KEY','')}&auth_token={e.get('RWGPS_AUTH_TOKEN','')}"
    payload = {"route": {"name": new_name}}
    r = httpx.put(url, json=payload, timeout=15.0)
    r.raise_for_status()

    # Zaktualizuj summary jesli jest
    if summary_file and Path(summary_file).exists():
        s = json.loads(Path(summary_file).read_text())
        s["status"] = "uploaded_to_rwgps"
        s["rwgps_upload_name"] = new_name
        s["uploaded_at"] = now.isoformat()
        Path(summary_file).write_text(json.dumps(s, ensure_ascii=False, default=str))

    return {
        "ok": True, "dry_run": False, "route_id": route_id,
        "original_name": orig_name, "new_name": new_name,
        "rwgps_status": r.status_code,
    }

def list_processed_routes(days: int = 7) -> list[dict]:
    """Lista tras przetworzonych w ostatnich N dniach."""
    results = []
    if not ARTIFACTS_BASE.exists():
        return results
    for day_dir in sorted(ARTIFACTS_BASE.iterdir(), reverse=True)[:days]:
        if not day_dir.is_dir():
            continue
        for f in sorted(day_dir.glob("*_summary_*.json"), reverse=True):
            try:
                s = json.loads(f.read_text())
                results.append({
                    "date": day_dir.name, "route_id": s.get("route_id"),
                    "name": s.get("name"), "distance_km": s.get("distance_km"),
                    "status": s.get("status"), "file": str(f),
                })
            except Exception:
                pass
    return results
