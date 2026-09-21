import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

RID = "komoot-3180619966"

Q = [
 ("route_base", """
  SELECT route_base_id, route_id, route_artifact_id, route_version_key, created_at, updated_at
  FROM qbot_v2.route_base WHERE route_id = %s ORDER BY route_base_id DESC LIMIT 10"""),
 ("route_artifacts", """
  SELECT id, route_id, kind, created_at, left(coalesce(path,''),80) AS path
  FROM qbot_v2.route_artifacts WHERE route_id = %s ORDER BY id DESC LIMIT 10"""),
 ("surface_profile", """
  SELECT id, route_id, route_artifact_id, created_at,
         left(coalesce(route_version_json::text,''),200) AS ver
  FROM qbot_v2.route_surface_profile WHERE route_id = %s ORDER BY id DESC LIMIT 10"""),
]
with _db_connect() as conn:
    cur = conn.cursor()
    for title, sql in Q:
        print("==", title, "==")
        try:
            cur.execute(sql, (RID,))
            for r in cur.fetchall():
                print(json.dumps(r, default=str, ensure_ascii=False))
        except Exception as e:
            conn.rollback()
            print("ERR", str(e)[:300])
