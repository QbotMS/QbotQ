#!/usr/bin/env python3
"""Ponowne przeliczenie profilu nawierzchni trasy + warstw precompute.

  .venv/bin/python3 scripts/recompute_route_surface.py <route_id> --bg   # w tle, od razu wraca
  log: /opt/qbot/artifacts/recompute_surface_<route_id>.log
Bez --bg dziala na pierwszym planie (tylko przez SSH, nie dev_shell_exec).

Kroki: (1) qbot_route_artifact_enrich z enrich=surface (zapis route_surface_profiles;
zrodlo drog: lokalna baza OSM PL lub Overpass - docs/OSM_LOCAL_SURFACE.md),
(2) ensure_route_precompute (route_base, route_surface_layer, wysokosci, ...).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

APP = "/opt/qbot/app"
sys.path.insert(0, APP)
os.chdir(APP)


def _load_env(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip().removeprefix("export ").strip()
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key, val)
    except OSError:
        pass


for _p in ("/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env"):
    _load_env(_p)
os.environ.setdefault("QBOT3_ENABLED", "1")


def _artifact_path(route_id: str) -> str:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
    ) as conn:
        row = conn.execute(
            "SELECT artifact_path FROM qbot_v2.route_artifacts WHERE route_id::text=%s "
            "ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1",
            (route_id,),
        ).fetchone()
    if not row or not row.get("artifact_path"):
        raise SystemExit(f"Brak artefaktu GPX dla {route_id}")
    return str(row["artifact_path"])


def run(route_id: str) -> int:
    path = _artifact_path(route_id)
    print(f"[{time.strftime('%H:%M:%S')}] trasa={route_id} plik={path}", flush=True)

    from qbot_route_tools import _tool_qbot_route_artifact_enrich

    t0 = time.time()
    res = _tool_qbot_route_artifact_enrich({
        "artifact_path": path, "enrich": ["summary", "surface"], "surface_source": "auto", "sample_every_m": 50,
    })
    prof = res.get("surface_profile") or {}
    print(json.dumps({
        "krok": "nawierzchnia", "sek": round(time.time() - t0, 1),
        "quality_status": prof.get("quality_status"), "coverage_pct": prof.get("coverage_pct"),
        "unknown_surface_pct": prof.get("unknown_surface_pct"), "warnings": prof.get("warnings"),
    }, ensure_ascii=False, default=str), flush=True)

    from qbot3.routes.route_precompute_orchestrator import ensure_route_precompute

    t1 = time.time()
    try:
        pre = ensure_route_precompute(route_id=route_id, trigger_source="manual_surface_recompute")
        print(json.dumps({"krok": "precompute", "sek": round(time.time() - t1, 1), "wynik": pre},
                         ensure_ascii=False, default=str)[:4000], flush=True)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"krok": "precompute", "blad": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), flush=True)
        return 1
    print(f"[{time.strftime('%H:%M:%S')}] KONIEC", flush=True)
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Uzycie: recompute_route_surface.py <route_id> [--bg]")
        return 2
    route_id = args[0].strip()
    if "--bg" in sys.argv:
        log = f"/opt/qbot/artifacts/recompute_surface_{route_id}.log"
        with open(os.devnull, "rb") as dn, open(log, "a") as lf:
            p = subprocess.Popen([sys.executable, __file__, route_id], stdin=dn, stdout=lf, stderr=lf,
                                 start_new_session=True, close_fds=True)
        print(f"przeliczanie w tle, pid={p.pid}, log={log}")
        return 0
    return run(route_id)


if __name__ == "__main__":
    raise SystemExit(main())
