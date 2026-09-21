import json, os, sys, traceback
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

RID = "komoot-3180619966"
out = {}

try:
    from qbot3.routes.route_surface_store import ensure_route_surface
    r = ensure_route_surface(route_id=RID)
    out["ensure_route_surface"] = {k: r.get(k) for k in
                                   ("status", "route_base_id", "route_version_key",
                                    "surface_profile_id", "surface_layer_count",
                                    "coverage_status")}
except Exception as e:
    out["ensure_route_surface"] = {"ERROR": f"{type(e).__name__}: {e}"}

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT route_base_id, route_version_key, created_at FROM qbot_v2.route_base
                   WHERE route_id=%s ORDER BY route_base_id DESC LIMIT 3""", (RID,))
    out["route_base"] = [list(r) for r in cur.fetchall()]
    cur.execute("""SELECT id, coverage_pct, status, enriched_at
                   FROM qbot_v2.route_surface_profiles WHERE route_artifact_id=599
                   ORDER BY id DESC""")
    out["profiles"] = [list(r) for r in cur.fetchall()]
    for tbl, col in (("route_surface_layer", "route_base_id"),
                     ("route_axis_segments", "route_base_id")):
        try:
            cur.execute(f"SELECT count(*) FROM qbot_v2.{tbl} WHERE {col} = %s",
                        (out["route_base"][0][0],))
            out[tbl] = cur.fetchone()[0]
        except Exception as e:
            conn.rollback()
            out[tbl] = f"ERR {str(e)[:120]}"

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
