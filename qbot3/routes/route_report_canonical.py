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
                "surface_category": m.get("surface_category"),
                "surface_category_label": m.get("surface_category_label"),
                "surface_category_reason": m.get("surface_category_reason"),
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
    """Zwraca (klasa_strategii, powod) na bazie surface_category (model 2026-07-03, z DB).

    4 koszyki: szybko(k1) / gravel(k2+k3) / trudna(k4) / ryzyko(k5).
    Powod = surface_category_reason (route_surface_category_store). Brak kategorii ->
    "nieznane" z sygnalem do przeliczenia (bez zgadywania).
    """
    k = seg.get("surface_category")
    reason = seg.get("surface_category_reason") or ""
    _MAP = {1: "szybko", 2: "gravel", 3: "gravel", 4: "trudna", 5: "ryzyko"}
    if k in _MAP:
        return _MAP[k], reason
    return "nieznane", (reason or "brak kategorii — przelicz trase")


def _macro_blocks(segs, ctx, min_km=3.0):
    """Grube bloki strategii (model 2026-07-03, 4 koszyki):
    szybko(k1) / gravel(k2+k3) / trudna(k4) / ryzyko(k5). Scala i polyka krotkie
    (<min_km) nie-ryzykowne wtracenia. ryzyko nigdy nie polykane."""
    raw = []
    for s in segs:
        c, _ = _seg_risk(s, ctx)
        if raw and raw[-1]["c"] == c:
            raw[-1]["km_to"] = s["km_to"]; raw[-1]["surfs"].append(s["surface"]); raw[-1]["clss"].append(s.get("cls"))
        else:
            raw.append({"km_from": s["km_from"], "km_to": s["km_to"], "c": c,
                        "surfs": [s["surface"]], "clss": [s.get("cls")]})

    def coalesce(blocks):
        out = []
        for b in blocks:
            length = b["km_to"] - b["km_from"]
            if out and length < min_km and b["c"] not in ("ryzyko", "trudna"):
                out[-1]["km_to"] = b["km_to"]; out[-1]["surfs"] += b["surfs"]; out[-1]["clss"] += b["clss"]
            elif out and out[-1]["c"] == b["c"]:
                out[-1]["km_to"] = b["km_to"]; out[-1]["surfs"] += b["surfs"]; out[-1]["clss"] += b["clss"]
            else:
                out.append(dict(b))
        return out

    blocks = coalesce(coalesce(raw))
    label = {"szybko": "asfalt/szybko", "gravel": "gravel/szuter", "trudna": "trudna/wolna",
             "ryzyko": "ryzyko", "nieznane": "b/d"}
    tip = {
        "szybko": "utwardzone — tempo dyktuje wiatr",
        "gravel": "dobry/zwykly szuter — rowne tempo",
        "trudna": "trawa/mixed/grade4 lub polna bez tagu — wolniej, oszczedzaj nogi; po deszczu ciezko",
        "ryzyko": "ostroznie: piach/grade5 — trzymaj rezerwe, w razie czego prowadz",
        "nieznane": "brak danych kategorii — przelicz trase",
    }
    for b in blocks:
        surfs = [x for x in b["surfs"] if x]
        b["surface"] = max(set(surfs), key=surfs.count) if surfs else "unknown"
        b["klasa"] = label.get(b["c"], b["c"])
        b["tip"] = tip.get(b["c"], "")
        b["ma_wniosk"] = any(cl not in ("tagged_surface", "inferred_tracktype") for cl in b["clss"])
    return blocks


def _km_by_category(segs):
    """Dokladny udzial km wg surface_category (z DB, bez scalania) -> {1:..,..,5:..}."""
    d = {}
    for s in segs:
        k = s.get("surface_category")
        if k is None:
            continue
        d[k] = d.get(k, 0.0) + (float(s["km_to"]) - float(s["km_from"]))
    return {k: round(v, 1) for k, v in d.items()}

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



