import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema='qbot_v2' AND table_name ILIKE '%komoot%'""")
    print("tabele komoot:", [r[0] for r in cur.fetchall()])
    cur.execute("""SELECT id, route_id, created_at, metadata_json->>'route_name'
                   FROM qbot_v2.route_artifacts
                   WHERE created_at > now() - interval '4 days'
                   ORDER BY id DESC LIMIT 15""")
    print("== artefakty z ostatnich 4 dni ==")
    for r in cur.fetchall():
        print(json.dumps(list(r), default=str, ensure_ascii=False))
