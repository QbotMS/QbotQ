"""Mini-router objazdow dla Naprawy trasy (sesje router2-1910, 19.10.2026).

Wyznacza objazd zlego odcinka TYM SAMYM modelem nawierzchni co Analiza trasy:
lokalna baza drog OSM (roads.sqlite, Geofabrik) -> siec (drogi lacza sie we wspolnych punktach)
-> klasyfikacja drogi TA SAMA FUNKCJA co silnik nawierzchni (route_surface_engine._infer_from_tags)
-> kategoria 1-5 (compute_category; dla drog bez danych kontekst WorldCover jak
route_surface_context_store) -> koszt = dlugosc x waga kategorii -> Dijkstra.
Warianty (do 3): kara za drogi poprzednich wariantow; wariant pokazujemy tylko gdy co najmniej
30% jego dlugosci rozni sie od juz przyjetych. Obszar rosnie (+2/+4/+7 km), gdy kotwice nie sa
w jednej sieci albo objazd nadal ma zla nawierzchnie - ale przestaje, gdy wiekszy obszar nic nie
poprawia. Poza zasiegiem bazy (poza Polska) zwraca None -> Valhalla.

Lekcja 19.10: wlasna kopia regul (np. "unclassified bez tagu = asfalt") rozjechala router z
sedzia (Rembertow: router 0,22 km zlej nawierzchni, sedzia 0,7 km). Dlatego ZERO wlasnych regul
nawierzchni - tylko funkcje silnika i kategoryzatora.

Kategoria liczona tu sluzy do WYSZUKIWANIA; ostateczna ocena wariantu w qbot_web
(_detour_surface_categories, silnik nawierzchni) - ten sam sedzia co Analiza trasy.

Zakazy: highway motorway/motorway_link/steps/platform/construction/proposed/...,
motorroad=yes, ref S*/A* (ekspresowki/autostrady), bicycle=no|dismount|use_sidepath,
access=no|private bez zezwolenia dla rowerow. Jednokierunkowosc: oneway=yes|1|true / -1,
chyba ze oneway:bicycle=no. Krajowek (trunk) NIE wycinamy - rowerem wolno.
Dok.: docs/PROJEKT_NAPRAWA_TRAS.md.
"""
from __future__ import annotations

import heapq
import math
import re
from typing import Any

PADS_KM = (2.0, 4.0, 7.0)
MAX_WAYS = 15000            # powyzej - nie powiekszamy obszaru (czas: miasto +7 km = ~16 s; test 19.10)
MAX_SNAP_M = 150.0          # kotwica dalej od sieci -> uznajemy, ze router nie pomoze
GOOD_ENOUGH_KM = 0.2        # zla nawierzchnia ponizej progu = objazd dobry (jak MIN_RISKY_SEGMENT_KM)
MIN_GAIN_KM = 0.05          # wiekszy obszar musi poprawic wynik o tyle, inaczej konczymy
VARIANT_PENALTY = 2.0
VARIANT_MIN_NEW = 0.30      # wariant musi miec >= 30% dlugosci poza poprzednimi wariantami
WEIGHTS = {1: 1.0, 2: 1.1, 3: 1.4, 4: 3.0, 5: 12.0}

_NO_BIKE_HW = {"motorway", "motorway_link", "construction", "proposed", "steps", "raceway",
               "bus_guideway", "corridor", "platform", "elevator", "via_ferrata", "escape"}
_REF_FAST = re.compile(r"^\s*[SA]\s*\d")


def _blocked(tg: dict) -> bool:
    if tg.get("highway") in _NO_BIKE_HW or tg.get("motorroad") == "yes":
        return True
    if any(_REF_FAST.match(r) for r in str(tg.get("ref") or "").split(";")):
        return True
    if tg.get("bicycle") in ("no", "dismount", "use_sidepath"):
        return True
    return tg.get("access") in ("no", "private") and tg.get("bicycle") not in ("yes", "designated", "permissive")


