import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT tour_id, name, created_date, last_status, route_id, updated_at
                   FROM qbot_v2.komoot_seen_tours
                   WHERE updated_at > now() - interval '5 days'
                      OR created_date >= current_date - 5
                   ORDER BY updated_at DESC LIMIT 20""")
    print("== tury widziane/zmienione w ostatnich 5 dniach ==")
    for r in cur.fetchall():
        print(json.dumps([str(x)[:60] for x in r], ensure_ascii=False))