def _modelq(conn):
    """Najnowszy snapshot ModelQ (Xert): FTP/LTP/W'/peak + obciazenie."""
    try:
        return conn.execute(
            "SELECT snapshot_at, ftp_power_w, ltp_power_w, w_prime_kj, peak_power_w, "
            "training_load, recovery_load FROM qbot_v2.xert_profile_snapshots "
            "ORDER BY snapshot_at DESC LIMIT 1").fetchone()
    except Exception:
        return None


def _climb_power(grade_pct, v_kmh, mass=100.0):
    """Zgrubna moc na podjezdzie [W]: grawitacja + toczenie + powietrze."""
    v = max(1.0, float(v_kmh)) / 3.6
    grav = mass * 9.81 * (float(grade_pct) / 100.0) * v
    roll = mass * 9.81 * 0.008 * v
    air = 0.5 * 1.2 * 0.4 * v ** 3
    return max(0.0, grav + roll + air)


def _modelq_form_for_xss(conn):
    """FTP + W' WYLACZNIE z ModelQ (fitmodel_daily) -- niezaleznie od zmiennej
    `ftp`/`mq` uzywanej wyzej w tej funkcji (ktora dziala Xert-first, legacy
    sprzed ustalenia zasady 'Xert = tylko benchmark'). Nowy szacunek XSS ma
    byc spojny z raportem po jezdzie (ride_report_builder.py), ktory zawsze
    bierze forme z ModelQ. Nie zmieniam tu istniejacej tabeli 'Twoja forma'
    (osobna, wieksza decyzja) -- tylko zrodlo dla XSS. Patrz DECISIONS.md 2026-07-07."""
    try:
        row = conn.execute(
            "SELECT ftp_est_w, wprime_modelq_kj FROM qbot_v2.fitmodel_daily "
            "WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1").fetchone()
    except Exception:
        return None, None
    if not row:
        return None, None
    return row.get("ftp_est_w"), row.get("wprime_modelq_kj")


def _estimate_route_xss(moving_h, dist_km, climbs, ftp, wprime_kj, mass=100.0, if_est=0.62):
    """Zgrubny szacunek XSS dla PLANOWANEJ trasy (jeszcze nie przejechanej).
    Nie ma tu prawdziwego pomiaru mocy, wiec dzielimy trase na segmenty:
    podjazdy (z `climbs`, moc z _climb_power) + reszta (plasko/falisto, moc
    stala IF_est*FTP) i puszczamy TEN SAM wzor fizyki W'bal/XSS co dla
    wykonanych jazd (fitmodel/wbal_replay.py -- (p/CP)*(1+BETA*zmeczenie)*
    (100/3600)*dt), tylko w grubszym kroku (per-segment, nie per-sekunda).
    To estymata, nie pomiar -- stad tier B, nie A."""
    import math
    if not ftp or not wprime_kj or not moving_h or moving_h <= 0 or not dist_km:
        return None
    cp = float(ftp)
    wprime_j = float(wprime_kj) * 1000.0
    baseline_p = if_est * cp

    segs = []
    cursor_km = 0.0
    climb_list = sorted(
        [(float(c.get("km_from") or 0), float(c.get("km_to") or 0), float(c.get("avg_gradient_pct") or 0))
         for c in (climbs or []) if c.get("km_to") is not None],
        key=lambda x: x[0],
    )
    for cf, ct, grade in climb_list:
        cf, ct = max(cf, cursor_km), max(ct, cursor_km)
        if cf > cursor_km:
            segs.append((cursor_km, cf, baseline_p))
        if ct > cf:
            v_climb_kmh = max(6.0, 22.0 - grade * 1.5)  # zgrubna predkosc na podjezdzie
            segs.append((cf, ct, _climb_power(grade, v_climb_kmh, mass)))
        cursor_km = max(cursor_km, ct)
    if cursor_km < dist_km:
        segs.append((cursor_km, dist_km, baseline_p))
    if not segs:
        segs = [(0.0, dist_km, baseline_p)]

    total_seg_km = sum(t - f for f, t, _ in segs) or dist_km
    wbal = wprime_j
    xss_sum = 0.0
    BETA = 1.0
    RECOVERY_TAU_S = 400.0  # uproszczenie -- bez zaleznosci od dcp jak w replayu realnych jazd
    for f, t, p in segs:
        seg_km = t - f
        if seg_km <= 0:
            continue
        dt = moving_h * 3600.0 * (seg_km / total_seg_km)
        fatigue = max(0.0, 1.0 - (wbal / wprime_j))
        xss_sum += (p / cp) * (1.0 + BETA * fatigue) * (100.0 / 3600.0) * dt
        if p > cp:
            wbal -= (p - cp) * dt
        else:
            k = 1 - math.exp(-dt / RECOVERY_TAU_S)
            wbal += (wprime_j - wbal) * k
        wbal = max(0.0, min(wprime_j, wbal))
    return round(xss_sum, 1)


