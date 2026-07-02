#!/usr/bin/env python3
"""ESA WorldCover 10 m tile cache for QBot route shade/landcover.

Lazy per-tile cache of the WorldCover v200 (2021) discrete Map COGs, in
3x3 degree tiles named by their lower-left corner (e.g. N51E021). Tiles are
downloaded on demand from the public AWS Open Data bucket (anonymous HTTPS)
and reused across all routes touching that region. Each tile carries a human
label (auto-seeded from a reverse geocode of the tile centre, editable).

Library use from the shade sampler: ensure_tile / tiles_for_bbox / touch_tile.
CLI for housekeeping:

  .venv/bin/python -m qbot3.routes.worldcover_tiles status
  .venv/bin/python -m qbot3.routes.worldcover_tiles where 50.9 14.2
  .venv/bin/python -m qbot3.routes.worldcover_tiles get N51E021
  .venv/bin/python -m qbot3.routes.worldcover_tiles name N48E012 "Saska Szwajcaria / Praga"
  .venv/bin/python -m qbot3.routes.worldcover_tiles rm N48E012
  .venv/bin/python -m qbot3.routes.worldcover_tiles prune --max-gb 0.5
  .venv/bin/python -m qbot3.routes.worldcover_tiles prune --older-than 60

Dokumentacja: docs/PROJEKT_OTOCZENIE.md (skąd/gdzie/po co/dlaczego; §6 = co odrzucono).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

WC_VERSION = "v200"
WC_YEAR = "2021"
_BASE_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/"
    f"{WC_VERSION}/{WC_YEAR}/map/ESA_WorldCover_10m_{WC_YEAR}_{WC_VERSION}_{{tile}}_Map.tif"
)
USER_AGENT = "QBot/1.0 (route shade tile cache)"
TILE_DEG = 3
_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"


def cache_dir() -> Path:
    d = Path(os.getenv("QBOT_WORLDCOVER_DIR", "/opt/qbot/artifacts/worldcover"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tile_name(lat: float, lon: float) -> str:
    """Lower-left-corner tile id for a coordinate, e.g. (52.6, 21.6) -> N51E021."""
    la = int(math.floor(lat / TILE_DEG) * TILE_DEG)
    lo = int(math.floor(lon / TILE_DEG) * TILE_DEG)
    ns = "N" if la >= 0 else "S"
    ew = "E" if lo >= 0 else "W"
    return f"{ns}{abs(la):02d}{ew}{abs(lo):03d}"


def parse_tile(tile: str) -> tuple[int, int]:
    """Tile id -> (lower-left lat, lower-left lon)."""
    la = int(tile[1:3]) * (1 if tile[0] == "N" else -1)
    lo = int(tile[4:7]) * (1 if tile[3] == "E" else -1)
    return la, lo


def tile_center(tile: str) -> tuple[float, float]:
    la, lo = parse_tile(tile)
    return la + TILE_DEG / 2, lo + TILE_DEG / 2


def tiles_for_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[str]:
    """All tiles intersecting a bbox (handles routes crossing a 3-degree line)."""
    la0 = int(math.floor(min_lat / TILE_DEG) * TILE_DEG)
    lo0 = int(math.floor(min_lon / TILE_DEG) * TILE_DEG)
    out: list[str] = []
    la = la0
    while la <= max_lat:
        lo = lo0
        while lo <= max_lon:
            out.append(tile_name(la + 0.001, lo + 0.001))
            lo += TILE_DEG
        la += TILE_DEG
    seen: set[str] = set()
    uniq = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def tile_path(tile: str, base: Path | None = None) -> Path:
    base = base or cache_dir()
    return base / f"ESA_WorldCover_10m_{WC_YEAR}_{WC_VERSION}_{tile}_Map.tif"


def _index_path(base: Path) -> Path:
    return base / "index.json"


def _load_index(base: Path) -> dict:
    p = _index_path(base)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"tiles": {}}


def _save_index(base: Path, idx: dict) -> None:
    tmp = _index_path(base).with_suffix(".json.part")
    tmp.write_text(json.dumps(idx, indent=2, sort_keys=True, ensure_ascii=False))
    tmp.replace(_index_path(base))


def geocode_label(tile: str) -> str:
    """Best-effort human label from a reverse geocode of the tile centre."""
    lat, lon = tile_center(tile)
    try:
        r = httpx.get(_NOMINATIM,
                      params={"lat": lat, "lon": lon, "format": "json", "zoom": 5,
                              "accept-language": "pl"},
                      headers={"User-Agent": "QBot/1.0 (tile labeler)"}, timeout=15)
        a = r.json().get("address", {})
        region = a.get("state") or a.get("region") or a.get("county") or ""
        country = a.get("country") or ""
        label = " / ".join(x for x in (region, country) if x)
        return label or ""
    except Exception:
        return ""


def set_label(tile: str, label: str, base: Path | None = None) -> None:
    base = base or cache_dir()
    idx = _load_index(base)
    ent = idx["tiles"].setdefault(tile, {})
    ent["label"] = label
    _save_index(base, idx)


def ensure_tile(tile: str, base: Path | None = None) -> Path:
    """Return local path to a tile, downloading it once if absent. Updates index."""
    base = base or cache_dir()
    path = tile_path(tile, base)
    idx = _load_index(base)
    if path.exists() and path.stat().st_size > 0:
        ent = idx["tiles"].setdefault(tile, {})
        ent.setdefault("bytes", path.stat().st_size)
        ent.setdefault("downloaded_at", _now())
        ent["last_used_at"] = _now()
        if not ent.get("label"):
            ent["label"] = geocode_label(tile)
        _save_index(base, idx)
        return path

    url = _BASE_URL.format(tile=tile)
    tmp = path.with_suffix(".tif.part")
    headers = {"User-Agent": USER_AGENT}
    with httpx.stream("GET", url, headers=headers, timeout=120, follow_redirects=True) as r:
        if r.status_code == 404:
            raise FileNotFoundError(f"WorldCover tile {tile} does not exist (ocean / out of grid)")
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        with open(tmp, "wb") as fh:
            for chunk in r.iter_bytes(1024 * 256):
                fh.write(chunk)
    size = tmp.stat().st_size
    if total and size != total:
        tmp.unlink(missing_ok=True)
        raise IOError(f"WorldCover tile {tile} truncated: {size} != {total}")
    tmp.replace(path)
    idx["tiles"][tile] = {"bytes": size, "downloaded_at": _now(), "last_used_at": _now(),
                          "label": geocode_label(tile)}
    _save_index(base, idx)
    return path


def touch_tile(tile: str, base: Path | None = None) -> None:
    """Mark a tile as just used (for LRU pruning). Call from the sampler."""
    base = base or cache_dir()
    idx = _load_index(base)
    if tile in idx["tiles"]:
        idx["tiles"][tile]["last_used_at"] = _now()
        _save_index(base, idx)


def _reconcile(base: Path) -> dict:
    """Sync index with files actually on disk (preserve labels)."""
    idx = _load_index(base)
    on_disk = {}
    for p in base.glob(f"ESA_WorldCover_10m_{WC_YEAR}_{WC_VERSION}_*_Map.tif"):
        tile = p.name.split("_")[-2]
        on_disk[tile] = p.stat().st_size
    for tile, size in on_disk.items():
        ent = idx["tiles"].setdefault(tile, {"downloaded_at": _now(), "last_used_at": _now()})
        ent["bytes"] = size
    for tile in list(idx["tiles"].keys()):
        if tile not in on_disk:
            del idx["tiles"][tile]
    _save_index(base, idx)
    return idx


def list_tiles(base: Path | None = None) -> list[dict]:
    base = base or cache_dir()
    idx = _reconcile(base)
    rows = []
    for tile, ent in idx["tiles"].items():
        rows.append({"tile": tile, "bytes": ent.get("bytes", 0),
                     "label": ent.get("label", ""),
                     "downloaded_at": ent.get("downloaded_at", "?"),
                     "last_used_at": ent.get("last_used_at", "?")})
    rows.sort(key=lambda r: r["last_used_at"])
    return rows


def remove_tiles(tiles: list[str], base: Path | None = None, dry_run: bool = False) -> list[str]:
    base = base or cache_dir()
    removed = []
    idx = _load_index(base)
    for tile in tiles:
        p = tile_path(tile, base)
        if p.exists():
            if not dry_run:
                p.unlink()
                idx["tiles"].pop(tile, None)
            removed.append(tile)
    if not dry_run:
        _save_index(base, idx)
    return removed


def prune(base: Path | None = None, max_gb: float | None = None,
          older_than_days: int | None = None, dry_run: bool = False) -> list[str]:
    base = base or cache_dir()
    rows = list_tiles(base)  # oldest-used first
    victims: list[str] = []
    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - older_than_days * 86400
        for r in rows:
            try:
                ts = datetime.fromisoformat(r["last_used_at"]).timestamp()
            except Exception:
                ts = 0
            if ts < cutoff:
                victims.append(r["tile"])
    if max_gb is not None:
        cap = max_gb * 1024 ** 3
        total = sum(r["bytes"] for r in rows)
        for r in rows:
            if total <= cap:
                break
            if r["tile"] not in victims:
                victims.append(r["tile"])
                total -= r["bytes"]
    return remove_tiles(victims, base, dry_run=dry_run)


def _fmt(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def _cmd_status(base: Path) -> None:
    rows = list_tiles(base)
    if not rows:
        print(f"cache pusty ({base})")
        return
    total = sum(r["bytes"] for r in rows)
    print(f"cache: {base}   kafli: {len(rows)}   razem: {_fmt(total)}\n")
    print(f"  {'kafel':9s} {'rozmiar':>9s}  {'ostatnio':10s}  nazwa")
    for r in rows:
        print(f"  {r['tile']:9s} {_fmt(r['bytes']):>9s}  {r['last_used_at'][:10]}  {r['label'] or '—'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="worldcover_tiles")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    w = sub.add_parser("where"); w.add_argument("lat", type=float); w.add_argument("lon", type=float)
    g = sub.add_parser("get"); g.add_argument("tiles", nargs="+")
    nm = sub.add_parser("name"); nm.add_argument("tile"); nm.add_argument("label", nargs="*")
    r = sub.add_parser("rm"); r.add_argument("tiles", nargs="+"); r.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("prune")
    p.add_argument("--max-gb", type=float); p.add_argument("--older-than", type=int)
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    base = cache_dir()

    if a.cmd == "status":
        _cmd_status(base)
    elif a.cmd == "where":
        t = tile_name(a.lat, a.lon)
        idx = _load_index(base)
        lab = idx["tiles"].get(t, {}).get("label", "")
        print(f"{t}  {lab}".rstrip())
    elif a.cmd == "get":
        for t in a.tiles:
            path = ensure_tile(t, base)
            lab = _load_index(base)["tiles"].get(t, {}).get("label", "")
            print(f"OK {t} -> {path} ({_fmt(path.stat().st_size)})  {lab}".rstrip())
    elif a.cmd == "name":
        if a.label:
            set_label(a.tile, " ".join(a.label), base)
            print(f"nazwa kafla {a.tile}: {' '.join(a.label)}")
        else:
            lab = geocode_label(a.tile)
            set_label(a.tile, lab, base)
            print(f"nazwa kafla {a.tile} (auto): {lab or '(nie udalo sie ustalic)'}")
    elif a.cmd == "rm":
        done = remove_tiles(a.tiles, base, dry_run=a.dry_run)
        tag = "[dry-run] usunalbym" if a.dry_run else "usunieto"
        print(f"{tag}: {', '.join(done) if done else '(nic – brak w cache)'}")
    elif a.cmd == "prune":
        if a.max_gb is None and a.older_than is None:
            print("podaj --max-gb i/lub --older-than"); return 2
        done = prune(base, max_gb=a.max_gb, older_than_days=a.older_than, dry_run=a.dry_run)
        tag = "[dry-run] usunalbym" if a.dry_run else "usunieto"
        print(f"{tag}: {', '.join(done) if done else '(nic do usuniecia)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
