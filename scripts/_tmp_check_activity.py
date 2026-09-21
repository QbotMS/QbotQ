import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

with _db_connect() as conn:
    cur = conn.cursor()
    for sch in ("qbot_v2", "public"):
        try:
            cur.execute(f"""SELECT id, external_id, date, started_at, name, distance_m, duration_s,
                                   avg_power_w, avg_hr_bpm
                            FROM {sch}.training_sessions
                            ORDER BY date DESC, started_at DESC LIMIT 6""")
            print("==", sch, "==")
            for r in cur.fetchall():
                print(json.dumps(list(r), default=str, ensure_ascii=False))
        except Exception as e:
            conn.rollback()
            print("==", sch, "ERR", str(e)[:150])
    # czy jest aktywnosc o tym external_id gdziekolwiek
    for sch in ("qbot_v2", "public"):
        try:
            cur.execute(f"""SELECT id, external_id, date FROM {sch}.training_sessions
                            WHERE external_id ILIKE %s OR id::text = %s""",
                        ("%175386234%", "175386234"))
            print(sch, "szukanie i175386234 ->", [list(r) for r in cur.fetchall()])
        except Exception as e:
            conn.rollback()
            print(sch, "szukanie ERR", str(e)[:120])