_WD_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_ATTR_GENERIC = {"kaplica", "kaplica cmentarna", "krzyz", "krzyż", "cmentarz",
                 "kosciol", "kościół", "kapliczka", "figura", "krzyz przydrozny"}


def _parse_hm(tok):
    tok = tok.strip().replace("\u202f", " ").replace("\u2009", " ")
    ap = None
    t = tok.lower()
    if t.endswith("am"):
        ap = "am"; tok = tok[:-2].strip()
    elif t.endswith("pm"):
        ap = "pm"; tok = tok[:-2].strip()
    tok = tok.strip()
    hh, mm = (tok.split(":")[:2] + ["0"])[:2] if ":" in tok else (tok, "0")
    try:
        h = int(hh); m = int(mm)
    except ValueError:
        return None
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return h + m / 60.0


def _oh_open_at(oh, weekday_name, hour_float):
    """(otwarte?, godziny_str) dla dnia z formatu Google. None gdy nieznane."""
    if not oh:
        return None, None
    seg = None
    for part in str(oh).split(";"):
        part = part.strip()
        if part.lower().startswith(weekday_name.lower() + ":"):
            seg = part.split(":", 1)[1].strip()
            break
    if seg is None:
        return None, None
    low = seg.lower()
    if "24 hour" in low or "calodob" in low:
        return True, "24h"
    if "closed" in low or "zamk" in low:
        return False, "zamkniete"
    for dash in ("–", "—", "-"):
        if dash in seg:
            a, b = seg.split(dash, 1)
            oa, ob = _parse_hm(a), _parse_hm(b)
            if oa is not None and ob is not None and hour_float is not None:
                return (oa <= hour_float <= ob), seg.strip()
            return None, seg.strip()
    return None, seg.strip()


def _eta_at_km(meteo, km):
    ps = meteo.get("per_segment") if isinstance(meteo, dict) else None
    if not ps:
        return None, None
    best = min(ps, key=lambda x: abs(float(x.get("km", 0)) - km))
    eta = best.get("eta")
    try:
        hh, mm = str(eta).split(":")
        return eta, int(hh) + int(mm) / 60.0
    except (ValueError, AttributeError):
        return eta, None


def _attr_worth(name):
    """Kuracja: pomijaj generyczne (byle kaplica/krzyz). (warto?, ranga)."""
    n = (name or "").strip().lower()
    if not n or n in _ATTR_GENERIC:
        return False, 9
    t = _attr_type(name)
    if t == "zabytek" and len(name.split()) < 3:
        return False, 9
    return True, {"widok": 0, "przyroda": 1, "muzeum": 1, "jezioro": 1, "zabytek": 2}.get(t, 3)


