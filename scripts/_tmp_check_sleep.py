import sys,os;sys.path.insert(0,"/opt/qbot/app");os.environ["QBOT3_ENABLED"]="1"
from fitmodel.api import _db_connect;c=_db_connect();cur=c.cursor()
cur.execute("SELECT day, sleep_h, sleep_score FROM qbot_v2.fitmodel_daily WHERE sleep_score IS NOT NULL ORDER BY day DESC LIMIT 5")
print("fitmodel:", cur.fetchall())
cur.execute("SELECT date, sleep_duration_min, sleep_score, sleep_quality FROM qbot_v2.qbot_wellness_daily ORDER BY date DESC LIMIT 5")
print("wellness:", cur.fetchall())
