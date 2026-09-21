import json, os, sys, urllib.parse, urllib.request
sys.path.insert(0, "/opt/qbot/app")
import komoot_watch
komoot_watch._load_env()
bearer = os.getenv("QBOT_MCP_BEARER")

NAME = "Sicily - D X Marzamemi"
q = urllib.parse.quote(NAME)
TARGETS = [
    ("lokalnie 8002", f"http://127.0.0.1:8002/api/surface/by-name?name={q}"),
    ("publicznie albert", f"https://albert.cytr.us/api/surface/by-name?name={q}"),
    ("publicznie qbot", f"https://qbot.cytr.us/api/surface/by-name?name={q}"),
]
for label, url in TARGETS:
    for with_auth in (True, False):
        h = {"Authorization": f"Bearer {bearer}"} if with_auth else {}
        req = urllib.request.Request(url, headers=h)
        tag = "z tokenem " if with_auth else "bez tokenu"
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read().decode("utf-8", "replace")
                try:
                    d = json.loads(body)
                    info = f"{len(d)} segmentow" if isinstance(d, list) else json.dumps(d, ensure_ascii=False)[:100]
                except Exception:
                    info = body[:100].replace("\n", " ")
                print(f"{label:20s} {tag} -> HTTP {r.status} | {info}")
        except Exception as e:
            body = getattr(e, "read", lambda: b"")().decode("utf-8", "replace")
            print(f"{label:20s} {tag} -> {type(e).__name__} {str(e)[:60]} | {body[:90]}")
