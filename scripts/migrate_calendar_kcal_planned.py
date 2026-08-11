"""Migracja: kolumna kcal_planned w qbot_v2.calendar_entry (ryczalt kalorii z eventu)."""
import os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as c:
    cur = c.cursor()
    cur.execute("ALTER TABLE qbot_v2.calendar_entry ADD COLUMN IF NOT EXISTS kcal_planned integer")
    c.commit()
    cur.execute("""select column_name, data_type from information_schema.columns
                   where table_schema='qbot_v2' and table_name='calendar_entry' and column_name='kcal_planned'""")
    print("po migracji:", cur.fetchall())
