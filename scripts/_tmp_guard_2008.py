import sys, os
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

AID = "24045426445"
with _db_connect() as conn, conn.cursor() as cur:
    cur.execute("select verdict, dev_full_pct from qbot_v2.power_meter_guard where external_id=%s", (AID,))
    print("GUARD:", cur.fetchone())
    cur.execute("select reason, released from qbot_v2.fitmodel_ride_quarantine where external_id=%s", (AID,))
    print("KWARANTANNA:", cur.fetchone())
    cur.execute("select xss_low, xss_high, xss_total, xss_source from qbot_v2.modelq2_ride where external_id=%s", (AID,))
    print("MQ2 RIDE:", cur.fetchone())
os.remove(__file__)
