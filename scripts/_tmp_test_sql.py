import sys, os
sys.path.insert(0,"/opt/qbot/app")
os.environ["QBOT3_ENABLED"]="1"
import psycopg
from psycopg.rows import dict_row
from qbot_config import DATABASE_URL
conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
try:
    rows = conn.execute(
        "SELECT afr.external_id AS ride_key, afr.fit_path AS fit_path, "
        "ts.started_at AS t_start, ts.activity_name AS name, ts.sport_type AS sport, "
        "(rrd.built_at IS NOT NULL) AS has_report, "
        "(afr.summary->>'distance')::numeric/1000 AS dist_km, "
        "(afr.summary->>'duration')::numeric AS duration_s, "
        "ts.xss "
        "FROM qbot_v2.activity_fit_raw afr "
        "JOIN qbot_v2.training_sessions ts ON ts.external_id = afr.external_id "
        "LEFT JOIN qbot_v2.ride_report_data rrd ON rrd.ride_key = afr.external_id "
        "WHERE afr.parse_error IS NULL "
        "ORDER BY ts.started_at DESC NULLS LAST LIMIT 5"
    ).fetchall()
    for r in rows:
        print(r["ride_key"], r["dist_km"], r["duration_s"], r["xss"])
except Exception as e:
    print("ERR:", e)
conn.close()
