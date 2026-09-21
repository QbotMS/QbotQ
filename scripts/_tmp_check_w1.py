import sys, os, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect
conn = _db_connect(); cur = conn.cursor()
for aid in ["24418375708","24407651968"]:
    cur.execute("SELECT w1 FROM qbot_v2.ride_report_data WHERE ride_key=%s", (aid,))
    row = cur.fetchone()
    w1 = row[0] if row else None
    if isinstance(w1, str): w1 = json.loads(w1)
    gears = (w1 or {}).get("gears") or (w1 or {}).get("bike") or {}
    txt = json.dumps(w1, ensure_ascii=False)
    print(f"\n=== {aid} ===")
    print("ma 'brak' o napedzie:", ("brak informacji o nap" in txt) or ("brak napędu" in txt) or ("brak napedu" in txt))
    # wyciagnij kawalek o biegach/rowerze
    b = (w1 or {}).get("bike"); g = (w1 or {}).get("gears")
    print("bike:", json.dumps(b, ensure_ascii=False)[:300] if b else None)
    if isinstance(g, dict):
        print("gears keys:", list(g.keys())[:10])
    elif isinstance(g, list):
        print("gears: lista", len(g), "poz")
conn.close()
os.remove(__file__)
