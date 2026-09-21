import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

RID = "komoot-3180619966"

with _db_connect() as conn:
    cur = conn.cursor()

    print("== route_artifacts (kolumny) ==")
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_schema='qbot_v2' AND table_name='route_artifacts'
                   ORDER BY ordinal_position""")
    print([r["column_name"] for r in cur.fetchall()])

    print("== artefakty trasy ==")
    cur.execute("""SELECT id, route_id, created_at, updated_at, left(coalesce(sha256,''),16) AS sha
                   FROM qbot_v2.route_artifacts WHERE route_id::text = %s
                   ORDER BY id DESC LIMIT 10""", (RID,))
    for r in cur.fetchall():
        print(json.dumps(r, default=str, ensure_ascii=False))

    print("== surface_profiles ==")
    cur.execute("""SELECT p.id, p.route_artifact_id, p.status, p.coverage_pct, p.enriched_at
                   FROM qbot_v2.route_surface_profiles p
                   JOIN qbot_v2.route_artifacts a ON a.id = p.route_artifact_id
                   WHERE a.route_id::text = %s ORDER BY p.id DESC LIMIT 10""", (RID,))
    for r in cur.fetchall():
        print(json.dumps(r, default=str, ensure_ascii=False))

    print("== route_base (klucze wersji) ==")
    cur.execute("""SELECT route_base_id, route_artifact_id, route_version_key, created_at
                   FROM qbot_v2.route_base WHERE route_id = %s
                   ORDER BY route_base_id DESC LIMIT 6""", (RID,))
    for r in cur.fetchall():
        print(json.dumps(r, default=str, ensure_ascii=False))
