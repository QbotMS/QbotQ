"""
qbot_route_time_tools_v2.py  --  MODEL CZASU PRZEJAZDU v2  (DO REVIEW, NIEWPIETY)

Status: gotowy do przegladu. NIE wpiety do tool_registry ani promptu Alberta.
Podmiana B4 + aktualizacja Alberta nastapi RAZEM przy wpieciu (twarda regula:
zmiana narzedzia = aktualizacja promptu w tym samym kroku). Stary B4 zostaje
nietkniety do czasu wpiecia (potem wywalany - bez smietnika).

ZASADA MODELU (wszystko z danych, nie z glowy):
- Predkosc MOVING per segment: empiryczna tabela nawierzchnia x nachylenie,
  grade liczony oknem 200 m (spojnie z kalibracja). Poziom = percentyl wg trybu:
    normalny = mediana (nieobciazony, domyslny),
    sport    = asfalt p75 / szuter mediana,
    wyscig   = asfalt p90 / szuter p75.
  Zrodlo: 7 jazd referencyjnych (~128 tys. sekund 1 Hz), dopasowanie po pozycji.
- STOPY:
    mikro (<2 min): 0.22 min/km, rozsiane proporcjonalnie do dystansu (auto),
    krotkie (2-20 min): ~dystans/9 x 4.5 min (auto),
    DLUGIE (>=20 min, obiad/zwiedzanie): WKLAD UZYTKOWNIKA (liczba + laczny czas).
  Dowod z 95 jazd >50 km: liczba dlugich jest NIEPRZEWIDYWALNA z trasy
  (Suchedniow 106 km/5 h -> 0 dlugich; Castagneto 90 km/5,2 h -> 3). Wiec ich
  NIE zgadujemy - podaje je uzytkownik. Reszta modelu jest nieobciazona (~+-15%).
- WYJSCIE: czas RUCHU i czas CALKOWITY osobno + profil czasu zegarowego per segment.
- Pogoda (wiatr/WBGT) poza tym modelem - liczy modul meteo, bierze predkosc per segment stad.

Walidacja in-sample (mediana, +uzytkownik dlugie): suma total -6%, 5/7 jazd w +-15%.
"""

from __future__ import annotations
from typing import Any, Optional
import os
import datetime as _dt

# ------------------------------------------------------------------ TABELA PREDKOSCI
# Wygenerowana z danych (scripts/_gen_speed_table_literal.py). km/h.
# Strome zjazdy asfaltu (<-6%) wygladzone (malo probek). Podjazdy >=6% scalone paved+unpaved.
SPEED_TABLE: dict[str, dict[str, dict[str, float]]] = {
    "normalny": {
        "paved":   {"<-8": 20.0, "-8..-6": 20.0, "-6..-4": 30.6, "-4..-2": 25.5, "-2..-1": 23.7, "-1..1": 22.5, "1..2": 20.6, "2..4": 17.2, "4..6": 12.4, "6..8": 9.3, ">8": 7.2},
        "unpaved": {"<-8": 21.8, "-8..-6": 22.7, "-6..-4": 21.3, "-4..-2": 19.4, "-2..-1": 19.4, "-1..1": 18.8, "1..2": 16.7, "2..4": 14.2, "4..6": 11.8, "6..8": 9.3, ">8": 7.2},
    },
    "sport": {
        "paved":   {"<-8": 33.8, "-8..-6": 33.8, "-6..-4": 39.1, "-4..-2": 31.8, "-2..-1": 28.7, "-1..1": 26.2, "1..2": 24.1, "2..4": 21.1, "4..6": 15.5, "6..8": 11.4, ">8": 9.1},
        "unpaved": {"<-8": 21.8, "-8..-6": 22.7, "-6..-4": 21.3, "-4..-2": 19.4, "-2..-1": 19.4, "-1..1": 18.8, "1..2": 16.7, "2..4": 14.2, "4..6": 11.8, "6..8": 9.3, ">8": 7.2},
    },
    "wyscig": {
        "paved":   {"<-8": 45.6, "-8..-6": 45.6, "-6..-4": 45.4, "-4..-2": 38.9, "-2..-1": 33.2, "-1..1": 30.0, "1..2": 27.7, "2..4": 24.9, "4..6": 19.0, "6..8": 14.1, ">8": 10.3},
        "unpaved": {"<-8": 28.0, "-8..-6": 32.8, "-6..-4": 32.3, "-4..-2": 26.0, "-2..-1": 23.4, "-1..1": 23.2, "1..2": 21.8, "2..4": 19.1, "4..6": 14.5, "6..8": 11.4, ">8": 9.1},
    },
}
DEFAULT_MODE = "normalny"
DOC = "docs/ROUTE_TIME_ESTIMATE_V2.md"  # pelna dokumentacja: po co/jak/dlaczego
GRADE_EDGES = [-8, -6, -4, -2, -1, 1, 2, 4, 6, 8]
GRADE_LABELS = ["<-8", "-8..-6", "-6..-4", "-4..-2", "-2..-1", "-1..1", "1..2", "2..4", "4..6", "6..8", ">8"]

