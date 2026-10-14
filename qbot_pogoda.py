"""Pogoda -- dane punktowe obok radaru: dom (z Trenera) i opad z modelu ICON-D2 co 15 min.

- model_point(lat, lon): Open-Meteo, models=icon_seamless (14.10.2026: samo icon_d2 zwracalo 400 'No data is available
  for this location' takze dla Warszawy; seamless = ICON-D2 gdzie jest, dalej ICON-EU), minutely_15=precipitation, na 12 h do przodu. ICON-D2 = siatka 2,2 km,
  liczony co 3 h, uwzglednia dane radarowe (asymilacja). Uzywany na osi czasu PO horyzoncie radaru (0-60/120 min).
  Cache w pamieci 10 min na punkt (zaokraglony do 0,05 st).
- home(): najczestszy punkt startu jazd (qbot_trener_engine.home_point, 60 ostatnich jazd, zaokr. 0,1 st).
Dok.: docs/POGODA_RADAR.md
"""
from __future__ import annotations

import datetime as _dtm
import json
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
URL = "https://api.open-meteo.com/v1/forecast"
HOURS = 12
_CACHE: dict = {}
CACHE_S = 600


def model_point(lat: float, lon: float, hours: int = HOURS) -> dict:
    """Opad godzinowy z modelu przydzielonego do opadu (przydzial wg sprawdzalnosci; wyprzedzenie 1/2/3 doby).
    14.10.2026: zastapil ICON seamless co 15 min -- os punktu korzysta z modelu, ktory u Ciebie najlepiej trafia opad."""
    key = (round(lat / 0.05) * 0.05, round(lon / 0.05) * 0.05, hours)
    hit = _CACHE.get(key)
    if hit and hit[0] > time.time() - CACHE_S:
        return hit[1]
    import qbot_pogoda_verif as PV
    asg = PV.przydzial(lat, lon)["opad"]
    mods = sorted({asg[d]["model"] for d in asg} | {"best_match"})
    try:   # E1: pobieranie przez rdzen danych qbot_wx (jeden klient Open-Meteo + cache)
        import qbot_wx as WX
        j = WX.forecast(lat, lon, "precipitation", models=mods, forecast_hours=hours + 1)
    except Exception as e:
        return {"status": "ERROR", "error": f"Model niedostepny: {type(e).__name__}"}
    h = j.get("hourly") or {}
    today = _dtm.datetime.now(TZ).date()
    pts = []
    for i, t in enumerate(h.get("time") or []):
        d = max(1, min(3, (_dtm.date.fromisoformat(t[:10]) - today).days or 1))
        # 14.10.2026: Open-Meteo 'precipitation' o czasie T = suma z godziny PRZED T -> punkt T (godzina T..T+1) bierze wartosc z T+1
        ser = h.get(f"precipitation_{asg[d]['model']}") or []
        mm = ser[i + 1] if i + 1 < len(ser) else None
        if mm is None:
            sb = h.get("precipitation_best_match") or []
            mm = sb[i + 1] if i + 1 < len(sb) else None
        if mm is None:
            continue
        pts.append({"iso": t, "t": t[11:16], "mm15": None, "mmh": round(mm, 1), "model": asg[d]["model"]})
    z = asg[1]
    opis = z["opis"] + (f" (trafnosc opadu {round(z['wartosc'] * 100)}%, {z['zakres']})" if z["wartosc"] is not None else "")
    res = {"status": "OK" if pts else "BRAK_DANYCH", "model": opis, "krok_min": 60, "punkty": pts}
    _CACHE[key] = (time.time(), res)
    return res

def home(cur) -> dict | None:
    """cur: kursor psycopg z wierszami jako dict."""
    import qbot_trener_engine as E
    p = E.home_point(cur)
    if not p:
        return None
    return {"lat": float(p[0]), "lon": float(p[1]), "zrodlo": "najczestszy start jazd (Trener)"}


# ---------------------------------------------------------------- warunki dla roweru (punkt, godzinowo)
HOURLY = ("temperature_2m,apparent_temperature,relative_humidity_2m,dew_point_2m,precipitation,snowfall,"
          "wind_speed_10m,wind_gusts_10m,wind_direction_10m,visibility,soil_temperature_0cm,weather_code,cloud_cover,is_day")