def _hav(p, q) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (p[0], p[1], q[0], q[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def _category(tg: dict, pts: list, reader) -> int:
    """Kategoria 1-5 drogi OSM - funkcje silnika nawierzchni + kategoryzatora (bez wlasnych regul)."""
    from tools.rwgps.route_surface_engine import _infer_from_tags
    from qbot3.routes.route_surface_category_store import compute_category
    from qbot3.routes.route_surface_context_store import infer_context, WC_PL
    surface, _conf, _expl, cls = _infer_from_tags(tg)
    ctx = None
    if cls == "unknown" and reader is not None:  # jak silnik: odcinek bez danych -> kontekst terenu
        counts: dict = {}
        for p in pts[::max(1, len(pts) // 12)]:
            c, _t = reader.sample(*p)
            if c is not None:
                counts[c] = counts.get(c, 0) + 1
        n = sum(counts.values())
        wc = max(counts, key=counts.get) if n else None
        ctx = infer_context(tg.get("highway"), tg.get("tracktype"), wc, round(counts[wc] / n * 100) if n else 0, False)
        ctx["dominant_pl"] = WC_PL.get(wc) if wc else None
    return compute_category(surface=surface, tracktype=tg.get("tracktype"), highway=tg.get("highway"),
                            classification_source=cls, smoothness=tg.get("smoothness"), ctx=ctx)[0]


def _build(A, B, pad: float):
    from tools.rwgps import osm_local
    lat0 = (A[0] + B[0]) / 2
    dl, dn = pad / 111.32, pad / (111.32 * math.cos(math.radians(lat0)))
    bb = (min(A[0], B[0]) - dl, min(A[1], B[1]) - dn, max(A[0], B[0]) + dl, max(A[1], B[1]) + dn)
    if not osm_local.covers_bbox(*bb):
        return None, "poza zasiegiem lokalnej bazy drog"
    ways = osm_local.query_ways(*bb).get("elements") or []
    if len(ways) > MAX_WAYS:
        return None, f"za duzo drog w obszarze ({len(ways)})"
    try:
        from qbot3.routes.route_shade_store import _TileReader
        reader = _TileReader(bb)
    except Exception:  # bez WorldCover: drogi bez danych zostaja kat. 5 (ostrozniej)
        reader = None
    adj: dict = {}
    for w in ways:
        tg = w.get("tags") or {}
        if _blocked(tg):
            continue
        pts = [(p["lat"], p["lon"]) for p in (w.get("geometry") or [])]
        if len(pts) < 2:
            continue
        cat = _category(tg, pts, reader)
        ow = str(tg.get("oneway") or "").lower()
        bike_two_way = tg.get("oneway:bicycle") == "no"
        fwd = bike_two_way or ow != "-1"
        bwd = bike_two_way or ow not in ("yes", "1", "true")
        for p, q in zip(pts, pts[1:]):
            d = _hav(p, q)
            adj.setdefault(p, [])
            adj.setdefault(q, [])
            if fwd:
                adj[p].append((q, d, cat))
            if bwd:
                adj[q].append((p, d, cat))
    return {"adj": adj, "ways": len(ways)}, None


def _dijkstra(adj, a, b, weights, penal: set):
    dist, prev, pq = {a: 0.0}, {}, [(0.0, a)]
    while pq:
        d, x = heapq.heappop(pq)
        if x == b:
            break
        if d > dist.get(x, 1e18):
            continue
        for y, L, c in adj.get(x, ()):
            nd = d + L * weights[c] * (VARIANT_PENALTY if (x, y) in penal else 1.0)
            if nd < dist.get(y, 1e18):
                dist[y] = nd
                prev[y] = (x, L, c)
                heapq.heappush(pq, (nd, y))
    if b not in prev:
        return None
    path, km, by, legs = [b], 0.0, {}, []
    x = b
    while x != a:
        px, L, c = prev[x]
        legs.append(((px, x), L))
        km += L
        by[c] = by.get(c, 0.0) + L
        x = px
        path.append(x)
    return {"coords": [[p[0], p[1]] for p in reversed(path)], "km": km, "by_cat": by, "legs": legs}


def _variants(adj, a, b, weights, threshold, max_variants):
    out, used = [], set()
    for _i in range(max_variants + 2):
        if len(out) >= max_variants:
            break
        r = _dijkstra(adj, a, b, weights, used)
        if r is None:
            break
        new_km = sum(L for (e, L) in r["legs"] if e not in used)
        if not out or (r["km"] > 0 and new_km / r["km"] >= VARIANT_MIN_NEW):
            out.append({
                "coordinates": r["coords"],
                "distance_km": round(r["km"], 2),
                "router_by_cat": {int(c): round(v, 2) for c, v in sorted(r["by_cat"].items())},
                "router_risky_km": round(sum(v for c, v in r["by_cat"].items() if c >= threshold), 2),
            })
        for (e, _L) in r["legs"]:
            used.add(e)
            used.add((e[1], e[0]))
    return out


def find_detours(origin, destination, *, threshold: int = 5, max_variants: int = 3) -> dict[str, Any] | None:
    """Zwraca {"variants": [...], "pad_km", "ways", "note"} albo None (poza baza / brak wyniku -> Valhalla).
    Wariant: coordinates [[lat, lon], ...], distance_km, router_by_cat {kat: km}, router_risky_km."""
    from tools.rwgps import osm_local
    if not osm_local.enabled():
        return None
    A, B = (float(origin[0]), float(origin[1])), (float(destination[0]), float(destination[1]))
    weights = {c: (WEIGHTS[5] if c >= threshold else w) for c, w in WEIGHTS.items()}
    best = None
    for pad in PADS_KM:
        g, _why = _build(A, B, pad)
        if g is None:
            break
        adj = g["adj"]
        if not adj:
            continue
        a = min(adj, key=lambda v: _hav(v, A))
        b = min(adj, key=lambda v: _hav(v, B))
        if _hav(a, A) * 1000 > MAX_SNAP_M or _hav(b, B) * 1000 > MAX_SNAP_M:
            continue
        variants = _variants(adj, a, b, weights, threshold, max_variants)
        if not variants:
            continue
        variants.sort(key=lambda v: (v["router_risky_km"], v["distance_km"]))
        est = variants[0]["router_risky_km"]
        if best is not None and est > best["variants"][0]["router_risky_km"] - MIN_GAIN_KM:
            break  # wiekszy obszar nic istotnie nie poprawil
        best = {"variants": variants, "pad_km": pad, "ways": g["ways"], "note": None}
        if est < GOOD_ENOUGH_KM:
            break
    return best
