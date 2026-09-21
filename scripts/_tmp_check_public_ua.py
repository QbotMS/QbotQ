import json, os, sys, urllib.parse, urllib.request
sys.path.insert(0, "/opt/qbot/app")
import komoot_watch
komoot_watch._load_env()
bearer = os.getenv("QBOT_MCP_BEARER")

q = urllib.parse.quote("Sicily - D X Marzamemi")
URL = f"https://qbot.cytr.us/api/surface/by-name?name={q}"
UAS = {
    "python-urllib (domyslny)": None,
    "okhttp (Android/QExt2)": "okhttp/4.12.0",
    "curl": "curl/8.5.0",
    "przegladarka": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "QExt2": "QExt2/147 (Karoo3; Android)",
}
for label, ua in UAS.items():
    h = {"Authorization": f"Bearer {bearer}"}
    if ua:
        h["User-Agent"] = ua
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, headers=h), timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                d = json.loads(body)
                info = f"{len(d)} segmentow" if isinstance(d, list) else json.dumps(d, ensure_ascii=False)[:90]
            except Exception:
                info = body[:90].replace("\n", " ")
            print(f"{label:26s} -> HTTP {r.status} | {info}")
    except Exception as e:
        body = getattr(e, "read", lambda: b"")().decode("utf-8", "replace")
        print(f"{label:26s} -> {type(e).__name__} {str(e)[:40]} | {body[:80].strip()}")
