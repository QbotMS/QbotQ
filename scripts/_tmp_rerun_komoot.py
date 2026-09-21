import json, os, sys, time, traceback
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"

OUT = "/opt/qbot/app/logs/_tmp_rerun_komoot.json"
RID = "komoot-3180619966"
ART_ID = 599

state = {"steps": []}


def save():
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, default=str)


def step(name, fn):
    t0 = time.time()
    entry = {"step": name, "started": time.strftime("%H:%M:%S")}
    state["steps"].append(entry)
    save()
    try:
        entry["result"] = fn()
        entry["status"] = "OK"
    except Exception as e:
        entry["status"] = "ERROR"
        entry["error"] = f"{type(e).__name__}: {e}"
        entry["trace"] = traceback.format_exc()[-1500:]
    entry["sec"] = round(time.time() - t0, 1)
    save()
    return entry


def do_surface():
    from scripts.route_precompute_trigger import _ensure_rwgps_surface_profile
    r = _ensure_rwgps_surface_profile(RID, route_artifact_id=ART_ID, force=True)
    return {k: r.get(k) for k in ("status", "surface_status", "surface_profile_id", "error")}


def check_profile():
    from fitmodel.api import _db_connect
    with _db_connect() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT id, coverage_pct, status, enriched_at
                       FROM qbot_v2.route_surface_profiles
                       WHERE route_artifact_id=%s ORDER BY id DESC""", (ART_ID,))
        return [list(r) for r in cur.fetchall()]


def do_precompute():
    from qbot3.routes.route_precompute_orchestrator import ensure_route_precompute
    r = ensure_route_precompute(route_id=RID, trigger_source="claude_manual_fix", scope="all")
    return {k: r.get(k) for k in ("status", "route_base_id", "route_version_key",
                                  "stages", "errors", "error")}


step("surface_enrich_force", do_surface)
step("profile_state", check_profile)
step("precompute_all", do_precompute)
state["done"] = True
save()
print("DONE")
