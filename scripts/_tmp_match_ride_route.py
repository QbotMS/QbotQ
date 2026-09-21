import json, os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect
from tools.rwgps import route_surface_engine as eng

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT id, route_id, artifact_path, metadata_json->>'route_name'
                   FROM qbot_v2.route_artifacts
                   WHERE route_id LIKE 'komoot-%' ORDER BY id DESC LIMIT 8""")
    rows = cur.fetchall()

print("== kandydaci (dystans, start) ==")
for aid, rid, path, name in rows:
    try:
        pts = eng.extract_artifact_points(path)
        d = eng._cumulative_distances(pts)
        km = round(d[-1] / 1000.0, 1)
        print(f"{rid:26s} {km:6.1f} km  start=({pts[0][0]:.4f},{pts[0][1]:.4f})  {str(name)[:45]}")
    except Exception as e:
        print(f"{rid:26s} BLAD {type(e).__name__}: {str(e)[:60]}")

# przejazd 14.08 z activity_record (1Hz), jesli jest
with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_schema='qbot_v2' AND table_name='activity_record'
                   ORDER BY ordinal_position""")
    print("kolumny activity_record:", [r[0] for r in cur.fetchall()][:20])
