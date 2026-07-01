"""Listowanie tras i ich wersji z route store (odczyt) + retencja (przycinanie).

Zrodla wersji:
 - aktywny plik gpx (stala nazwa rwgps_<id>.gpx),
 - zarchiwizowane pliki wersji (rwgps_<id>_<sha>.gpx),
 - wiersze route_base per route_id (wersje z policzonymi warstwami).

Retencja: zostaw N najnowszych wersji. Osobno w bazie (route_base + kaskada
warstw) i w plikach archiwalnych. Aktywny plik gpx nigdy nie jest kasowany.

Bazuje pod przyszle narzedzia Alberta route_list / route_recompute.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

EXPORT_DIR = Path("/opt/qbot/artifacts/exports/rwgps")
DEFAULT_KEEP = 3


def _conn():
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row, connect_timeout=5)


def _archived_files(route_id: str) -> list[dict[str, Any]]:
    out = []
    for p in sorted(EXPORT_DIR.glob(f"rwgps_{route_id}_*.gpx")):
        tag = p.stem[len(f"rwgps_{route_id}_"):]
        # tylko realne wersje (sam skrot sha) - pomin poi_backup, course_points itp.
        if not tag or not all(c in "0123456789abcdef" for c in tag):
            continue
        st = p.stat()
        out.append({"sha10": tag, "file": p.name, "size_bytes": st.st_size, "mtime": st.st_mtime})
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def _bases(conn, route_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT route_base_id, route_version_key, distance_m, status, updated_at "
        "FROM qbot_v2.route_base WHERE route_id::text=%s "
        "ORDER BY updated_at DESC NULLS LAST, route_base_id DESC", (route_id,)).fetchall()
    return [dict(r) for r in rows]


def _layers_present(conn, base_id: int) -> dict[str, int]:
    def c(t):
        return conn.execute(f"SELECT count(*) n FROM qbot_v2.{t} WHERE route_base_id=%s",
                            (base_id,)).fetchone()["n"]
    return {"surface": c("route_surface_layer"), "elevation": c("route_elevation_samples"),
            "axis": c("route_axis_segments")}


def list_route_versions(route_id: str) -> dict[str, Any]:
    rid = str(route_id).strip()
    with _conn() as conn:
        bases = _bases(conn, rid)
        active_layers = _layers_present(conn, bases[0]["route_base_id"]) if bases else {}
        name_row = conn.execute(
            "SELECT metadata_json->>'route_name' AS name FROM qbot_v2.route_artifacts "
            "WHERE route_id::text=%s ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1",
            (rid,)).fetchone()
    active = EXPORT_DIR / f"rwgps_{rid}.gpx"
    return {
        "route_id": rid,
        "name": (name_row or {}).get("name"),
        "active_file": active.name if active.exists() else None,
        "active_computed": bool(active_layers.get("axis")),
        "active_layers": active_layers,
        "versions_in_db": len(bases),
        "bases": [{"route_base_id": b["route_base_id"],
                   "route_version_key": (b["route_version_key"] or "")[:12],
                   "distance_km": round(b["distance_m"] / 1000.0, 2) if b.get("distance_m") else None,
                   "status": b.get("status"),
                   "updated_at": str(b.get("updated_at"))} for b in bases],
        "archived_files": _archived_files(rid),
    }


def list_all_routes() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT route_id::text rid, metadata_json->>'route_name' AS name, updated_at "
            "FROM qbot_v2.route_artifacts ORDER BY updated_at DESC NULLS LAST, id DESC").fetchall()
        out = []
        for r in rows:
            rid = r["rid"]
            bases = _bases(conn, rid)
            computed = False
            dist = None
            if bases:
                dist = round(bases[0]["distance_m"] / 1000.0, 2) if bases[0].get("distance_m") else None
                computed = bool(_layers_present(conn, bases[0]["route_base_id"]).get("axis"))
            out.append({"route_id": rid, "name": r.get("name"),
                        "distance_km": dist, "versions_in_db": len(bases),
                        "archived_versions": len(_archived_files(rid)),
                        "computed": computed, "updated_at": str(r.get("updated_at"))})
    return out


def prune_route_versions(route_id: str, keep: int = DEFAULT_KEEP, confirm: bool = False) -> dict[str, Any]:
    """Zostaw N najnowszych wersji trasy; starsze usun.

    Baza: route_base (kaskada zdejmuje warstwy tej wersji). Pliki: archiwalne
    rwgps_<id>_<sha>.gpx. Aktywny plik NIGDY nie jest kasowany. Artefakt trasy,
    ramki i pogoda (dla aktywnej) pozostaja nietkniete.
    Domyslnie DRY-RUN; realne usuniecie wymaga confirm=True.
    """
    rid = str(route_id).strip()
    keep = max(1, int(keep))
    with _conn() as conn:
        bases = _bases(conn, rid)              # najnowsze pierwsze
        arch = _archived_files(rid)            # najnowsze pierwsze
        prune_bases = bases[keep:]
        prune_files = arch[keep:]

        base_report = [{"route_base_id": b["route_base_id"],
                        "route_version_key": (b["route_version_key"] or "")[:12],
                        "updated_at": str(b.get("updated_at")),
                        "layers": _layers_present(conn, b["route_base_id"])}
                       for b in prune_bases]
        file_report = [f["file"] for f in prune_files]

        if not prune_bases and not prune_files:
            return {"status": "NOOP", "route_id": rid, "keep": keep,
                    "versions_in_db": len(bases), "archived_files": len(arch),
                    "note": f"Nie ma czego przycinac (wersji <= {keep})."}

        if not confirm:
            return {"status": "DRY_RUN", "route_id": rid, "keep": keep,
                    "versions_in_db": len(bases), "archived_files": len(arch),
                    "would_delete_bases": base_report,
                    "would_delete_files": file_report,
                    "note": "Podglad. Aby przyciac, uzyj confirm=True."}

        deleted_bases = []
        for b in prune_bases:
            conn.execute("DELETE FROM qbot_v2.route_base WHERE route_base_id=%s",
                         (b["route_base_id"],))
            deleted_bases.append(b["route_base_id"])
        conn.commit()

    removed_files, file_errors = [], []
    for f in prune_files:
        try:
            (EXPORT_DIR / f["file"]).unlink()
            removed_files.append(f["file"])
        except Exception as exc:
            file_errors.append(f"{f['file']}: {exc}")

    return {"status": "PRUNED", "route_id": rid, "keep": keep,
            "deleted_base_ids": deleted_bases, "pruned_bases": base_report,
            "removed_files": removed_files, "file_errors": file_errors}
