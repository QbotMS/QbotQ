import subprocess, json, sys
cmd = ["/opt/qbot/app/.venv/bin/python3", "/opt/qbot/app/scripts/dev_fetch.py",
       "/api/report/data?route_id=komoot-3180619966&date=2026-08-13&time=06:15&long_stops=0&long_stop_min=0"]
p = subprocess.run(cmd, cwd="/opt/qbot/app", capture_output=True, text=True, timeout=300)
out = p.stdout
print("RC", p.returncode, "| dlugosc odpowiedzi:", len(out))
print("STDERR:", p.stderr[:500])
try:
    d = json.loads(out)
    print("KLUCZE:", sorted(d.keys())[:20])
    r = d.get("route") or {}
    print("route:", {k: r.get(k) for k in ("name", "route_id", "distance_km", "ascent_m")})
    ch = d.get("chart") or {}
    print("chart klucze:", sorted(ch.keys())[:15] if isinstance(ch, dict) else type(ch))
    for k in ("elevation", "elev", "points", "samples"):
        if isinstance(ch, dict) and k in ch:
            print(f"  chart[{k}] dlugosc:", len(ch[k]))
except Exception as e:
    print("NIE JSON:", type(e).__name__, str(e)[:200])
    print(out[:800])
