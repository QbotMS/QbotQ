import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_schema='qbot_v2' AND table_name='komoot_seen_tours'
                   ORDER BY ordinal_position""")
    cols = [r[0] for r in cur.fetchall()]
    print("kolumny:", cols)
    cur.execute("""SELECT * FROM qbot_v2.komoot_seen_tours
                   ORDER BY 1 DESC LIMIT 12""")
    for r in cur.fetchall():
        print(json.dumps(dict(zip(cols, [str(x)[:70] for x in r])), ensure_ascii=False))
