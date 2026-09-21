import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
import api_db
with api_db._conn() as c:
    row = c.execute("SELECT tour_id, name, route_id, last_status, changed_at "
                    "FROM qbot_v2.komoot_seen_tours WHERE tour_id='3276635248'").fetchone()
print("SEEN:", json.dumps({k: str(row[k]) for k in row.keys()}, ensure_ascii=False) if row else None)
