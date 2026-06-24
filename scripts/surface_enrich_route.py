#!/usr/bin/env python3
"""Surface enrichment worker for a single RWGPS route_id.
Used by the RWGPS webhook (B3) to enrich a route in the background:
  export route -> GPX artifact -> surface analysis (Overpass) -> persist to DB.
Usage: .venv/bin/python3 scripts/surface_enrich_route.py <route_id>
"""
import sys
import time

sys.path.insert(0, "/opt/qbot/app")


def _db_connect():
    """Polaczenie do Postgresa (psycopg3; fallback psycopg2) — wzorzec z tools.rwgps.route_frames."""
    import os
    from pathlib import Path
    try:
        import psycopg2 as _pg
    except ModuleNotFoundError:
        import psycopg as _pg
    envp = Path("/opt/qbot/app/.env.local")
    if envp.exists():
        for line in envp.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)
    kwargs = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return _pg.connect(**kwargs)


def _infer_and_save_highway(route_id):
    """FAZA B — dla ramek 80 m bez nawierzchni: map-match highway (Overpass) i zapis do bazy.

    Etykiete zapisujemy CZYSTA (bez sufiksu '(szac.)'). Fail-safe: zaden blad nie moze
    wywrocic workera (enrichment juz sie udal)."""
    try:
        conn = _db_connect()
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            "SELECT frame_index, mid_lat, mid_lon FROM qbot_v2.route_frames "
            "WHERE route_id=%s AND frame_size_m=80 "
            "AND (surface IS NULL OR surface='' OR surface='nieznana')",
            (route_id,),
        )
        rows = cur.fetchall()
        total = len(rows)
        filled = 0
        from tools.rwgps.surface_landcover import _fetch_highway_for_point
        for frame_index, mid_lat, mid_lon in rows:
            label = _fetch_highway_for_point(mid_lat, mid_lon)
            if label is not None:
                cur.execute(
                    "UPDATE qbot_v2.route_frames SET surface=%s "
                    "WHERE route_id=%s AND frame_size_m=80 AND frame_index=%s",
                    (label, route_id, frame_index),
                )
                filled += 1
        conn.commit()
        print("HIGHWAY_DONE route_id=" + str(route_id) + " filled=" + str(filled) + "/" + str(total))
    except Exception as _e:
        print("HIGHWAY_FAILED route_id=" + str(route_id) + " error=" + repr(_e))
        pass


def _precompute_poi(route_id):
    """FAZA C — policz pozycje POI raz przy ingeście i zapisz do artefaktu JSON.

    Fail-safe: zaden blad nie moze wywrocic workera."""
    try:
        import json
        import os
        from datetime import datetime, timezone
        from qbot_route_report_tool import _call_tool
        res = _call_tool("route_poi_analyze_readonly", {"route_id": route_id, "open_window": False})
        container = res.get("data") if isinstance(res, dict) and isinstance(res.get("data"), dict) else res
        if isinstance(container, dict) and isinstance(container.get("analysis"), dict):
            analysis = container.get("analysis")
        else:
            analysis = container
        points = []
        if isinstance(analysis, dict):
            for typ, items in analysis.items():
                if not isinstance(items, list):
                    continue
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    km = it.get("dist_km")
                    if km is None:
                        km = it.get("route_km")
                    if km is None:
                        continue
                    try:
                        km = float(km)
                    except (TypeError, ValueError):
                        continue
                    points.append({
                        "km": km,
                        "type": str(it.get("category") or typ),
                        "name": str(it.get("name") or ""),
                    })
        out_dir = "/opt/qbot/artifacts/reports"
        os.makedirs(out_dir, exist_ok=True)
        out_path = out_dir + "/poi_positions_" + str(route_id) + ".json"
        payload = {
            "route_id": route_id,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "points": points,
        }
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print("POI_DONE route_id=" + str(route_id) + " points=" + str(len(points)))
    except Exception as _e:
        print("POI_FAILED route_id=" + str(route_id) + " error=" + repr(_e))
        pass


def main():
    if len(sys.argv) < 2:
        print("usage: surface_enrich_route.py <route_id>")
        sys.exit(2)
    route_id = str(sys.argv[1]).strip()
    t0 = time.time()
    print("ENRICH_START route_id=" + route_id + " ts=" + time.strftime("%Y-%m-%d %H:%M:%S"))

    import qbot_route_tools as t
    from tools.rwgps.client import export_route_to_artifact

    exp = export_route_to_artifact(route_id, fmt="gpx", return_mode="metadata")
    if not isinstance(exp, dict) or not exp.get("artifact_path"):
        print("EXPORT_FAILED status=" + str(exp.get("status")) + " error=" + str(exp.get("error")))
        sys.exit(1)
    artifact_path = exp["artifact_path"]
    print("EXPORTED artifact_path=" + str(artifact_path))

    r = t._tool_qbot_route_artifact_enrich({
        "artifact_path": artifact_path,
        "enrich": ["surface"],
        "surface_source": "osm",
        "sample_every_m": 100,
    })
    sp = (r or {}).get("surface_profile") or {}
    segs = sp.get("segments") or []
    print(
        "ENRICH_DONE route_id=" + route_id
        + " status=" + str((r or {}).get("status"))
        + " segments=" + str(len(segs))
        + " coverage=" + str(sp.get("coverage_pct"))
        + " dominant=" + str(sp.get("dominant_surface"))
        + " took_s=" + str(round(time.time() - t0, 1))
    )

    # FAZA A: zbuduj siatke pudelek 80 m (qbot_v2.route_frames) tuz po enrichmencie.
    # GPX i segmenty nawierzchni juz sa. Blad framingu NIE moze wywrocic workera —
    # enrichment juz sie udal, wiec lapiemy wyjatek i tylko logujemy.
    try:
        from tools.rwgps.route_frames import build as _build_frames
        _build_frames(route_id=route_id, frame_size=80.0)
        print("FRAMES_DONE route_id=" + route_id)
    except Exception as _e:
        print("FRAMES_FAILED route_id=" + route_id + " error=" + repr(_e))

    # FAZA B: highway dla nieznanych ramek
    _infer_and_save_highway(route_id)
    # FAZA C: POI pozycje
    _precompute_poi(route_id)


if __name__ == "__main__":
    main()
