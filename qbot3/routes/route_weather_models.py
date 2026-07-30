"""Porownanie modeli pogodowych i wybor modelu kanonicznego.

PO CO TO JEST. Do tej pory QBot bral z Open-Meteo tryb "best_match" -- serwis sam wybieral
model i podawal wynik bez slowa wyjasnienia. Efekt: na 4.08.2026 panel pokazal 40.3 C, bo
best_match wybral ICON, podczas gdy ECMWF (to, co widac na Windy) dawal 37.9 C, a model AI
ECMWF -- 35.7 C. Rozjazd 4.6 C podany jako jedna pewna liczba.

DWIE ZASADY, ktore to naprawiaja:

1. MODEL KANONICZNY WYBIERA REGULA, NIE SERWIS I NIE LLM. Regula: bierzemy model o
   NAJDROBNIEJSZEJ siatce, ktory faktycznie SIEGA danej daty; gdy zaden model
   wysokorozdzielczy nie siega -- ECMWF IFS. Zasieg sprawdzamy NA ZYWO, bo modele
   wysokorozdzielcze koncza sie szybko (ICON-D2 = 2.2 km, ale tylko ~3 dni) i hardkod
   po cichu by sklamal.

2. ROZBIEZNOSC POKAZUJEMY, NIE CHOWAMY. Obok kanonu leci komplet 6 modeli i rozrzut
   zespolu ECMWF (51 wariantow tego samego modelu). Gdy modele sie zgadzaja -- prognoza jest
   pewna. Gdy sie rozjezdzaja o 5 C -- to tez jest informacja, wazniejsza niz srednia z nich.

WAZNE O ROZDZIELCZOSCI: drobna siatka pomaga TYLKO w zasiegu modelu. Poza nim liczby nie sa
"dokladniejsze" -- pochodza z grubszego wariantu tej samej rodziny. Dlatego zasieg jest
w tym module rownie wazny jak rozdzielczosc.

Koszt: komplet 6 modeli dla wszystkich punktow dnia = JEDNO zapytanie (~180 ms),
zespol = drugie. Zmierzone na zywo 2026-07-30.
"""
from __future__ import annotations

import datetime as _dt
import json
import threading
import urllib.parse
import urllib.request
from typing import Optional

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
TZ_NAME = "Europe/Warsaw"
UA = {"User-Agent": "QBot-METEO-MODELE/1.0"}

# Siatka w km wg dokumentacji Open-Meteo. "wysoka" = ponizej progu HIRES_KM.
HIRES_KM = 10.0
FALLBACK_MODEL = "ecmwf_ifs025"

MODELS: dict[str, dict] = {
    "icon_d2": {"nazwa": "ICON-D2", "dostawca": "DWD (Niemcy)", "siatka_km": 2.2,
                "typ": "regionalny wysokiej rozdzielczosci"},
    "icon_eu": {"nazwa": "ICON-EU", "dostawca": "DWD (Niemcy)", "siatka_km": 7.0,
                "typ": "regionalny"},
    "ecmwf_ifs025": {"nazwa": "ECMWF IFS", "dostawca": "ECMWF", "siatka_km": 25.0,
                     "typ": "globalny fizyczny"},
    "ecmwf_aifs025_single": {"nazwa": "ECMWF AIFS", "dostawca": "ECMWF", "siatka_km": 25.0,
                             "typ": "globalny AI (to pokazuje Windy w trybie AI)"},
    "gfs_seamless": {"nazwa": "GFS", "dostawca": "NOAA (USA)", "siatka_km": 13.0,
                     "typ": "globalny fizyczny"},
    "ukmo_seamless": {"nazwa": "UKMO", "dostawca": "UK Met Office", "siatka_km": 10.0,
                      "typ": "globalny fizyczny"},
}
MODEL_IDS = list(MODELS.keys())

_reach_cache: dict[str, tuple[float, dict]] = {}
_reach_lock = threading.Lock()
REACH_TTL_S = 6 * 3600.0


