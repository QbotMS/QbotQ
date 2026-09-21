import sys
sys.path.insert(0, "/opt/qbot/app")
from tools.rwgps import route_surface_engine as e
print("kolejnosc:", e._configured_overpass_endpoints())
print("timeout:", e.OVERPASS_TIMEOUT_SEC, "retries:", e.OVERPASS_RETRIES)
