import json, os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

RID = "komoot-3180619966"
out = {}
with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema='qbot_v2' AND table_name LIKE '%elev%'""")
    out["tabele_elev"] = [r[0] for r in cur.fetchall()]
    cur.execute("""SELECT route_base_id, route_version_key FROM qbot_v2.route_base
                   WHERE route_id=%s ORDER BY route_base_id DESC LIMIT 4""", (RID,))
    bases = [list(r) for r in cur.fetchall()]
    out["bases"] = bases
    for t in out["tabele_elev"]:
        try:
            cur.execute(f"""SELECT route_base_id, count(*) FROM qbot_v2.{t}
                            WHERE route_base_id = ANY(%s) GROUP BY route_base_id
                            ORDER BY route_base_id DESC""",
                        ([b[0] for b in bases],))
            out[t] = [list(r) for r in cur.fetchall()]
        except Exception as e:
            conn.rollback()
            out[t] = f"ERR {str(e)[:150]}"
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
