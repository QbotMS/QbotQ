import importlib.util, json, sys, time, urllib.request

spec = importlib.util.spec_from_file_location("dev_fetch", "/opt/qbot/app/scripts/dev_fetch.py")
mod = importlib.util.module_from_spec(spec)
sys.argv = ["dev_fetch", "/"]
try:
    spec.loader.exec_module(mod)
except SystemExit:
    pass
except Exception as e:
    print("import dev_fetch:", type(e).__name__, str(e)[:200])

base, cookie = mod.get_auth() if hasattr(mod, "get_auth") else (None, None)
print("auth:", type(base), str(base)[:80], "| cookie:", bool(cookie))

url = (str(base).rstrip("/") if base else "http://127.0.0.1:30181") + \
      "/api/report/data?route_id=komoot-3180619966&date=2026-08-13&time=06:15&long_stops=0&long_stop_min=0"
req = urllib.request.Request(url)
if cookie:
    req.add_header("Cookie", cookie)
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=240) as r:
        body = r.read().decode("utf-8", "replace")
        print("HTTP", r.status, "| sec", round(time.time() - t0, 1), "| bytes", len(body))
except Exception as e:
    body = getattr(e, "read", lambda: b"")().decode("utf-8", "replace")
    print("BLAD:", type(e).__name__, str(e)[:200], "| sec", round(time.time() - t0, 1))
    print("BODY:", body[:400])
    raise SystemExit(0)

try:
    d = json.loads(body)
    print("KLUCZE:", sorted(d.keys()))
    for k in ("route", "start", "time"):
        if isinstance(d.get(k), dict):
            print(k, ":", json.dumps(d[k], ensure_ascii=False)[:300])
    ch = d.get("chart")
    if isinstance(ch, dict):
        print("chart:", {k: (len(v) if isinstance(v, list) else v) for k, v in list(ch.items())[:12]})
except Exception as e:
    print("NIE JSON:", e)
    print(body[:400])