def _get(url: str, timeout: float = 30.0):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _as_list(payload):
    """Open-Meteo zwraca liste przy wielu punktach, pojedynczy obiekt przy jednym."""
    return payload if isinstance(payload, list) else [payload]


# --- zasieg modeli ----------------------------------------------------------
def model_reach(lat: float, lon: float, timeout: float = 30.0) -> dict:
    """Do ktorego DNIA siega kazdy model w tym punkcie. Jedno zapytanie, cache 6 h.

    Zwraca {model_id: {"ostatni_dzien": "RRRR-MM-DD", "dni": N}}. Model bez danych: dni=0.
    """
    key = "%.1f,%.1f" % (lat, lon)
    now = _dt.datetime.now().timestamp()
    with _reach_lock:
        hit = _reach_cache.get(key)
        if hit and (now - hit[0]) < REACH_TTL_S:
            return hit[1]

    params = {"latitude": round(float(lat), 2), "longitude": round(float(lon), 2),
              "hourly": "temperature_2m", "models": ",".join(MODEL_IDS),
              "forecast_days": 16, "timezone": TZ_NAME}
    data = _get(FORECAST_URL + "?" + urllib.parse.urlencode(params), timeout)
    h = (_as_list(data)[0].get("hourly") or {})
    times = h.get("time") or []
    today = _dt.date.today()

    out = {}
    for mid in MODEL_IDS:
        seria = h.get("temperature_2m_" + mid) or []
        ostatni = None
        for i in range(min(len(times), len(seria))):
            if seria[i] is not None:
                ostatni = times[i][:10]
        if ostatni:
            dni = (_dt.date.fromisoformat(ostatni) - today).days + 1
            out[mid] = {"ostatni_dzien": ostatni, "dni": dni}
        else:
            out[mid] = {"ostatni_dzien": None, "dni": 0}

    with _reach_lock:
        _reach_cache[key] = (now, out)
    return out


def canonical_model(lat: float, lon: float, date_str: str,
                    reach: Optional[dict] = None) -> dict:
    """Model kanoniczny dla tej daty: najdrobniejsza siatka, ktora TAM SIEGA.

    Zwraca {"model": id, "nazwa", "siatka_km", "powod", "odrzucone": [...]}.
    """
    target = _dt.date.fromisoformat(date_str[:10])
    reach = reach if reach is not None else model_reach(lat, lon)

    dostepne = []
    odrzucone = []
    for mid, meta in MODELS.items():
        ost = (reach.get(mid) or {}).get("ostatni_dzien")
        siega = bool(ost) and _dt.date.fromisoformat(ost) >= target
        (dostepne if siega else odrzucone).append(mid)

    hires = sorted([m for m in dostepne if MODELS[m]["siatka_km"] < HIRES_KM],
                   key=lambda m: MODELS[m]["siatka_km"])
    if hires:
        wybor = hires[0]
        powod = ("%s ma najdrobniejsza siatke (%s km) sposrod modeli siegajacych tej daty"
                 % (MODELS[wybor]["nazwa"], MODELS[wybor]["siatka_km"]))
    elif FALLBACK_MODEL in dostepne:
        wybor = FALLBACK_MODEL
        powod = ("zaden model wysokiej rozdzielczosci nie siega tak daleko -- "
                 "kanonem jest %s (%s km), model referencyjny dla dalszych terminow"
                 % (MODELS[FALLBACK_MODEL]["nazwa"], MODELS[FALLBACK_MODEL]["siatka_km"]))
    elif dostepne:
        wybor = sorted(dostepne, key=lambda m: MODELS[m]["siatka_km"])[0]
        powod = "jedyny dostepny model siegajacy tej daty: %s" % MODELS[wybor]["nazwa"]
    else:
        return {"model": None, "nazwa": None, "siatka_km": None,
                "powod": "zaden z %d modeli nie siega %s" % (len(MODELS), date_str),
                "odrzucone": odrzucone}

    return {"model": wybor, "nazwa": MODELS[wybor]["nazwa"],
            "siatka_km": MODELS[wybor]["siatka_km"], "dostawca": MODELS[wybor]["dostawca"],
            "typ": MODELS[wybor]["typ"], "powod": powod,
            "odrzucone": [{"model": m, "nazwa": MODELS[m]["nazwa"],
                           "powod": "nie siega tej daty (konczy sie %s)"
                                    % ((reach.get(m) or {}).get("ostatni_dzien") or "?")}
                          for m in odrzucone]}


