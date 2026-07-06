#!/usr/bin/env python3
"""Wejscie trasy z Komoot do bazy QBota (droga A - natywnie).

punkty Komoot -> GPX -> upsert_route_artifact(source="komoot") -> parse (route_parse_results)
-> ensure_route_base -> profil nawierzchni -> ensure_route_precompute -> (push_karoo osobno).

route_id = "komoot-<tour_id>". Pliki GPX ida do outgoing/komoot/.
"""
from __future__ import annotations
import hashlib, os, sys
from pathlib import Path

sys.path.insert(0, "/opt/qbot/app")
import komoot_auth
from tools.komoot import client as kclient
import api_db
from tools.rwgps.client import _parse_gpx_for_summary, RWGPS_PARSE_VERSION
from qbot3.routes.route_base_store import ensure_route_base

OUT_DIR = Path("/opt/qbot/app/outgoing/komoot")
KOMOOT_TAG = "[Q] "  # widoczny znacznik trasy wzbogaconej przez QBot (odroznia od golej kopii z Komoot)


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_gpx(name, points):
    parts = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
             "<gpx version=\"1.1\" creator=\"QBot-Komoot\" xmlns=\"http://www.topografix.com/GPX/1/1\">",
             "<trk><name>" + _esc(name) + "</name><trkseg>"]
    for p in points:
        lat = p.get("lat"); lon = p.get("lng"); ele = p.get("alt")
        if lat is None or lon is None:
            continue
        if ele is not None:
            parts.append("<trkpt lat=\"%.7f\" lon=\"%.7f\"><ele>%.1f</ele></trkpt>" % (float(lat), float(lon), float(ele)))
        else:
            parts.append("<trkpt lat=\"%.7f\" lon=\"%.7f\"></trkpt>" % (float(lat), float(lon)))
    parts.append("</trkseg></trk>")
    parts.append("</gpx>")
    return "\n".join(parts) + "\n"


def _store_parse_result(fpath, artifact):
    summary = _parse_gpx_for_summary(fpath)
    bounds = summary.get("bounds") or {}
    fp = summary.get("first_point") or {}
    lp = summary.get("last_point") or {}
    dkm = summary.get("distance_km")
    rec = {
        "route_artifact_id": artifact["id"],
        "parser_version": RWGPS_PARSE_VERSION,
        "source_artifact_sha256": artifact.get("sha256"),
        "track_points": summary.get("point_count"),
        "distance_m": round(float(dkm) * 1000.0, 1) if dkm is not None else None,
        "distance_km": dkm,
        "elevation_gain_m": summary.get("elevation_gain_m"),
        "elevation_loss_m": summary.get("elevation_loss_m"),
        "bbox_min_lat": bounds.get("sw_lat"), "bbox_min_lon": bounds.get("sw_lng"),
        "bbox_max_lat": bounds.get("ne_lat"), "bbox_max_lon": bounds.get("ne_lng"),
        "start_lat": fp.get("lat"), "start_lon": fp.get("lon"),
        "end_lat": lp.get("lat"), "end_lon": lp.get("lon"),
        "min_ele": summary.get("min_elevation_m"), "max_ele": summary.get("max_elevation_m"),
        "looks_valid": summary.get("looks_valid"),
        "summary_json": summary,
    }
    return api_db.upsert_route_parse_result(rec)


def ensure_komoot_route_artifact(tour_id, session=None):
    session = session or komoot_auth.KomootSession()
    meta = kclient.get_tour_meta(tour_id, session)
    points = kclient.get_tour_coordinates(tour_id, session)
    if not points:
        raise RuntimeError("Komoot trasa %s: brak punktow" % tour_id)
    gpx = build_gpx(meta.get("name") or ("Komoot " + str(tour_id)), points)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = "komoot-%s.gpx" % tour_id
    fpath = OUT_DIR / fname
    fpath.write_text(gpx, encoding="utf-8")
    data = gpx.encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    route_id = "komoot-%s" % tour_id
    artifact = api_db.upsert_route_artifact({
        "artifact_path": str(fpath),
        "artifact_relative_path": "outgoing/komoot/" + fname,
        "filename": fname,
        "route_id": route_id,
        "source": "komoot",
        "export_format": "gpx_track",
        "file_size_bytes": len(data),
        "sha256": sha,
        "status": "ok",
        "metadata_json": {
            "route_name": (KOMOOT_TAG + (meta.get("name") or "")).strip(),
            "source_tour_id": str(tour_id),
            "changed_at": meta.get("changed_at"),
            "komoot_status": meta.get("status"),
            "distance_m": meta.get("distance_m"),
        },
    })
    parse = _store_parse_result(fpath, artifact)
    return {"route_id": route_id, "points": len(points), "name": meta.get("name"),
            "artifact_id": artifact.get("id"), "parse_id": parse.get("id") if parse else None,
            "sha256": sha[:12]}


def ingest_komoot_tour(tour_id, session=None, precompute=False):
    """Pelne wejscie trasy: artefakt+parse -> route_base -> (opcjonalnie) nawierzchnia + precompute."""
    session = session or komoot_auth.KomootSession()
    art = ensure_komoot_route_artifact(tour_id, session)
    base = ensure_route_base(art["route_id"])
    out = {"artifact": art, "route_base": base if isinstance(base, dict) else None}
    if precompute:
        from scripts.route_precompute_trigger import _ensure_rwgps_surface_profile
        surf = _ensure_rwgps_surface_profile(art["route_id"], route_artifact_id=art["artifact_id"], force=True)
        out["surface"] = {"status": surf.get("status"), "surface_profile_id": surf.get("surface_profile_id")}
        from qbot3.routes.route_elevation_store import ensure_route_elevation
        elev = ensure_route_elevation(route_id=art["route_id"])
        out["elevation"] = {"status": elev.get("status")}
        from qbot3.routes.route_precompute_orchestrator import ensure_route_precompute
        pc = ensure_route_precompute(route_id=art["route_id"], trigger_source="komoot", scope="all")
        out["precompute"] = {"status": pc.get("status"),
                             "jobs": {k: v.get("status") for k, v in (pc.get("jobs") or {}).items()}}
    return out


if __name__ == "__main__":
    import json
    s = komoot_auth.KomootSession()
    tid = sys.argv[1] if len(sys.argv) > 1 else kclient.list_planned_tours(s, limit=1)["tours"][0]["id"]
    do_pc = "--precompute" in sys.argv
    print("INGEST trasy Komoot:", tid, "| precompute:", do_pc)
    res = ingest_komoot_tour(tid, s, precompute=do_pc)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
