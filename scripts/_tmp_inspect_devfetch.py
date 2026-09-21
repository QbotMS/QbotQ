import json, sys, time, urllib.request, http.cookiejar
sys.path.insert(0, "/opt/qbot/app")
sys.argv = ["dev_fetch"]
import importlib.util
spec = importlib.util.spec_from_file_location("dev_fetch", "/opt/qbot/app/scripts/dev_fetch.py")
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except SystemExit:
    pass

URL = ("/api/report/data?route_id=komoot-3180619966&date=2026-08-13"
       "&time=06:15&long_stops=0&long_stop_min=0")

# uzyj funkcji budujacych sesje z dev_fetch, ale z dluzszym timeoutem
build = getattr(mod, "_session", None) or getattr(mod, "build_opener", None)
print("funkcje w dev_fetch:", [n for n in dir(mod) if not n.startswith("__")][:25])
