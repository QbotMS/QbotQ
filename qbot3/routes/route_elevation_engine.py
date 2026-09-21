#!/usr/bin/env python3
"""Silnik przewyzszen i podjazdow (2C) — czysta logika, bez DB.

Dokumentacja: docs/architecture/ROUTE_ELEVATION_CLIMB.md

Buduje gesty profil wysokosci (ksztalt route_elevation_samples) z otwartego DEM
oraz wykrywa podjazdy (ksztalt route_climb_events) progami Karoo.

Zrodlo wysokosci jest WSTRZYKIWANE (elevation_fn) -> modul testowalny offline.
Domyslne zrodlo: opentopodata SRTM30m (rodzina DEM Karoo).

Zasady (DECISIONS 2026-06-30, 2C):
- siatka 50 m (wspolna z nawierzchnia), surowe probki trzymane wiernie,
- DWA okna wygladzania, lokalne (nie globalne), do ROZNYCH celow:
    * suma przewyzszen (summarize): ~200 m — skalibrowane pod barometr,
    * detekcja granic / srednie / segmenty 100 m / max: ~100 m — lokalizuje
      podjazd i scianki bez rozlewania krotkich podjazdow ponad prog
      (okno 200 m przesuwa pozorny szczyt o ~pol okna do przodu),
- detekcja progami Karoo: >=400 m i >=3% (tryb All Climbs),
- podjazd konczy sie na SZCZYCIE (max wygladzonej wysokosci w obrebie biegu),
- SCALANIE (2026-08-16): pojedyncza ramka ponizej CLIMB_CONTINUE_PCT to czesto
  plaska polka serpentyny albo szum DEM (-0.7% na 100 m = 70 cm), a nie koniec
  podjazdu. Sasiadujace biegi laczymy, gdy przerwa <= MERGE_MAX_GAP_M ORAZ
  spadek w dolku <= MERGE_MAX_DIP_M. Filtr 400 m / 3% dziala PO scaleniu, zeby
  krotkie kawalki mogly byc mostkiem miedzy fragmentami tego samego podjazdu,
- podjazd dwupoziomowo: naglowek + segmenty 100 m z gradientem kazdego.

Uwaga: prog 400 m ma naturalna tolerancje ~pol okna (precyzja do metra
swiadomie nieistotna — liczy sie sygnatura podjazdu i profil scianek).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

# --- stale / wersje ---
FRAME_M = 50.0
ASCENT_WINDOW_M = 200.0      # suma przewyzszen (summarize) — pod barometr
DETECTION_WINDOW_M = 100.0   # detekcja / srednie / segmenty / max (scianki)
SEGMENT_M = 100.0
MIN_CLIMB_LEN_M = 400.0
MIN_CLIMB_AVG_PCT = 3.0
CLIMB_START_PCT = 3.0        # ramka rozpoczynajaca podjazd
CLIMB_CONTINUE_PCT = -0.5    # tolerancja dolka w obrebie podjazdu (rolling)
MERGE_MAX_GAP_M = 400.0      # przerwa miedzy biegami dopuszczalna do scalenia
MERGE_MAX_DIP_M = 12.0       # spadek w dolku (od szczytu poprzednika) do scalenia
SMOOTHING_VERSION = "asc200_det100_50_v1"
DETECTION_VERSION = "karoo_400_3_merge_v2"
DEFAULT_SOURCE = "srtm30m_opentopodata"

# --- typy wyjsciowe ---

@dataclass
class ElevationSample:
    sample_index: int
    distance_m: float
    lat: float
    lon: float
    elevation_m: float | None
    source: str
    smoothing_version: str = SMOOTHING_VERSION


@dataclass
class ClimbSegment:
    seg_index: int
    start_m: float
    end_m: float
    length_m: float
    gradient_pct: float
    category: str  # pasmo stromosci (do kolorowania, jak Climber)


@dataclass
class ClimbEvent:
    event_index: int
    start_m: float
    end_m: float
    length_m: float
    elevation_gain_m: float
    avg_gradient_pct: float
    max_gradient_pct: float
    severity: str
    source: str
    detection_version: str
    segments: list[ClimbSegment] = field(default_factory=list)


# --- pasma stromosci (kolor/kategoria segmentu) ---

def gradient_category(g: float) -> str:
    if g < 0:
        return "spadek"
    if g < 3.0:
        return "lagodny"
    if g < 6.0:
        return "umiarkowany"
    if g < 9.0:
        return "stromy"
    return "bardzo_stromy"


def _severity(length_m: float, avg_pct: float, max_pct: float, gain_m: float) -> str:
    if length_m <= 600.0 and (avg_pct >= 8.0 or max_pct >= 12.0):
        return "sciana"
    if gain_m >= 150.0 or length_m >= 3000.0:
        return "dlugi"
    return "umiarkowany"


# --- geometria: wezly siatki ---

def _interp_nodes(points: Sequence[tuple[float, float, float]], frame_m: float) -> list[tuple[float, float, float]]:
    """points: rosnaco po dystansie krotki (distance_m, lat, lon). Zwraca wezly co frame_m."""
    pts = list(points)
    if len(pts) < 2:
        raise ValueError("za malo punktow")
    total = pts[-1][0]
    if total <= 0:
        raise ValueError("zerowy dystans")

    def interp(target: float) -> tuple[float, float, float]:
        if target <= pts[0][0]:
            return pts[0]
        if target >= pts[-1][0]:
            return pts[-1]
        lo, hi = 0, len(pts) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if pts[mid][0] <= target:
                lo = mid
            else:
                hi = mid
        a, b = pts[lo], pts[hi]
        t = (target - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
        return (target, a[1] + t * (b[1] - a[1]), a[2] + t * (b[2] - a[2]))

    n = int(total // frame_m) + 1
    nodes = [interp(i * frame_m) for i in range(n)]
    if nodes[-1][0] < total:
        nodes.append(pts[-1])
    return nodes


# --- domyslne zrodlo DEM: opentopodata SRTM30m ---

def srtm30m_opentopodata(coords: list[tuple[float, float]]) -> list[float | None]:
    import time
    import httpx
    out: list[float | None] = []
    for i in range(0, len(coords), 100):
        chunk = coords[i:i + 100]
        locs = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in chunk)
        got: list[float | None] | None = None
        for _ in range(3):
            try:
                r = httpx.get("https://api.opentopodata.org/v1/srtm30m",
                              params={"locations": locs}, timeout=40)
                if r.status_code == 200:
                    got = [x.get("elevation") for x in r.json().get("results", [])]
                    break
                time.sleep(2)
            except Exception:
                time.sleep(2)
        if got is None:
            raise RuntimeError(f"opentopodata: brak odpowiedzi dla chunku {i}")
        out += got
        time.sleep(1.1)
    return out


# --- profil ---

def build_route_elevation_profile(
    points: Sequence[tuple[float, float, float]],
    elevation_fn: Callable[[list[tuple[float, float]]], list[float | None]] | None = None,
    frame_m: float = FRAME_M,
    source: str = DEFAULT_SOURCE,
) -> list[ElevationSample]:
    """Gesty profil co frame_m. points: (distance_m, lat, lon) rosnaco po dystansie."""
    nodes = _interp_nodes(points, frame_m)
    fn = elevation_fn or srtm30m_opentopodata
    elevs = fn([(lat, lon) for (_d, lat, lon) in nodes])
    if len(elevs) != len(nodes):
        raise RuntimeError(f"zrodlo DEM zwrocilo {len(elevs)} != {len(nodes)} wezlow")
    return [
        ElevationSample(i, round(d, 3), round(lat, 7), round(lon, 7),
                        (round(float(e), 1) if e is not None else None), source)
        for i, ((d, lat, lon), e) in enumerate(zip(nodes, elevs))
    ]


# --- wygladzanie po dystansie (lokalne, centrowane) ---

def smooth_elevation(samples: Sequence[ElevationSample], window_m: float = ASCENT_WINDOW_M) -> list[float | None]:
    d = [s.distance_m for s in samples]
    e = [s.elevation_m for s in samples]
    n = len(e)
    half = window_m / 2.0
    out: list[float | None] = []
    for i in range(n):
        lo = i
        while lo > 0 and (d[i] - d[lo - 1]) <= half:
            lo -= 1
        hi = i
        while hi + 1 < n and (d[hi + 1] - d[i]) <= half:
            hi += 1
        vals = [e[k] for k in range(lo, hi + 1) if e[k] is not None]
        out.append(sum(vals) / len(vals) if vals else None)
    return out


def _frame_grades(smoothed: list[float | None], d: list[float]) -> list[float | None]:
    g: list[float | None] = []
    for k in range(len(smoothed) - 1):
        dd = d[k + 1] - d[k]
        if dd > 0 and smoothed[k] is not None and smoothed[k + 1] is not None:
            g.append((smoothed[k + 1] - smoothed[k]) / dd * 100.0)
        else:
            g.append(None)
    return g


def summarize(samples: Sequence[ElevationSample], window_m: float = ASCENT_WINDOW_M) -> dict:
    d = [s.distance_m for s in samples]
    raw = [s.elevation_m for s in samples]
    sm = smooth_elevation(samples, window_m)

    def asc_desc(e):
        a = b = 0.0
        for k in range(len(e) - 1):
            if e[k] is None or e[k + 1] is None:
                continue
            delta = e[k + 1] - e[k]
            if delta > 0:
                a += delta
            else:
                b += -delta
        return a, b

    ar, _ = asc_desc(raw)
    asm, dsm = asc_desc(sm)
    grades = [x for x in _frame_grades(sm, d) if x is not None]
    return {
        "distance_m": round(d[-1], 1) if d else 0.0,
        "samples": len(samples),
        "ascent_raw_m": round(ar, 1),
        "ascent_smoothed_m": round(asm, 1),
        "descent_smoothed_m": round(dsm, 1),
        "max_grade_pct": round(max((abs(x) for x in grades), default=0.0), 1),
        "ascent_window_m": window_m,
        "smoothing_version": SMOOTHING_VERSION,
    }


# --- detekcja podjazdow ---

def _segments_100m(smoothed: list[float | None], d: list[float], start_i: int, end_i: int) -> list[ClimbSegment]:
    """Dzieli [start_i..end_i] na odcinki ~SEGMENT_M, gradient z wygladzonego profilu detekcji."""
    segs: list[ClimbSegment] = []
    seg_start_i = start_i
    idx = 0
    for k in range(start_i, end_i + 1):
        span = d[k] - d[seg_start_i]
        if (span >= SEGMENT_M or k == end_i) and k > seg_start_i:
            a, b = smoothed[seg_start_i], smoothed[k]
            if a is not None and b is not None:
                length = d[k] - d[seg_start_i]
                grad = (b - a) / length * 100.0 if length > 0 else 0.0
                segs.append(ClimbSegment(idx, round(d[seg_start_i], 1), round(d[k], 1),
                                         round(length, 1), round(grad, 1), gradient_category(grad)))
                idx += 1
            seg_start_i = k
    return segs


def _climb_runs(g: list[float | None], sm: list[float | None], d: list[float]) -> list[tuple[int, int]]:
    """Surowi kandydaci (start_i, summit_i) — BEZ filtra dlugosci/nachylenia."""
    runs: list[tuple[int, int]] = []
    i, n = 0, len(g)
    while i < n:
        if g[i] is not None and g[i] >= CLIMB_START_PCT:
            j = i
            while j + 1 < n and g[j + 1] is not None and g[j + 1] >= CLIMB_CONTINUE_PCT:
                j += 1
            run_end = j + 1  # ostatni wezel biegu (moze siegac w plaskie za szczytem)
            # docinamy do SZCZYTU = max wygladzonej wysokosci w obrebie biegu
            summit = i
            best = sm[i] if sm[i] is not None else float("-inf")
            for k in range(i, run_end + 1):
                if sm[k] is not None and sm[k] > best:
                    best, summit = sm[k], k
            if summit > i and sm[i] is not None and sm[summit] is not None:
                runs.append((i, summit))
            i = j + 1
        else:
            i += 1
    return runs


def _run_stats(start_i: int, end_i: int, sm: list[float | None], d: list[float]) -> tuple[float, float, float]:
    """(dlugosc, przewyzszenie, srednie nachylenie %) dla biegu start..end."""
    a, b = sm[start_i], sm[end_i]
    if a is None or b is None:
        return 0.0, 0.0, 0.0
    length = d[end_i] - d[start_i]
    gain = b - a
    return length, gain, (gain / length * 100.0 if length > 0 else 0.0)


def _run_passes(start_i: int, end_i: int, sm: list[float | None], d: list[float]) -> bool:
    """Czy bieg sam w sobie przechodzi prog Karoo (>=400 m i >=3%)."""
    length, _gain, avg = _run_stats(start_i, end_i, sm, d)
    return length >= MIN_CLIMB_LEN_M and avg >= MIN_CLIMB_AVG_PCT


def _merge_climb_runs(runs: list[tuple[int, int]], sm: list[float | None], d: list[float]) -> list[tuple[int, int]]:
    """Scala biegi rozdzielone plaska polka albo szumem DEM.

    Laczy, gdy JEDNOCZESNIE:
    - przerwa <= MERGE_MAX_GAP_M,
    - spadek w dolku od szczytu poprzednika <= MERGE_MAX_DIP_M,
    - szczyt nastepnika lezy WYZEJ (inaczej nie ma czego doklejac),
    - SCALANIE NIE POGARSZA: albo scalony blok dalej przechodzi prog 400 m/3%,
      albo zaden ze skladnikow i tak by sam nie przeszedl. Bez tego warunku
      doklejenie krotkiego, lagodnego ogonka rozcienczalo srednia ponizej 3%
      i kasowalo podjazd, ktory wczesniej byl widoczny (audyt 2026-08-16:
      base 183, odcinek 1200 m @3.7% ginal po sklejeniu ze 150 m @2.7%).

    Iteracyjnie, wiec A+B moze dalej wchlonac C.
    """
    if not runs:
        return []
    out: list[tuple[int, int]] = [runs[0]]
    for b_start, b_end in runs[1:]:
        a_start, a_end = out[-1]
        top_a, top_b = sm[a_end], sm[b_end]
        if top_a is None or top_b is None:
            out.append((b_start, b_end))
            continue
        gap = d[b_start] - d[a_end]
        vals = [sm[k] for k in range(a_end, b_start + 1) if sm[k] is not None]
        dip = top_a - min(vals) if vals else 0.0
        geometry_ok = gap <= MERGE_MAX_GAP_M and dip <= MERGE_MAX_DIP_M and top_b > top_a
        if geometry_ok:
            merged_ok = _run_passes(a_start, b_end, sm, d)
            no_loss = merged_ok or not (
                _run_passes(a_start, a_end, sm, d) or _run_passes(b_start, b_end, sm, d)
            )
        else:
            no_loss = False
        if geometry_ok and no_loss:
            out[-1] = (a_start, b_end)
        else:
            out.append((b_start, b_end))
    return out


def detect_route_climb_events(
    samples: Sequence[ElevationSample],
    detection_window_m: float = DETECTION_WINDOW_M,
    source: str = DEFAULT_SOURCE,
) -> list[ClimbEvent]:
    d = [s.distance_m for s in samples]
    sm = smooth_elevation(samples, detection_window_m)  # detekcja / srednie / segmenty / max
    g = _frame_grades(sm, d)
    events: list[ClimbEvent] = []
    for start_i, end_i in _merge_climb_runs(_climb_runs(g, sm, d), sm, d):
        a, b = sm[start_i], sm[end_i]
        if a is None or b is None:
            continue
        length = d[end_i] - d[start_i]
        gain = b - a
        avg = gain / length * 100.0 if length > 0 else 0.0
        if length < MIN_CLIMB_LEN_M or avg < MIN_CLIMB_AVG_PCT:
            continue
        segs = _segments_100m(sm, d, start_i, end_i)
        mx = max((s.gradient_pct for s in segs), default=round(avg, 1))
        events.append(ClimbEvent(
            event_index=len(events),
            start_m=round(d[start_i], 1),
            end_m=round(d[end_i], 1),
            length_m=round(length, 1),
            elevation_gain_m=round(gain, 1),
            avg_gradient_pct=round(avg, 1),
            max_gradient_pct=round(mx, 1),
            severity=_severity(length, avg, mx, gain),
            source=source,
            detection_version=DETECTION_VERSION,
            segments=segs,
        ))
    return events
