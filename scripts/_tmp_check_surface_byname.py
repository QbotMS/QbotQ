import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn:
    cur = conn.cursor()
    print("== ostatnie artefakty tras: czy jest route_name w metadata ==")
    cur.execute("""SELECT id, route_id, created_at,
                          metadata_json->>'route_name' AS route_name,
                          left(coalesce(metadata_json::text,'NULL'), 160) AS meta
                   FROM qbot_v2.route_artifacts ORDER BY id DESC LIMIT 12""")
    for r in cur.fetchall():
        print(json.dumps(list(r), default=str, ensure_ascii=False))

    print("== czy sa segmenty nawierzchni dla tych tras ==")
    cur.execute("""SELECT a.route_id, p.id AS profile_id, p.enriched_at, p.coverage_pct,
                          (SELECT count(*) FROM qbot_v2.route_surface_segments s
                            WHERE s.route_surface_profile_id = p.id) AS segs
                   FROM qbot_v2.route_surface_profiles p
                   JOIN qbot_v2.route_artifacts a ON a.id = p.route_artifact_id
                   ORDER BY p.id DESC LIMIT 8""")
    for r in cur.fetchall():
        print(json.dumps(list(r), default=str, ensure_ascii=False))
