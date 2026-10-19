"""Pelne przeliczenie naprawionej trasy (NAPRAWA) w tle + Telegram po koncu (sesja naprawa3-1910).

Uruchamiane przez qbot3/routes/route_repair_store.start_precompute_background po zapisie trasy
w "Napraw trase". To samo pelne przeliczenie co dla nowej trasy (ensure_route_precompute, scope all).
Log: /opt/qbot/artifacts/naprawa_precompute.log
Uzycie: .venv/bin/python3 scripts/naprawa_precompute.py naprawa-<hash8>-<nn>
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

APP = Path("/opt/qbot/app")
sys.path.insert(0, str(APP))


def _telegram(text: str) -> None:
    try:
        import httpx
        import qbot_config as cfg
        httpx.post(f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage",
                   json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": text[:4000]}, timeout=15)
    except Exception as exc:  # noqa: BLE001
        print(f"Telegram niewyslany: {exc}", file=sys.stderr)


def main() -> int:
    if len(sys.argv) < 2:
        print("uzycie: naprawa_precompute.py <route_id>", file=sys.stderr)
        return 2
    route_id = sys.argv[1].strip()
    from qbot3.routes.route_repair_store import REPAIR_ROUTE_RE, precompute_status
    if not REPAIR_ROUTE_RE.fullmatch(route_id):
        print(f"to nie jest trasa NAPRAWA: {route_id}", file=sys.stderr)
        return 2
    title = route_id
    try:
        from qbot3.routes.route_poi_store import _db_conn
        with _db_conn() as conn:
            r = conn.execute("SELECT metadata_json->>'route_name' AS n FROM qbot_v2.route_artifacts WHERE route_id=%s "
                             "ORDER BY updated_at DESC NULLS LAST LIMIT 1", (route_id,)).fetchone()
            if r and (r["n"] if isinstance(r, dict) else r[0]):
                title = r["n"] if isinstance(r, dict) else r[0]
    except Exception:
        pass
    # srodowisko qbot-api (flagi krokow przeliczania) - jak Albert/import tras
    import os
    from qbot3.routes.route_repair_store import api_env
    for k, v in api_env().items():
        os.environ[k] = v
    from qbot3.routes.route_precompute_orchestrator import active_precompute_job_types
    from qbot3.routes.route_repair_store import set_run_state
    set_run_state(route_id, "running", list(active_precompute_job_types()))
    t0 = time.time()
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} START {route_id} ({title}) kroki: {','.join(active_precompute_job_types())}", flush=True)
    try:
        # Ta sama sciezka co import nowej trasy (webhook RWGPS / Telegram): profil nawierzchni
        # (route_artifact_enrich) -> route_base -> ramki -> pelne przeliczenie. Bez profilu krok
        # route_surface pada ("brak profilu nawierzchni") - sprawdzone 19.10.
        import importlib.util
        spec = importlib.util.spec_from_file_location("route_precompute_trigger", str(APP / "scripts/route_precompute_trigger.py"))
        trig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(trig)
        res = trig.ensure_route_precompute_trigger(route_id=route_id, trigger_source="naprawa", env=dict(os.environ))
        print(f"trigger: status={res.get('status')} trigger_status={res.get('trigger_status')} "
              f"surface={(res.get('route_surface') or {}).get('status')} frames={(res.get('route_frames') or {}).get('status')}", flush=True)
        if res.get("status") != "OK":
            raise RuntimeError(f"{res.get('trigger_status')}: surface={res.get('route_surface')} frames={res.get('route_frames')}"[:600])
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        set_run_state(route_id, "failed")
        _telegram(f"QBot: przeliczanie trasy „{title}” NIEUDANE: {exc}")
        return 1
    set_run_state(route_id, "complete")
    st = precompute_status(route_id)
    mins = max(1, round((time.time() - t0) / 60))
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} KONIEC {route_id} status={res.get('status')} done={st.get('done')} "
          f"failed={st.get('failed')}", flush=True)
    if st.get("done") and not st.get("failed"):
        _telegram(f"QBot: trasa „{title}” przeliczona ({mins} min). Gotowa w Analizie trasy — "
                  f"zakładka Udostępnij: Wyślij na Karoo / GPX z POI.")
        return 0
    bad = ", ".join(f"{j['job_type']}={j['status']}" for j in st.get("jobs", []) if j["status"] != "complete")
    _telegram(f"QBot: przeliczanie trasy „{title}” zakończone z problemami ({mins} min): {bad or res.get('status')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
