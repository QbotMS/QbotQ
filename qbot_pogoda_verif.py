"""Sprawdzalnosc modeli pogody (Pogoda, etap 1). Dok.: docs/POGODA_SPRAWDZALNOSC.md

Pomiary: IMGW synop -- archiwum miesieczne (terminowe/synop/RRRR/RRRR_MM_s.zip, co godzine UTC: temp, wiatr, poryw, wilg.,
punkt rosy, widzialnosc, opad 6 h) + biezace API /api/data/synop (temp, wiatr, wilg.; co godzine).
Prognozy: Open-Meteo Previous Runs API -- dla kazdej godziny prognoza wydana 1/2/3 doby wczesniej (zmienne *_previous_dayN),
modele: MODELS. Rozliczenie: score() -- blad sredni (MAE) i znak (bias) temp./wiatru/porywow, opad 6 h: trafienie / falszywy
alarm / przegapione (prog OPAD_PROG mm). Widok 'u Ciebie' = stacje w promieniu, waga 1/(1+d/50 km); 'Polska' = wszystkie.
Klucz stacji = znormalizowana nazwa (archiwum ma kody 9-cyfrowe, API -- WMO 12xxx; laczy je nazwa).
Archiwum i API IMGW: godziny UTC. Opad 6 h (WO6G) w archiwum stoi przy 02/08/14/20 UTC -- okno modelu dobiera OPAD_LAG_H.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import re
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

PL = ZoneInfo("Europe/Warsaw")

UA = {"User-Agent": "QBot/1.0 (sprawdzalnosc)"}
IMGW = "https://danepubliczne.imgw.pl"
ARCH = IMGW + "/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/terminowe/synop/{y}/{y}_{m:02d}_s.zip"
PREV = "https://previous-runs-api.open-meteo.com/v1/forecast"
MODELS = {  # id Open-Meteo -> opis
    "dmi_harmonie_arome_europe": "HARMONIE DMI 2 km",
    "knmi_harmonie_arome_europe": "HARMONIE KNMI 5,5 km",
    "icon_eu": "ICON-EU 7 km",
    "ecmwf_ifs025": "ECMWF IFS 25 km",
    "gfs_global": "GFS 13-25 km",
}
DAYS = (1, 2, 3)
OPAD_PROG = 0.5   # mm/6 h -- "padalo"
OPAD_LAG_H = 0    # przesuniecie konca okna 6 h modelu wzgledem godziny pomiaru (test w log)
# synop (API) -> nazwa stacji z wspolrzednymi w /api/data/meteo (lotniska itd.)
ALIAS = {"GORZOW": "GORZOWWIELKOPOLSKI", "KATOWICE": "KATOWICEMUCHOWIEC", "KIELCE": "KIELCESUKOW",
         "KOLOBRZEG": "KOLOBRZEGDZWIRZYNO", "KRAKOW": "KRAKOWBALICE", "LUBLIN": "LUBLINRADAWIEC", "LODZ": "LODZLUBLINEK",
         "POZNAN": "POZNANLAWICA", "RESKO": "RESKOSMOLSKO", "RZESZOW": "RZESZOWJASIONKA", "WARSZAWA": "WARSZAWAOKECIE",
         "GDANSK": "GDANSKSWIBNO", "WROCLAW": "WROCLAWSTRACHOWICE", "ELBLAG": "ELBLAGMILEJEWO"}   # WMO 12155/12424/12160
# archiwum (nazwa w s_t_*.csv) -> klucz stacji, gdy nazwy sie roznia
ARCH_ALIAS = {"WARSZAWA": "WARSZAWAOKECIE", "LODZ": "LODZLUBLINEK"}
FIXED = {"KOLO": (52.20, 18.66)}   # brak w /api/data/meteo


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").upper().replace("Ł", "L")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z]", "", s)


def _get(u: str, t: float = 60) -> bytes:
    import qbot_wx as WX
    if u.startswith(WX.ALLOWED):      # E4.4: zapytania Open-Meteo przez wspolny transport (archiwa IMGW -- bez zmian)
        return json.dumps(WX.get_url(u, timeout=t, ttl=3600, ua=UA.get("User-Agent", "QBot/1.0"))).encode("utf-8")
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
        return r.read()


DDL = """
CREATE TABLE IF NOT EXISTS qbot_v2.pogoda_stacja (klucz text PRIMARY KEY, nazwa text, wmo text, lat double precision,
  lon double precision, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS qbot_v2.pogoda_obs (stacja text, ts timestamptz, temp real, wiatr real, poryw real, rh real,
  rosa real, opad6 real, widz real, zrodlo text, PRIMARY KEY (stacja, ts));
CREATE TABLE IF NOT EXISTS qbot_v2.pogoda_prog (stacja text, model text, wyprz smallint, ts timestamptz, temp real,
  wiatr real, poryw real, opad real, PRIMARY KEY (stacja, model, wyprz, ts));
CREATE INDEX IF NOT EXISTS pogoda_prog_ts ON qbot_v2.pogoda_prog (ts);
"""


def ensure_schema(cur) -> None:
    cur.execute(DDL)


# ---------------------------------------------------------------- stacje
def sync_stations(cur) -> dict:
    syn = json.loads(_get(IMGW + "/api/data/synop"))
    met = json.loads(_get(IMGW + "/api/data/meteo"))
    idx = {}
    for m in met:
        if m.get("lat") and m.get("lon"):
            idx.setdefault(norm(m["nazwa_stacji"]), (float(m["lat"]), float(m["lon"])))
    ok, brak = 0, []
    for s in syn:
        n = norm(s["stacja"]); k = ALIAS.get(n, n)
        ll = idx.get(k) or FIXED.get(n)
        if not ll:
            brak.append(s["stacja"]); continue
        cur.execute("""INSERT INTO qbot_v2.pogoda_stacja (klucz, nazwa, wmo, lat, lon) VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (klucz) DO UPDATE SET nazwa=EXCLUDED.nazwa, wmo=EXCLUDED.wmo, lat=EXCLUDED.lat,
                       lon=EXCLUDED.lon, updated_at=now()""", (k, s["stacja"], s["id_stacji"], ll[0], ll[1]))
        ok += 1
    return {"stacji": ok, "bez_wspolrzednych": brak}


def stations(cur) -> list:
    cur.execute("SELECT klucz, nazwa, wmo, lat, lon FROM qbot_v2.pogoda_stacja ORDER BY klucz")
    return [dict(zip(("klucz", "nazwa", "wmo", "lat", "lon"), r)) if not isinstance(r, dict) else r for r in cur.fetchall()]


# ---------------------------------------------------------------- pomiary
def _f(x):
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def obs_archive(cur, year: int, month: int) -> dict:
    """Miesiac z archiwum IMGW (UTC, co godzine). Kolumny wg s_t_format.txt (indeksy od 0)."""
    keys = {s["klucz"] for s in stations(cur)}
    z = zipfile.ZipFile(io.BytesIO(_get(ARCH.format(y=year, m=month), 120)))
    name = [i.filename for i in z.infolist() if i.filename.lower().startswith("s_t_")][0]
    rows, nieznane = 0, set()
    for r in csv.reader(io.StringIO(z.read(name).decode("cp1250", "replace"))):
        k = ARCH_ALIAS.get(norm(r[1]), norm(r[1]))
        if k not in keys:
            nieznane.add(r[1]); continue
        # 14.10.2026: godziny w archiwum = UTC (zweryfikowane: prognozy ICON-EU/Open-Meteo pokrywaja sie bez przesuniecia;
        # wariant 'czas polski' dawal wzrost temp. przed wschodem slonca). Opad 6 h IMGW wpisuje o 02/08/14/20 UTC.
        ts = dt.datetime(int(r[2]), int(r[3]), int(r[4]), int(r[5]), tzinfo=dt.timezone.utc)
        wid = _f(r[19]) if _f(r[19]) is not None else _f(r[17])
        cur.execute("""INSERT INTO qbot_v2.pogoda_obs (stacja, ts, temp, wiatr, poryw, rh, rosa, opad6, widz, zrodlo)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'archiwum') ON CONFLICT (stacja, ts) DO UPDATE SET
                       temp=EXCLUDED.temp, wiatr=EXCLUDED.wiatr, poryw=EXCLUDED.poryw, rh=EXCLUDED.rh, rosa=EXCLUDED.rosa,
                       opad6=EXCLUDED.opad6, widz=EXCLUDED.widz, zrodlo='archiwum'""",
                    (k, ts, _f(r[29]), _f(r[25]), _f(r[27]), _f(r[37]), _f(r[39]), _f(r[48]), wid))
        rows += 1
    return {"miesiac": f"{year}-{month:02d}", "wierszy": rows, "pominiete_stacje": sorted(nieznane)}


def obs_live(cur) -> dict:
    """Biezaca godzina z API (godzina_pomiaru = UTC). Nie nadpisuje danych z archiwum."""
    n = 0
    for s in json.loads(_get(IMGW + "/api/data/synop")):
        k = ALIAS.get(norm(s["stacja"]), norm(s["stacja"]))
        d = dt.date.fromisoformat(s["data_pomiaru"])
        ts = dt.datetime(d.year, d.month, d.day, int(s["godzina_pomiaru"]), tzinfo=dt.timezone.utc)
        cur.execute("""INSERT INTO qbot_v2.pogoda_obs (stacja, ts, temp, wiatr, rh, zrodlo)
                       SELECT %s,%s,%s,%s,%s,'api' WHERE EXISTS (SELECT 1 FROM qbot_v2.pogoda_stacja WHERE klucz=%s)
                       ON CONFLICT (stacja, ts) DO NOTHING""",
                    (k, ts, _f(s["temperatura"]), _f(s["predkosc_wiatru"]), _f(s["wilgotnosc_wzgledna"]), k))
        n += cur.rowcount
    return {"nowych": n}


# ---------------------------------------------------------------- prognozy (Previous Runs)
def forecasts(cur, start: dt.date, end: dt.date, models=None, only=None) -> dict:
    st = [s for s in stations(cur) if not only or s["klucz"] in only]
    out = {}
    for model in (models or MODELS):
        hv = []
        for d in DAYS:
            hv += [f"temperature_2m_previous_day{d}", f"wind_speed_10m_previous_day{d}",
                   f"wind_gusts_10m_previous_day{d}", f"precipitation_previous_day{d}"]
        q = urllib.parse.urlencode({"latitude": ",".join(f"{s['lat']:.4f}" for s in st),
                                    "longitude": ",".join(f"{s['lon']:.4f}" for s in st),
                                    "hourly": ",".join(hv), "models": model, "start_date": start.isoformat(),
                                    "end_date": end.isoformat(), "wind_speed_unit": "ms", "timezone": "UTC"})
        try:
            data = json.loads(_get(PREV + "?" + q, 120))
        except Exception as e:
            out[model] = f"BLAD {type(e).__name__}: {e}"[:200]; continue
        data = data if isinstance(data, list) else [data]
        n = 0
        for s, js in zip(st, data):
            h = js.get("hourly") or {}
            tt = h.get("time") or []
            off = dt.timedelta(seconds=int(js.get("utc_offset_seconds") or 0))   # 14.10: bez tego prognozy wychodzily o 2 h przesuniete
            for d in DAYS:
                T, W, G, P = (h.get(f"{v}_previous_day{d}") or [None] * len(tt)
                              for v in ("temperature_2m", "wind_speed_10m", "wind_gusts_10m", "precipitation"))
                for i, t in enumerate(tt):
                    if T[i] is None and W[i] is None and P[i] is None:
                        continue
                    ts = (dt.datetime.fromisoformat(t) - off).replace(tzinfo=dt.timezone.utc)
                    cur.execute("""INSERT INTO qbot_v2.pogoda_prog (stacja, model, wyprz, ts, temp, wiatr, poryw, opad)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (stacja, model, wyprz, ts) DO UPDATE SET
                                   temp=EXCLUDED.temp, wiatr=EXCLUDED.wiatr, poryw=EXCLUDED.poryw, opad=EXCLUDED.opad""",
                                (s["klucz"], model, d, ts, T[i], W[i], G[i], P[i]))
                    n += 1
        out[model] = n
    return out


# ---------------------------------------------------------------- rozliczenie
def _km(a, b, c, d):
    p = math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def score(cur, dni: int = 30, lat: float | None = None, lon: float | None = None, promien_km: float = 100) -> dict:
    st = stations(cur)
    if lat is not None:
        wagi = {s["klucz"]: 1 / (1 + _km(lat, lon, s["lat"], s["lon"]) / 50) for s in st
                if _km(lat, lon, s["lat"], s["lon"]) <= promien_km}
    else:
        wagi = {s["klucz"]: 1.0 for s in st}
    if not wagi:
        return {"status": "BRAK_STACJI"}
    od = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dni)
    cur.execute("""SELECT p.stacja, p.model, p.wyprz, p.ts, p.temp AS pt, p.wiatr AS pw, p.poryw AS pg, p.opad AS pp,
                          o.temp AS ot, o.wiatr AS ow, o.poryw AS og, o.opad6 AS oo
                   FROM qbot_v2.pogoda_prog p JOIN qbot_v2.pogoda_obs o ON o.stacja = p.stacja AND o.ts = p.ts
                   WHERE p.ts >= %s AND p.stacja = ANY(%s)""", (od, list(wagi)))
    rows = cur.fetchall()
    # opad modelu w 6 h konczacych sie o ts (suma godzin ts-5h..ts)
    cur.execute("""SELECT stacja, model, wyprz, ts, opad FROM qbot_v2.pogoda_prog WHERE ts >= %s AND stacja = ANY(%s)""",
                (od - dt.timedelta(hours=12), list(wagi)))
    hop = {}
    for r in cur.fetchall():
        r = list(r.values()) if isinstance(r, dict) else r
        hop[(r[0], r[1], r[2], r[3])] = r[4]
    acc = {}
    for r in rows:
        r = list(r.values()) if isinstance(r, dict) else r
        s, m, d, ts, pt, pw, pg, pp, ot, ow, og, oo = r
        w = wagi[s]
        a = acc.setdefault((m, d), {"t": [0, 0, 0], "w": [0, 0, 0], "g": [0, 0, 0], "hit": 0, "fa": 0, "miss": 0, "cn": 0, "n": 0})
        for key, f, o in (("t", pt, ot), ("w", pw, ow), ("g", pg, og)):
            if f is not None and o is not None:
                a[key][0] += w * abs(f - o); a[key][1] += w * (f - o); a[key][2] += w
                if key == "t":
                    a["n"] += 1
        if oo is not None:
            vals = [hop.get((s, m, d, ts - dt.timedelta(hours=k + OPAD_LAG_H))) for k in range(6)]
            if all(v is not None for v in vals):
                fw, ow6 = sum(vals) >= OPAD_PROG, oo >= OPAD_PROG
                a["hit" if fw and ow6 else "fa" if fw else "miss" if ow6 else "cn"] += 1
    wyn = []
    for (m, d), a in sorted(acc.items(), key=lambda x: (x[0][1], x[0][0])):
        def mae(k):
            return (round(a[k][0] / a[k][2], 2), round(a[k][1] / a[k][2], 2)) if a[k][2] else (None, None)
        tm, tb = mae("t"); wm, wb = mae("w"); gm, gb = mae("g")
        n_op = a["hit"] + a["fa"] + a["miss"]
        wyn.append({"model": m, "opis": MODELS.get(m, m), "wyprz_dni": d, "temp_mae": tm, "temp_bias": tb,
                    "wiatr_mae": wm, "wiatr_bias": wb, "poryw_mae": gm, "poryw_bias": gb,
                    "opad_trafione": a["hit"], "opad_falszywe": a["fa"], "opad_przegapione": a["miss"],
                    "opad_trafnosc": round(a["hit"] / n_op, 2) if n_op else None, "n": a["n"]})
    return {"status": "OK", "dni": dni, "stacji": len(wagi), "zakres": "u Ciebie" if lat is not None else "Polska",
            "opad_prog_mm_6h": OPAD_PROG, "wyniki": wyn}


# ---------------------------------------------------------------- praca w tle (petla w qbot-web)
_SC: dict = {}


def score_cached(cur, dni: int = 60, lat=None, lon=None) -> dict:
    import time as _t
    key = (dni, None if lat is None else round(lat, 2), None if lon is None else round(lon, 2))
    hit = _SC.get(key)
    if hit and hit[0] > _t.time() - 3600:
        return hit[1]
    res = score(cur, dni=dni, lat=lat, lon=lon)
    if res.get("status") == "OK":
        od = cur.execute if False else None
        cur.execute("SELECT min(o.ts), max(o.ts) FROM qbot_v2.pogoda_obs o JOIN qbot_v2.pogoda_prog p ON p.stacja=o.stacja AND p.ts=o.ts "
                    "WHERE o.ts >= now() - (%s || ' days')::interval", (str(dni),))
        r = cur.fetchone(); r = list(r.values()) if isinstance(r, dict) else r
        res["okres"] = [r[0].isoformat() if r[0] else None, r[1].isoformat() if r[1] else None]
    _SC[key] = (_t.time(), res)
    return res


_STATE = {"obs_h": None, "prog_d": None, "arch_m": None}


def tick(cur) -> dict:
    """Wolane co ~10 min: pomiary co godzine, prognozy raz na dobe (3 ostatnie doby), archiwum IMGW poprzedniego miesiaca
    (probuje od 3. dnia miesiaca, az sie pojawi). Zwraca co zrobiono."""
    now = dt.datetime.now(dt.timezone.utc); done = {}
    hkey = now.strftime("%Y%m%d%H")
    if _STATE["obs_h"] != hkey and now.minute >= 20:
        done["obs"] = obs_live(cur); _STATE["obs_h"] = hkey
    dkey = now.date().isoformat()
    if _STATE["prog_d"] != dkey and now.hour >= 3:
        done["prog"] = forecasts(cur, now.date() - dt.timedelta(days=3), now.date() - dt.timedelta(days=1))
        _STATE["prog_d"] = dkey; _SC.clear()
        done["stats"] = build_stats(cur)
    pm = (now.replace(day=1) - dt.timedelta(days=1))
    mkey = pm.strftime("%Y-%m")
    if _STATE["arch_m"] != mkey and now.day >= 3:
        cur.execute("SELECT count(*) FROM qbot_v2.pogoda_obs WHERE zrodlo='archiwum' AND ts >= %s AND ts < %s",
                    (pm.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)))
        r = cur.fetchone(); n = list(r.values())[0] if isinstance(r, dict) else r[0]
        if n > 20000:
            _STATE["arch_m"] = mkey
        else:
            try:
                done["archiwum"] = obs_archive(cur, pm.year, pm.month)["wierszy"]; _STATE["arch_m"] = mkey; _SC.clear()
                done["prog_mies"] = forecasts(cur, pm.replace(day=1).date(), pm.date())
            except Exception as e:  # jeszcze nie opublikowane -- sprobuje jutro
                done["archiwum"] = f"brak: {type(e).__name__}"
    return done


# ---------------------------------------------------------------- automatyczny przydzial modeli (decyzja Michala 14.10.2026)
# Raz na dobe build_stats() liczy bledy per stacja x model x wyprzedzenie (60 dni) i zapisuje do pliku; przydzial(lat, lon)
# wybiera dla parametru i wyprzedzenia model z najmniejszym bledem "u Ciebie" (stacje <= 100 km, waga 1/(1+d/50)),
# a gdy par jest za malo -- wg "Polska". Opad: najwyzsza trafnosc. Bez danych: DOMYSLNY.
import os as _os
STATS_FILE = "/opt/qbot/artifacts/pogoda_stats.json"
PARAMS = ("temp", "wiatr", "poryw", "opad")
MIN_N = {"temp": 500, "wiatr": 500, "poryw": 500, "opad": 150}
DOMYSLNY = {"temp": "icon_eu", "wiatr": "icon_eu", "poryw": "knmi_harmonie_arome_europe", "opad": "ecmwf_ifs025"}
_ST = {"data": None, "mtime": 0}


def build_stats(cur, dni: int = 60) -> dict:
    od = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dni)
    cur.execute("""SELECT p.stacja, p.model, p.wyprz, p.ts, p.temp AS pt, p.wiatr AS pw, p.poryw AS pg, o.temp AS ot,
                          o.wiatr AS ow, o.poryw AS og, o.opad6 AS oo
                   FROM qbot_v2.pogoda_prog p JOIN qbot_v2.pogoda_obs o ON o.stacja = p.stacja AND o.ts = p.ts WHERE p.ts >= %s""", (od,))
    rows = [list(r.values()) if isinstance(r, dict) else list(r) for r in cur.fetchall()]
    cur.execute("SELECT stacja, model, wyprz, ts, opad FROM qbot_v2.pogoda_prog WHERE ts >= %s", (od - dt.timedelta(hours=12),))
    hop = {}
    for r in cur.fetchall():
        r = list(r.values()) if isinstance(r, dict) else r
        hop[(r[0], r[1], r[2], r[3])] = r[4]
    acc = {}
    for s, m, d, ts, pt, pw, pg, ot, ow, og, oo in rows:
        a = acc.setdefault((s, m, d), [0.0, 0, 0.0, 0, 0.0, 0, 0, 0, 0, 0])
        for j, f, o in ((0, pt, ot), (2, pw, ow), (4, pg, og)):
            if f is not None and o is not None:
                a[j] += abs(f - o); a[j + 1] += 1
        if oo is not None:
            vals = [hop.get((s, m, d, ts - dt.timedelta(hours=k + OPAD_LAG_H))) for k in range(6)]
            if all(x is not None for x in vals):
                fw, ow6 = sum(vals) >= OPAD_PROG, oo >= OPAD_PROG
                a[6 if fw and ow6 else 7 if fw else 8 if ow6 else 9] += 1
    data = {"built": dt.datetime.now(dt.timezone.utc).isoformat(), "dni": dni,
            "stacje": {s["klucz"]: [s["lat"], s["lon"]] for s in stations(cur)},
            "rows": [[k[0], k[1], k[2]] + val for k, val in acc.items()]}
    tmp = STATS_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh)
    _os.replace(tmp, STATS_FILE)
    _ST.update(data=data, mtime=_os.path.getmtime(STATS_FILE))
    return {"wierszy": len(data["rows"]), "par": len(rows)}


def _stats():
    try:
        mt = _os.path.getmtime(STATS_FILE)
    except OSError:
        return None
    if _ST["data"] is None or mt != _ST["mtime"]:
        with open(STATS_FILE) as fh:
            _ST.update(data=json.load(fh), mtime=mt)
    return _ST["data"]


def przydzial(lat: float, lon: float, promien_km: float = 100) -> dict:
    """{param: {wyprz: {model, opis, wartosc, zakres}}}; wartosc = blad (MAE) albo trafnosc opadu."""
    data = _stats()
    out = {p: {d: {"model": DOMYSLNY[p], "opis": MODELS[DOMYSLNY[p]], "wartosc": None, "zakres": "domyslny"} for d in DAYS} for p in PARAMS}
    if not data:
        return out
    wl = {}
    for k, (la, lo) in data["stacje"].items():
        km = _km(lat, lon, la, lo)
        if km <= promien_km:
            wl[k] = 1 / (1 + km / 50)
    for zakres, wagi in (("Polska", None), ("u Ciebie", wl)):
        if zakres == "u Ciebie" and not wl:
            continue
        agg = {}
        for r in data["rows"]:
            s, m, d = r[0], r[1], r[2]
            w = 1.0 if wagi is None else wagi.get(s)
            if not w:
                continue
            a = agg.setdefault((m, d), [0.0] * 14)
            for j in range(3):
                a[j * 3] += w * r[3 + j * 2]; a[j * 3 + 1] += w * r[4 + j * 2]; a[j * 3 + 2] += r[4 + j * 2]
            for j in range(4):
                a[9 + j] += w * r[9 + j]
            a[13] += r[9] + r[10] + r[11] + r[12]
        for p_i, p in enumerate(("temp", "wiatr", "poryw")):
            for d in DAYS:
                c = [(a[p_i * 3] / a[p_i * 3 + 1], m) for (m, dd), a in agg.items() if dd == d and a[p_i * 3 + 2] >= MIN_N[p] and a[p_i * 3 + 1] > 0]
                if c:
                    val, m = min(c)
                    out[p][d] = {"model": m, "opis": MODELS.get(m, m), "wartosc": round(val, 2), "zakres": zakres}
        for d in DAYS:
            c = []
            for (m, dd), a in agg.items():
                den = a[9] + a[10] + a[11]
                if dd == d and a[13] >= MIN_N["opad"] and den > 0:
                    c.append((a[9] / den, m))
            if c:
                val, m = max(c)
                out["opad"][d] = {"model": m, "opis": MODELS.get(m, m), "wartosc": round(val, 2), "zakres": zakres}
    return out
