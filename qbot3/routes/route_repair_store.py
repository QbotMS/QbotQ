"""Zapis naprawionej trasy jako NOWEJ trasy "NAPRAWA" (sesja naprawa3-1910, 19.10.2026).

Oryginal zostaje nietkniety. Nowa trasa = oryginalny przebieg z wszytymi przyjetymi objazdami
(kazdy od kotwicy do kotwicy), zapisana jak trasy Planera: plik
/opt/qbot/artifacts/exports/rwgps/rwgps_naprawa-<hash8>-<nn>.gpx -> summarize_rwgps_artifact
(route_artifacts + parse) -> ensure_route_base. Potem PELNE przeliczenie (nowy przebieg, nic
nie dziedziczymy) w tle: scripts/naprawa_precompute.py (Telegram po koncu). Dzieki temu
Analiza trasy i "Udostepnij" (GPX z POI, Wyslij na Karoo, mail) dzialaja bez zmian po route_id.

Wysokosc objazdow: SRTM30m (route_elevation_engine.srtm30m_opentopodata) - to samo zrodlo co
profil przewyzszen; gdy nie odpowie, punkty objazdu bez <ele> (profil i tak liczy sie z SRTM).
Dok.: docs/PROJEKT_NAPRAWA_TRAS.md (Etap 3).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPAIR_ROUTE_RE = re.compile(r"^naprawa-[0-9a-f]{8}-\d{2}$")
MAX_ANCHOR_GAP_M = 300.0   # koniec objazdu musi lezec przy kotwicy na trasie
GPX_NS = "http://www.topografix.com/GPX/1/1"
APP = Path("/opt/qbot/app")
# Flagi krokow przeliczania (przewyzszenia, cien, kontekst, 5 kategorii) sa w env qbot-api - ten sam
# zestaw co Albert/import tras. Bez nich przeliczenie robi tylko 3 kroki (sprawdzone 19.10).
API_ENV = Path("/etc/qbot/qbot-api.env")


def api_env() -> dict[str, str]:
    """Zmienne z /etc/qbot/qbot-api.env (KEY=VALUE)."""
    out: dict[str, str] = {}
    try:
        for line in API_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().removeprefix("export ").strip()
            out[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


DDL = """
CREATE TABLE IF NOT EXISTS qbot_v2.route_repairs (
    route_id            text PRIMARY KEY,
    parent_route_id     text NOT NULL,
    parent_route_base_id bigint,
    title               text,
    meta_json           jsonb NOT NULL DEFAULT '{}'::jsonb,
    precompute_state    text,
    precompute_jobs     jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS route_repairs_parent_idx ON qbot_v2.route_repairs (parent_route_id);
"""
# Pochodzenie trasy NAPRAWA trzymamy TU, nie w route_artifacts.metadata_json: krok profilu
# nawierzchni (route_artifact_enrich) zapisuje rekord pliku na nowo i kasuje dopisane klucze.


def ensure_table(conn) -> None:
    for stmt in [x.strip() for x in DDL.split(";") if x.strip()]:
        conn.execute(stmt)


def _hav_m(a: dict, b: dict) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000.0 * 2 * math.asin(math.sqrt(h))


def _gpx_bytes(points: list[dict[str, Any]], title: str, parent_name: str) -> bytes:
    ET.register_namespace("", GPX_NS)
    gpx = ET.Element(f"{{{GPX_NS}}}gpx", {"version": "1.1", "creator": "QBot naprawa trasy"})
    md = ET.SubElement(gpx, f"{{{GPX_NS}}}metadata")
    ET.SubElement(md, f"{{{GPX_NS}}}name").text = title
    ET.SubElement(md, f"{{{GPX_NS}}}desc").text = f"Naprawiona wersja trasy: {parent_name}"
    trk = ET.SubElement(gpx, f"{{{GPX_NS}}}trk")
    ET.SubElement(trk, f"{{{GPX_NS}}}name").text = title
    seg = ET.SubElement(trk, f"{{{GPX_NS}}}trkseg")
    for p in points:
        pt = ET.SubElement(seg, f"{{{GPX_NS}}}trkpt", {"lat": f"{p['lat']:.6f}", "lon": f"{p['lon']:.6f}"})
        if p.get("ele") is not None:
            ET.SubElement(pt, f"{{{GPX_NS}}}ele").text = f"{float(p['ele']):.1f}"
    tree = ET.ElementTree(gpx)
    try:
        ET.indent(tree, space="  ")
    except Exception:
        pass
    import io
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue()


def _next_route_id(conn, parent_route_id: str) -> tuple[str, int]:
    from qbot3.routes.planer_stage_export import EXPORT_ROOT
    key = hashlib.sha256(parent_route_id.encode("utf-8")).hexdigest()[:8]
    used = set()
    for r in conn.execute("SELECT route_id FROM qbot_v2.route_artifacts WHERE route_id LIKE %s", (f"naprawa-{key}-%",)).fetchall():
        rid = r["route_id"] if isinstance(r, dict) else r[0]
        if REPAIR_ROUTE_RE.fullmatch(str(rid)):
            used.add(int(str(rid)[-2:]))
    for f in EXPORT_ROOT.glob(f"rwgps_naprawa-{key}-*.gpx"):
        m = re.search(r"-(\d{2})\.gpx$", f.name)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    if n > 99:
        raise RuntimeError("za duzo wersji NAPRAWA dla tej trasy (99)")
    return f"naprawa-{key}-{n:02d}", n


def _detour_points(coords: list) -> list[dict[str, Any]]:
    pts = [{"lat": float(c[0]), "lon": float(c[1])} for c in coords]
    try:
        from qbot3.routes.route_elevation_engine import srtm30m_opentopodata
        eles = srtm30m_opentopodata([(p["lat"], p["lon"]) for p in pts])
        for p, e in zip(pts, eles or []):
            p["ele"] = e
    except Exception:
        pass
    return pts


def save_repaired_route(*, route_id: str, detours: list[dict[str, Any]], kat4: bool = False) -> dict[str, Any]:
    """detours: [{anchor_from_km, anchor_to_km, coordinates: [[lat, lon], ...], distance_km?, risky_km?, km_from?, km_to?}]"""
    from qbot3.routes.planer_stage_export import EXPORT_ROOT, _parent_name
    from qbot3.routes.route_poi_store import _db_conn, _resolve_source_path, _route_base_row
    from qbot3.artifacts.gpx_splitter import _build_segment_points, _parse_gpx_points, _point_at_km, _validate_gpx_file
    from qbot3.routes.route_base_store import ensure_route_base
    from tools.rwgps.client import summarize_rwgps_artifact

    route_id = str(route_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", route_id):
        raise ValueError("niepoprawny route_id")
    if not detours:
        raise ValueError("brak przyjetych objazdow")

    with _db_conn() as conn:
        parent = _route_base_row(conn, route_id=route_id)
        if not parent:
            raise LookupError(f"trasa nie znaleziona: {route_id}")
        parent = dict(parent)
        source_path = _resolve_source_path(parent, conn)
        parent_name = _parent_name(conn, parent)
        new_id, n = _next_route_id(conn, route_id)

    points, _ = _parse_gpx_points(Path(source_path))
    total_km = float(points[-1]["cum_km"])
    ds = sorted(detours, key=lambda d: float(d["anchor_from_km"]))
    prev_to = 0.0
    for d in ds:
        a, b = float(d["anchor_from_km"]), float(d["anchor_to_km"])
        if not (0.0 <= a < b <= total_km + 0.05):
            raise ValueError(f"objazd poza trasa: km {a}-{b} (trasa {total_km:.2f} km)")
        if a < prev_to - 1e-6:
            raise ValueError(f"objazdy nachodza na siebie przy km {a}")
        if len(d.get("coordinates") or []) < 2:
            raise ValueError("objazd bez przebiegu")
        prev_to = b

    out: list[dict[str, Any]] = []

    def add(pts):
        for p in pts:
            q = {"lat": p["lat"], "lon": p["lon"], "ele": p.get("ele")}
            if out and abs(out[-1]["lat"] - q["lat"]) < 1e-7 and abs(out[-1]["lon"] - q["lon"]) < 1e-7:
                continue
            out.append(q)

    cur = 0.0
    lineage_detours = []
    for d in ds:
        a, b = float(d["anchor_from_km"]), min(float(d["anchor_to_km"]), total_km)
        if a > cur + 1e-6:
            seg, _ = _build_segment_points(points, cur, a)
            add(seg)
        dp = _detour_points(d["coordinates"])
        pa, pb = _point_at_km(points, a), _point_at_km(points, b)
        gap_a, gap_b = _hav_m(pa, dp[0]), _hav_m(pb, dp[-1])
        if gap_a > MAX_ANCHOR_GAP_M or gap_b > MAX_ANCHOR_GAP_M:
            raise ValueError(f"objazd km {a:.2f}-{b:.2f} nie styka sie z trasa ({gap_a:.0f} m / {gap_b:.0f} m)")
        add(dp)
        lineage_detours.append({
            "anchor_from_km": round(a, 3), "anchor_to_km": round(b, 3),
            "km_from": d.get("km_from"), "km_to": d.get("km_to"),
            "detour_km": d.get("distance_km"), "risky_km": d.get("risky_km"),
            "variant": d.get("variant"), "source": d.get("source"),
        })
        cur = b
    if cur < total_km - 1e-6:
        seg, _ = _build_segment_points(points, cur, None)
        add(seg)

    new_km = sum(_hav_m(p, q) for p, q in zip(out, out[1:])) / 1000.0
    title = f"{parent_name} · NAPRAWA {n}"
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    file_path = EXPORT_ROOT / f"rwgps_{new_id}.gpx"
    tmp = file_path.with_suffix(".gpx.tmp")
    tmp.write_bytes(_gpx_bytes(out, title, parent_name))
    tmp.replace(file_path)
    val = _validate_gpx_file(file_path, round(new_km, 3))
    if not val.get("valid_gpx"):
        file_path.unlink(missing_ok=True)
        raise RuntimeError("wygenerowany GPX jest niepoprawny")

    summary = summarize_rwgps_artifact(str(file_path))
    if not summary.get("ok"):
        raise RuntimeError(summary.get("reason") or summary.get("error") or "rejestracja GPX nie powiodla sie")
    lineage = {
        "kind": "naprawa_route",
        "route_name": title,
        "parent_route_id": route_id,
        "parent_route_base_id": int(parent["route_base_id"]),
        "parent_route_version_key": str(parent.get("route_version_key") or ""),
        "parent_distance_km": round(total_km, 3),
        "repair_kat4": bool(kat4),
        "repair_detours": lineage_detours,
    }
    with _db_conn() as conn:
        row = conn.execute("SELECT id FROM qbot_v2.route_artifacts WHERE route_id=%s ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1",
                           (new_id,)).fetchone()
        if not row:
            raise RuntimeError(f"brak zapisu route_artifacts dla {new_id}")
        art_id = int(row["id"] if isinstance(row, dict) else row[0])
        conn.execute("UPDATE qbot_v2.route_artifacts SET source='naprawa', "
                     "metadata_json=COALESCE(metadata_json, '{}'::jsonb) || %s::jsonb, updated_at=now() WHERE id=%s",
                     (json.dumps(lineage, ensure_ascii=False), art_id))
        conn.commit()
    with _db_conn() as conn:
        ensure_table(conn)
        conn.execute(
            "INSERT INTO qbot_v2.route_repairs (route_id, parent_route_id, parent_route_base_id, title, meta_json) "
            "VALUES (%s, %s, %s, %s, %s::jsonb) ON CONFLICT (route_id) DO UPDATE SET parent_route_id=EXCLUDED.parent_route_id, "
            "parent_route_base_id=EXCLUDED.parent_route_base_id, title=EXCLUDED.title, meta_json=EXCLUDED.meta_json, updated_at=now()",
            (new_id, route_id, int(parent["route_base_id"]), title, json.dumps(lineage, ensure_ascii=False)))
        conn.commit()
    base = ensure_route_base(new_id)
    return {
        "route_id": new_id,
        "title": title,
        "distance_km": round(new_km, 2),
        "parent_route_id": route_id,
        "parent_distance_km": round(total_km, 2),
        "delta_km": round(new_km - total_km, 2),
        "detours": len(ds),
        "route_artifact_id": art_id,
        "route_base_id": int(base["route_base"]["route_base_id"]),
        "file": str(file_path),
    }


def start_precompute_background(route_id: str) -> int:
    """Pelne przeliczenie nowej trasy w osobnym procesie (Telegram po koncu). Zwraca PID."""
    if not REPAIR_ROUTE_RE.fullmatch(str(route_id)):
        raise ValueError("to nie jest trasa NAPRAWA")
    log = Path("/opt/qbot/artifacts/naprawa_precompute.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(os.devnull, "rb") as dn, log.open("a") as lf:
        p = subprocess.Popen([str(APP / ".venv/bin/python3"), str(APP / "scripts/naprawa_precompute.py"), str(route_id)],
                             cwd=str(APP), stdin=dn, stdout=lf, stderr=lf, start_new_session=True, close_fds=True)
    return p.pid


def precompute_status(route_id: str) -> dict[str, Any]:
    """Stan zadan przeliczania biezacej wersji trasy (z route_precompute_jobs)."""
    from qbot3.routes.route_poi_store import _db_conn, _route_base_row
    from qbot3.routes.route_precompute_orchestrator import active_precompute_job_types
    with _db_conn() as conn:
        base = _route_base_row(conn, route_id=route_id)
        if not base:
            return {"route_id": route_id, "exists": False, "jobs": [], "done": False}
        # Kroki zapisane przez scripts/naprawa_precompute.py (env qbot-api); serwis WWW moze nie
        # miec dostepu do /etc/qbot/qbot-api.env i widzialby tylko 3 kroki (sprawdzone 19.10).
        ensure_table(conn)
        mrow = conn.execute(
            "SELECT precompute_jobs AS j, precompute_state AS st FROM qbot_v2.route_repairs WHERE route_id=%s",
            (route_id,)).fetchone()
        expected = list((mrow or {}).get("j") or []) if isinstance(mrow, dict) else []
        run_state = (mrow or {}).get("st") if isinstance(mrow, dict) else None
        rows = conn.execute(
            "SELECT job_type, status, error, finished_at FROM qbot_v2.route_precompute_jobs "
            "WHERE route_id=%s AND route_version_key=%s", (route_id, base["route_version_key"])).fetchall()
    have = {(r["job_type"] if isinstance(r, dict) else r[0]): (dict(r) if isinstance(r, dict) else {"status": r[1], "error": r[2]}) for r in rows}
    jobs = []
    for jt in (expected or active_precompute_job_types({**os.environ, **api_env()})):
        r = have.get(jt)
        # statusy orkiestratora: running / failed / complete (brak wiersza = czeka)
        jobs.append({"job_type": jt, "status": str((r or {}).get("status") or "pending").lower(), "error": (r or {}).get("error")})
    failed = [j for j in jobs if j["status"] == "failed"]
    done = bool(jobs) and all(j["status"] == "complete" for j in jobs)
    if run_state == "running":
        done = False  # proces w tle jeszcze pracuje (np. profil nawierzchni przed krokami)
    if run_state == "failed":
        failed = failed or [{"job_type": "trigger", "status": "failed"}]
    return {"route_id": route_id, "exists": True, "jobs": jobs, "done": done, "failed": bool(failed),
            "state": run_state}


def set_run_state(route_id: str, state: str, jobs: list[str] | None = None) -> None:
    """Zapis stanu procesu przeliczania przy trasie (running/complete/failed) + lista krokow."""
    from qbot3.routes.route_poi_store import _db_conn
    with _db_conn() as conn:
        ensure_table(conn)
        if jobs is not None:
            conn.execute("UPDATE qbot_v2.route_repairs SET precompute_state=%s, precompute_jobs=%s::jsonb, updated_at=now() "
                         "WHERE route_id=%s", (state, json.dumps(list(jobs)), route_id))
        else:
            conn.execute("UPDATE qbot_v2.route_repairs SET precompute_state=%s, updated_at=now() WHERE route_id=%s",
                         (state, route_id))
        conn.commit()


def repair_info(route_id: str) -> dict[str, Any]:
    """Pochodzenie trasy NAPRAWA + lista napraw danego oryginalu (dla Analizy trasy)."""
    from qbot3.routes.route_poi_store import _db_conn
    with _db_conn() as conn:
        ensure_table(conn)
        conn.commit()
        me = conn.execute("SELECT * FROM qbot_v2.route_repairs WHERE route_id=%s", (route_id,)).fetchone()
        kids = conn.execute("SELECT route_id, title, created_at FROM qbot_v2.route_repairs WHERE parent_route_id=%s "
                            "ORDER BY created_at", (route_id,)).fetchall()
        parent_name = None
        own = conn.execute("SELECT distance_m FROM qbot_v2.route_base WHERE route_id=%s ORDER BY route_modified_at DESC NULLS LAST LIMIT 1",
                           (route_id,)).fetchone()
        if me:
            p = conn.execute("SELECT metadata_json->>'route_name' AS n FROM qbot_v2.route_artifacts WHERE route_id=%s "
                             "ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1", (me["parent_route_id"],)).fetchone()
            parent_name = (p or {}).get("n")
    out: dict[str, Any] = {"route_id": route_id, "is_repair": bool(me),
                           "distance_km": round(float(own["distance_m"]) / 1000.0, 2) if own and own.get("distance_m") else None,
                           "repairs": [{"route_id": k["route_id"], "name": k["title"]} for k in kids]}
    if me:
        meta = me.get("meta_json") or {}
        ds = meta.get("repair_detours") or []
        out.update({"parent_route_id": me["parent_route_id"], "parent_name": parent_name,
                    "parent_distance_km": meta.get("parent_distance_km"), "detours": len(ds),
                    "kat4": bool(meta.get("repair_kat4")), "detour_list": ds,
                    "precompute_state": me.get("precompute_state")})
    return out


# ---------------------------------------------------------------------------
# Szkic naprawy (19.10.2026, sesja szkic-1910). Decyzja Michala: w "Napraw trase" tylko ustalamy
# odcinki; zapis nowej wersji robi sie w Analizie trasy (tam widac stary i naprawiony przebieg).
# Szkic trzyma przyjete objazdy per ORYGINAL, niezaleznie od przelacznika kat. 4 i odswiezenia.
# ---------------------------------------------------------------------------
DRAFT_DDL = """
CREATE TABLE IF NOT EXISTS qbot_v2.route_repair_drafts (
    route_id    text PRIMARY KEY,
    kat4        boolean NOT NULL DEFAULT false,
    detours     jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_at  timestamptz NOT NULL DEFAULT now()
)
"""


def _draft_table(conn) -> None:
    conn.execute(DRAFT_DDL)


def get_draft(route_id: str) -> dict[str, Any]:
    from qbot3.routes.route_poi_store import _db_conn
    with _db_conn() as conn:
        _draft_table(conn)
        conn.commit()
        r = conn.execute("SELECT kat4, detours, updated_at FROM qbot_v2.route_repair_drafts WHERE route_id=%s",
                         (route_id,)).fetchone()
    if not r:
        return {"route_id": route_id, "kat4": False, "detours": [], "updated_at": None}
    return {"route_id": route_id, "kat4": bool(r["kat4"]), "detours": list(r["detours"] or []),
            "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None}


def put_draft(route_id: str, *, kat4: bool, detours: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(detours, list):
        raise ValueError("detours musi byc lista")
    clean = []
    for d in detours:
        if not isinstance(d, dict) or len(d.get("coordinates") or []) < 2:
            raise ValueError("objazd bez przebiegu")
        a, b = float(d["anchor_from_km"]), float(d["anchor_to_km"])
        if not a < b:
            raise ValueError("objazd: zle kotwice")
        clean.append(d)
    clean.sort(key=lambda d: float(d["anchor_from_km"]))
    for x, y in zip(clean, clean[1:]):
        if float(y["anchor_from_km"]) < float(x["anchor_to_km"]):
            raise ValueError(f"objazdy nachodza na siebie przy km {y['anchor_from_km']}")
    from qbot3.routes.route_poi_store import _db_conn
    with _db_conn() as conn:
        _draft_table(conn)
        if clean:
            conn.execute("INSERT INTO qbot_v2.route_repair_drafts (route_id, kat4, detours, updated_at) VALUES (%s,%s,%s::jsonb,now()) "
                         "ON CONFLICT (route_id) DO UPDATE SET kat4=EXCLUDED.kat4, detours=EXCLUDED.detours, updated_at=now()",
                         (route_id, bool(kat4), json.dumps(clean, ensure_ascii=False)))
        else:
            conn.execute("DELETE FROM qbot_v2.route_repair_drafts WHERE route_id=%s", (route_id,))
        conn.commit()
    return get_draft(route_id)


def delete_draft(route_id: str) -> dict[str, Any]:
    return put_draft(route_id, kat4=False, detours=[])
