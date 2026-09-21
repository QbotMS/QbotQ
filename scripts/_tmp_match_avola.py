import json, math, os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"
import komoot_watch
komoot_watch._load_env()

from fitmodel.api import _db_connect
from tools.rwgps import route_surface_engine as eng

TOUR = "3194997623"          # Avola - Syracuse (status 'asked', bez artefaktu)
EXT = "23971453077"          # przejazd 14.08

# 1. pobierz geometrie trasy z Komoota (bez precompute, tylko artefakt)
from komoot_ingest import ensure_komoot_route_artifact
info = ensure_komoot_route_artifact(TOUR)
print("artefakt:", json.dumps(info, default=str, ensure_ascii=False)[:300])

path = info.get("artifact_path") or info.get("path")
pts = [(p[0], p[1]) for p in eng.extract_artifact_points(path)]
d = eng._cumulative_distances(eng.extract_artifact_points(path))
print("Avola - Syracuse:", round(d[-1] / 1000, 1), "km,", len(pts), "punktow")

# 2. przejazd
with _db_connect() as conn:
    cur = conn.cursor()
    cur.execute("""SELECT lat, lon FROM qbot_v2.activity_record
                   WHERE external_id=%s AND lat IS NOT NULL ORDER BY sec""", (EXT,))
    ride = [(float(a), float(b)) for a, b in cur.fetchall()]


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


sample = ride[::max(1, len(ride) // 200)]
hit = sum(1 for p in sample if near(p, pts))
print(f"pokrycie przejazdu 14.08 trasa 'Avola - Syracuse': {100.0*hit/len(sample):.1f}%")
