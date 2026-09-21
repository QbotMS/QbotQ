import json, os, sys, math
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect
from tools.rwgps import route_surface_engine as eng

EXT = "23971453077"  # jazda 14.08
with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT lat, lon FROM qbot_v2.activity_record
                   WHERE external_id = %s AND lat IS NOT NULL
                   ORDER BY sec""", (EXT,))
    ride = [(float(r[0]), float(r[1])) for r in cur.fetchall()]
    cur.execute("""SELECT id, route_id, artifact_path FROM qbot_v2.route_artifacts
                   WHERE route_id LIKE 'komoot-%' ORDER BY id DESC LIMIT 8""")
    cands = cur.fetchall()

print("punktow GPS przejazdu:", len(ride))
if not ride:
    raise SystemExit(0)


def near(p, pts, tol_m=60):
    la, lo = p
    for (a, b) in pts:
        if abs(a - la) > 0.002 or abs(b - lo) > 0.002:
            continue
        dx = (b - lo) * 111320 * math.cos(math.radians(la))
        dy = (a - la) * 110540
        if dx * dx + dy * dy <= tol_m * tol_m:
            return True
    return False


sample = ride[::max(1, len(ride) // 200)]
for aid, rid, path in cands:
    try:
        pts = [(p[0], p[1]) for p in eng.extract_artifact_points(path)]
        hit = sum(1 for p in sample if near(p, pts))
        print(f"{rid:26s} pokrycie przejazdu: {100.0*hit/len(sample):5.1f}%")
    except Exception as e:
        print(f"{rid:26s} BLAD {type(e).__name__}: {str(e)[:60]}")
