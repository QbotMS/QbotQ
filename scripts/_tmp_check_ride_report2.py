import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='ride_report_data' ORDER BY ordinal_position""")
    cols = [r[0] for r in cur.fetchall()]
    print("kolumny:", cols)
    cur.execute("""SELECT * FROM ride_report_data ORDER BY 1 DESC LIMIT 3""")
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        for k in list(d):
            v = str(d[k])
            d[k] = v[:120]
        print(json.dumps(d, ensure_ascii=False, default=str))