# stopy
MICRO_MIN_PER_KM = 0.22
SHORT_BREAK_EVERY_KM = 9.0
SHORT_BREAK_MIN = 4.5

# nawierzchnia binarna (PL + EN; "nieznana" = blad Overpass -> None, nie klasa)
_PAVED = {"asphalt", "paving_stones", "concrete", "cobblestone", "concrete:plates",
          "asfalt", "kostka brukowa", "beton", "kocie łby", "asfalt/utwardzona"}
_UNPAVED = {"gravel", "ground", "dirt", "compacted", "grass", "fine_gravel", "sand", "wood",
            "szuter", "grunt", "gruntowa", "gruntowa/szuter", "szuter ubity", "gravel/żwir",
            "ubita nawierzchnia", "sciezka/nieutwardzona", "ubita", "trawa", "nieutwardzona",
            "ziemia/grunt", "gravel drobny", "ubita/zwir", "piach", "piasek",
            "gruntowa techniczna", "sciezka", "zwir/luzna", "ziemia", "ubita/żwir",
            "nieutwardzona nieokreslona"}


# ============================================================= CZESC CZYSTA (testowalna)
def _grade_bin(g: float) -> str:
    for j, e in enumerate(GRADE_EDGES):
        if g < e:
            return GRADE_LABELS[j]
    return GRADE_LABELS[-1]


def surface_class(raw: Optional[str]) -> Optional[str]:
    """surowa nazwa nawierzchni -> 'paved'/'unpaved'/None (None = nieznana/blad)."""
    if not raw:
        return None
    r = str(raw).strip().lower()
    if r in _PAVED:
        return "paved"
    if r in _UNPAVED:
        return "unpaved"
    return None


def segment_speed_kmh(grade_pct: float, surf_class: Optional[str], mode: str = DEFAULT_MODE) -> float:
    """km/h dla segmentu. surf nieznana -> srednia paved+unpaved (bez biasu)."""
    tbl = SPEED_TABLE.get(mode, SPEED_TABLE[DEFAULT_MODE])
    b = _grade_bin(grade_pct)
    if surf_class in ("paved", "unpaved"):
        return tbl[surf_class][b]
    return round((tbl["paved"][b] + tbl["unpaved"][b]) / 2.0, 1)


def moving_time_h(segments: list[dict], mode: str = DEFAULT_MODE) -> tuple[float, float]:
    """segments: [{'len_m','grade_pct','surface'(klasa lub surowa)}]. Zwraca (godziny, metry_nieznane)."""
    h = 0.0
    unknown_m = 0.0
    for s in segments:
        ln = float(s.get("len_m") or 0.0)
        if ln <= 0:
            continue
        g = float(s.get("grade_pct") or 0.0)
        sc = s.get("surface")
        sc = sc if sc in ("paved", "unpaved") else surface_class(sc)
        if sc is None:
            unknown_m += ln
        v = segment_speed_kmh(g, sc, mode)
        if v and v > 0:
            h += (ln / 1000.0) / v
    return h, unknown_m


