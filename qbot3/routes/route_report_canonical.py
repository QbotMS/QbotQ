"""Kanoniczny raport trasy (V2) — uklad 1:1 z makieta.

Zrodla (zywe/strukturalne, bez zgadywania):
- route_base + GPX (nazwa/start), Nominatim (gmina/powiat/woj., cache)
- _read_route_source: canonical_surface_summary / _elevation_summary
- route_surface_layer (tag OSM/tracktype) + route_surface_context (WorldCover -> interpretacja gruntu)
- run_meteo_engine: WBGT/UTCI/opad/wiatr (30 min, POPRZECZNIE) + alerty + peak + caveats
- estimate_route_time_v2: czas ruchu/calkowity + postoje
- fitmodel_daily: FTP_est / W/kg / glikogen; route_poi_layer: zaopatrzenie/atrakcje/miejscowosci

3 POZIOMY PEWNOSCI NAWIERZCHNI (audyt 2026-07-02):
- TWARDE   = tag OSM surface (classification_source=tagged_surface)
- TRACKTYPE = grade1-4 -> jakosc z OSM (inferred_tracktype), przejezdne
- POKRYCIE  = goly track bez tagu -> interpretacja z WorldCover (route_surface_context):
             las->grunt/ubity, pole/laka->droga polna/grunt; "mozliwy piach" TYLKO jako
             WNIOSKOWANIE (latem/susza na Podlasiu), nie fakt; laka=otoczenie, nie nawierzchnia.

Konwencja: po polsku, wiatr m/s (+ tylny, - czolowy), C, czas lokalny. Bez danych -> "b/d".
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


def _hms(hours):
    if hours is None:
        return "b/d"
    m = int(round(float(hours) * 60))
    return f"{m // 60} h {m % 60:02d} min"


def _f(v, nd=1, dflt="b/d"):
    try:
        return f"{float(v):.{nd}f}".replace(".", ",")
    except (TypeError, ValueError):
        return dflt


def _wind_arrow(v):
    if v is None:
        return "b/d"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "b/d"
    if abs(x) < 1.0:
        return f"{_f(abs(x))} ~0"
    return f"{_f(abs(x))} {'tylny ↑' if x > 0 else 'czolowy ↓'}"


# ---- ZRODLA ---------------------------------------------------------------

def _route_base(conn, route_id):
    return conn.execute(
        "SELECT route_base_id, route_id, source_path, distance_m FROM qbot_v2.route_base "
        "WHERE route_id=%s ORDER BY updated_at DESC, route_base_id DESC LIMIT 1",
        (route_id,)).fetchone()


def _gpx_name_start(source_path):
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


def _admin(conn, route_id, latlon):
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


def _surface_segments(conn, route_base_id):
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
                "surface_raw": m.get("surface_raw"),
                "cls": m.get("classification_source"),
                "risk": list(m.get("risk_flags") or []),
                "highway": r.get("highway"), "tracktype": r.get("tracktype"),
                "coverage_status": r.get("coverage_status"), "confidence": r.get("confidence"),
            })
        except (TypeError, ValueError):
            continue
    return segs


def _surface_context(conn, route_base_id):
    """route_surface_context -> lista {km_from,km_to,dominant_pl,agreement_pct,surface_estimate,sand_risk,reason}."""
    try:
        rows = conn.execute(
            "SELECT km_from, km_to, dominant_pl, agreement_pct, surface_estimate, "
            "sand_risk, reason FROM qbot_v2.route_surface_context "
            "WHERE route_base_id=%s ORDER BY km_from", (route_base_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _ctx_at_km(ctx, km):
    for c in ctx:
        if float(c["km_from"]) <= km < float(c["km_to"]):
            return c
    return None


def _surface_at_km(segs, km):
    for s in segs:
        if s["km_from"] <= km <= s["km_to"]:
            return s
    return None


def _fitmodel(conn):
    return conn.execute(
        "SELECT day, ftp_est_w, w_per_kg, weight_kg, glycogen_pct FROM qbot_v2.fitmodel_daily "
        "WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1").fetchone()


def _poi(conn, route_base_id):
    rows = conn.execute(
        "SELECT name, category, km_on_route, distance_from_route_m, opening_hours "
        "FROM qbot_v2.route_poi_layer WHERE route_base_id=%s ORDER BY km_on_route",
        (route_base_id,)).fetchall()
    out = {"hard_resupply": [], "soft_food_stop": [], "water": [], "attraction": [], "town": []}
    for r in rows:
        out.setdefault(r["category"], []).append(dict(r))
    try:
        d = conn.execute("SELECT fetched_at FROM qbot_v2.route_poi_meta "
                         "WHERE route_base_id=%s ORDER BY fetched_at DESC LIMIT 1",
                         (route_base_id,)).fetchone()
        out["_fetched_at"] = d["fetched_at"] if d else None
    except Exception:
        out["_fetched_at"] = None
    return out


def _nearest_town(km, towns):
    best, bd = None, 9e9
    for t in towns:
        k = t.get("km_on_route")
        if k is None:
            continue
        d = abs(float(k) - km)
        if d < bd:
            best, bd = t.get("name"), d
    return best


def _attr_type(name):
    n = (name or "").lower()
    if any(w in n for w in ("kosciol", "kościół", "kaplica", "parafia", "fort", "twierdz", "zamek", "dwor", "dwór", "pomnik")):
        return "zabytek"
    if "muze" in n:
        return "muzeum"
    if "jezior" in n or "zalew" in n:
        return "jezioro"
    if "rezerwat" in n or "park" in n or "aleja" in n:
        return "przyroda"
    if "widok" in n or "punkt" in n or "wzgor" in n or "wzgór" in n or "gora" in n or "góra" in n:
        return "widok"
    return "atrakcja"


# ---- KLASYFIKACJA JAZDY (3 poziomy pewnosci) -----------------------------

def _seg_risk(seg, ctx):
    """Zwraca (klasa_jazdy, powod). Klasy: twarde/gravel/wnioskowane/ryzyko.

    RYZYKO (twarde) tylko: tag sand, track grade5, lub kontekst sand_risk WYSOKIE.
    WNIOSKOWANE: goly track bez tagu (interpretacja z pokrycia terenu) - nie fakt.
    """
    surf = seg.get("surface")
    hw = str(seg.get("highway") or "").lower().strip()
    tt = str(seg.get("tracktype") or "").lower().strip()
    cls = seg.get("cls")
    if surf == "sand":
        return "ryzyko", "piach (tag OSM)"
    if hw == "track" and tt == "grade5":
        return "ryzyko", "track grade5 (luzny)"
    c = _ctx_at_km(ctx, (seg["km_from"] + seg["km_to"]) / 2.0) if ctx else None
    if c and str(c.get("sand_risk")) == "WYSOKIE":
        return "ryzyko", "otwarty teren + geologia: mozliwy gleboki piach"
    if cls == "tagged_surface":
        return ("twarde" if surf in _HARD else "gravel"), ""
    if cls == "inferred_tracktype" or (hw == "track" and tt in _GRADE_OK):
        return "gravel", "z tracktype (grade1-4)"
    # goly track / inferred_highway -> wnioskowane z pokrycia terenu
    return "wnioskowane", (c.get("reason") if c else "brak tagu OSM")


def _macro_blocks(segs, ctx, min_km=1.0):
    """Bloki wg klasy jazdy; polyka krotkie nie-ryzykowne wtracenia -> ~5-8 odcinkow."""
    raw = []
    for s in segs:
        cls, _ = _seg_risk(s, ctx)
        if raw and raw[-1]["c"] == cls:
            raw[-1]["km_to"] = s["km_to"]
            raw[-1]["surfs"].append(s["surface"])
        else:
            raw.append({"km_from": s["km_from"], "km_to": s["km_to"], "c": cls, "surfs": [s["surface"]]})
    merged = []
    for b in raw:
        length = b["km_to"] - b["km_from"]
        if merged and length < min_km and b["c"] not in ("ryzyko",):
            merged[-1]["km_to"] = b["km_to"]
            merged[-1]["surfs"] += b["surfs"]
        elif merged and merged[-1]["c"] == b["c"]:
            merged[-1]["km_to"] = b["km_to"]
            merged[-1]["surfs"] += b["surfs"]
        else:
            merged.append(b)
    out = []
    for b in merged:
        if out and out[-1]["c"] == b["c"]:
            out[-1]["km_to"] = b["km_to"]
            out[-1]["surfs"] += b["surfs"]
        else:
            out.append(b)
    label = {"ryzyko": "ryzyko", "twarde": "szybko", "gravel": "gravel", "wnioskowane": "wniosk."}
    tip = {
        "ryzyko": "ostroznie: piach/grade5 — trzymaj rezerwe, w razie czego prowadz",
        "twarde": "utwardzone — tempo dyktuje wiatr",
        "gravel": "rowne tempo, lekko na kierownice",
        "wnioskowane": "polna/grunt (z pokrycia terenu); latem mozliwe piaszczyste fragmenty",
    }
    for b in out:
        surfs = [x for x in b["surfs"] if x]
        b["surface"] = max(set(surfs), key=surfs.count) if surfs else "unknown"
        b["klasa"] = label.get(b["c"], b["c"])
        b["tip"] = tip.get(b["c"], "")
    return out


def _wind_at_km(meteo, km):
    if not isinstance(meteo, dict):
        return "b/d"
    for w in (meteo.get("tabela_30min") or []):
        try:
            if float(w.get("km_od")) <= km <= float(w.get("km_do")):
                return _wind_arrow(w.get("wiatr_wzdluz_ms"))
        except (TypeError, ValueError):
            continue
    return "b/d"


def _profil_at(km_from, km_to, climbs):
    for e in climbs:
        cf, ct = float(e.get("km_from") or 0), float(e.get("km_to") or 0)
        if cf <= km_to and ct >= km_from:
            return f"⬈ podjazd {_f(e.get('elevation_gain_m'),0)} m / {_f(e.get('avg_gradient_pct'))}%"
    return "plasko/falisto"


def _supply_in(km_from, km_to, supply):
    names = []
    for x in supply:
        k = x.get("km_on_route")
        if k is not None and km_from <= float(k) <= km_to:
            names.append(f"{x.get('name')} (km {_f(k)})")
    return "; ".join(names[:2]) if names else "—"


def _utci_repr(od):
    """Reprezentatywna odczuwalna zamiast surowego min-max (mediana zakresu)."""
    try:
        a, b = float(od.get("od")), float(od.get("do"))
        return str(int(round((a + b) / 2)))
    except (TypeError, ValueError, AttributeError):
        return "b/d"


def _gap_km(points, dist_km):
    pts = sorted(set([0.0] + [p for p in points if p is not None] + ([dist_km] if dist_km else [])))
    return max((b - a for a, b in zip(pts, pts[1:])), default=(dist_km or 0.0))


def _water_rec(moving_h, peak_wbgt):
    t = peak_wbgt if peak_wbgt is not None else 15.0
    rate = 0.4 if t < 18 else 0.5 if t < 23 else 0.7 if t < 28 else 0.9
    demand = round((moving_h or 0) * rate, 1)
    if t > 20:
        rec = "buklak 1,5 l + 2×0,5 l = 2,5 l (regula lato >20C: buklak + min. 2 bidony)"
    elif demand <= 1.5:
        rec = "2 bidony (0,75 + 0,5) — chlodno, male zapotrzebowanie"
    else:
        rec = "buklak 1,5 l + 1 bidon 0,5 l"
    return demand, rec


# ---- GLOWNA FUNKCJA -------------------------------------------------------

def build_canonical_report_v1(route_id, start=None, mode="normalny"):
    from qbot_route_report_tool import _read_route_source, _parse_route_report_start
    from qbot3.routes.route_meteo_engine import run_meteo_engine
    from qbot_route_time_tools import estimate_route_time_v2

    L = []
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
        ctx = _surface_context(conn, rbid) if rbid else []
        fit = _fitmodel(conn)
        poi = _poi(conn, rbid) if rbid else {}

        try:
            meteo = run_meteo_engine(route_id=route_id, date_str=date_str, start_time=start_time, mode=mode)
        except Exception as e:
            meteo = {"status": "ERROR", "error": str(e)[:160]}
        try:
            tt = estimate_route_time_v2(route_id=route_id, mode=mode)
        except Exception as e:
            tt = {"status": "ERROR", "error": str(e)[:160]}

        moving_h = tt.get("moving_h") if isinstance(tt, dict) else None
        total_h = tt.get("total_h") if isinstance(tt, dict) else None
        peak = meteo.get("peak") if isinstance(meteo, dict) else {}
        peak_wbgt = (peak or {}).get("wbgt_eff")
        alerts = meteo.get("alerts") if isinstance(meteo, dict) else []
        climbs = sorted((elev.get("top_climb_events") or []), key=lambda e: float(e.get("km_from") or 0))

        supply = (poi.get("hard_resupply") or []) + (poi.get("soft_food_stop") or []) + (poi.get("water") or [])
        supply = sorted(supply, key=lambda x: (x.get("km_on_route") is None, x.get("km_on_route") or 0))
        resupply_km = [float(x["km_on_route"]) for x in supply if x.get("km_on_route") is not None]
        towns = poi.get("town") or []

        # ---------- 0 ----------
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
        H(f"| Start (data / godzina) | {date_str} / {start_time} |")
        H(f"| Dlugie postoje (Twoje) | {tt.get('planned_long_stop_min') if isinstance(tt, dict) and tt.get('planned_long_stop_min') else 'brak (dolicz sam)'} |")
        H(f"| Dystans | {_f(dist_km)} km |")
        H(f"| Suma podjazdow | {_f(elev.get('ascent_smoothed_m'), 0)} m |")
        H(f"| Wys. min / max | {_f(elev.get('min_elevation_m'), 0)} / {_f(elev.get('max_elevation_m'), 0)} m |")
        H(f"| Max nachylenie | {_f(elev.get('max_climb_event_gradient_pct'))} % |")
        H(f"| Zrodlo geometrii / data | RWGPS GPX / {date_str} |")
        H("")

        # ---------- 1 ----------
        risky_blocks = [b for b in _macro_blocks(segs, ctx) if b["c"] == "ryzyko"]
        alert_types = sorted({a.get("typ") for a in (alerts or [])})
        H("## 1. Werdykt")
        H("")
        v = f"Trasa {_f(dist_km)} km, podjazdy {_f(elev.get('ascent_smoothed_m'),0)} m — profil "
        v += "umiarkowany. " if (elev.get("ascent_smoothed_m") or 0) < 800 else "wymagajacy. "
        if risky_blocks:
            v += "Odcinki do uwagi: " + ", ".join(f"km {_f(b['km_from'])}–{_f(b['km_to'])}" for b in risky_blocks[:3]) + " (piach/grade5). "
        else:
            v += "Brak twardych odcinkow ryzyka (nietagowane tracki = grunt/polna wg pokrycia terenu, przejezdne). "
        v += ("METEO: " + ", ".join(alert_types) + ". ") if alert_types else "Pogoda bez alarmow. "
        dem, rec = _water_rec(moving_h, peak_wbgt)
        v += f"Woda: {rec.split('(')[0].strip()}. Czas ~{_hms(total_h)}."
        H(v)
        H("")

        # ---------- 2 ----------
        H("## 2. FitModel — odniesienie tej jazdy do formy")
        H("")
        if fit:
            gly = fit.get("glycogen_pct")
            gly_txt = f"{_f(gly, 0)} %" if (gly is not None and float(gly) > 0) else "b/d"
            H("**Twoja forma (fitmodel_daily):**")
            H("")
            H("| Parametr | Wartosc |")
            H("|---|---|")
            H(f"| FTP_est (wlasny, submax) | {_f(fit.get('ftp_est_w'), 0)} W |")
            H(f"| W/kg | {_f(fit.get('w_per_kg'), 2)} |")
            H(f"| Glikogen dzis | {gly_txt} |")
            H(f"| Data FitModel | {fit.get('day')} |")
        else:
            H("- forma: b/d (brak fitmodel_daily)")
        H("")
        cho = round((moving_h or 0) * 50) if moving_h else None
        H("**Ta trasa kontra forma:**")
        H("")
        H("| Miara | Szacunek trasy | Ocena |")
        H("|---|---|---|")
        H(f"| Zapotrzebowanie CHO | ~50 g/h -> ~{cho if cho is not None else 'b/d'} g | tankuj 40–60 g/h |")
        H(f"| Zapotrzebowanie woda | ~{_f(dem)} l ({_hms(moving_h)} ruchu) | pokryjesz z refilami |")
        H("| Obciazenie (strain) | b/d | _do wpiecia: route_fuel_plan / strain buckets_ |")
        H("| Rezerwa W′ na podjazdach | b/d | _do wpiecia: route_fuel_plan_ |")
        H("")
        H("**Fueling:** sniadanie weglowodanowe + tankuj w trasie 40–60 g CHO/h; nie zjezdzaj na rezerwie glikogenu.")
        H("")
        H("**Woda — rekomendacja (uwzglednia refile i limity pojemnikow):**")
        H("")
        H("| Element | Info |")
        H("|---|---|")
        H(f"| Limit noszenia | buklak <= 2 l + 2 bidony (1 l / 0,75 / 0,5) |")
        H(f"| Zapotrzebowanie | ~{_f(dem)} l na cala trase |")
        H(f"| Najdluzsza luka | ~{_f(_gap_km(resupply_km, dist_km))} km |")
        H(f"| Rekomendacja | {rec} |")
        H("")

        # ---------- 3 ----------
        H("## 3. Nawierzchnia — twarde dane vs interpretacja")
        H("")
        # 3 poziomy pewnosci z segmentow
        def _kmlen(s):
            return max(0.0, float(s["km_to"]) - float(s["km_from"]))
        hard = [s for s in segs if s.get("cls") == "tagged_surface"]
        ttk = [s for s in segs if s.get("cls") == "inferred_tracktype"]
        infr = [s for s in segs if s.get("cls") not in ("tagged_surface", "inferred_tracktype")]
        tot = sum(_kmlen(s) for s in segs) or (dist_km or 1)

        def _bysurf(rs):
            d = {}
            for s in rs:
                d[s["surface"]] = d.get(s["surface"], 0.0) + _kmlen(s)
            return sorted(d.items(), key=lambda kv: -kv[1])
        H(f"**A. Twarde dane — tag OSM `surface` ({_f(sum(_kmlen(s) for s in hard))} km · "
          f"{_f(100*sum(_kmlen(s) for s in hard)/tot)} %)** — tym ufasz:")
        H("")
        H("| Nawierzchnia | km |")
        H("|---|---|")
        for k, v2 in _bysurf(hard):
            H(f"| {_SURF_PL.get(k, k)} | {_f(v2)} |")
        H("")
        if ttk:
            H(f"**B. Interpretacja z `tracktype` (grade1-4) ({_f(sum(_kmlen(s) for s in ttk))} km · "
              f"{_f(100*sum(_kmlen(s) for s in ttk)/tot)} %)** — przejezdne, dosc pewne:")
            H("")
            H("| km od–do | z tracktype -> nawierzchnia |")
            H("|---|---|")
            for s in ttk:
                H(f"| {_f(s['km_from'])}–{_f(s['km_to'])} | {s.get('tracktype')} -> {_SURF_PL.get(s['surface'], s['surface'])} |")
            H("")
        H(f"**C. Interpretacja z pokrycia terenu — WorldCover ({_f(sum(_kmlen(s) for s in infr))} km · "
          f"{_f(100*sum(_kmlen(s) for s in infr)/tot)} %)** — to WNIOSKOWANIE, nie dane:")
        H("")
        if ctx:
            H("| km od–do | teren (WorldCover) | interpretacja nawierzchni | piach? |")
            H("|---|---|---|---|")
            for c in ctx:
                H(f"| {_f(c['km_from'])}–{_f(c['km_to'])} | {c.get('dominant_pl') or 'b/d'} ({c.get('agreement_pct')}%) "
                  f"| {c.get('surface_estimate')} | {c.get('sand_risk')} |")
            H("")
            H("_Teren = OTOCZENIE (pole/laka/las), nie sama nawierzchnia. Nietagowany track przez pola/laki "
              "to zwykle droga polna/grunt. „WNIOSK.\" = latem/susza na Podlasiu mozliwe piaszczyste fragmenty "
              "(wnioskowanie z otoczenia+geologii), wiosna zwykle grunt — brak tagu OSM, nie brak przejezdnosci._")
        else:
            H("_Brak warstwy route_surface_context — przelicz trase._")
        H("")

        # ---------- 4 ----------
        H("## 4. Strategia jazdy — trasa w odcinkach")
        H("")
        blocks = _macro_blocks(segs, ctx)
        if blocks:
            H("| km od–do | Nawierzchnia | Profil | Wiatr (vs jazda) | Zaopatrzenie | Jak jechac |")
            H("|---|---|---|---|---|---|")
            for b in blocks:
                mid = (b["km_from"] + b["km_to"]) / 2.0
                H(f"| {_f(b['km_from'])}–{_f(b['km_to'])} | {_SURF_PL.get(b['surface'], b['surface'])} ({b['klasa']}) "
                  f"| {_profil_at(b['km_from'], b['km_to'], climbs)} | {_wind_at_km(meteo, mid)} "
                  f"| {_supply_in(b['km_from'], b['km_to'], supply)} | {b['tip']} |")
            H("")
            H("_Klasy: szybko=utwardzone · gravel=szuter/tracktype · wniosk.=grunt/polna z pokrycia terenu · ryzyko=piach/grade5._")
        else:
            H("- b/d")
        H("")

        # ---------- 4a ----------
        H("## 4a. Podjazdy (z nawierzchnia)")
        H("")
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

        # ---------- 5 (POPRZECZNA) ----------
        H("## 5. Pogoda — METEO (co 30 min, POPRZECZNIE)")
        H("")
        tab = meteo.get("tabela_30min") if isinstance(meteo, dict) else None
        if tab:
            okna = [w.get("okno") for w in tab]
            H("| Parametr | " + " | ".join(str(o) for o in okna) + " |")
            H("|---|" + "---|" * len(okna))
            H("| km od–do | " + " | ".join(f"{_f(w.get('km_od'))}–{_f(w.get('km_do'))}" for w in tab) + " |")
            H("| WBGT (C) | " + " | ".join(_f(w.get("wbgt_max")) for w in tab) + " |")
            H("| Odczuw. UTCI (C) | " + " | ".join(_utci_repr(w.get("odczuwalna") or {}) for w in tab) + " |")
            H("| Kat. UTCI | " + " | ".join(str((w.get("odczuwalna") or {}).get("kat") or "—") for w in tab) + " |")
            H("| Wiatr wzdluz | " + " | ".join(_wind_arrow(w.get("wiatr_wzdluz_ms")) for w in tab) + " |")
            H("| Opad (mm/%) | " + " | ".join(f"{_f((w.get('opad') or {}).get('mm'))}/{(w.get('opad') or {}).get('prob')}" for w in tab) + " |")
            def _bz(w):
                b = w.get("burza") or {}
                if not isinstance(b, dict):
                    return str(b or "—")
                if b.get("poziom"):
                    return str(b["poziom"])
                cape = b.get("cape")
                return f"CAPE {cape}" if (cape and float(cape) >= 200) else "—"
            H("| Burza | " + " | ".join(_bz(w) for w in tab) + " |")
            H("")
            H(f"Peak WBGT: {_f(peak_wbgt)} C @ km {(peak or {}).get('km')} ({(peak or {}).get('eta')}). "
              "Strzalka: + tylny ↑ / − czolowy ↓. Odczuwalna = reprezentatywna (mediana okna), nie min-max.")
            for a in (alerts or []):
                H(f"- ALERT {a.get('typ','?').upper()} [{a.get('severity')}] km {_f(a.get('km_od'))}–"
                  f"{_f(a.get('km_do'))} ({a.get('eta_od')}–{a.get('eta_do')})")
            for c in (meteo.get("caveats") or [])[:3]:
                H(f"- _caveat: {c}_")
        else:
            H(f"- b/d ({(meteo or {}).get('error', 'METEO niedostepne')})")
        H("")

        # ---------- 6 ----------
        H("## 6. Czas przejazdu (model v2)")
        H("")
        if isinstance(tt, dict) and tt.get("status") == "OK":
            stops = tt.get("stops") or {}
            H("| Pozycja | Wartosc |")
            H("|---|---|")
            H(f"| Czas ruchu | {_hms(moving_h)} |")
            H(f"| Postoje (auto) | {_f((stops.get('suma_min') or 0)/60.0)} h |")
            H(f"| Czas calkowity | {_hms(total_h)} |")
            H(f"| Dokladnosc | ±15 % |")
            if tt.get("warning"):
                H("")
                H(f"_{tt.get('warning')}_")
        else:
            H(f"- b/d ({(tt or {}).get('error', 'brak')})")
        H("")

        # ---------- 7 ----------
        H("## 7. Alarmy i ryzyka")
        H("")
        rows7 = []
        for a in (alerts or []):
            env = "otwarte" if a.get("typ") in ("wiatr", "upal") else "—"
            rows7.append(("METEO", _f(a.get("km_od")), _f(a.get("km_do")), a.get("severity"),
                          f"{a.get('typ')} — {a.get('opis') or ''}".strip(" —"), env))
        for b in blocks:
            if b["c"] == "ryzyko":
                rows7.append(("Nawierzchnia", _f(b["km_from"]), _f(b["km_to"]), "flaga",
                              "piach/grade5 — luzna nawierzchnia", "—"))
            elif b["c"] == "wnioskowane":
                c = _ctx_at_km(ctx, (b["km_from"] + b["km_to"]) / 2.0)
                terr = (c.get("dominant_pl") if c else None) or "otwarte"
                rows7.append(("Nawierzchnia", _f(b["km_from"]), _f(b["km_to"]), "info",
                              "nietagowany track — grunt wg pokrycia; latem mozliwy piach (wniosk.)", terr))
        if rows7:
            H("| Zrodlo | km od | km do | Poziom | Powod | Srodowisko |")
            H("|---|---|---|---|---|---|")
            for r in rows7:
                H(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")
        else:
            H("- Brak.")
        H("")

        # ---------- 8 ----------
        H("## 8. POI — zaopatrzenie i atrakcje")
        H("")
        poi_date = poi.get("_fetched_at")
        poi_date_s = poi_date.date().isoformat() if hasattr(poi_date, "date") else (str(poi_date)[:10] if poi_date else "b/d")
        H("| Kategoria | Info |")
        H("|---|---|")
        supply_pts = ", ".join(f"km {_f(k)}" for k in resupply_km[:8]) or "—"
        H(f"| Woda / sklepy (punkty) | {supply_pts} |")
        H(f"| Zaopatrzenie/jedzenie | {len(supply)} pkt |")
        H(f"| Miejscowosci | {len(towns)} |")
        H(f"| Najdluzsza luka zaopatrz. | ~{_f(_gap_km(resupply_km, dist_km))} km |")
        H(f"| Dane POI z dnia | {poi_date_s} |")
        H("")
        atr = [a for a in (poi.get("attraction") or [])
               if a.get("distance_from_route_m") is None or float(a["distance_from_route_m"]) <= 800]
        atr = sorted(atr, key=lambda a: (a.get("km_on_route") is None, a.get("km_on_route") or 0))[:15]
        if atr:
            H("**Atrakcje (z kilometrazem, miejscowoscia i typem):**")
            H("")
            H("| km | Atrakcja | Miejscowosc | Typ | Odl. |")
            H("|---|---|---|---|---|")
            for a in atr:
                km = a.get("km_on_route")
                H(f"| {_f(km)} | {a.get('name')} | {_nearest_town(float(km), towns) if km is not None else 'b/d'} "
                  f"| {_attr_type(a.get('name'))} | {_f(a.get('distance_from_route_m'), 0)} m |")
        else:
            H("- Atrakcje: brak w promieniu 800 m.")
        H("")

        # ---------- 9 ----------
        H("## 9. Sprzet (sugestia, nie wyrocznia)")
        H("")
        hard_pct = 100 * sum(_kmlen(s) for s in hard if s["surface"] in _HARD) / tot
        infr_pct = 100 * sum(_kmlen(s) for s in infr) / tot
        if infr_pct >= 25:
            tyre = ("Duzo nietagowanych tracktow ({}%) przez pola/laki/las -> **G-One Pro RS (Zipp 303 S)** "
                    "jako bezpieczniejszy uniwersal; Thunder Burt tylko jesli wiesz ze grunt twardy.").format(round(infr_pct))
        elif hard_pct >= 60:
            tyre = "Przewaga asfaltu -> szybsza guma OK (Thunder Burt / G-One Pro RS na Zipp 303 S)."
        else:
            tyre = "Mieszanka szuter/grunt -> **G-One Pro RS (Zipp 303 S)** uniwersalnie."
        H(tyre)
        H("")

        # ---------- 10 ----------
        H("## 10. Jakosc danych / metadane")
        H("")
        H("| Zrodlo | Zastosowanie | Swiezosc |")
        H("|---|---|---|")
        H(f"| RWGPS GPX | geometria, nazwa | {date_str} |")
        H("| OSM surface_layer | nawierzchnia + tag/tracktype | live |")
        H("| WorldCover (route_surface_context) | interpretacja gruntu nietagowanego | 2021 (ESA) |")
        H("| SRTM 30m | wysokosci (wygl. 200 m) | statyczne |")
        H("| run_meteo_engine (Open-Meteo) | WBGT/UTCI/opad/wiatr | live |")
        H(f"| fitmodel_daily | forma | {fit.get('day') if fit else 'b/d'} |")
        H(f"| GeoNames + Google Places | miejscowosci/zaopatrzenie/atrakcje | {poi_date_s} |")
        H("| Nominatim | gmina/powiat/woj. | cache |")
        H("")
        H("_Liczby przyblizone. „Wnioskowane\" = brak tagu OSM (interpretacja z pokrycia terenu), nie brak przejezdnosci. "
          "Odczuwalna = reprezentatywna. Czas rekreacyjny ±15%._")

        return "\n".join(L)
    finally:
        conn.close()
