import sys, os
sys.path.insert(0,"/opt/qbot/app")
os.environ["QBOT3_ENABLED"]="1"
from fitmodel.api import _db_connect
conn = _db_connect()
cur = conn.cursor()
try:
    cur.execute(
        "SELECT afr.external_id AS ride_key, "
        "(afr.summary->>'distance')::numeric/1000 AS dist_km, "
        "(afr.summary->>'duration')::numeric AS duration_s, "
        "ts.xss "
        "FROM qbot_v2.activity_fit_raw afr "
        "JOIN qbot_v2.training_sessions ts ON ts.external_id = afr.external_id "
        "WHERE afr.parse_error IS NULL "
        "ORDER BY ts.started_at DESC NULLS LAST LIMIT 3"
    )
    for r in cur.fetchall():
        print(r)
except Exception as e:
    print("ERR:", e)
conn.close()