def stops_minutes(distance_km: float, long_count: int = 0, long_total_min: float = 0.0) -> dict:
    """mikro + krotkie auto; dlugie = wklad uzytkownika."""
    micro = MICRO_MIN_PER_KM * distance_km
    n_break = round(distance_km / SHORT_BREAK_EVERY_KM)
    short = n_break * SHORT_BREAK_MIN
    longm = max(0.0, float(long_total_min or 0.0))
    return {
        "mikro_min": round(micro, 1),
        "krotkie_min": round(short, 1),
        "krotkie_liczba": n_break,
        "dlugie_min": round(longm, 1),
        "dlugie_liczba": int(long_count or 0),
        "suma_min": round(micro + short + longm, 1),
    }


def _long_stop_positions(n: int) -> list[float]:
    """frakcje dystansu dla dlugich postojow - srodek trasy (mediana 0.46)."""
    if n <= 0:
        return []
    if n == 1:
        return [0.46]
    return [round(0.30 + 0.40 * i / (n - 1), 3) for i in range(n)]  # rozsiane w srodku


def clock_profile(segments: list[dict], mode: str, start_time: Optional[_dt.datetime],
                  stops: dict, total_km: float) -> list[dict]:
    """Profil czasu zegarowego per segment: start + Sigma ruch + Sigma stopy dotad."""
    micro_per_m = (stops["mikro_min"] + stops["krotkie_min"]) / 60.0 / max(total_km * 1000.0, 1.0)  # h/m rozsiane
    long_positions = _long_stop_positions(stops["dlugie_liczba"])
    long_each_h = (stops["dlugie_min"] / 60.0 / len(long_positions)) if long_positions else 0.0
    prof = []
    cum_dist = 0.0
    cum_move_h = 0.0
    cum_stop_h = 0.0
    long_done = 0
    for s in segments:
        ln = float(s.get("len_m") or 0.0)
        if ln <= 0:
            continue
        g = float(s.get("grade_pct") or 0.0)
        sc = s.get("surface")
        sc = sc if sc in ("paved", "unpaved") else surface_class(sc)
        v = segment_speed_kmh(g, sc, mode)
        cum_move_h += (ln / 1000.0) / v if v > 0 else 0.0
        cum_stop_h += ln * micro_per_m
        cum_dist += ln
        frac = cum_dist / max(total_km * 1000.0, 1.0)
        while long_done < len(long_positions) and frac >= long_positions[long_done]:
            cum_stop_h += long_each_h
            long_done += 1
        row = {"km": round(cum_dist / 1000.0, 2), "grade_pct": round(g, 1),
               "surface": sc or "nieznana", "v_kmh": v,
               "moving_h": round(cum_move_h, 3), "stop_h": round(cum_stop_h, 3)}
        if start_time is not None:
            eta = start_time + _dt.timedelta(hours=cum_move_h + cum_stop_h)
            row["eta"] = eta.strftime("%H:%M")
        prof.append(row)
    return prof


# ============================================================= CZYTNIK Z BAZY (do weryfikacji przy wpieciu)
def _pg_connect():
    try:
        import psycopg2 as pg  # type: ignore
    except ModuleNotFoundError:
        import psycopg as pg  # type: ignore
    return pg.connect(host=os.getenv("PGHOST", "127.0.0.1"), port=int(os.getenv("PGPORT", "5432")),
                      user=os.getenv("PGUSER", "qbot"), dbname=os.getenv("PGDATABASE", "qbot"),
                      password=os.getenv("PGPASSWORD"))


