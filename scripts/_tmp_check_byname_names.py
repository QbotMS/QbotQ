import json, os, sys, urllib.request, urllib.parse
sys.path.insert(0, "/opt/qbot/app")
import komoot_watch
komoot_watch._load_env()
bearer = os.getenv("QBOT_MCP_BEARER")

NAMES = [
    "Sicily Syracuse",
    "[Q] Sicily - D X Marzamemi · 2026-08-12 · #3193596102",
    "[Q] Sicily D X - SSW · 2026-08-11 · #3190786401",
    "[Q] Sicily - DX Cavagrande · 2026-08-12 · #3186954572",
    "[Q] Sicily D X - nowa 1 · 2026-08-10 · #3186890339",
    "[Q] Sicily - D X ciągle stromo · 2026-08-08 · #3180602371",
    # warianty jakie moze wyslac Karoo (skrocenie / brak srodkowej kropki)
    "[Q] Sicily - D X Marzamemi",
    "Sicily - D X Marzamemi",
    "Marzamemi",
]
for name in NAMES:
    url = "http://127.0.0.1:8002/api/surface/by-name?name=" + urllib.parse.quote(name)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                d = json.loads(body)
                info = (f"{len(d)} segmentow" if isinstance(d, list)
                        else json.dumps(d, ensure_ascii=False)[:120])
            except Exception:
                info = body[:120]
            print(f"HTTP {r.status} | {name[:55]!r} -> {info}")
    except Exception as e:
        body = getattr(e, "read", lambda: b"")().decode("utf-8", "replace")
        print(f"BLAD  | {name[:55]!r} -> {type(e).__name__} {str(e)[:60]} {body[:100]}")
