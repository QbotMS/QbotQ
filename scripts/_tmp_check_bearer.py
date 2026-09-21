import hashlib, json, os, sys, urllib.request, urllib.parse
sys.path.insert(0, "/opt/qbot/app")
import komoot_watch
komoot_watch._load_env()


def h(v):
    return hashlib.sha256((v or "").encode()).hexdigest()[:10] if v else "(brak)"


bearer = os.getenv("QBOT_MCP_BEARER")
print("QBOT_MCP_BEARER:", h(bearer), "| dlugosc:", len(bearer or ""))
for k in ("QBOT_MCP_TOKEN", "MCP_BEARER", "QBOT_API_TOKEN", "QEXT2_BEARER"):
    v = os.getenv(k)
    if v:
        print(f"{k}: {h(v)} | dlugosc: {len(v)}")

# jaki port ma qbot-api?
import socket
for port in (8000, 8001, 8002, 8181, 30181, 8080):
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port))
        print("port otwarty:", port)
    except Exception:
        pass
    finally:
        s.close()

NAMES = ["Sicily Syracuse", "Marzamemi", "Cavagrande", "Sicily"]
for port in (8001, 8002, 8000, 8181):
    for name in NAMES[:1]:
        url = f"http://127.0.0.1:{port}/api/surface/by-name?name=" + urllib.parse.quote(name)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                body = r.read().decode("utf-8", "replace")
                print(f"port {port} '{name}' -> HTTP {r.status} | {body[:200]}")
        except Exception as e:
            body = getattr(e, "read", lambda: b"")().decode("utf-8", "replace")
            print(f"port {port} '{name}' -> {type(e).__name__} {str(e)[:80]} | {body[:150]}")
