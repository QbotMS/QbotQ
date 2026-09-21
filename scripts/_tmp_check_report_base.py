import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

RID = "komoot-3180619966"
with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT rb.route_base_id, rb.route_modified_at, rb.distance_m
                   FROM qbot_v2.route_base rb WHERE rb.route_id=%s
                   ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1""", (RID,))
    row = cur.fetchone()
    print("baza wybierana przez raport:", row)
    cur.execute("""SELECT count(*) FROM qbot_v2.route_elevation_samples
                   WHERE route_base_id=%s""", (row[0],))
    print("probki wysokosci dla tej bazy:", cur.fetchone()[0])
