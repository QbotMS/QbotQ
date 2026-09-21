import os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

con = _db_connect(); cur = con.cursor()
cur.execute("""select column_name from information_schema.columns
 where table_schema='qbot_v2' and table_name='route_base' order by ordinal_position""")
print("route_base cols:", [r[0] for r in cur.fetchall()])
cur.execute("""select route_base_id, external_route_id, name from qbot_v2.route_base
 where external_route_id like %s or name ilike %s""", ("%3186954572%", "%Cavagrande%"))
rows = cur.fetchall()
for r in rows:
    print("BASE:", r)
for r in rows:
    bid = r[0]
    cur.execute("""select event_index, start_m, end_m, length_m, elevation_gain_m,
      avg_gradient_pct, max_gradient_pct, severity, detection_version
      from qbot_v2.route_climb_events where route_base_id=%s order by event_index""", (bid,))
    for c in cur.fetchall():
        print("CLIMB", bid, c)
con.rollback(); cur.close(); con.close()
os.remove(__file__)
