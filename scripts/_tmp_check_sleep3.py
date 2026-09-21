import sys,os;sys.path.insert(0,"/opt/qbot/app");os.environ["QBOT3_ENABLED"]="1"
from fitmodel.api import _db_connect;c=_db_connect();cur=c.cursor()
cur.execute("SELECT date, sleep_score, sleep_duration_min FROM qbot_v2.qbot_wellness_daily WHERE sleep_score IS NOT NULL ORDER BY date DESC LIMIT 10")
print("wellness sleep_score:", cur.fetchall())