# --- porownanie modeli w punktach kontrolnych -------------------------------
def compare_models(points: list[dict], date_str: str, timeout: float = 40.0) -> dict:
    """Komplet 6 modeli dla kilku punktow trasy. JEDNO zapytanie.

    points: [{"nazwa": "start", "lat":, "lon":, "km":, "godzina": "09:00"}, ...]
    Dla kazdego punktu bierzemy wartosc z JEGO godziny (moment przejazdu), nie z doby.
    """
    if not points:
        return {"status": "ERROR", "error": "brak punktow kontrolnych"}

    params = {"latitude": ",".join("%.3f" % float(p["lat"]) for p in points),
              "longitude": ",".join("%.3f" % float(p["lon"]) for p in points),
              "start_date": date_str, "end_date": date_str,
              "hourly": "temperature_2m,relative_humidity_2m,precipitation,"
                        "precipitation_probability,wind_speed_10m,wind_gusts_10m,cloud_cover",
              "models": ",".join(MODEL_IDS), "windspeed_unit": "ms", "timezone": TZ_NAME}
    data = _as_list(_get(FORECAST_URL + "?" + urllib.parse.urlencode(params), timeout))

    wiersze = []
    for i, p in enumerate(points):
        if i >= len(data):
            break
        h = (data[i].get("hourly") or {})
        times = h.get("time") or []
        godz = str(p.get("godzina") or "12:00")[:2]
        try:
            j = next(k for k in range(len(times)) if times[k][11:13] == godz)
        except StopIteration:
            j = min(12, len(times) - 1) if times else None
        if j is None:
            continue

        per_model = {}
        for mid in MODEL_IDS:
            def _v(pole, nd=1):
                seria = h.get("%s_%s" % (pole, mid)) or []
                v = seria[j] if j < len(seria) else None
                return round(float(v), nd) if v is not None else None
            temp = _v("temperature_2m")
            if temp is None:
                continue  # model nie siega tej daty -- pomijamy, zamiast wpisywac zero
            per_model[mid] = {
                "temp_c": temp, "rh_pct": _v("relative_humidity_2m", 0),
                "opad_mm": _v("precipitation"), "opad_prob": _v("precipitation_probability", 0),
                "wiatr_ms": _v("wind_speed_10m"), "porywy_ms": _v("wind_gusts_10m"),
                "zachmurzenie_pct": _v("cloud_cover", 0),
            }

        temps = [v["temp_c"] for v in per_model.values() if v["temp_c"] is not None]
        opady = [v["opad_mm"] for v in per_model.values() if v["opad_mm"] is not None]
        wiersze.append({
            "nazwa": p.get("nazwa"), "km": p.get("km"), "godzina": p.get("godzina"),
            "modele": per_model,
            "temp_min": (min(temps) if temps else None),
            "temp_max": (max(temps) if temps else None),
            "temp_rozrzut": (round(max(temps) - min(temps), 1) if len(temps) > 1 else 0.0),
            "temp_mediana": (round(sorted(temps)[len(temps) // 2], 1) if temps else None),
            "opad_zgoda": (sum(1 for o in opady if o >= 0.1), len(opady)) if opady else (0, 0),
        })

    rozrzuty = [w["temp_rozrzut"] for w in wiersze if w["temp_rozrzut"] is not None]
    return {"status": "OK", "data": date_str, "punkty": wiersze,
            "rozrzut_max_c": (max(rozrzuty) if rozrzuty else None),
            "rozrzut_sr_c": (round(sum(rozrzuty) / len(rozrzuty), 1) if rozrzuty else None),
            "modele_opis": MODELS}


# --- zespol (ensemble) ------------------------------------------------------
def ensemble_spread(lat: float, lon: float, date_str: str, godziny: Optional[list] = None,
                    timeout: float = 40.0) -> dict:
    """Rozrzut zespolu ECMWF (51 wariantow tego samego modelu) dla wybranych godzin.

    Zespol pokazuje, jak bardzo prognoza jest niepewna WEWNATRZ jednego modelu -- inaczej
    niz compare_models, ktore pokazuje niezgode MIEDZY osrodkami.
    """
    godziny = godziny or ["09:00", "12:00", "15:00", "18:00"]
    params = {"latitude": round(float(lat), 3), "longitude": round(float(lon), 3),
              "start_date": date_str, "end_date": date_str,
              "hourly": "temperature_2m,precipitation", "models": "ecmwf_ifs025",
              "timezone": TZ_NAME}
    try:
        d = _get(ENSEMBLE_URL + "?" + urllib.parse.urlencode(params), timeout)
    except Exception as exc:  # noqa
        return {"status": "ERROR", "error": str(exc)[:150]}

    h = (_as_list(d)[0].get("hourly") or {})
    times = h.get("time") or []
    t_klucze = [k for k in h.keys() if k.startswith("temperature_2m")]
    p_klucze = [k for k in h.keys() if k.startswith("precipitation")]

    def _pct(v, p):
        v = sorted(x for x in v if x is not None)
        if not v:
            return None
        return v[min(len(v) - 1, max(0, int(round(p / 100.0 * (len(v) - 1)))))]

    out = []
    for g in godziny:
        try:
            j = next(k for k in range(len(times)) if times[k][11:13] == g[:2])
        except StopIteration:
            continue
        tv = [h[k][j] for k in t_klucze if j < len(h[k])]
        pv = [h[k][j] for k in p_klucze if j < len(h[k])]
        tv_ok = [x for x in tv if x is not None]
        if not tv_ok:
            continue
        out.append({
            "godzina": g,
            "temp_p10": round(_pct(tv, 10), 1), "temp_mediana": round(_pct(tv, 50), 1),
            "temp_p90": round(_pct(tv, 90), 1),
            "temp_rozrzut": round(max(tv_ok) - min(tv_ok), 1),
            "szansa_opadu_pct": (round(100.0 * sum(1 for x in pv if x and x >= 0.1) / len(pv))
                                 if pv else None),
        })

    return {"status": "OK", "czlonkow": len(t_klucze), "model": "ECMWF IFS (zespol)",
            "godziny": out,
            "uwaga": ("p10-p90 to widelki tego samego modelu: 8 na 10 wariantow miesci sie "
                      "w tym zakresie. Szeroko = prognoza niepewna, waska = pewna.")}


if __name__ == "__main__":
    import sys
    la = float(sys.argv[1]) if len(sys.argv) > 1 else 50.584
    lo = float(sys.argv[2]) if len(sys.argv) > 2 else 18.038
    ds = sys.argv[3] if len(sys.argv) > 3 else (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    r = model_reach(la, lo)
    print("ZASIEG:", json.dumps(r, ensure_ascii=False))
    print("KANON :", json.dumps(canonical_model(la, lo, ds, r), ensure_ascii=False, indent=2))
    pts = [{"nazwa": "start", "lat": la, "lon": lo, "km": 0, "godzina": "09:00"},
           {"nazwa": "poludnie", "lat": la, "lon": lo, "km": 50, "godzina": "13:00"}]
    print("MODELE:", json.dumps(compare_models(pts, ds), ensure_ascii=False, indent=2)[:2500])
    print("ZESPOL:", json.dumps(ensemble_spread(la, lo, ds), ensure_ascii=False, indent=2))