def _surface_svg(p_hard, p_ttk, p_infr, hard_km, ttk_km, infr_km, risky_blocks):
    """Wektorowy (SVG) pasek pewnosci nawierzchni do raportu HTML (/kanon).
    Kolory ciemne + bialy tekst -> czytelne w light i dark mode. Samodzielny (bez CSS)."""
    W, x0, y, h = 648.0, 16.0, 34.0, 46.0
    wh = W * p_hard / 100.0
    wt = W * p_ttk / 100.0
    wi = max(0.0, W - wh - wt)
    xh, xt, xi = x0, x0 + wh, x0 + wh + wt
    P = []
    P.append('<svg viewBox="0 0 680 150" xmlns="http://www.w3.org/2000/svg" role="img" '
             'aria-label="Pewnosc klasyfikacji nawierzchni" style="max-width:680px;width:100%">')
    P.append('<defs><pattern id="hatch" width="7" height="7" patternTransform="rotate(45)" '
             'patternUnits="userSpaceOnUse"><rect width="7" height="7" fill="#5F5E5A"/>'
             '<line x1="0" y1="0" x2="0" y2="7" stroke="#ffffff" stroke-width="1.6" opacity="0.35"/></pattern></defs>')
    P.append('<text x="16" y="20" font-size="14" fill="#888780">Nawierzchnia \u2014 pewnosc klasyfikacji</text>')
    P.append(f'<rect x="{xh:.1f}" y="{y}" width="{wh:.1f}" height="{h}" rx="6" fill="#3B6D11"/>')
    P.append(f'<rect x="{xt:.1f}" y="{y}" width="{wt:.1f}" height="{h}" rx="6" fill="#854F0B"/>')
    P.append(f'<rect x="{xi:.1f}" y="{y}" width="{wi:.1f}" height="{h}" rx="6" fill="url(#hatch)"/>')

    def two(cx, title, pct, km):
        return (f'<text x="{cx:.0f}" y="54" text-anchor="middle" font-size="14" fill="#ffffff" '
                f'font-weight="500">{title}</text>'
                f'<text x="{cx:.0f}" y="71" text-anchor="middle" font-size="12.5" fill="#ffffff">'
                f'{round(pct)}% \u00b7 {_f(km)} km</text>')

    def one(cx, pct):
        return (f'<text x="{cx:.0f}" y="62" text-anchor="middle" font-size="12.5" fill="#ffffff" '
                f'font-weight="500">{round(pct)}%</text>')

    P.append(two(xh + wh / 2, "tag OSM (fakt)", p_hard, hard_km) if wh >= 110 else (one(xh + wh / 2, p_hard) if wh >= 30 else ""))
    P.append(two(xt + wt / 2, "tracktype", p_ttk, ttk_km) if wt >= 110 else (one(xt + wt / 2, p_ttk) if wt >= 30 else ""))
    P.append(two(xi + wi / 2, "z terenu (wniosk.)", p_infr, infr_km) if wi >= 110 else (one(xi + wi / 2, p_infr) if wi >= 30 else ""))

    P.append('<g font-size="12.5">'
             '<rect x="16" y="100" width="12" height="12" rx="2" fill="#3B6D11"/>'
             '<text x="34" y="110" fill="#888780">tag OSM \u2014 fakt z mapy</text>'
             '<rect x="196" y="100" width="12" height="12" rx="2" fill="#854F0B"/>'
             '<text x="214" y="110" fill="#888780">tracktype grade1\u20134 \u2014 przejezdne</text>'
             '<rect x="430" y="100" width="12" height="12" rx="2" fill="url(#hatch)"/>'
             '<text x="448" y="110" fill="#888780">z pokrycia terenu \u2014 wnioskowane</text></g>')

    rkm = sum(b["km_to"] - b["km_from"] for b in risky_blocks) if risky_blocks else 0.0
    if risky_blocks:
        zak = ", ".join(f"km {_f(b['km_from'])}\u2013{_f(b['km_to'])}" for b in risky_blocks[:2])
        rtxt = f"ryzyko: piach ~{_f(rkm)} km ({zak}, tag OSM) \u2014 reszta gruntu przejezdna"
        rcol = "#C0392B"
    else:
        rtxt = "brak twardych odcinkow ryzyka \u2014 nietagowany grunt to przejezdna polna"
        rcol = "#3B6D11"
    P.append(f'<g font-size="12.5"><rect x="16" y="124" width="12" height="12" rx="2" fill="{rcol}"/>'
             f'<text x="34" y="134" fill="{rcol}" font-weight="500">{rtxt}</text></g>')
    P.append('</svg>')
    return "".join(P)


