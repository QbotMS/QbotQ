import sys, os
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

conn = _db_connect()
cur = conn.cursor()

# 1) jazda 19.09 -> external_id
cur.execute("""
  SELECT external_id, activity_name, started_at, distance_m
  FROM qbot_v2.training_sessions
  WHERE started_at::date = '2026-09-19' AND sport_type='cycling'
  ORDER BY started_at
""")
rows = cur.fetchall()
print("=== training_sessions 19.09 ===")
for r in rows:
    print(r)

if not rows:
    sys.exit()

ext = rows[0][0]
print("external_id =", ext)

# 2) rower/czujniki
cur.execute("""
  SELECT device_type, manufacturer, product, serial_number
  FROM qbot_v2.activity_device
  WHERE external_id = %s
  ORDER BY device_type
""", (ext,))
print("=== activity_device ===")
for r in cur.fetchall():
    print(r)

# 3) ride_drivetrain
cur.execute("""
  SELECT *
  FROM qbot_v2.ride_drivetrain
  WHERE external_id = %s
""", (ext,))
cols = [d[0] for d in cur.description]
print("=== ride_drivetrain kolumny ===")
print(cols)
dt = cur.fetchall()
print("=== ride_drivetrain wiersze ===")
print("liczba:", len(dt))
for r in dt:
    print(r)

conn.close()
