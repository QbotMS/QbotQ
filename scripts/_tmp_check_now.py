import os, sys, json
from datetime import datetime, timezone
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
print("czas serwera:", datetime.now().isoformat(), "| UTC:", datetime.now(timezone.utc).isoformat())
from fitmodel.api import _db_connect
with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("SELECT now()")
    print("czas bazy:", cur.fetchone()[0])
    cur.execute("""SELECT id, external_id, date, started_at, distance_m, activity_name
                   FROM qbot_v2.training_sessions ORDER BY date DESC, started_at DESC LIMIT 5""")
    for r in cur.fetchall():
        print(json.dumps(list(r), default=str, ensure_ascii=False))
