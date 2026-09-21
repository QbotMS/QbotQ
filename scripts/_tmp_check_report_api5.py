import importlib.util, json, sys, time, urllib.request

spec = importlib.util.spec_from_file_location("dev_fetch", "/opt/qbot/app/scripts/dev_fetch.py")
mod = importlib.util.module_from_spec(spec)
sys.argv = ["dev_fetch", "/"]
try:
    spec.loader.exec_module(mod)
except SystemExit:
    pass

users, sign_val, cookie_make = mod.get_auth()
username = sorted(users.keys())[0]
cookie_value = cookie_make(username, sign_val)
if isinstance(cookie_value, tuple):
    cookie_value = cookie_value[0]

url = ("http://127.0.0.1:%d/api/report/data?route_id=komoot-3180619966"
       "&date=2026-08-13&time=06:15&long_stops=0&long_stop_min=0" % mod.PORT)
req = urllib.request.Request(url, headers={"Cookie": "qbot_session=" + cookie_value})
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

d = json.loads(body)
print("KLUCZE:", sorted(d.keys()))
for k in ("route", "start"):
    if isinstance(d.get(k), dict):
        print(k, json.dumps(d[k], ensure_ascii=False)[:300])
ch = d.get("chart")
if isinstance(ch, dict):
    print("chart:", {k: (len(v) if isinstance(v, list) else v) for k, v in list(ch.items())[:14]})
