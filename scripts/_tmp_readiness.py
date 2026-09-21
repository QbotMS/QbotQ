import sys, os
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect
conn = _db_connect(); cur = conn.cursor()

# kolumny fitmodel_daily zwiazane z readiness
cur.execute("""select column_name from information_schema.columns
 where table_schema='qbot_v2' and table_name='fitmodel_daily'
 and (column_name ilike '%readiness%' or column_name ilike '%ctl%' or column_name ilike '%atl%'
      or column_name ilike '%tsb%' or column_name ilike '%hrv%' or column_name ilike '%rhr%'
      or column_name ilike '%sleep%' or column_name ilike '%glyc%' or column_name ilike '%today%')
 order by ordinal_position""")
cols = [r[0] for r in cur.fetchall()]
print("kolumny readiness/pochodne:", cols)

sel = ",".join(cols)
cur.execute(f"select date,{sel} from qbot_v2.fitmodel_daily where date between '2026-09-14' and '2026-09-21' order by date")
rows = cur.fetchall()
hdr = ["date"]+cols
for r in rows:
    print(" | ".join(f"{h}={v}" for h,v in zip(hdr,r)))
os.remove(__file__)
