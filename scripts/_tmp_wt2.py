import sys,os;sys.path.insert(0,"/opt/qbot/app");os.environ["QBOT3_ENABLED"]="1"
from fitmodel.api import _db_connect;c=_db_connect();cur=c.cursor()
cur.execute("SELECT date, weight_kg FROM qbot_v2.qbot_wellness_daily WHERE weight_kg IS NOT NULL ORDER BY date DESC LIMIT 10")
print("wellness weight:", cur.fetchall())
cur.execute("SELECT day, weight_kg FROM qbot_v2.fitmodel_daily WHERE weight_kg IS NOT NULL ORDER BY day DESC LIMIT 10")
print("fitmodel weight:", cur.fetchall())
