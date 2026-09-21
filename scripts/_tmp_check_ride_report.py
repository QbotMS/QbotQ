import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

try:
    os.kill(1242689, 0)
    print("proces 1242689: ZYJE")
except ProcessLookupError:
    print("proces 1242689: zakonczony")

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_name ILIKE '%report%status%' OR table_name ILIKE '%ride_report%'""")
    print("tabele:", [r[0] for r in cur.fetchall()])
