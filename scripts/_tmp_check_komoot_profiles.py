import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT id, status, coverage_pct, enriched_at, surface_summary_json
                   FROM qbot_v2.route_surface_profiles WHERE id IN (75, 85) ORDER BY id""")
    for pid, status, cov, enr, js in cur.fetchall():
        if isinstance(js, str):
            try:
                js = json.loads(js)
            except Exception:
                js = {}
        js = js or {}
        print("== profil", pid, "status", status, "coverage", cov, "enriched", enr, "==")
        for k in ("quality_status", "coverage_pct", "tagged_surface_pct", "inferred_surface_pct",
                  "unknown_surface_pct", "unknown_pct_refined", "unknown_pct_raw",
                  "distance_m", "track_points", "point_count", "segment_count",
                  "source_segments", "dominant_surface", "notes", "warnings", "errors"):
            if k in js:
                print(f"   {k}: {json.dumps(js[k], ensure_ascii=False, default=str)[:200]}")
        print("   klucze:", sorted(js.keys())[:40])
