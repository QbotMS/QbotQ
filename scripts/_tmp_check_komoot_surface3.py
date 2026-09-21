import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

RID = "komoot-3180619966"

def show(cur, title, sql, args=()):
    print("==", title, "==")
    try:
        cur.execute(sql, args)
        for r in cur.fetchall():
            print(json.dumps(list(r), default=str, ensure_ascii=False))
    except Exception as e:
        print("ERR", str(e)[:300])

with _db_connect() as conn:
    cur = conn.cursor()
    show(cur, "kolumny route_artifacts",
         """SELECT column_name FROM information_schema.columns
            WHERE table_schema='qbot_v2' AND table_name='route_artifacts'
            ORDER BY ordinal_position""")
    show(cur, "artefakty trasy",
         """SELECT id, route_id, created_at, updated_at
            FROM qbot_v2.route_artifacts WHERE route_id::text = %s
            ORDER BY id DESC LIMIT 10""", (RID,))
    show(cur, "surface_profiles",
         """SELECT p.id, p.route_artifact_id, p.status, p.coverage_pct, p.enriched_at
            FROM qbot_v2.route_surface_profiles p
            JOIN qbot_v2.route_artifacts a ON a.id = p.route_artifact_id
            WHERE a.route_id::text = %s ORDER BY p.id DESC LIMIT 10""", (RID,))
    show(cur, "route_base",
         """SELECT route_base_id, route_artifact_id, route_version_key, created_at
            FROM qbot_v2.route_base WHERE route_id = %s
            ORDER BY route_base_id DESC LIMIT 6""", (RID,))
