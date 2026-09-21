import sys, os
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn, conn.cursor() as cur:
    cur.execute("select * from qbot_v2.modelq2_anchor order by day")
    cols = [d[0] for d in cur.description]
    print("ANCHOR cols:", cols)
    for r in cur.fetchall():
        print(" ", r)
