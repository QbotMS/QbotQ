"""Kanoniczny raport trasy (V1) — jeden, staly uklad sekcji 1:1 z makiety.

Zrodla (wszystkie zywe/strukturalne, bez zgadywania):
- route_base (nazwa/plik/dystans), GPX (start latlon), Nominatim (gmina/powiat/woj., cache)
- _read_route_source: canonical_surface_summary / _elevation_summary / _poi_summary
- route_surface_layer (highway/tracktype/coverage_status + meta km_from/km_to/surface_refined): join podjazd x nawierzchnia + ryzyko
- run_meteo_engine: WBGT/UTCI/opad/wiatr (tabela 30 min) + alerty + peak + caveats
- estimate_route_time_v2: czas ruchu/calkowity + postoje
- fitmodel_daily: FTP_est / W/kg / glikogen (odniesienie do formy)
- route_poi_layer (per route_base_id): zaopatrzenie, jedzenie, miejscowosci, atrakcje

REGULA RYZYKA NAWIERZCHNI (potwierdzona, route 55798129):
- highway=track z tracktype grade1-4  -> NIGDY ryzyko
- highway=track bez tracktype / grade5 -> ryzyko (luzny/nieznany)
- poza track: piach (sand) -> ryzyko; tag OSM wygrywa nad wnioskowaniem

Konwencja: po polsku, wiatr m/s (+ = tylny, - = czolowy), temperatury C, czas lokalny.
Bez danych -> "b/d" (nie zgadujemy). V1: dopieszczamy na zywo.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Optional

import psycopg
from psycopg.rows import dict_row

_SURF_PL = {
    "asphalt": "asfalt", "concrete": "beton", "paving_stones": "kostka",
    "gravel": "zwir", "fine_gravel": "drobny zwir", "compacted": "ubita",
    "ground": "grunt/polna", "dirt": "grunt", "mixed": "mieszana",
    "sand": "piach", "unknown": "nieznana",
}
_HARD = {"asphalt", "concrete", "paving_stones"}
_GRAVEL = {"gravel", "fine_gravel", "compacted"}
_GRADE_OK = {"grade1", "grade2", "grade3", "grade4"}


def _db():
    import os
    return psycopg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "qbot"), user=os.getenv("PGUSER", "qbot"),
        password=os.getenv("PGPASSWORD", ""), row_factory=dict_row,
        connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT", "5")),
    )


def _hms(hours: Optional[float]) -> str:
    if hours is None:
        return "b/d"
    m = int(round(float(hours) * 60))
    return f"{m // 60} h {m % 60:02d} min"


def _f(v: Any, nd: int = 1, dflt: str = "b/d") -> str:
    try:
        return f"{float(v):.{nd}f}".replace(".", ",")
    except (TypeError, ValueError):
        return dflt


def _wind_arrow(v: Optional[float]) -> str:
    if v is None:
        return "b/d"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "b/d"
    if abs(x) < 1.0:
        return f"{_f(abs(x))} ~0"
    return f"{_f(abs(x))} {'tylny ↑' if x > 0 else 'czolowy ↓'}"


def _is_risky(seg: dict) -> bool:
    """Regula potwierdzona (route 55798129)."""
    hw = str(seg.get("highway") or "").lower().strip()
    tt = str(seg.get("tracktype") or "").lower().strip()
    surf = seg.get("surface")
    if hw == "track":
        if tt in _GRADE_OK:
            return False
        return True  # brak tracktype lub grade5 -> luzny/nieznany
    if surf == "sand":
        return True
    return False


def _risk_reason(seg: dict) -> str:
    hw = str(seg.get("highway") or "").lower().strip()
    tt = str(seg.get("tracktype") or "").lower().strip()
    if seg.get("surface") == "sand":
        return "piach"
    if hw == "track" and (tt == "grade5"):
        return "track grade5"
    if hw == "track":
        return "track bez klasy (tracktype brak)"
    return ", ".join(seg.get("risk") or []) or "ryzyko"


# ---- ZRODLA ---------------------------------------------------------------

def _route_base(conn, route_id: str) -> Optional[dict]:
    return conn.execute(
        "SELECT route_base_id, route_id, source_path, distance_m FROM qbot_v2.route_base "
        "WHERE route_id=%s ORDER BY updated_at DESC, route_base_id DESC LIMIT 1",
        (route_id,)).fetchone()


def _gpx_name_start(source_path: Optional[str]) -> tuple[Optional[str], Optional[tuple[float, float]]]:
    if not source_path:
        return None, None
    try:
        txt = open(source_path, encoding="utf-8").read()
    except Exception:
        return None, None
    mn = re.search(r"<name>(.*?)</name>", txt, re.S)
    name = mn.group(1).strip() if mn else None
    mp = re.search(r'lat="([-\d.]+)"\s+lon="([-\d.]+)"', txt)
    start = (float(mp.group(1)), float(mp.group(2))) if mp else None
    return name, start


def _admin(conn, route_id: str, latlon: Optional[tuple[float, float]]) -> dict:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS qbot_v2.route_admin_cache ("
        "route_id text PRIMARY KEY, miejscowosc text, gmina text, powiat text, "
        "wojewodztwo text, lat double precision, lon double precision, "
        "updated_at timestamptz NOT NULL DEFAULT now())")
    row = conn.execute("SELECT miejscowosc, gmina, powiat, wojewodztwo FROM "
                       "qbot_v2.route_admin_cache WHERE route_id=%s", (route_id,)).fetchone()
    if row:
        return dict(row)
    out = {"miejscowosc": None, "gmina": None, "powiat": None, "wojewodztwo": None}
    if latlon:
        try:
            q = urllib.parse.urlencode({"format": "json", "lat": latlon[0], "lon": latlon[1],
                                        "zoom": 10, "addressdetails": 1, "accept-language": "pl"})
            req = urllib.request.Request("https://nominatim.openstreetmap.org/reverse?" + q,
                                         headers={"User-Agent": "qbot-report/1.0"})
            data = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8"))
            a = data.get("address", {})
            out = {
                "miejscowosc": a.get("village") or a.get("town") or a.get("city") or a.get("hamlet"),
                "gmina": a.get("municipality"), "powiat": a.get("county"),
                "wojewodztwo": a.get("state"),
            }
            conn.execute(
                "INSERT INTO qbot_v2.route_admin_cache (route_id, miejscowosc, gmina, powiat, "
                "wojewodztwo, lat, lon) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (route_id) DO NOTHING",
                (route_id, out["miejscowosc"], out["gmina"], out["powiat"], out["wojewodztwo"],
                 latlon[0], latlon[1]))
            conn.commit()
        except Exception:
            pass
    return out


def _surface_segments(conn, route_base_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT highway, tracktype, coverage_status, confidence, surface_meta_json "
        "FROM qbot_v2.route_surface_layer WHERE route_base_id=%s ORDER BY segment_index",
        (route_base_id,)).fetchall()
    segs = []
    for r in rows:
        m = r["surface_meta_json"] or {}
        try:
            segs.append({
                "km_from": float(m.get("km_from")), "km_to": float(m.get("km_to")),
                "surface": m.get("surface_refined") or m.get("surface_raw") or "unknown",
                "cls": m.get("classification_source"),
                "risk": list(m.get("risk_flags") or []),
                "highway": r.get("highway"),
                "tracktype": r.get("tracktype"),
                "coverage_status": r.get("coverage_status"),
                "confidence": r.get("confidence"),
            })
        except (TypeError, ValueError):
            continue
    return segs


def _surface_at_km(segs: list[dict], km: float) -> Optional[dict]:
    for s in segs:
        if s["km_from"] <= km <= s["km_to"]:
            return s
    return None


def _fitmodel(conn) -> Optional[dict]:
    return conn.execute(
        "SELECT day, ftp_est_w, w_per_kg, weight_kg, glycogen_pct FROM qbot_v2.fitmodel_daily "
        "WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1").fetchone()


def _poi(conn, route_base_id: int) -> dict:
    rows = conn.execute(
        "SELECT name, category, km_on_route, distance_from_route_m, opening_hours "
        "FROM qbot_v2.route_poi_layer WHERE route_base_id=%s ORDER BY km_on_route", (route_base_id,)).fetchall()
    out: dict[str, list] = {"hard_resupply": [], "soft_food_stop": [], "water": [],
                            "attraction": [], "town": []}
    for r in rows:
        out.setdefault(r["category"], []).append(dict(r))
    return out


# ---- STRATEGIA (segmentacja makro) ---------------------------------------

def _ride_class(seg: dict) -> str:
    if _is_risky(seg):
        return "ryzyko"
    if seg["surface"] in _HARD:
        return "twarde"
    return "gravel"


def _macro_blocks(segs: list[dict], min_km: float = 0.6) -> list[dict]:
    """Laczy segmenty w bloki wg klasy jazdy; polyka bardzo krotkie wtracenia."""
    raw: list[dict] = []
    for s in segs:
        c = _ride_class(s)
        if raw and raw[-1]["c"] == c:
            raw[-1]["km_to"] = s["km_to"]
            raw[-1]["surfs"].append(s["surface"])
        else:
            raw.append({"km_from": s["km_from"], "km_to": s["km_to"], "c": c,
                        "surfs": [s["surface"]]})
    # polkniecie krotkich nie-ryzykownych wtracen w poprzedni blok
    merged: list[dict] = []
    for b in raw:
        length = b["km_to"] - b["km_from"]
        if merged and length < min_km and b["c"] != "ryzyko":
            merged[-1]["km_to"] = b["km_to"]
            merged[-1]["surfs"] += b["surfs"]
        elif merged and merged[-1]["c"] == b["c"]:
            merged[-1]["km_to"] = b["km_to"]
            merged[-1]["surfs"] += b["surfs"]
        else:
            merged.append(b)
    # drugi przebieg scalania po polknieciu
    out: list[dict] = []
    for b in merged:
        if out and out[-1]["c"] == b["c"]:
            out[-1]["km_to"] = b["km_to"]
            out[-1]["surfs"] += b["surfs"]
        else:
            out.append(b)
    for b in out:
        surfs = b["surfs"]
        dom = max(set(surfs), key=surfs.count)
        b["surface"] = dom
        c = b["c"]
        if c == "ryzyko":
            b["klasa"] = "ryzyko"
            b["tip"] = "ostroznie: track bez klasy / grade5 / piach"
        elif c == "twarde":
            b["klasa"] = "szybko"
            b["tip"] = "utwardzone — tempo dyktuje wiatr"
        else:
            b["klasa"] = "gravel"
            b["tip"] = "rowne tempo, lekko na kierownice"
    return out


def _wind_at_km(meteo: Any, km: float) -> str:
    if not isinstance(meteo, dict):
        return "b/d"
    for w in (meteo.get("tabela_30min") or []):
        try:
            if float(w.get("km_od")) <= km <= float(w.get("km_do")):
                return _wind_arrow(w.get("wiatr_wzdluz_ms"))
        except (TypeError, ValueError):
            continue
    return "b/d"


# ---- WODA -----------------------------------------------------------------

def _water_plan(moving_h: Optional[float], peak_wbgt: Optional[float],
                resupply_km: list[float], dist_km: Optional[float]) -> list[str]:
    if moving_h is None:
        return ["- b/d (brak czasu ruchu)"]
    t = peak_wbgt if peak_wbgt is not None else 15.0
    rate = 0.4 if t < 18 else 0.5 if t < 23 else 0.7 if t < 28 else 0.9
    demand = round(moving_h * rate, 1)
    pts = sorted(set([0.0] + [k for k in resupply_km if k is not None] + ([dist_km] if dist_km else [])))
    gap = max((b - a for a, b in zip(pts, pts[1:])), default=(dist_km or 0.0))
    if t > 20:
        rec = "buklak 1,5 l + 2×0,5 l = 2,5 l (regula lato >20C: buklak + min. 2 bidony)"
    elif demand <= 1.5:
        rec = "2 bidony (np. 0,75 + 0,5) — chlodno, male zapotrzebowanie"
    else:
        rec = "buklak 1,5 l + 1 bidon 0,5 l"
    return [
        f"- Zapotrzebowanie: ~{_f(demand)} l ({_hms(moving_h)} ruchu, WBGT szczyt {_f(peak_wbgt) if peak_wbgt is not None else 'b/d'} C)",
        f"- Najdluzsza luka miedzy uzupelnieniami: ~{_f(gap)} km",
        "- Limit noszenia: buklak <= 2 l + 2 bidony (1 l / 0,75 / 0,5)",
        f"- REKOMENDACJA: {rec}",
    ]


# ---- GLOWNA FUNKCJA -------------------------------------------------------

def build_canonical_report_v1(route_id: str, start: Any = None, mode: str = "normalny") -> str:
    from qbot_route_report_tool import _read_route_source, _parse_route_report_start
    from qbot3.routes.route_meteo_engine import run_meteo_engine
    from qbot_route_time_tools import estimate_route_time_v2

    L: list[str] = []
    H = L.append
    route_id = str(route_id).strip()

    parsed = _parse_route_report_start(start) if start else None
    date_str, start_time = (parsed if parsed else (_dt.date.today().isoformat(), "10:00"))

    conn = _db()
    try:
        rb = _route_base(conn, route_id)
        rbid = int(rb["route_base_id"]) if rb else None
        dist_km = (float(rb["distance_m"]) / 1000.0) if (rb and rb.get("distance_m")) else None
        name, latlon = _gpx_name_start(rb.get("source_path") if rb else None)
        adm = _admin(conn, route_id, latlon)
        rs = _read_route_source(route_id) or {}
        surf_sum = rs.get("canonical_surface_summary") or {}
        elev = rs.get("canonical_elevation_summary") or {}
        segs = _surface_segments(conn, rbid) if rbid else []
        fit = _fitmodel(conn)
        poi = _poi(conn, rbid) if rbid else {}

        try:
            meteo = run_meteo_engine(route_id=route_id, date_str=date_str, start_time=start_time, mode=mode)
        except Exception as e:
            meteo = {"status": "ERROR", "error": str(e)[:160]}
        try:
            t = estimate_route_time_v2(route_id=route_id, mode=mode)
        except Exception as e:
            t = {"status": "ERROR", "error": str(e)[:160]}

        moving_h = t.get("moving_h") if isinstance(t, dict) else None
        total_h = t.get("total_h") if isinstance(t, dict) else None
        peak = meteo.get("peak") if isinstance(meteo, dict) else {}
        peak_wbgt = (peak or {}).get("wbgt_eff")
        climb_ranges = [(float(e.get("km_from") or 0), float(e.get("km_to") or 0))
                        for e in (elev.get("top_climb_events") or [])]

        # ---------- 0. PODSTAWOWE ----------
        H(f"# RAPORT TRASY — {name or '(bez nazwy)'}  (ID: {route_id})")
        H("")
        H("## 0. Dane podstawowe i start")
        H("")
        H("| Parametr | Wartosc |")
        H("|---|---|")
        H(f"| Nazwa trasy (RWGPS) | {name or 'b/d'} |")
        H(f"| Start — miejscowosc | {adm.get('miejscowosc') or 'b/d'} |")
        H(f"| Start — gmina | {adm.get('gmina') or 'b/d'} |")
        H(f"| Start — powiat | {adm.get('powiat') or 'b/d'} |")
        H(f"| Start — wojewodztwo | {adm.get('wojewodztwo') or 'b/d'} |")
        H(f"| Start (data) | {date_str} |")
        H(f"| Start (godzina) | {start_time} |")
        H(f"| Dystans | {_f(dist_km)} km |")
        H(f"| Suma podjazdow | {_f(elev.get('ascent_smoothed_m'), 0)} m |")
        H(f"| Wys. min / max | {_f(elev.get('min_elevation_m'), 0)} / {_f(elev.get('max_elevation_m'), 0)} m |")
        H(f"| Max nachylenie | {_f(elev.get('max_climb_event_gradient_pct'))} % |")
        H("")

        # ---------- 1. WERDYKT ----------
        alerts = meteo.get("alerts") if isinstance(meteo, dict) else []
        alert_types = sorted({a.get("typ") for a in (alerts or [])})
        H("## 1. Werdykt")
        H("")
        verdict = f"Trasa {_f(dist_km)} km, podjazdy {_f(elev.get('ascent_smoothed_m'), 0)} m. "
        verdict += ("Uwaga METEO: " + ", ".join(alert_types) + ". ") if alert_types else "Brak alarmow pogodowych. "
        verdict += f"Czas calkowity ~{_hms(total_h)}."
        H(verdict)
        H("")

        # ---------- 2. FITMODEL ----------
        H("## 2. FitModel — odniesienie do formy")
        H("")
        if fit:
            gly = fit.get("glycogen_pct")
            gly_txt = f"{_f(gly, 0)} %" if (gly is not None and float(gly) > 0) else "b/d"
            H("| Miara | Wartosc |")
            H("|---|---|")
            H(f"| FTP_est (wlasny, submax) | {_f(fit.get('ftp_est_w'), 0)} W |")
            H(f"| W/kg | {_f(fit.get('w_per_kg'), 2)} |")
            H(f"| Glikogen | {gly_txt} |")
            H(f"| Data FitModel | {fit.get('day')} |")
        else:
            H("- b/d (brak danych fitmodel_daily)")
        H("")

        # ---------- 3. NAWIERZCHNIA ----------
        H("## 3. Nawierzchnia (przeglad)")
        H("")
        by = (surf_sum.get("by_surface") or {})
        if by:
            H("| Nawierzchnia | km | % |")
            H("|---|---|---|")
            for k, v in sorted(by.items(), key=lambda kv: -float(kv[1].get("pct") or 0)):
                H(f"| {_SURF_PL.get(k, k)} | {_f((v.get('distance_m') or 0)/1000.0)} | {_f(v.get('pct'))} |")
            H("")
            H(f"Tagowane (pewne): {_f(surf_sum.get('tagged_surface_pct'))} % · "
              f"wnioskowane (niepewne): {_f(surf_sum.get('inferred_surface_pct'))} % · "
              f"pokrycie: {_f(surf_sum.get('coverage_pct'))} %.")
        else:
            H("- b/d")
        H("")

        # ---------- 4. STRATEGIA ----------
        H("## 4. Strategia jazdy — odcinki")
        H("")
        blocks = _macro_blocks(segs)
        if blocks:
            H("| km od–do | Nawierzchnia | Klasa | Wiatr (vs jazda) | Wskazowka |")
            H("|---|---|---|---|---|")
            for b in blocks:
                mid = (b["km_from"] + b["km_to"]) / 2.0
                w = _wind_at_km(meteo, mid)
                tip = b["tip"]
                if any(cf <= b["km_to"] and ct >= b["km_from"] for cf, ct in climb_ranges):
                    tip += " · ⬈ podjazd"
                H(f"| {_f(b['km_from'])}–{_f(b['km_to'])} | {_SURF_PL.get(b['surface'], b['surface'])} "
                  f"| {b['klasa']} | {w} | {tip} |")
            H("")
            H("_Ryzyko = highway=track bez klasy / grade5 / piach. track grade1-4 = NIE ryzyko._")
        else:
            H("- b/d")
        H("")

        # ---------- 4a. PODJAZDY ----------
        H("## 4a. Podjazdy (z nawierzchnia)")
        H("")
        climbs = sorted((elev.get("top_climb_events") or []), key=lambda e: float(e.get("km_from") or 0))
        if climbs:
            H("| km od–do | Dlug. | Przewyzsz. | Sr. % | Max % | Nawierzchnia |")
            H("|---|---|---|---|---|---|")
            for e in climbs:
                mid = (float(e.get("km_from") or 0) + float(e.get("km_to") or 0)) / 2.0
                sseg = _surface_at_km(segs, mid)
                sname = _SURF_PL.get(sseg["surface"], sseg["surface"]) if sseg else "b/d"
                H(f"| {_f(e.get('km_from'))}–{_f(e.get('km_to'))} | {_f((e.get('length_m') or 0)/1000.0, 2)} km "
                  f"| {_f(e.get('elevation_gain_m'), 0)} m | {_f(e.get('avg_gradient_pct'))} | "
                  f"{_f(e.get('max_gradient_pct'))} | {sname} |")
        else:
            H("- Brak istotnych podjazdow (trasa plaska).")
        H("")

        # ---------- 5. POGODA ----------
        H("## 5. Pogoda — METEO (co 30 min, wzgledem jazdy)")
        H("")
        tab = meteo.get("tabela_30min") if isinstance(meteo, dict) else None
        if tab:
            H("| Okno | km od–do | WBGT | Odczuw. UTCI | Wiatr wzdluz | Opad (mm/%) |")
            H("|---|---|---|---|---|---|")
            for w in tab:
                od = (w.get("odczuwalna") or {})
                op = (w.get("opad") or {})
                H(f"| {w.get('okno')} | {_f(w.get('km_od'))}–{_f(w.get('km_do'))} "
                  f"| {_f(w.get('wbgt_max'))} | {od.get('od')}–{od.get('do')} ({od.get('kat')}) "
                  f"| {_wind_arrow(w.get('wiatr_wzdluz_ms'))} | {_f(op.get('mm'))}/{op.get('prob')} |")
            H("")
            H(f"Peak WBGT: {_f(peak_wbgt)} C @ km {(peak or {}).get('km')} ({(peak or {}).get('eta')}). "
              "Strzalka: + tylny ↑ / − czolowy ↓.")
            for a in (alerts or []):
                H(f"- ALERT {a.get('typ','?').upper()} [{a.get('severity')}] km {_f(a.get('km_od'))}–"
                  f"{_f(a.get('km_do'))} ({a.get('eta_od')}–{a.get('eta_do')})")
            for c in (meteo.get("caveats") or [])[:3]:
                H(f"- _caveat: {c}_")
        else:
            H(f"- b/d ({(meteo or {}).get('error', 'METEO niedostepne')})")
        H("")

        # ---------- 6. CZAS ----------
        H("## 6. Czas przejazdu (model v2)")
        H("")
        if isinstance(t, dict) and t.get("status") == "OK":
            stops = t.get("stops") or {}
            H("| Pozycja | Wartosc |")
            H("|---|---|")
            H(f"| Czas ruchu | {_hms(moving_h)} |")
            H(f"| Postoje (auto) | {_f((stops.get('suma_min') or 0)/60.0)} h |")
            H(f"| Czas calkowity | {_hms(total_h)} |")
            H(f"| Nieznana nawierzchnia | {_f(t.get('unknown_surface_pct'))} % |")
            if t.get("warning"):
                H("")
                H(f"_{t.get('warning')}_")
        else:
            H(f"- b/d ({(t or {}).get('error', 'brak')})")
        H("")

        # ---------- 7. ALARMY ----------
        H("## 7. Alarmy i ryzyka")
        H("")
        risky = [s for s in segs if _is_risky(s)]
        if alerts or risky:
            H("| Zrodlo | km od–do | Poziom | Powod |")
            H("|---|---|---|---|")
            for a in (alerts or []):
                H(f"| METEO | {_f(a.get('km_od'))}–{_f(a.get('km_do'))} | {a.get('severity')} | {a.get('typ')} |")
            for s in risky[:10]:
                H(f"| Nawierzchnia | {_f(s['km_from'])}–{_f(s['km_to'])} | flaga | {_risk_reason(s)} |")
        else:
            H("- Brak.")
        H("")

        # ---------- 8. POI ----------
        H("## 8. POI — zaopatrzenie i atrakcje")
        H("")
        supply = (poi.get("hard_resupply") or []) + (poi.get("soft_food_stop") or []) + (poi.get("water") or [])
        H(f"Zaopatrzenie/jedzenie: {len(supply)} · miejscowosci: {len(poi.get('town') or [])} · "
          f"atrakcje: {len(poi.get('attraction') or [])}.")
        H("")
        atr = [a for a in (poi.get("attraction") or [])
               if a.get("distance_from_route_m") is None or float(a["distance_from_route_m"]) <= 800][:15]
        if atr:
            H("**Atrakcje turystyczne (do ~800 m od trasy):**")
            H("")
            H("| km | Atrakcja | Odleglosc |")
            H("|---|---|---|")
            for a in atr:
                H(f"| {_f(a.get('km_on_route'))} | {a.get('name')} | {_f(a.get('distance_from_route_m'), 0)} m |")
        else:
            H("- Atrakcje: brak w promieniu 800 m (pelna lista w bazie).")
        H("")

        # ---------- 9. WODA ----------
        H("## 9. Woda — rekomendacja")
        H("")
        resupply_km = [float(x["km_on_route"]) for x in supply if x.get("km_on_route") is not None]
        for line in _water_plan(moving_h, peak_wbgt, resupply_km, dist_km):
            H(line)
        H("")

        # ---------- 10. METADANE ----------
        H("## 10. Jakosc danych / zrodla")
        H("")
        H("| Zrodlo | Zastosowanie |")
        H("|---|---|")
        H("| RWGPS GPX | geometria, nazwa |")
        H("| OSM (surface_layer) | nawierzchnia + ryzyko (track/tracktype) |")
        H("| SRTM 30m | wysokosci (wygl. 200 m) |")
        H("| run_meteo_engine (Open-Meteo) | WBGT/UTCI/opad/wiatr |")
        H("| fitmodel_daily | forma |")
        H("| GeoNames + Google Places | miejscowosci, zaopatrzenie, atrakcje |")
        H("| Nominatim | gmina/powiat/wojewodztwo (cache) |")
        H("")
        H("_Liczby przyblizone. Nawierzchnia wnioskowana = brak taga OSM, nie brak ryzyka. "
          "Czas rekreacyjny +-15 proc._")

        return "\n".join(L)
    finally:
        conn.close()
