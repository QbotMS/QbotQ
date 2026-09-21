import json, os, sys, time, traceback
sys.path.insert(0, "/opt/qbot/app")

OUT = "/opt/qbot/app/logs/_tmp_rerun_komoot2.json"
RID = "komoot-3180619966"
state = {"steps": []}


def save():
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, default=str)


def step(name, fn):
    t0 = time.time()
    e = {"step": name, "start": time.strftime("%H:%M:%S")}
    state["steps"].append(e)
    save()
    try:
        e["result"] = fn()
        e["status"] = "OK"
    except Exception as ex:
        e["status"] = "ERROR"
        e["error"] = f"{type(ex).__name__}: {ex}"
        e["trace"] = traceback.format_exc()[-1500:]
    e["sec"] = round(time.time() - t0, 1)
    save()


def load_env():
    import komoot_watch
    komoot_watch._load_env()
    return {k: os.getenv(k) for k in (
        "QBOT_ROUTE_ELEVATION_ENABLED", "QBOT_ROUTE_SHADE_ENABLED",
        "QBOT_ROUTE_SURFACE_CONTEXT_ENABLED", "QBOT_ROUTE_SURFACE_CATEGORY_ENABLED")}


def precompute():
    from qbot3.routes.route_precompute_orchestrator import ensure_route_precompute
    r = ensure_route_precompute(route_id=RID, trigger_source="claude_manual_fix2", scope="all")
    return {k: r.get(k) for k in ("status", "route_base_id", "route_version_key",
                                  "jobs", "stages", "errors", "error")}


def counts():
    from fitmodel.api import _db_connect
    res = {}
    with _db_connect() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT route_base_id FROM qbot_v2.route_base WHERE route_id=%s
                       ORDER BY route_base_id DESC LIMIT 1""", (RID,))
        bid = cur.fetchone()[0]
        res["route_base_id"] = bid
        for t in ("route_elevation_samples", "route_surface_layer", "route_axis_segments",
                  "route_poi", "route_climb_events"):
            try:
                cur.execute(f"SELECT count(*) FROM qbot_v2.{t} WHERE route_base_id=%s", (bid,))
                res[t] = cur.fetchone()[0]
            except Exception as ex:
                conn.rollback()
                res[t] = f"ERR {str(ex)[:90]}"
    return res


step("load_env", load_env)
step("precompute_all", precompute)
step("counts", counts)
state["done"] = True
save()
print("DONE")
