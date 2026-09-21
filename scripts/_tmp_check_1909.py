import sys, os
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect
c = _db_connect()
cur = c.cursor()
cur.execute("""
  SELECT date, started_at, activity_name, sport_type,
         (distance_m/1000.0)::numeric(6,1) AS km, duration_s, source, external_id, imported_at
  FROM qbot_v2.training_sessions
  WHERE date >= '2026-09-15'
  ORDER BY started_at DESC
""")
rows = cur.fetchall()
print("training_sessions od 15.09 (", len(rows), "szt.):")
for r in rows:
    print(r)
