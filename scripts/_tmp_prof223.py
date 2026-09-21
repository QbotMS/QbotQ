import os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect
from qbot3.routes.route_elevation_engine import smooth_elevation, _frame_grades, ElevationSample

con = _db_connect(); cur = con.cursor()
cur.execute("""select sample_index, distance_m, lat, lon, elevation_m
 from qbot_v2.route_elevation_samples where route_base_id=223 order by sample_index""")
rows = cur.fetchall()
con.rollback(); cur.close(); con.close()
print("N samples:", len(rows), "krok m:", rows[1][1]-rows[0][1])

samples = [ElevationSample(sample_index=r[0], distance_m=float(r[1]), lat=float(r[2]),
                           lon=float(r[3]), elevation_m=float(r[4])) for r in rows]
d = [s.distance_m for s in samples]
sm = smooth_elevation(samples, 100.0)
g = _frame_grades(sm, d)
for i in range(len(d)):
    if 9800 <= d[i] <= 13200:
        print(int(d[i]), round(sm[i],1) if sm[i] is not None else None,
              round(g[i],2) if g[i] is not None else None)
os.remove(__file__)