# ---- GLOWNA FUNKCJA -------------------------------------------------------

def build_canonical_report_v1(route_id, start=None, mode="normalny", fmt="md"):
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
        _macro = _macro_blocks(segs, ctx)
        risky_blocks = [b for b in _macro if b["c"] == "ryzyko"]
        kmcat = _km_by_category(segs)
        alert_types = sorted({a.get("typ") for a in (alerts or [])})
        H("## 1. Werdykt")
        H("")
        v = f"Trasa {_f(dist_km)} km, podjazdy {_f(elev.get('ascent_smoothed_m'),0)} m — profil "
        v += "umiarkowany. " if (elev.get("ascent_smoothed_m") or 0) < 800 else "wymagajacy. "
        if risky_blocks:
            v += "Odcinki do uwagi: " + ", ".join(f"km {_f(b['km_from'])}–{_f(b['km_to'])}" for b in risky_blocks[:3]) + " (piach/grade5). "
        else:
            v += "Brak twardych odcinkow ryzyka (nietagowane tracki = grunt/polna wg pokrycia terenu, przejezdne). "
        _trudna_km_v = kmcat.get(4, 0.0)
        if _trudna_km_v >= 3:
            v += f"Trudna/wolna ~{_f(_trudna_km_v)} km — wolniejsze tempo. "
        v += ("METEO: " + ", ".join(alert_types) + ". ") if alert_types else "Pogoda bez alarmow. "
        dem, rec = _water_rec(moving_h, peak_wbgt)
        v += f"Woda: {rec.split('(')[0].strip()}. Czas ~{_hms(total_h)}."
        H(v)
        H("")

        # ---------- 2 ----------
        mq = _modelq(conn)
        mass = float(fit["weight_kg"]) if (fit and fit.get("weight_kg")) else 100.0
        H("## 2. FitModel (ModelQ) — odniesienie tej jazdy do formy")
        H("")
        ftp = None
        if mq:
            ftp = mq.get("ftp_power_w")
            H("**Twoja forma (ModelQ / Xert):**")
            H("")
            H("| Parametr | Wartosc |")
            H("|---|---|")
            H(f"| FTP | {_f(ftp, 0)} W |")
            H(f"| W/kg (~{_f(mass, 0)} kg) | {_f((ftp / mass) if ftp else None, 2)} |")
            H(f"| LTP (prog tlenowy) | {_f(mq.get('ltp_power_w'), 0)} W |")
            H(f"| W′ (zapas beztlenowy) | {_f(mq.get('w_prime_kj'), 1)} kJ |")
            H(f"| Peak power | {_f(mq.get('peak_power_w'), 0)} W |")
            H(f"| Obciazenie / regeneracja | {_f(mq.get('training_load'), 0)} / {_f(mq.get('recovery_load'), 0)} |")
            H(f"| Snapshot ModelQ | {str(mq.get('snapshot_at'))[:10]} |")
        elif fit:
            ftp = fit.get("ftp_est_w")
            H("**Twoja forma (fitmodel_daily — brak ModelQ):**")
            H("")
            H("| Parametr | Wartosc |")
            H("|---|---|")
            H(f"| FTP_est | {_f(ftp, 0)} W |")
            H(f"| W/kg | {_f(fit.get('w_per_kg'), 2)} |")
        else:
            H("- forma: b/d")
        H("")
        cho = round((moving_h or 0) * 55) if moving_h else None
        if_est = 0.62
        ftp_mq, wprime_mq_kj = _modelq_form_for_xss(conn)
        xss_est = _estimate_route_xss(moving_h, dist_km, climbs, ftp_mq, wprime_mq_kj, mass, if_est)
        wprime_txt = "b/d"
        if climbs and ftp:
            steep = max(climbs, key=lambda e: float(e.get("avg_gradient_pct") or 0))
            pw = _climb_power(float(steep.get("avg_gradient_pct") or 0), 12.0, mass)
            if pw <= float(ftp):
                wprime_txt = f"pelna — podjazdy krotkie/lagodne (~{_f(pw, 0)} W < FTP), nie ruszasz zapasu"
            else:
                wprime_txt = f"czesciowa — najstromszy ~{_f(pw, 0)} W (> FTP o {_f(pw - float(ftp), 0)} W), krotkie dziury w W′"
        elif not climbs:
            wprime_txt = "pelna — trasa plaska, brak istotnych podjazdow"
        H("**Ta trasa kontra forma:**")
        H("")
        H("| Miara | Szacunek trasy | Ocena |")
        H("|---|---|---|")
        H(f"| Obciazenie (szac. XSS) | ~{xss_est if xss_est is not None else 'b/d'} ({_hms(moving_h)}, IF~{if_est}) | dlugi endurance, nie interwaly |")
        H(f"| Zapotrzebowanie CHO | ~{cho if cho is not None else 'b/d'} g (55 g/h) | tankuj 40–70 g/h |")
        H(f"| Zapotrzebowanie woda | ~{_f(dem)} l | pokryjesz z refilami |")
        H(f"| Rezerwa W′ na podjazdach | {wprime_txt} | — |")
        H("")
        H("**Fueling:** sniadanie weglowodanowe + w trasie 40–70 g CHO/h; na dlugiej jezdzie nie zjezdzaj na rezerwie.")
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
        H("## 3. Nawierzchnia — pewnosc i sklad (twarde dane vs interpretacja)")
        H("")
        def _kmlen(s):
            return max(0.0, float(s["km_to"]) - float(s["km_from"]))
        hard = [s for s in segs if s.get("cls") == "tagged_surface"]
        ttk = [s for s in segs if s.get("cls") == "inferred_tracktype"]
        infr = [s for s in segs if s.get("cls") not in ("tagged_surface", "inferred_tracktype")]
        tot = sum(_kmlen(s) for s in segs) or (dist_km or 1)
        hard_km = sum(_kmlen(s) for s in hard)
        ttk_km = sum(_kmlen(s) for s in ttk)
        infr_km = sum(_kmlen(s) for s in infr)
        p_hard, p_ttk, p_infr = 100 * hard_km / tot, 100 * ttk_km / tot, 100 * infr_km / tot

        def _bysurf(rs, top=None):
            d = {}
            for s in rs:
                d[s["surface"]] = d.get(s["surface"], 0.0) + _kmlen(s)
            items = sorted(d.items(), key=lambda kv: -kv[1])
            return items[:top] if top else items

        if segs:
            if fmt == "html":
                H("<!--RAW-->")
                H(_surface_svg(p_hard, p_ttk, p_infr, hard_km, ttk_km, infr_km, risky_blocks))
                H("<!--/RAW-->")
            else:
                H(f"Pewnosc: tag OSM **{round(p_hard)}%** · tracktype **{round(p_ttk)}%** · z terenu (wnioskowane) **{round(p_infr)}%**")
            H("")
            hard_txt = " · ".join(f"{_SURF_PL.get(k, k)} {_f(v)}" + (" ⚠" if k == "sand" else "")
                                  for k, v in _bysurf(hard, 6)) or "—"
            ttk_txt = " · ".join(f"{_SURF_PL.get(k, k)} {_f(v)}" for k, v in _bysurf(ttk, 4)) or "—"
            terr_ct = {}
            for sg in infr:
                c = _ctx_at_km(ctx, (sg["km_from"] + sg["km_to"]) / 2.0)
                t = (c.get("dominant_pl") if c else None) or "teren"
                terr_ct[t] = terr_ct.get(t, 0.0) + _kmlen(sg)
            terr_top = ", ".join(t for t, _ in sorted(terr_ct.items(), key=lambda kv: -kv[1])[:3]) or "pola/laki/las"
            H("| Zrodlo | km | udzial | Co to znaczy |")
            H("|---|---|---|---|")
            H(f"| █ tag OSM (fakt) | {_f(hard_km)} | {round(p_hard)}% | z mapy: {hard_txt} |")
            if ttk_km > 0:
                H(f"| ▓ tracktype grade1-4 | {_f(ttk_km)} | {round(p_ttk)}% | jakosc drogi z OSM → {ttk_txt}; przejezdne |")
            H(f"| ░ z pokrycia terenu | {_f(infr_km)} | {round(p_infr)}% | brak tagu → grunt/polna wg WorldCover ({terr_top}); latem mozliwy piach — wnioskowanie |")
            H("")
            if risky_blocks:
                zak = ", ".join(f"km {_f(b['km_from'])}–{_f(b['km_to'])}" for b in risky_blocks[:3])
                rkm = sum(b["km_to"] - b["km_from"] for b in risky_blocks)
                H(f"⚠ **Ryzyko:** piach/luzne ~{_f(rkm)} km ({zak}; tag OSM). Reszta „z terenu\" to przejezdna polna, nie piach.")
            else:
                H("✓ **Brak twardych odcinkow ryzyka** — nietagowany grunt = przejezdna polna, nie piach.")
            H("")
            H("_█ tag = fakt z mapy · ░ „z terenu\" = wnioskowanie z pokrycia (WorldCover), nie pomiar — "
              "latem/susza mozliwe piaszczyste fragmenty. Gdzie dokladnie co jest — sekcja 4 (strategia)._")
        else:
            H("- b/d (brak warstwy nawierzchni)")
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
                surf = _SURF_PL.get(b["surface"], b["surface"])
                if b.get("ma_wniosk") and b["c"] in ("gravel", "trudna"):
                    surf += ", cz. wnioskowana"
                H(f"| {_f(b['km_from'])}–{_f(b['km_to'])} | {surf} ({b['klasa']}) "
                  f"| {_profil_at(b['km_from'], b['km_to'], climbs)} | {_wind_at_km(meteo, mid)} "
                  f"| {_supply_in(b['km_from'], b['km_to'], supply)} | {b['tip']} |")
            H("")
            H("_Klasy: asfalt/szybko=utwardzone · gravel/szuter=dobry+zwykly szuter · trudna/wolna=trawa/mixed/grade4/polna · ryzyko=piach/grade5. Pewnosc nawierzchni (tag vs wnioskowane) w sek. 3._")
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
            H("| Odczuwalna (C) | " + " | ".join(_utci_repr(w.get("odczuwalna") or {}) for w in tab) + " |")
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
              "Strzalka: + tylny ↑ / − czolowy ↓. Odczuwalna = Steadman (temp + wilg + wiatr 10 m + slonce z Tmrt, cap +8 C), srednia okna.")
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
        if kmcat.get(4, 0.0) > 0:
            rows7.append(("Nawierzchnia", "—", "—", "info",
                          f"trudna/wolna ~{_f(kmcat.get(4, 0.0))} km (trawa/mixed/grade4/polna) — wolniej, po deszczu ciezko", "—"))
        _infr_km = sum(_kmlen(sg) for sg in infr)
        if _infr_km > 0:
            rows7.append(("Nawierzchnia", "—", "—", "info",
                          f"{_f(_infr_km)} km nietagowanych trackow — grunt/polna wg pokrycia terenu; "
                          "latem mozliwy piach (wnioskowanie, nie fakt)", "pola/laki/las"))
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
        try:
            weekday = _WD_EN[_dt.date.fromisoformat(date_str).weekday()]
        except Exception:
            weekday = "Saturday"
        seen = set()
        sup_rows = []
        for x in supply:
            km = x.get("km_on_route")
            if km is None:
                continue
            key = (round(float(km), 1), (x.get("name") or "")[:24])
            if key in seen:
                continue
            seen.add(key)
            eta, hf = _eta_at_km(meteo, float(km))
            openq, hrs = _oh_open_at(x.get("opening_hours"), weekday, hf)
            status = "otwarte" if openq is True else ("ZAMKNIETE" if openq is False else "godz.?")
            sup_rows.append((float(km), x.get("name"), eta or "b/d", status, hrs or "—"))
        sup_rows.sort(key=lambda r: r[0])
        H("**Zaopatrzenie — czy otwarte w Twoim oknie przejazdu (%s)?**" % weekday)
        H("")
        H("| km | Punkt | ETA | Status | Godziny |")
        H("|---|---|---|---|---|")
        for km, nm, eta, status, hrs in sup_rows[:14]:
            H(f"| {_f(km)} | {nm} | {eta} | {status} | {hrs} |")
        H("")
        H(f"Najdluzsza luka zaopatrzenia: ~{_f(_gap_km(resupply_km, dist_km))} km · Dane POI z dnia: {poi_date_s}")
        H("")
        H("_„godz.?\" = brak godzin w danych (czesto OSM). Miejscowosci -> patrz sekcja burz (schronienie), nie tu._")
        H("")
        atr = []
        for a in (poi.get("attraction") or []):
            d = a.get("distance_from_route_m")
            if d is not None and float(d) > 800:
                continue
            worth, rank = _attr_worth(a.get("name"))
            if not worth:
                continue
            atr.append((rank, a))
        atr.sort(key=lambda ra: (ra[0], ra[1].get("km_on_route") or 0))
        H("**Atrakcje warte zajazdu (kuracja wg typu/nazwy):**")
        H("")
        if atr:
            H("| km | Atrakcja | Miejscowosc | Typ | Odl. |")
            H("|---|---|---|---|---|")
            for rank, a in atr[:10]:
                km = a.get("km_on_route")
                H(f"| {_f(km)} | {a.get('name')} | {_nearest_town(float(km), towns) if km is not None else 'b/d'} "
                  f"| {_attr_type(a.get('name'))} | {_f(a.get('distance_from_route_m'), 0)} m |")
            H("")
            H("_Brak ocen Google w danych POI (zrodlo OSM) — kuracja wg typu/nazwy; pominieto bezimienne kaplice/krzyze. "
              "Prawdziwe oceny/rekomendacje wymagaja pobrania z Google Places (osobne zadanie)._")
        else:
            H("- Brak wyroznionych atrakcji w promieniu 800 m.")
        H("")

        # ---------- 9 ----------
        H("## 9. Sprzet (sugestia, nie wyrocznia)")
        H("")
        hard_pct = 100 * sum(_kmlen(s) for s in hard if s["surface"] in _HARD) / tot
        infr_pct = 100 * sum(_kmlen(s) for s in infr) / tot
        sand_tag = any(s["surface"] == "sand" for s in segs)
        if infr_pct >= 25 or sand_tag:
            tyre = ("Duzo luznego/nietagowanego gruntu (~{}%{}) -> **Thunder Burt 2.1 (Zipp 303 S XPLR)** — "
                    "wieksza objetosc i przyczepnosc na piachu/luznym. G-One tylko gdy wiesz, ze sucho i twardo."
                    ).format(round(infr_pct), " + tag piachu" if sand_tag else "")
        elif hard_pct >= 65:
            tyre = ("Przewaga asfaltu (~{}%) -> **G-One Pro RS (Zipp 303 S)** — szybsze i gladsze; "
                    "Thunder Burt zbedny.").format(round(hard_pct))
        else:
            tyre = ("Mieszanka asfalt + szuter -> **G-One Pro RS (Zipp 303 S)** uniwersalnie; "
                    "Thunder Burt gdy spodziewasz sie luznego/piachu.")
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
        H("| run_meteo_engine (Open-Meteo) | WBGT/odczuwalna(Steadman)/opad/wiatr | live |")
        H(f"| fitmodel_daily | forma | {fit.get('day') if fit else 'b/d'} |")
        H(f"| GeoNames + Google Places | miejscowosci/zaopatrzenie/atrakcje | {poi_date_s} |")
        H("| Nominatim | gmina/powiat/woj. | cache |")
        H("")
        H("_Liczby przyblizone. „Wnioskowane\" = brak tagu OSM (interpretacja z pokrycia terenu), nie brak przejezdnosci. "
          "Odczuwalna = reprezentatywna. Czas rekreacyjny ±15%._")

        return "\n".join(L)
    finally:
        conn.close()
