import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

RID = "komoot-3180619966"
with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_schema='qbot_v2' AND table_name='route_base'
                   ORDER BY ordinal_position""")
    print("kolumny route_base:", [r[0] for r in cur.fetchall()])
    cur.execute("""SELECT id, parsed_at, distance_m, distance_km, track_points, elevation_gain_m
                   FROM qbot_v2.route_parse_results WHERE route_artifact_id=599
                   ORDER BY parsed_at DESC NULLS LAST, id DESC LIMIT 6""")
    print("== parse_results art 599 ==")
    for r in cur.fetchall():
        print(json.dumps(list(r), default=str, ensure_ascii=False))
