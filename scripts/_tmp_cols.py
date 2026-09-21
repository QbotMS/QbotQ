import sys, os
sys.path.insert(0,"/opt/qbot/app")
os.environ["QBOT3_ENABLED"]="1"
from fitmodel.api import _db_connect
conn = _db_connect()
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='qbot_v2' AND table_name='training_sessions' AND column_name LIKE '%ss%'")
print([r[0] for r in cur.fetchall()])
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='qbot_v2' AND table_name='training_sessions' AND column_name LIKE '%xss%'")
print("xss cols:", [r[0] for r in cur.fetchall()])
