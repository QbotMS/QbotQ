#!/usr/bin/env python3
"""Czy trasa jest na liscie /api/routes/ready (lista tras Planera wyprawy)? Sekundy."""
import sys

import httpx

sys.path.insert(0, "/opt/qbot/app")
try:
    import qbot_web as w  # noqa: F401
    host, port = getattr(w, "HOST", "127.0.0.1"), getattr(w, "PORT", 8000)
except Exception:
    host, port = "127.0.0.1", 8000
host = "127.0.0.1" if host in ("0.0.0.0", "", None) else host
needle = sys.argv[1] if len(sys.argv) > 1 else "3331694546"
r = httpx.get(f"http://{host}:{port}/api/routes/ready", timeout=10)
print("HTTP", r.status_code, "port", port)
data = r.json()
rows = data if isinstance(data, list) else (data.get("routes") or data.get("items") or [])
print("tras na liscie:", len(rows))
for row in rows:
    if needle in str(row):
        print("ZNALEZIONA:", {k: row.get(k) for k in list(row)[:10]} if isinstance(row, dict) else row)
        break
else:
    print("NIE MA na liscie")
