import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_schema='qbot_v2' AND table_name='training_sessions'
                   ORDER BY ordinal_position""")
    print("kolumny:", [r[0] for r in cur.fetchall()])
    cur.execute("""SELECT id, external_id, date, started_at, distance_m, duration_s,
                          avg_power_w, avg_hr_bpm
                   FROM qbot_v2.training_sessions
                   ORDER BY date DESC, started_at DESC LIMIT 8""")
    print("== ostatnie treningi qbot_v2 ==")
    for r in cur.fetchall():
        print(json.dumps(list(r), default=str, ensure_ascii=False))
    cur.execute("""SELECT count(*), max(date) FROM qbot_v2.training_sessions""")
    print("razem / ostatnia data:", cur.fetchone())
    # activity_record (1Hz)
    cur.execute("""SELECT count(DISTINCT activity_id), max(activity_id::text)
                   FROM qbot_v2.activity_record""")
    print("activity_record: liczba aktywnosci / max id:", cur.fetchone())
