import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"

from qbot_route_tools import _fetch_best_route_surface_profile
from fitmodel.api import _db_connect

RID = "komoot-3180619966"

prof = _fetch_best_route_surface_profile(route_id=RID)
print("profil wybrany id:", (prof or {}).get("id"), "coverage:", (prof or {}).get("coverage_pct"))
rv = (prof or {}).get("route_version") or {}
print("profil route_version_key:", rv.get("route_version_key"))
print("payload profilu:", json.dumps(rv.get("route_version_payload"), default=str, ensure_ascii=False))

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT route_base_id, route_version_key, route_version_payload_json
                   FROM qbot_v2.route_base WHERE route_id=%s
                   ORDER BY route_base_id DESC LIMIT 2""", (RID,))
    for r in cur.fetchall():
        print("base:", r[0], r[1])
        print("  payload base:", json.dumps(r[2], default=str, ensure_ascii=False)[:600])
    cur.execute("""SELECT id, parsed_at, distance_m, distance_km, track_points, elevation_gain_m
                   FROM qbot_v2.route_parse_results WHERE route_artifact_id=599
                   ORDER BY parsed_at DESC NULLS LAST, id DESC LIMIT 5""")
    print("== parse_results art 599 ==")
    for r in cur.fetchall():
        print(json.dumps(list(r), default=str, ensure_ascii=False))
