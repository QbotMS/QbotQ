import sys, os
sys.path.insert(0, '/opt/qbot/app')
os.environ['QBOT3_ENABLED'] = '1'
from fitmodel.api import _db_connect
conn = _db_connect()
cur = conn.cursor()

# Today's ride
cur.execute("""
SELECT id, date, activity_name, duration_s, distance_m,
       calories, avg_power_w, avg_hr_bpm, normalized_power_w,
       tss, mmp_300_w, mmp_1200_w
FROM qbot_v2.training_sessions
WHERE date = '2026-08-18'
""")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
for r in rows:
    for c, v in zip(cols, r):
        print(f'{c}: {v}')
    print('---')

# Last 15 rides - calories vs work from power
print('\n=== LAST 15 RIDES: calories vs kJ from power ===')
cur.execute("""
SELECT date, activity_name,
       duration_s, ROUND(distance_m/1000.0,1) as dist_km, calories,
       avg_power_w, avg_hr_bpm,
       ROUND(avg_power_w * duration_s / 1000.0, 1) as work_kj,
       CASE WHEN avg_power_w * duration_s / 1000.0 != 0
            THEN ROUND(calories::numeric / (avg_power_w * duration_s / 1000.0), 2)
            ELSE NULL END as kcal_per_kj
FROM qbot_v2.training_sessions
WHERE date >= '2026-07-01'
ORDER BY date DESC
LIMIT 15
""")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
print(' | '.join(cols))
for r in rows:
    print(' | '.join(str(v) for v in r))

conn.close()
os.remove(__file__)
