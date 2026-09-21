import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT id, artifact_path, sha256, updated_at FROM qbot_v2.route_artifacts
                   WHERE id = 599""")
    print(cur.fetchone())
    cur.execute("""SELECT id, coverage_pct, status,
                   left(surface_summary_json::text, 900)
                   FROM qbot_v2.route_surface_profiles WHERE id = 85""")
    print(cur.fetchone())
