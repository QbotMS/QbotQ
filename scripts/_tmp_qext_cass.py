import sys, os
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect
con = _db_connect(); cur = con.cursor()
cur.execute("select reported_at, override_enabled, cogs from qbot_v2.qext2_cassette_report "
            "order by reported_at desc limit 15")
print("--- co Karoo raportuje o swoim override kasety ---")
for r in cur.fetchall():
    print(r["reported_at"], "| override =", r["override_enabled"], "| cogs =", r["cogs"])
cur.execute("select count(*), min(reported_at), max(reported_at) from qbot_v2.qext2_cassette_report")
print("razem:", cur.fetchone())
con.close()
os.remove(__file__)
