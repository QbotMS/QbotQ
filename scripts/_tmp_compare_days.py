import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
from fitmodel.api import _db_connect

# Ktora trasa byla jechana 13.08 (dzien, kiedy nawierzchnia dzialala)?
import math
from tools.rwgps import route_surface_engine as eng

for EXT, dzien in (("23959147495", "13.08"), ("23971453077", "14.08")):
    with _db_connect() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT lat, lon FROM qbot_v2.activity_record
                       WHERE external_id=%s AND lat IS NOT NULL ORDER BY sec""", (EXT,))
        ride = [(float(a), float(b)) for a, b in cur.fetchall()]
        cur.execute("""SELECT route_id, artifact_path FROM qbot_v2.route_artifacts
                       WHERE route_id LIKE 'komoot-%' ORDER BY id DESC LIMIT 8""")
        cands = cur.fetchall()

    def near(p, pts, tol=60):
        la, lo = p
        for (a, b) in pts:
            if abs(a - la) > 0.002 or abs(b - lo) > 0.002:
                continue
            dx = (b - lo) * 111320 * math.cos(math.radians(la))
            dy = (a - la) * 110540
            if dx * dx + dy * dy <= tol * tol:
                return True
        return False

    sample = ride[::max(1, len(ride) // 150)]
    best = []
    for rid, path in cands:
        try:
            pts = [(p[0], p[1]) for p in eng.extract_artifact_points(path)]
            hit = sum(1 for p in sample if near(p, pts))
            best.append((100.0 * hit / len(sample), rid))
        except Exception:
            pass
    best.sort(reverse=True)
    print(f"== {dzien} ({EXT}) ==")
    for pct, rid in best[:3]:
        print(f"   {pct:5.1f}%  {rid}")
