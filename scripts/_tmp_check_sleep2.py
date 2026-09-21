import sys,os;sys.path.insert(0,"/opt/qbot/app");os.environ["QBOT3_ENABLED"]="1"
from fitmodel.api import _db_connect;c=_db_connect();cur=c.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='qbot_v2' AND table_name='fitmodel_daily' AND column_name LIKE '%sleep%'")
print("fitmodel sleep cols:", [r[0] for r in cur.fetchall()])
cur.execute("SELECT day, sleep_h, sleep_score_garmin FROM qbot_v2.fitmodel_daily WHERE sleep_score_garmin IS NOT NULL ORDER BY day DESC LIMIT 5")
print("fitmodel:", cur.fetchall())
