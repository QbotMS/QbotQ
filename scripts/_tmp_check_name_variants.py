import json, os, sys, urllib.parse, urllib.request
sys.path.insert(0, "/opt/qbot/app")
import komoot_watch
komoot_watch._load_env()
bearer = os.getenv("QBOT_MCP_BEARER")
UA = "okhttp/4.12.0"

PELNA = "[Q] Sicily - D X Marzamemi · 2026-08-12 · #3193596102"
WCZORAJ = "Sicily Syracuse"

WARIANTY = [
    ("wczorajsza nazwa (dziala?)", "https://qbot.cytr.us/api/surface/by-name?name=" + urllib.parse.quote(WCZORAJ)),
    ("dzisiejsza, poprawnie zakodowana", "https://qbot.cytr.us/api/surface/by-name?name=" + urllib.parse.quote(PELNA)),
    ("dzisiejsza, BEZ kodowania (# ucina URL)", "https://qbot.cytr.us/api/surface/by-name?name=" + PELNA.replace(" ", "%20")),
    ("dzisiejsza, urwana na #", "https://qbot.cytr.us/api/surface/by-name?name=" + urllib.parse.quote(PELNA.split("#")[0])),
    ("dzisiejsza, kropki zamienione na ?", "https://qbot.cytr.us/api/surface/by-name?name=" + urllib.parse.quote(PELNA.replace("·", "?"))),
    ("dzisiejsza, kropki wyciete", "https://qbot.cytr.us/api/surface/by-name?name=" + urllib.parse.quote(PELNA.replace("·", ""))),
]

for label, url in WARIANTY:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                d = json.loads(body)
                info = f"{len(d)} segmentow" if isinstance(d, list) else json.dumps(d, ensure_ascii=False)[:90]
            except Exception:
                info = body[:90]
            print(f"{label:42s} -> HTTP {r.status} | {info}")
    except Exception as e:
        body = getattr(e, "read", lambda: b"")().decode("utf-8", "replace")
        print(f"{label:42s} -> {type(e).__name__} {str(e)[:40]} | {body[:80].strip()}")
