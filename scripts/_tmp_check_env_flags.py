import os, sys, json
sys.path.insert(0, "/opt/qbot/app")
# odtworz srodowisko tak, jak robi to worker uruchamiany przez systemd/cron
keys = ["QBOT_ROUTE_ELEVATION_ENABLED", "QBOT_ROUTE_SHADE_ENABLED",
        "QBOT_ROUTE_SURFACE_CONTEXT_ENABLED", "QBOT_ROUTE_SURFACE_CATEGORY_ENABLED",
        "QBOT3_ENABLED"]
print("== przed zaladowaniem env ==")
for k in keys:
    print(" ", k, "=", os.getenv(k, "(brak)"))

loaded = None
for mod, fn in (("qbot_env", "load_env"), ("komoot_watch", "_load_env"),
                ("qbot_config", "load_env")):
    try:
        m = __import__(mod)
        getattr(m, fn)()
        loaded = f"{mod}.{fn}"
        break
    except Exception as e:
        print("  proba", mod, fn, "->", type(e).__name__, str(e)[:80])

print("zaladowano przez:", loaded)
print("== po zaladowaniu ==")
for k in keys:
    print(" ", k, "=", os.getenv(k, "(brak)"))
