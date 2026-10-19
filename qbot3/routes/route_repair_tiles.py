"""Kwadraty (StatsHunters, kafle z14) w Naprawie trasy (sesja kwadraty-1910, 19.10.2026).

Te same zasady co Analiza trasy (/api/routes/{id}/tiles): kafel z14, probkowanie linii co ~0,0008 st.,
"masz" = kafle z cache StatsHunters (tools.tile_store.fetch_tiles). Dla odcinka do naprawy:
- piece   = kafle zastepowanego kawalka (kotwica-kotwica),
- rest    = kafle reszty trasy (zaliczane i tak),
- nowe kawalka = piece - masz - rest  -> to sa kwadraty, ktore objazd moze zgubic.
Dla wariantu: zachowane / zgubione nowe kwadraty kawalka i nowe zdobyte (poza trasa).
Dok.: docs/PROJEKT_NAPRAWA_TRAS.md.
"""
from __future__ import annotations

import math
import os
from typing import Any, Iterable

ZOOM = 14


def latlon_to_tile(lat: float, lon: float) -> tuple[int, int]:
    from tools.tile_store import _latlon_to_tile
    return _latlon_to_tile(lat, lon, ZOOM)


def tile_bounds(x: int, y: int) -> list[list[float]]:
    n = 2 ** ZOOM
    def lat(yy):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
    w, e = x / n * 360.0 - 180.0, (x + 1) / n * 360.0 - 180.0
    return [[lat(y + 1), w], [lat(y), e]]


def tiles_of(coords: Iterable) -> list[tuple[int, int]]:
    """Kafle po kolei wzdluz linii [[lat, lon], ...] (kolejnosc pierwszego wjazdu)."""
    pts = [(float(c[0]), float(c[1])) for c in coords]
    out: list[tuple[int, int]] = []
    seen = set()
    if len(pts) == 1:
        pts = pts * 2
    for (la1, lo1), (la2, lo2) in zip(pts, pts[1:]):
        steps = max(1, int(math.hypot(la2 - la1, lo2 - lo1) / 0.0008))
        for s in range(steps + 1):
            t = s / steps
            k = latlon_to_tile(la1 + (la2 - la1) * t, lo1 + (lo2 - lo1) * t)
            if k not in seen:
                seen.add(k)
                out.append(k)
    return out


_OWNED_CACHE: dict[str, Any] = {}


def owned_tiles() -> tuple[set[tuple[int, int]], str | None]:
    from tools.tile_store import fetch_tiles, get_tile_set, _env
    share = os.getenv("STATSHUNTERS_SHARE_ID") or _env().get("STATSHUNTERS_SHARE_ID", "")
    if not share:
        return set(), "brak STATSHUNTERS_SHARE_ID"
    td = fetch_tiles(share)
    return get_tile_set(td.get("tiles", [])), td.get("_error")


def piece_context(axis_rows: list[dict], anchor_from_km: float, anchor_to_km: float) -> dict[str, Any]:
    """axis_rows: [{km_from, km_to, coordinates:[[lat,lon],...]}] calej trasy."""
    piece_c, rest_c = [], []
    for r in axis_rows:
        mid = (r["km_from"] + r["km_to"]) / 2.0
        (piece_c if anchor_from_km <= mid <= anchor_to_km else rest_c).append(r["coordinates"])
    piece = []
    for c in piece_c:
        for t in tiles_of(c):
            if t not in piece:
                piece.append(t)
    rest = set()
    for c in rest_c:
        rest.update(tiles_of(c))
    owned, err = owned_tiles()
    new_piece = [t for t in piece if t not in owned and t not in rest]
    return {"piece": piece, "rest": rest, "owned": owned, "new_piece": new_piece, "error": err}


def variant_effect(ctx: dict[str, Any], coords: list) -> dict[str, Any]:
    vt = set(tiles_of(coords))
    req = ctx["new_piece"]
    kept = [t for t in req if t in vt]
    lost = [t for t in req if t not in vt]
    gained = [t for t in vt if t not in ctx["owned"] and t not in ctx["rest"] and t not in set(ctx["piece"])]
    return {"required": len(req), "kept": len(kept), "lost": len(lost), "gained": len(gained),
            "lost_tiles": [{"x": x, "y": y, "bounds": tile_bounds(x, y)} for x, y in lost]}
