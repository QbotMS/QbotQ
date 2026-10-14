"""Okno jazdy (Pogoda, krok 2): przesunac jazde czy moknac? Dok.: docs/POGODA_OKNO.md

Jazda: z kalendarza Trenera (trainer_session, sport=rower, status=plan) albo zadana (dzien, start, czas). Kandydaci startu:
co STEP_MIN min w oknach Trenera na rower (qbot_trener_engine.day_info -> win['rower']), bez kolizji z zajetosciami i innymi
sesjami dnia; zawsze + godzina z planu. Pogoda dla punktu (dom / zadany): warunki z przydzialu modeli wg sprawdzalnosci
(qbot_pogoda.conditions_point), szansa opadu z zespolu ICON-EU-EPS (Open-Meteo Ensemble, odsetek wariantow >= 0,2 mm/h),
dla startow w najblizszej godzinie -- radar (qbot_radar.nowcast_point). Progi = Trener (P(ov, 'wx.*')), wiatr w m/s.
Ocena 0-100 = 100 - 10 x kara; kara: deszcz na jazde, szansa opadu, porywy ponad prog, oblodzenie, mgla, jazda po zmroku,
mokra nawierzchnia, chlod / upal. Uwagi prostym jezykiem.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
STEP_MIN = 30
ENS = "https://ensemble-api.open-meteo.com/v1/ensemble"
FC = "https://api.open-meteo.com/v1/forecast"
EPS_PROG = 0.2
USER = "admin"
_C: dict = {}


def _get_json(url: str, t: float = 15):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "QBot/1.0"}), timeout=t) as r:
        return json.load(r)


def _ens_prob(lat: float, lon: float) -> dict:
    """Szansa opadu z zespolu ICON-EU-EPS dla godziny HH..HH+1 -- E1: z rdzenia danych qbot_wx (jedno zrodlo dla Pogody i Okna jazdy)."""
    import qbot_wx as WX
    return WX.ens_prob(lat, lon, prog=EPS_PROG)


def _sun(lat: float, lon: float) -> dict:
    key = ("sun", round(lat, 1), round(lon, 1), dt.date.today())
    if key in _C:
        return _C[key][1]
    q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "daily": "sunrise,sunset", "forecast_days": 4, "timezone": "Europe/Warsaw"})
    d = (_get_json(FC + "?" + q).get("daily") or {})
    out = {day: (dt.datetime.fromisoformat(a), dt.datetime.fromisoformat(b)) for day, a, b in zip(d.get("time", []), d.get("sunrise", []), d.get("sunset", []))}
    _C[key] = (time.time(), out)
    return out


def rides(cur, dni: int = 3, user: str = USER) -> list:
    today = dt.datetime.now(TZ).date()
    cur.execute("""SELECT id, day, name, start_time, dur_min FROM qbot_v2.trainer_session WHERE username=%s AND sport='rower'
                   AND status='plan' AND day BETWEEN %s AND %s AND start_time IS NOT NULL ORDER BY day, start_time""",
                (user, today, today + dt.timedelta(days=dni)))
    out = []
    for r in cur.fetchall():
        r = r if isinstance(r, dict) else dict(zip(("id", "day", "name", "start_time", "dur_min"), r))
        out.append({"id": r["id"], "dzien": r["day"].isoformat(), "nazwa": r["name"], "start": str(r["start_time"])[:5], "czas_min": r["dur_min"]})
    return out


def _hm(s: str) -> int:
    h, m = s.split(":")[:2]
    return int(h) * 60 + int(m)


def _t2(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def window(cur, lat: float, lon: float, day: dt.date, start: str, dur: int, ride_id=None, user: str = USER) -> dict:
    import qbot_pogoda as PG
    import qbot_trener_engine as E
    now = dt.datetime.now(TZ)
    today = now.date()
    ctx = E.build_context(cur, user, E.monday(day), today)
    ov = ctx.get("ov") or {}
    info = E.day_info(ctx, day)
    cur.execute("SELECT id, start_time, dur_min FROM qbot_v2.trainer_session WHERE username=%s AND day=%s AND status NOT IN ('skip') AND start_time IS NOT NULL",
                (user, day))
    others = []
    for r in cur.fetchall():
        r = r if isinstance(r, dict) else dict(zip(("id", "start_time", "dur_min"), r))
        if r["id"] != ride_id:
            a = _hm(str(r["start_time"])); others.append((a, a + int(r["dur_min"] or 0)))
    busy = [(a, b) for a, b, *_ in info["busy"]] + others
    plan_m = _hm(start)
    cand = set([plan_m])
    for a, b in info["win"].get("rower", [E.DEFAULT_WIN]):
        s = ((a + STEP_MIN - 1) // STEP_MIN) * STEP_MIN
        while s + dur <= b:
            if not any(s < y and s + dur > x for x, y in busy):
                cand.add(s)
            s += STEP_MIN
    if day == today:
        nm = now.hour * 60 + now.minute + 10
        cand = {c for c in cand if c >= nm or c == plan_m}
    w = PG.conditions_point(lat, lon, hours=96)
    hrs = {r["iso"][:13]: r for r in (w.get("godziny") or [])}
    prob = _ens_prob(lat, lon)
    sun = _sun(lat, lon).get(day.isoformat())
    radar = {}
    if day == today:
        try:
            import qbot_radar as RAD
            n = RAD.nowcast_point(lat, lon, lead_max=60)
            for p in n.get("prognoza") or []:
                radar[p["t"]] = p
        except Exception:
            pass
    P = lambda k: E.P(ov, k)
    starty = []
    for s in sorted(cand):
        e = s + dur
        rain = pmax = 0.0; gust = wind = 0.0; tmin, tmax, omin = 99.0, -99.0, 99.0; lod = mg = naw = 0; dark = 0; zr_radar = False; brak = False
        m = s
        while m < e:
            seg = min(60 - m % 60, e - m)
            hkey = f"{day.isoformat()}T{(m // 60) % 24:02d}"
            h = hrs.get(hkey)
            if not h:
                brak = True; m += seg; continue
            mmh = h.get("opad") or 0.0
            rk = _t2(m - m % 5)
            if rk in radar and radar[rk].get("udzial") is not None:      # najblizsza godzina: radar zamiast modelu
                mmh = radar[rk]["mmh"] if radar[rk]["udzial"] >= 0.5 else 0.0; zr_radar = True
            rain += mmh * seg / 60
            pmax = max(pmax, prob.get(hkey, 0.0))
            gust = max(gust, h.get("porywy") or 0); wind = max(wind, h.get("wiatr") or 0)
            if h.get("temp") is not None:
                tmin, tmax = min(tmin, h["temp"]), max(tmax, h["temp"])
            if h.get("odcz") is not None:
                omin = min(omin, h["odcz"])
            lod, mg, naw = max(lod, h.get("lod") or 0), max(mg, h.get("mgla") or 0), max(naw, h.get("nawierzchnia") or 0)
            if sun:
                t0 = dt.datetime.combine(day, dt.time(m // 60 % 24, m % 60))
                if t0 < sun[0] or t0 >= sun[1]:
                    dark += seg
            m += seg
        uw, kara = [], 0.0
        if rain >= 0.3:
            uw.append(f"deszcz ok. {rain:.1f} mm".replace(".", ",")); kara += rain * 3
        # 14.10.2026 (decyzja Michala po ulewie 14:50 przy ocenie 85/100): szansa >= progu Trenera (40%) karze mocno -- 40% -> ok. 76,
        # 75% -> ok. 55, 100% -> 40 (deterministyczne modele czesto nie widza przelotnych opadow, zespol tak)
        if pmax >= P("wx.rain_prob") / 100:
            uw.append(f"szansa opadu {round(pmax * 100)}%"); kara += pmax * 6
        elif pmax >= 0.2:
            kara += pmax * 2
        if gust >= P("wx.gust_ms"):
            uw.append(f"porywy do {gust:.0f} m/s"); kara += (gust - P("wx.gust_ms")) * 0.6 + 1
        elif wind >= P("wx.wind_ms"):
            uw.append(f"wiatr do {wind:.0f} m/s"); kara += 0.8
        if lod >= 2:
            uw.append("ryzyko oblodzenia"); kara += 3
        if mg == 2:
            uw.append("mgła"); kara += 1.5
        if naw >= 2:
            uw.append("mokro, błoto"); kara += 1
        elif naw == 1:
            kara += 0.4
        if dark:
            uw.append(f"{dark} min po zmroku"); kara += dark / 20
        if omin < P("wx.cold_long_c") and omin < 99:
            uw.append(f"odczuwalna {omin:.0f}°C"); kara += (P("wx.cold_long_c") - omin) * 0.2
        if tmax > P("wx.heat_c") and tmax > -99:
            uw.append(f"upał {tmax:.0f}°C"); kara += (tmax - P("wx.heat_c")) * 0.5
        starty.append({"start": _t2(s), "koniec": _t2(e), "plan": s == plan_m, "ocena": max(0, min(100, round(100 - 10 * kara))),
                       "deszcz_mm": round(rain, 1), "szansa": round(pmax, 2), "poryw": round(gust, 1), "wiatr": round(wind, 1),
                       "temp": [None if tmin == 99 else round(tmin, 1), None if tmax == -99 else round(tmax, 1)],
                       "odcz_min": None if omin == 99 else round(omin, 1), "lod": lod, "mgla": mg, "nawierzchnia": naw, "po_zmroku_min": dark,
                       "radar": zr_radar, "brak_danych": brak, "uwagi": uw or ["dobre warunki"]})
    plan = next((x for x in starty if x["plan"]), None)
    ok = [x for x in starty if not x["brak_danych"]]
    best = lambda L: max(L, key=lambda x: (x["ocena"], -abs(_hm(x["start"]) - plan_m))) if L else None
    return {"status": "OK", "dzien": day.isoformat(), "start": start, "czas_min": dur, "punkt": [lat, lon],
            "okna_rower": [[_t2(a), _t2(b)] for a, b in info["win"].get("rower", [])], "zajete": [[_t2(a), _t2(b)] for a, b in busy],
            "slonce": [sun[0].strftime("%H:%M"), sun[1].strftime("%H:%M")] if sun else None,
            "plan": plan, "najlepszy_wczesniej": best([x for x in ok if _hm(x["start"]) < plan_m]),
            "najlepszy_pozniej": best([x for x in ok if _hm(x["start"]) > plan_m]), "najlepszy": best(ok), "starty": starty,
            "progi": {"wiatr_ms": P("wx.wind_ms"), "poryw_ms": P("wx.gust_ms"), "szansa_proc": P("wx.rain_prob")},
            "zrodla": "warunki: modele wg sprawdzalności; szansa opadu: ICON-EU-EPS (40 wariantów); najbliższa godzina: radar"}