def _load_route_segments(route_id: str) -> Optional[list[dict]]:
    """Buduje segmenty z qbot_v2.route_frames: nawierzchnia + grade 200 m (z wysokosci ramek,
    wygladzone oknem 200 m - spojnie z kalibracja). Zwraca None gdy brak danych kanonicznych.

    UWAGA: do weryfikacji przy wpieciu wzgledem schematu 'nowych zasad' uploadu.
    Preferowane zrodlo wysokosci to route_elevation_samples (DEM 50 m); tu uzyto
    route_frames bo jest szeroko zapelnione i ma nawierzchnie w jednym miejscu.
    """
    import sys
    sys.path.insert(0, "/opt/qbot/app")
    from qbot3.routes.route_elevation_engine import ElevationSample, smooth_elevation, _frame_grades  # type: ignore

    conn = _pg_connect()
    cur = conn.cursor()
    cur.execute("""SELECT frame_index, dist_start_m, dist_end_m, frame_len_m,
                          mid_lat, mid_lon, ele_start_m, ele_end_m, surface
                   FROM qbot_v2.route_frames WHERE route_id=%s ORDER BY frame_index""", (route_id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return None
    # seria wysokosci po dystansie (start kazdej ramki) + domkniecie koncem ostatniej
    samples = []
    for i, r in enumerate(rows):
        d = float(r[1] or 0.0)
        ele = r[6]
        samples.append(ElevationSample(i, d, float(r[4] or 0.0), float(r[5] or 0.0),
                                       (float(ele) if ele is not None else None), "route_frames"))
    dists = [s.distance_m for s in samples]
    grades = _frame_grades(smooth_elevation(samples, 200.0), dists)  # len = len-1
    segs = []
    for i, r in enumerate(rows):
        ln = float(r[3] or 0.0)
        g = grades[i] if i < len(grades) and grades[i] is not None else (grades[-1] if grades else 0.0)
        segs.append({"len_m": ln, "grade_pct": float(g or 0.0), "surface": r[8]})
    return segs


# ============================================================= WEJSCIE NARZEDZIA
def estimate_route_time_v2(route_id: Optional[str] = None, mode: str = DEFAULT_MODE,
                           planned_long_stops: int = 0, planned_long_stop_min: float = 0.0,
                           start_time: Optional[str] = None,
                           segments: Optional[list[dict]] = None) -> dict:
    """Glowne wejscie (wolane przez analizator trasy).

    route_id            - zaplanowana trasa (czyta segmenty z bazy),
    mode                - 'normalny'(domyslny) / 'sport' / 'wyscig',
    planned_long_stops  - liczba dlugich postojow (Twoja deklaracja),
    planned_long_stop_min - laczny czas dlugich postojow [min],
    start_time          - 'HH:MM' lub ISO (opcjonalnie, dla profilu zegarowego),
    segments            - alternatywnie podane wprost (do testow / analizatora).
    """
    if mode not in SPEED_TABLE:
        mode = DEFAULT_MODE
    if segments is None:
        if not route_id:
            return {"status": "NEEDS_INPUT", "notes": "Podaj route_id albo segments."}
        try:
            segments = _load_route_segments(route_id)
        except Exception as exc:  # noqa
            return {"status": "ERROR", "error": f"load_route_segments: {exc}"}
    if not segments:
        return {"status": "NEEDS_INPUT",
                "notes": "Brak danych kanonicznych (grade 200 m + nawierzchnia) dla tej trasy. "
                         "Trasa musi byc wgrana wg nowych zasad. Bez fallbacku - stary model wywalony."}

    total_m = sum(float(s.get("len_m") or 0.0) for s in segments)
    total_km = total_m / 1000.0
    move_h, unknown_m = moving_time_h(segments, mode)
    stops = stops_minutes(total_km, planned_long_stops, planned_long_stop_min)
    total_h = move_h + stops["suma_min"] / 60.0

    st = None
    if start_time:
        try:
            if "T" in start_time or "-" in start_time:
                st = _dt.datetime.fromisoformat(start_time)
            else:
                hh, mm = start_time.split(":")
                st = _dt.datetime.combine(_dt.date.today(), _dt.time(int(hh), int(mm)))
        except Exception:  # noqa
            st = None
    profile = clock_profile(segments, mode, st, stops, total_km)

    unknown_pct = 100.0 * unknown_m / total_m if total_m else 0.0
    warn = []
    if unknown_pct > 5:
        warn.append(f"{unknown_pct:.0f}% trasy ma nieznana nawierzchnie (blad Overpass) - "
                    f"liczone jako srednia paved/unpaved.")
    if planned_long_stops == 0 and planned_long_stop_min == 0:
        warn.append("Nie zadeklarowano dlugich postojow - czas = sama jazda + mikro/krotkie. "
                    "Na obiad/zwiedzanie dodaj liczbe i czas postojow.")

    def hm(h):
        return f"{int(h)}h{int(round((h - int(h)) * 60)):02d}"

    analysis = (
        f"CZAS RUCHU: {hm(move_h)}  |  CZAS CALKOWITY: {hm(total_h)}  (tryb: {mode})\n"
        f"Dystans {total_km:.1f} km. Predkosc moving z empirycznej tabeli nawierzchnia x nachylenie "
        f"(grade 200 m), poziom = {mode}.\n"
        f"Stopy: mikro {stops['mikro_min']:.0f} min + krotkie {stops['krotkie_liczba']}x = "
        f"{stops['krotkie_min']:.0f} min + dlugie {stops['dlugie_liczba']}x = {stops['dlugie_min']:.0f} min.\n"
        f"Dokladnosc czesci tocznej ~+-15% (nieobciazona); dlugie postoje wg Twojej deklaracji.\n"
        f"Wiatr/pogoda liczone osobno (modul meteo).\n"
        f"Dokumentacja narzedzia: {DOC}"
    )

    return {
        "status": "OK",
        "moving_h": round(move_h, 2),
        "total_h": round(total_h, 2),
        "distance_km": round(total_km, 1),
        "mode": mode,
        "stops": stops,
        "profile": profile,
        "unknown_surface_pct": round(unknown_pct, 1),
        "analysis": analysis,
        "warning": " ".join(warn) if warn else "",
        "doc": DOC,
        "model_version": "v2_2026-06-30",
    }


# ============================================================= SELF-TEST
if __name__ == "__main__":
    import json
    print("== test czysty (segmenty syntetyczne) ==")
    segs = [{"len_m": 1000, "grade_pct": 0, "surface": "asfalt"},
            {"len_m": 1000, "grade_pct": 5, "surface": "asfalt"},
            {"len_m": 1000, "grade_pct": -5, "surface": "szuter"},
            {"len_m": 1000, "grade_pct": 0, "surface": "nieznana"}]
    out = estimate_route_time_v2(segments=segs, mode="normalny",
                                 planned_long_stops=1, planned_long_stop_min=40, start_time="09:00")
    print(json.dumps({k: out[k] for k in ("status", "moving_h", "total_h", "stops", "unknown_surface_pct", "warning")},
                     ensure_ascii=False, indent=2))
    print("profil[0], profil[-1]:", out["profile"][0], out["profile"][-1])

    # test z baza na realnej trasie z route_frames (jesli jest)
    try:
        conn = _pg_connect(); cur = conn.cursor()
        cur.execute("SELECT route_id FROM qbot_v2.route_frames GROUP BY route_id ORDER BY count(*) DESC LIMIT 1")
        rid = cur.fetchone()[0]; conn.close()
        print(f"\n== test z baza (route_id={rid}) ==")
        out2 = estimate_route_time_v2(route_id=rid, mode="normalny", planned_long_stops=1, planned_long_stop_min=40)
        print(json.dumps({k: out2[k] for k in ("status", "distance_km", "moving_h", "total_h", "stops", "unknown_surface_pct")},
                         ensure_ascii=False, indent=2))
    except Exception as e:  # noqa
        print("test bazy pominiety:", e)


# ============================================================= KOMPAT WRAPPER (tool_registry)
def _tool_route_time_estimate(args=None):
    """Kompatybilne wejscie dla tool_registry: mapuje dict args -> estimate_route_time_v2."""
    a = args or {}
    return estimate_route_time_v2(
        route_id=a.get("route_id"),
        mode=a.get("mode", DEFAULT_MODE),
        planned_long_stops=int(a.get("planned_long_stops") or 0),
        planned_long_stop_min=float(a.get("planned_long_stop_min") or 0.0),
        start_time=a.get("start_time"),
        segments=a.get("segments"),
    )
