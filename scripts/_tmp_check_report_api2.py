import subprocess, json
cmd = ["/opt/qbot/app/.venv/bin/python3", "/opt/qbot/app/scripts/dev_fetch.py",
       "--timeout", "180",
       "/api/report/data?route_id=komoot-3180619966&date=2026-08-13&time=06:15&long_stops=0&long_stop_min=0"]
p = subprocess.run(cmd, cwd="/opt/qbot/app", capture_output=True, text=True, timeout=300)
print("RC", p.returncode, "| dlugosc:", len(p.stdout))
print("STDERR:", p.stderr[-600:])
if p.stdout:
    try:
        d = json.loads(p.stdout)
        print("KLUCZE:", sorted(d.keys()))
        r = d.get("route") or {}
        print("route:", {k: r.get(k) for k in list(r)[:12]})
        ch = d.get("chart")
        if isinstance(ch, dict):
            print("chart klucze:", sorted(ch.keys()))
            for k, v in ch.items():
                if isinstance(v, list):
                    print("  ", k, "len", len(v))
    except Exception as e:
        print("NIE JSON:", e)
        print(p.stdout[:600])
