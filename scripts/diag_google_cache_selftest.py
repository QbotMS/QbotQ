#!/usr/bin/env python3
"""Zaklada tabele qbot_v2.google_places_cache i sprawdza zapis/odczyt (wpis testowy usuwany). Bez Google."""
import os
import sys

sys.path.insert(0, "/opt/qbot/app")
for p in ("/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env"):
    try:
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip().removeprefix("export ").strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass
from qbot3.routes import google_places_cache as gc  # noqa: E402

key = "selftest-" + gc.cache_key(0, 0, 1, ["x"], 1)[:16]
gc.put(key, {"selftest": True}, [{"id": "t"}])
print("odczyt:", gc.get(key))
with gc._conn() as c:
    c.execute("DELETE FROM qbot_v2.google_places_cache WHERE cache_key=%s", (key,))
    n = c.execute("SELECT count(*) FROM qbot_v2.google_places_cache").fetchone()[0]
print("wpisow w cache po sprzataniu:", n)