_CC: dict = {}


def _kier(deg):
    if deg is None:
        return None
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((deg + 22.5) // 45) % 8]


def conditions_point(lat: float, lon: float, hours: int = 24) -> dict:
    """Godzinowe warunki dla roweru (Open-Meteo best_match = w Europie ICON, 12 h wstecz + `hours` naprzod).

    Wyliczane flagi (proste, jawne progi -- do kalibracji):
      mgla: widocznosc < 1000 m; ograniczona < 4000 m
      oblodzenie: grunt (0 cm) <= 0,5 C ORAZ (opad/snieg w ostatnich 12 h lub punkt rosy >= temp. gruntu -> szron)
      nawierzchnia: suma opadu z 6 h wstecz >= 2 mm -> mokra/bloto; >= 0,3 mm -> wilgotna
      rosa: temp - punkt rosy < 2 C
    Wiatr w m/s.
    """
    key = (round(lat / 0.05) * 0.05, round(lon / 0.05) * 0.05, hours)
    hit = _CC.get(key)
    if hit and hit[0] > time.time() - CACHE_S:
        return hit[1]
    import qbot_pogoda_verif as PV
    asg = PV.przydzial(lat, lon)
    mods = sorted({asg[p][d]["model"] for p in asg for d in asg[p]} | {"best_match"})
    try:   # E1: pobieranie przez rdzen danych qbot_wx
        import qbot_wx as WX
        j = WX.forecast(lat, lon, HOURLY, models=mods, past_hours=12, forecast_hours=hours + 1)
    except Exception as e:
        return {"status": "ERROR", "error": f"Prognoza warunkow niedostepna: {type(e).__name__}"}
    hr = j.get("hourly") or {}
    tt = hr.get("time") or []
    today = _dtm.datetime.now(TZ).date()
    lead = [max(1, min(3, (_dtm.date.fromisoformat(t[:10]) - today).days or 1)) for t in tt]
    PMAP = {"temperature_2m": "temp", "apparent_temperature": "temp", "relative_humidity_2m": "temp", "dew_point_2m": "temp",
            "wind_speed_10m": "wiatr", "wind_direction_10m": "wiatr", "wind_gusts_10m": "poryw", "precipitation": "opad", "snowfall": "opad"}
    h = {}
    for var in HOURLY.split(","):
        bm = hr.get(f"{var}_best_match") or [None] * len(tt)
        par = PMAP.get(var)
        col = []
        for i in range(len(tt)):
            x = (hr.get(f"{var}_{asg[par][lead[i]]['model']}") or [None] * len(tt))[i] if par else None
            col.append(x if x is not None else bm[i])
        h[var] = col
    g = lambda k, i: (h.get(k) or [None] * len(tt))[i]
    import datetime as _dt
    now = _dt.datetime.now(TZ).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    rows = []
    for i, t in enumerate(tt):
        prec = [g("precipitation", k) or 0 for k in range(max(0, i - 12), i)]
        snow = [g("snowfall", k) or 0 for k in range(max(0, i - 12), i)]
        p6 = sum((g("precipitation", k) or 0) for k in range(max(0, i - 6), i + 1))
        T, Td, Ts, vis = g("temperature_2m", i), g("dew_point_2m", i), g("soil_temperature_0cm", i), g("visibility", i)
        lod = 0
        if Ts is not None and Ts <= 0.5:
            wet = sum(prec) > 0.1 or sum(snow) > 0 or (g("precipitation", i) or 0) > 0
            frost = Td is not None and Td >= Ts
            lod = 3 if (wet and Ts <= -0.5) else 2 if (wet or frost) else 1
        mgla = None if vis is None else (2 if vis < 1000 else 1 if vis < 4000 else 0)
        naw = 2 if p6 >= 2 else 1 if p6 >= 0.3 else 0
        rosa = None if (T is None or Td is None) else round(T - Td, 1)
        # opad, snieg i porywy z Open-Meteo dotycza GODZINY POPRZEDZAJACEJ (qbot_wx.PREV_HOUR) -> wiersz T (godzina T..T+1) bierze wartosc z T+1.
        # UWAGA: komentarzy NIE wstawiac w srodek tego slownika (14.10 dwa razy wyciely pola) -- pilnuje tests/test_pogoda_conditions.py
        rows.append({"iso": t, "t": t[11:16], "przeszlosc": _dt.datetime.fromisoformat(t) < now,
                     "temp": T, "odcz": g("apparent_temperature", i), "rh": g("relative_humidity_2m", i), "rosa_pkt": Td,
                     "opad": g("precipitation", i + 1) if i + 1 < len(tt) else None, "snieg": g("snowfall", i + 1) if i + 1 < len(tt) else None, "wiatr": g("wind_speed_10m", i),
                     "porywy": g("wind_gusts_10m", i + 1) if i + 1 < len(tt) else None, "kier": g("wind_direction_10m", i), "skad": _kier(g("wind_direction_10m", i)),
                     "widocznosc": vis, "grunt": Ts, "kod": g("weather_code", i), "chmury": g("cloud_cover", i), "dzien": g("is_day", i),
                     "mgla": mgla, "lod": lod, "nawierzchnia": naw, "zapas_rosy": rosa})
    try:   # szansa opadu z zespolu ICON-EU-EPS dla godziny T..T+1 (do wizualizacji Warunkow)
        import qbot_pogoda_okno as _PO
        _pr = _PO._ens_prob(lat, lon)
        for _r in rows:
            _r["szansa"] = _pr.get(_r["iso"][:13])
    except Exception:
        pass
    res = {"status": "OK" if rows else "BRAK_DANYCH", "model": "przydzial automatyczny wg sprawdzalnosci", "godziny": rows,
           "zrodla": {p: asg[p][1] for p in asg}, "przydzial": asg}
    _CC[key] = (time.time(), res)
    return res


def kwadraty(share: str = "") -> dict:
    """Wszystkie zdobyte kwadraty z14 (StatsHunters) -- [x, y]. Strona rysuje te w widoku.
    share: STATSHUNTERS_SHARE_ID (qbot_web podaje z _env(), jak route_tiles)."""
    import os as _os
    from tools.tile_store import fetch_tiles, get_tile_set
    share = share or _os.getenv("STATSHUNTERS_SHARE_ID", "")
    if not share:
        try:
            for line in open("/opt/qbot/app/.env"):
                if line.startswith("STATSHUNTERS_SHARE_ID="):
                    share = line.strip().split("=", 1)[1]
        except Exception:
            pass
    if not share:
        return {"status": "BRAK_DANYCH", "error": "brak STATSHUNTERS_SHARE_ID", "zoom": 14, "kwadraty": []}
    td = fetch_tiles(share)
    owned = sorted(get_tile_set(td.get("tiles", [])))
    return {"status": "OK" if not td.get("_error") else "BLAD", "error": td.get("_error"), "zoom": 14,
            "kwadraty": [[x, y] for x, y in owned]}


# ---------------------------------------------------------------- charakter dnia (14.10.2026, po ulewie z "niczego")
# Chmury w niestabilnym powietrzu rosna na miejscu w 20-40 min -- radar ich wczesniej nie widzi, przesuwanie obrazu nie przewidzi.
# Etykieta z prognozy chwiejnosci (Open-Meteo best_match, godz. 8-20): CAPE [J/kg] = energia wznoszenia, LI = lifted index
# (< 0 = chwiejnie). Progi skalibrowane na 11-16.10.2026: 14.10 (ulewy 39 dBZ) CAPE 210 / LI 0,3; pozostale dni CAPE <= 80, LI >= 0,4.
CH_PRZELOT = (150, 1.5)    # CAPE >= i LI <= -> przelotne opady
CH_BURZA = (600, -1.0)     # CAPE >= i LI <= -> burzowo
_CH: dict = {}


def charakter_dni(lat: float, lon: float, dni: int = 3) -> dict:
    key = (round(lat, 1), round(lon, 1))
    hit = _CH.get(key)
    if hit and hit[0] > time.time() - 1800:
        return hit[1]
    try:   # E1: rdzen danych qbot_wx
        import qbot_wx as WX
        h = WX.forecast(lat, lon, "cape,lifted_index", forecast_days=dni).get("hourly") or {}
    except Exception as e:
        return {"status": "ERROR", "error": f"{type(e).__name__}"}
    out = {}
    for i, t in enumerate(h.get("time") or []):
        hh = int(t[11:13])
        if not 8 <= hh <= 20:
            continue
        c, li = h["cape"][i] or 0, h["lifted_index"][i]
        x = out.setdefault(t[:10], {"dzien": t[:10], "cape": 0, "li": 99.0, "godz": []})
        x["cape"] = max(x["cape"], c); x["li"] = min(x["li"], li if li is not None else 99.0)
        if c >= 100 and (li is None or li <= 2):
            x["godz"].append(hh)
    dd = []
    for x in out.values():
        typ = "burzowy" if x["cape"] >= CH_BURZA[0] and x["li"] <= CH_BURZA[1] else "przelotny" if x["cape"] >= CH_PRZELOT[0] and x["li"] <= CH_PRZELOT[1] else "stabilny"
        okno = f"{min(x['godz']):02d}–{max(x['godz']) + 1:02d}" if x["godz"] else None
        opis = {"burzowy": "⛈ Dzień burzowy", "przelotny": "🌦 Dzień przelotnych opadów", "stabilny": "Pogoda stabilna"}[typ] + (f" (najbardziej ok. {okno})" if okno and typ != "stabilny" else "")
        if typ != "stabilny":
            opis += ": chmury mogą wyrosnąć na miejscu w 20–40 min — czysty radar nie gwarantuje suchej jazdy" + ("; możliwe ulewy, grad, porywy." if typ == "burzowy" else ".")
        dd.append({"dzien": x["dzien"], "typ": typ, "cape": round(x["cape"]), "li": round(x["li"], 1), "okno": okno, "opis": opis})
    res = {"status": "OK", "dni": dd, "zrodlo": "Open-Meteo (CAPE, lifted index), godz. 8–20"}
    _CH[key] = (time.time(), res)
    return res


# ---------------------------------------------------------------- warunki na kolejne dni (14.10.2026)
DNI_MAX = 4          # dzis + 4 dni: zasieg ICON-EU (mapy) i zespolu ICON-EU-EPS; dalej tylko modele globalne -- falszywa precyzja


def conditions_day(lat: float, lon: float, d: int, od: int = 6, do: int = 22) -> dict:
    """Warunki godzinowe na dzien kalendarzowy dzis+d (1..DNI_MAX), godz. od..do, + pewnosc ze sprawdzalnosci (1-3 doba)."""
    d = max(1, min(int(d), DNI_MAX))
    w = conditions_point(lat, lon, hours=24 * (d + 1) + 2)
    if w.get("status") != "OK":
        return w
    day = (_dtm.datetime.now(TZ) + _dtm.timedelta(days=d)).date().isoformat()
    rows = [r for r in w["godziny"] if r["iso"][:10] == day and od <= int(r["iso"][11:13]) <= do]
    asg = w.get("przydzial") or {}
    ld = min(d, 3)
    val = lambda p: ((asg.get(p) or {}).get(ld) or {}).get("wartosc")
    t, wi, op = val("temp"), val("wiatr"), val("opad")
    pl = lambda x, n=1: "–" if x is None else str(round(x, n)).replace(".", ",")
    if d <= 3:
        poziom = "wysoka" if d == 1 else "średnia"
        opis = (f"wg sprawdzalności {ld}. doby u Ciebie: błąd temperatury ok. {pl(t)} °C, wiatru ok. {pl(wi)} m/s"
                + (f", trafność opadu {round(op * 100)}%" if op is not None else ""))
    else:
        poziom = "orientacyjna"
        opis = f"{d + 1}. dzień prognozy — pewność wyraźnie mniejsza; sprawdzalności tak dalekich prognoz jeszcze nie mierzymy"
    return dict(w, godziny=rows, dzien=day, pewnosc={"poziom": poziom, "opis": opis, "temp_blad": t, "wiatr_blad": wi, "opad_trafnosc": op})
