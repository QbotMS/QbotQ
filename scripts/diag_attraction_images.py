#!/usr/bin/env python3
"""Sprawdza, czy image_url polecanych atrakcji trasy zwracaja obraz (HTTP 200, image/*)."""
import os
import sys

import httpx
import psycopg

sys.path.insert(0, "/opt/qbot/app")
rid = sys.argv[1] if len(sys.argv) > 1 else "komoot-3331694546"
with psycopg.connect(host=os.getenv("PGHOST", "127.0.0.1"), dbname=os.getenv("PGDATABASE", "qbot"),
                     user=os.getenv("PGUSER", "qbot"), password=os.getenv("PGPASSWORD", "")) as c:
    rows = c.execute(
        "SELECT l.name, l.image_url FROM qbot_v2.route_attraction_layer l "
        "JOIN qbot_v2.route_attraction_run r ON r.run_id=l.run_id JOIN qbot_v2.route_base b ON b.route_base_id=r.route_base_id "
        "WHERE b.route_id=%s AND b.status='active' AND r.published AND l.is_recommended ORDER BY l.km_on_route",
        (rid,)).fetchall()
ok = 0
hdr = {"User-Agent": "QBot/1.0 (qbot-local; image check)"}
for name, url in rows:
    if not url:
        print("BRAK  ", name)
        continue
    try:
        r = httpx.get(url, headers=hdr, timeout=8, follow_redirects=True)
        ct = r.headers.get("content-type", "")
        good = r.status_code == 200 and ct.startswith("image/")
        ok += good
        print("OK    " if good else f"ZLE {r.status_code} {ct[:20]}", name)
    except Exception as exc:
        print("BLAD  ", name, type(exc).__name__)
print(f"{ok}/{len(rows)} zdjec dziala")
