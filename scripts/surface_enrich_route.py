#!/usr/bin/env python3
"""Surface enrichment worker for a single RWGPS route_id.
Used by the RWGPS webhook (B3) to enrich a route in the background:
  export route -> GPX artifact -> surface analysis (Overpass) -> persist to DB.
Usage: .venv/bin/python3 scripts/surface_enrich_route.py <route_id>
"""
import sys
import time

sys.path.insert(0, "/opt/qbot/app")


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


if __name__ == "__main__":
    main()
