"""Dobor ubioru na jazde z garazu (garage.db gear) dla KONKRETNEGO planu (godzina + przerwy). Wersja 2.

1) warunki(plan)   - przebieg warunkow W CZASIE jazdy (okna 30 min z warstwy planu, bez AI) + dlugie postoje.
2) kandydaci(...)  - cala szafa oceniona dla tej jazdy. Rzeczy z AUDYTEM (pola a_* w gear, docs/audit/*.json,
                     scripts/garage_audit_import.py) oceniane z audytu: zakres temp. zestawu, status, fit,
                     sprawdzony deszcz, mokra-wychladza, sprawdzony czas wkladki. Rzeczy bez audytu - stara logika
                     z notatek. Jedyne twarde wykluczenie: a_out=1 (fit blokuje / wycofane / tylko poza rowerem).
                     Wstepna punktacja sluzy TYLKO do zawezenia listy dla AI (top N na warstwe); decyzje podejmuje AI.
3) historia_jazd   - "W czym jechalem" (garage.db ride_gear_log) + warunki z raportu z jazdy (ride_report_data.w1_json:
                     odczuwalna, wiatr m/s, opad, czas, IF). ZASADA (decyzja 2026-09-23): konkretne rzeczy tylko z jazd
                     dluzsza/wyprawa; komfort termiczny ze wszystkich, waga = min(1, czas_h/3).
4) AI              - 2 rozne zestawy wylacznie z kandydatow; zasady ważenia = docs/OUTFIT_ADVISOR_RULES.md
                     (tekst czytany przy kazdym doborze - zmiana zasad bez zmiany kodu).
Zapis: qbot_v2.route_outfit (historia propozycji -> rotacja, wyswietlanie).
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
import sqlite3
import time

GARAGE_DB = "/opt/qbot/app/data/garage.db"
RULES_MD = "/opt/qbot/app/docs/OUTFIT_ADVISOR_RULES.md"
VERSION = 3
# temperatura na trasie / na rowerze: qbot3/routes/ride_thermal.py (kalibracja Karoo + UTCI), zamiast stalej -6 C
_SPODNIE = ["Spodnie rowerowe (bez wk\u0142adki)"]
LAYERS = [
    ("baza_gora", ["Bielizna termoaktywna \u2014 g\u00f3ra"]),
    ("koszulka", ["Koszulka kr\u00f3tki r\u0119kaw", "Koszulka d\u0142ugi r\u0119kaw", "Koszulka techniczna"]),
    ("kamizelka", ["Kamizelka"]),
    ("kurtka", ["Kurtka"]),
    ("baza_dol", ["Bielizna termoaktywna \u2014 d\u00f3\u0142", "Spodnie termiczne"]),
    ("spodenki", ["Spodenki z wk\u0142adk\u0105"]),          # warstwa Z WKLADKA (bibsy, liner, tights z wkladka)
    ("spodnie", _SPODNIE),                                  # zewnetrzne bez wkladki (wymagaja warstwy 'spodenki')
    ("rekawki", []),
    ("nogawki", []),
    ("rekawiczki", ["R\u0119kawiczki"]),
    ("glowa", ["Nakrycie g\u0142owy"]),
    ("szyja", ["Komin i chusta"]),
    ("skarpety", ["Skarpety"]),
    ("buty", ["Buty"]),
    ("ochraniacze", ["Ochraniacze na buty"]),
]
# warstwy wynikaja z taksonomii (kategoria + parametry rzeczy): qbot_garage_taxonomy.slot_of/LAYER_OF_SLOT
LAYER_KEYS = ["baza_gora", "koszulka", "kamizelka", "kurtka", "deszcz_gora", "baza_dol", "spodenki", "spodnie",
              "deszcz_dol", "rekawki", "nogawki", "rekawiczki", "glowa", "szyja", "skarpety", "buty", "ochraniacze"]
_WARMERS = "R\u0119kawki i nogawki"
SEASON_RANGE = {"lato": (16, 30), "przejsciowy": (6, 18), "zima": (-10, 6)}
# UWAGA: 'hoodie' celowo NIE jest znakiem ocieplenia (np. North Face Sun Hoodie = letnia warstwa na upal)
_WARM = re.compile(r"primaloft|insulat|ocieplan|thermal|termiczn|puch|down|winter|zimow|fleece|polar|alpha", re.I)
_TEMP = re.compile(r"(-?\+?\d{1,2})\s*(?:\u00b0C)?\s*(?:\u2026|\.\.\.|\u2013|-|do)\s*\+?(-?\d{1,2})\s*\u00b0\s*C", re.I)
_OUT = re.compile(r"WYCOFAN|ZA MA[\u0141L][AEY]|WISI W SZAFIE|NIE WYBIERA|ZAGUBION", re.I)
_PLUS2 = re.compile(r"G[\u0141L]\u00d3WN[AY]", re.I)
_PLUS1 = re.compile(r"ULUBION", re.I)
_MINUS1 = re.compile(r"RZADKO|\u0179LE LE\u017bY|ZLE LEZY|RZADKO WYBIERAN", re.I)
_MINUS05 = re.compile(r"NIE TESTOWAN|NIE SPRAWDZON|JESZCZE NIE", re.I)
_LEG = re.compile(r"leg|nogawk|3/4|knee", re.I)
# wstepne wagi audytu (tylko do zawezenia listy dla AI)
ST_W = {"CORE": 2.0, "ROTATION": 0.7, "SPECIAL": 0.3, "BACKUP": -1.0, "NEW": -0.5,
        "RETIRE_CANDIDATE": -3.0, "OFF_BIKE": -2.5, "FIT_BLOCKED": -9.0}
RAIN_W = {"ulewa_sucho": 2.0, "umiarkowany_sucho": 1.5, "mzawka_sucho": 0.8, "umiarkowany_przemaka_po_czasie": 0.4}
PAD_LONG = {">6": 1.5, "4-6": 0.5, "2-4": -1.0, "1-2": -2.0, "<1": -4.0}
PAD_MID = {">6": 0.5, "4-6": 0.5, "2-4": 0.0, "1-2": -1.0, "<1": -3.0}
_SLAB = (("s_breath", "oddychalnosc"), ("s_dry", "szybkoschniecie"), ("s_wind", "wiatroszczelnosc"),
         ("s_water", "wodoodpornosc"), ("s_pack", "pakownosc"), ("s_comfort", "komfort_wykonania"),
         ("s_fit", "dopasowanie_rozmiaru"), ("s_insul", "izolacja_jakosc_grzania"), ("s_cond", "stan_techniczny"))
_WEATHER_LAYERS = ("kurtka", "kamizelka", "deszcz_gora", "deszcz_dol", "spodnie", "rekawiczki", "buty", "nogawki", "ochraniacze")


def _f(x, d=None):
    try:
        return float(x)
    except Exception:
        return d


def _hm(s):
    try:
        h, m = [int(x) for x in str(s).split(":")[:2]]
        return h * 60 + m
    except Exception:
        return None


def _fmt(m):
    return "%02d:%02d" % ((int(m) // 60) % 24, int(m) % 60)


def _row(r, keys):
    return dict(r) if isinstance(r, dict) else dict(zip(keys, r))


# ---------------- 1) warunki ----------------
def warunki(d: dict, start: str, long_stops: int = 0, long_stop_min: int = 0) -> dict:
    det = d.get("details") or {}
    w = det.get("weather") or {}
    win = w.get("windows") or []
    ch = (d.get("chart") or {}).get("weather") or []
    tm = d.get("time") or {}
    st = _hm(start)
    meta = st + int(round(float(tm.get("total_h") or 0) * 60)) if st is not None else None
    fe = [(x.get("okno"), _f(x.get("feels"))) for x in win if _f(x.get("feels")) is not None]
    ta = [(x.get("okno"), _f(x.get("temp"))) for x in win if _f(x.get("temp")) is not None]
    out = {"start": start, "meta": _fmt(meta) if meta is not None else None, "czas_h": _f(tm.get("total_h"))}
    if long_stops:   # przywrocone (zgubione przy przebudowie v3 2026-09-25)
        out["dlugie_postoje"] = {"ile": int(long_stops), "min_kazdy": int(long_stop_min or 0)}

    def _sum(key):
        v = [_f(x.get(key)) for x in win if _f(x.get(key)) is not None]
        if not v:
            return None
        return {"start": v[0], "koniec": v[-1], "min": min(v), "max": max(v), "srednia": round(sum(v) / len(v), 1)}
    for key, lab in (("temp", "prognoza_powietrza"), ("na_trasie", "na_trasie"), ("na_rowerze", "na_rowerze")):
        sm = _sum(key)
        if sm:
            out[lab] = sm
    termika = w.get("termika") or {}
    if termika:
        out["temperatura_opis"] = {
            "prognoza_powietrza": "prognoza temperatury powietrza (model pogody)",
            "na_trasie": "prognoza + poprawka z kalibracji na Karoo Michala (%s jazd): tam gdzie jezdzi jest zwykle chlodniej; "
                         "niepewnosc 80%%: %s C" % (termika.get("kalibracja_jazd"), termika.get("niepewnosc_80proc")),
            "na_rowerze": "TEMPERATURA DO UBIORU: jak na trasie (tyle pokazuje Karoo i tyle Michal czuje na twarzy - ped jazdy"
                          " i cieplo z wysilku sie znosza)"
                          " + osobista korekta %s C (z %s jazd w 'W czym jechalem')" % (
                              (termika.get("osobista_korekta") or {}).get("c"), (termika.get("osobista_korekta") or {}).get("jazd")),
        }
        lo80 = (termika.get("niepewnosc_80proc") or [None])[0]
        if lo80 is not None and out.get("na_rowerze"):
            out["zapas_bezpieczenstwa"] = {"na_rowerze_chlodny_wariant_min": round(out["na_rowerze"]["min"] + lo80, 1),
                                           "opis": "w 1 na 10 jazd bywa o %.1f C chlodniej niz przewidywanie - rzeczy do "
                                                   "dolozenia musza to pokryc" % abs(lo80)}
    na_s = [x.get("okno") for x in win if x.get("wiatr_ochrona") == "na_sobie"]
    pod_r = [x.get("okno") for x in win if x.get("wiatr_ochrona") == "pod_reka"]
    if na_s:
        out["wiatr_ochrona_wymagana"] = {"okna": na_s[:10], "co": "ochrona od wiatru NA SOBIE (kamizelka/wiatrowka)"}
    if pod_r:
        out["wiatr_ochrona_pod_reka"] = {"okna": pod_r[:10], "co": "kamizelka/wiatrowka pod reka (kieszen), zaloz przy dluzszym wietrze"}
    tmap = {x.get("okno"): x for x in win}
    if fe:
        lo = min(fe, key=lambda x: x[1]); hi = max(fe, key=lambda x: x[1])
        out["odczuwalna"] = {"start": fe[0][1], "koniec": fe[-1][1], "min": lo[1], "min_o": lo[0], "max": hi[1], "max_o": hi[0],
                             "rozrzut": round(hi[1] - lo[1], 1)}
        out["przebieg"] = [{x: y for x, y in (("godz", o), ("prognoza", _f((tmap.get(o) or {}).get("temp"))),
                            ("na_trasie", _f((tmap.get(o) or {}).get("na_trasie"))),
                            ("na_rowerze", _f((tmap.get(o) or {}).get("na_rowerze"))),
                            ("czolowy_ms", _f((tmap.get(o) or {}).get("czolowy_sr"))),
                            ("porywy_ms", _f((tmap.get(o) or {}).get("porywy_max"))),
                            ("wiatr_ochrona", (tmap.get(o) or {}).get("wiatr_ochrona")), ("odczuwalna_w_sloncu", v))
                            if y is not None} for o, v in fe]
    wb = [_f(x.get("wbgt")) for x in win if _f(x.get("wbgt")) is not None]
    if wb:
        out["wbgt_max"] = max(wb)
    wr = []
    for x in ch:
        a, c = _f(x.get("w_along"), 0.0), _f(x.get("w_cross"), 0.0)
        wr.append((math.hypot(a, c), -a))
    if wr:
        out["wiatr_ms"] = {"max": round(max(v[0] for v in wr), 1), "czolowy_max": round(max(0.0, max(v[1] for v in wr)), 1)}
    pr = [(x.get("okno"), _f(x.get("opad_prob"), 0.0), _f(x.get("opad_mm"), 0.0)) for x in win]
    if pr:
        wet = [p for p in pr if p[1] >= 40]
        out["deszcz"] = {"max_proc": max(p[1] for p in pr), "suma_mm": round(sum(p[2] for p in pr), 1),
                         "okna_40proc": [p[0] for p in wet][:8]}
    sl = w.get("slonce") or {}
    out["slonce"] = {"wschod": sl.get("wschod"), "zachod": sl.get("zachod"), "sloneczne_h": sl.get("sloneczne_h"), "uv_max": sl.get("uv_max")}
    if meta is not None and _hm(sl.get("zachod")) is not None:
        out["meta_po_zmroku"] = meta > _hm(sl.get("zachod"))
    return out


# ---------------- 2) kandydaci ----------------
def _range(season, insul, notes):
    m = _TEMP.search(notes or "")
    if m:
        a, b = int(m.group(1).replace("+", "")), int(m.group(2).replace("+", ""))
        return (min(a, b), max(a, b)), "notatka"
    rs = [SEASON_RANGE[s.strip()] for s in str(season or "").split(",") if s.strip() in SEASON_RANGE]
    if rs:
        lo, hi = min(r[0] for r in rs), max(r[1] for r in rs)
        ins = _f(insul)
        if ins is not None:          # ocieplenie przesuwa zakres: 0-1 cieplo, 4-5 zimno
            lo, hi = lo + (2 - ins) * 2, hi + (2 - ins) * 2
        return (int(lo), int(hi)), "sezon"
    return None, None


def recent_ids(conn, n=3, skip=None) -> set:
    """Rzeczy z ostatnich propozycji (rotacja). skip=(route_id, data): ponowne dobory TEJ SAMEJ jazdy sie nie licza
    (decyzja 2026-10-04: inaczej kazde ponowne generowanie karze sprawdzony zestaw)."""
    try:
        ensure(conn)
        if skip and skip[0] and skip[1]:
            rows = conn.execute("SELECT proposal FROM qbot_v2.route_outfit WHERE NOT (route_id=%s AND ride_date=%s) "
                                "ORDER BY created_at DESC LIMIT %s", (skip[0], skip[1], n)).fetchall()
        else:
            rows = conn.execute("SELECT proposal FROM qbot_v2.route_outfit ORDER BY created_at DESC LIMIT %s", (n,)).fetchall()
        conn.commit()
    except Exception:
        return set()
    ids = set()
    for r in rows:
        p = r["proposal"] if isinstance(r, dict) else r[0]
        p = json.loads(p) if isinstance(p, str) else p
        for z in (p or {}).get("zestawy") or []:
            for it in (z.get("rzeczy") or []) + (z.get("do_kieszeni") or []):
                if it.get("id") is not None:
                    ids.add(int(it["id"]))
    return ids


def _pad_eff(r):
    """Wkladka na dlugie jazdy (decyzja Michala 2026-09-25): Komfort z Ankiety ocen >= +1 = wkladka na > 6 h
    (godziny z audytu to najdluzsza jazda w 2026, nie limit). Komfort <= 0 -> godziny z audytu (zwykle krotko)."""
    try:
        if r["s_comfort"] is not None and int(r["s_comfort"]) >= 1:
            return ">6"
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return r["a_pad_h"]


def _layer(r, cat2layer=None):
    import qbot_garage_taxonomy as T
    return T.LAYER_OF_SLOT.get(T.slot_of(r["category"], r["g_body"], r["g_len"]) or "")


def _gear_rows():
    g = sqlite3.connect(GARAGE_DB)
    g.row_factory = sqlite3.Row
    have = {r["name"] for r in g.execute("PRAGMA table_info(gear)")}
    acols = [c for c in ("a_status", "a_fit", "a_use", "a_temp_min", "a_temp_max", "a_effort", "a_rain", "a_wind",
                         "a_wet_cold", "a_pad_h", "a_carry", "a_role", "a_pairs", "a_note", "a_out", "a_src", "a_date",
                         "g_body", "g_len", "s_breath", "s_dry", "s_wind", "s_water", "s_pack", "s_comfort", "s_fit",
                         "s_insul", "s_cond", "s_status", "g_layer", "g_style", "color_q")]
    sel = ", ".join(c if c in have else "NULL AS %s" % c for c in acols)
    rc = [c for c in ("r_intensity", "r_breath", "r_dry", "r_insul", "r_wind", "r_water", "r_pack", "ratings_status")]
    rsel = ", ".join(c if c in have else "NULL AS %s" % c for c in rc if c not in ("r_insul", "r_wind", "r_water", "r_breath"))
    rows = g.execute("SELECT id, category, brand, model, color, season, rating, r_insul, r_wind, r_water, r_breath, fabric, notes, "
                     + rsel + ", "
                     + sel + " FROM gear WHERE active=1").fetchall()
    g.close()
    return rows


def kandydaci(war: dict, recent: set, per_layer: int = 7, liked: set | None = None, strong: set | None = None) -> dict:
    # dopasowanie do zakresow z audytu po TEMPERATURZE POWIETRZA (tak Michal podawal, w czym jezdzil);
    # odczuwalna tylko gdy brak powietrza
    # dopasowanie do zakresow z audytu (temperatura, w jakiej Michal nosil zestaw): od chlodniejszej temperatury
    # na trasie do prognozy powietrza (obejmuje zapas); odczuwalna tylko gdy brak danych
    lo_src = war.get("na_trasie") or war.get("prognoza_powietrza") or war.get("odczuwalna") or {}
    hi_src = war.get("prognoza_powietrza") or war.get("odczuwalna") or {}
    lo_t, hi_t = _f(lo_src.get("min"), 10.0), _f(hi_src.get("max"), 15.0)
    rain = war.get("deszcz") or {}
    wet = rain.get("max_proc", 0) >= 40
    heavy = _f(rain.get("suma_mm"), 0.0) >= 5
    czas = _f(war.get("czas_h"), 0.0) or 0.0
    cold_stops = bool(war.get("dlugie_postoje")) or czas >= 4 or bool(war.get("meta_po_zmroku"))
    windy = bool(war.get("wiatr_ochrona_wymagana")) or (_f((war.get("wiatr_ms") or {}).get("max"), 0.0) >= 6 and lo_t < 15)
    liked = liked or set()
    strong = strong or set()
    cat2layer = {c: k for k, cs in LAYERS for c in cs}
    out = {k: [] for k in LAYER_KEYS}
    for r in _gear_rows():
        k = _layer(r, cat2layer)
        if not k:
            continue
        audited = bool(r["a_date"])
        if r["s_fit"] is not None and int(r["s_fit"]) < 0:
            continue                                             # Dopasowanie < 0 (ankieta) = nie do jazdy
        notes = r["notes"] or ""
        if audited:
            if int(r["a_out"] or 0):
                continue                                         # jedyne twarde "nie"
            if r["a_temp_min"] is not None and r["a_temp_max"] is not None:
                rng, src = (int(r["a_temp_min"]), int(r["a_temp_max"])), "audyt"
            else:
                rng, src = _range(r["season"], r["r_insul"], notes)
        else:
            if _OUT.search(notes):
                continue
            rng, src = _range(r["season"], r["r_insul"], notes)
        if not rng:
            continue
        a, b = rng
        margin = 3 if audited else 2
        ov = max(0.0, min(b, hi_t + margin) - max(a, lo_t - margin))   # zachodzenie na przebieg jazdy
        if ov <= 0 and k not in ("kamizelka", "kurtka", "deszcz_gora", "deszcz_dol", "rekawki", "nogawki"):
            continue
        if ov <= 0 and a > hi_t + margin:
            continue                                             # warstwy zdejmowane moga lezec nizej, ale nie wyzej
        if ov <= 0 and b < lo_t - 8:
            continue                                             # zbyt ciepla nawet 'do kieszeni' (np. zimowa kurtka w upal)
        mid_i, mid_r = (max(a, -10) + min(b, 35)) / 2.0, (lo_t + hi_t) / 2.0
        fit_t = max(0.0, 3.0 - abs(mid_i - mid_r) / 3.0)
        if audited:
            sc = 3.0 + fit_t + ST_W.get(r["a_status"] or "", 0.0)
            if r["a_fit"] in ("LEKKO_CIASNA", "ZA_LUZNA"):
                sc -= 0.4
            if int(r["a_wet_cold"] or 0) and cold_stops:
                sc -= 1.0
            if wet and k in _WEATHER_LAYERS:
                sc += RAIN_W.get(r["a_rain"] or "", 0.0) + (1.0 if heavy and r["a_rain"] == "ulewa_sucho" else 0.0)
                if r["a_carry"] == "czesto":
                    sc += 0.5
            if windy and k in ("kurtka", "kamizelka", "deszcz_gora") and r["a_wind"] in ("mocna", "umiarkowana"):
                sc += 0.7
            if k == "spodenki" and r["a_pad_h"]:
                sc += (PAD_LONG if czas >= 5 else PAD_MID if czas >= 3 else {}).get(_pad_eff(r), 0.0)
        else:
            sc = float(r["rating"] or 3) + fit_t + (0.5 if src == "notatka" else 0.0)
            warm_item = bool(_WARM.search(" ".join(str(x or "") for x in (r["model"], r["fabric"], notes)))) or (_f(r["r_insul"], 0) >= 3)
            if hi_t >= 18 and warm_item:
                sc -= 3.0
            sc += 2.0 if _PLUS2.search(notes) else 0.0
            sc += 1.0 if _PLUS1.search(notes) else 0.0
            sc -= 1.0 if _MINUS1.search(notes) else 0.0
            sc -= 0.5 if _MINUS05.search(notes) else 0.0
            if wet and _f(r["r_water"], 0) >= 3:
                sc += 1.0
        # niepakowna warstwa wierzchnia (nie da sie jej schowac) na dzien cieplejszy niz jej zakres -> odpada
        nb_max = _f((war.get("na_rowerze") or {}).get("max"), None)
        if k in ("kurtka", "kamizelka") and nb_max is not None and r["s_pack"] is not None and int(r["s_pack"]) < 1 \
                and b < 40 and nb_max > b:
            continue
        if int(r["id"]) in liked:
            sc += 0.7                                            # noszone z 'ok' na dluzszej jezdzie
        if int(r["id"]) in strong:
            sc += 2.5                                            # 'ok' w PODOBNYCH warunkach (decyzja 2026-10-04)
        if int(r["id"]) in recent:
            sc -= 0.7
        it = {"id": int(r["id"]), "warstwa": k, "kategoria": r["category"],
              "nazwa": ("%s %s" % (r["brand"] or "", r["model"] or "")).strip(), "kolor": r["color_q"] or r["color"],
              "zakres_c": [a, b], "zakres_z": src, "ostatnio_proponowane": int(r["id"]) in recent, "_score": round(sc, 2)}
        it["marka"] = (r["brand"] or "").strip()
        if r["g_len"]:
            it["dlugosc"] = r["g_len"]
        if r["g_layer"]:
            it["warstwowanie"] = {"chetnie": "chetnie", "potrzeba": "w razie potrzeby (niepreferowane)", "nie": "nie - tylko sama"}.get(r["g_layer"])
        if r["g_style"]:
            it["styl"] = "outdoorowy" if r["g_style"] == "outdoor" else "kolarski"
        oc = {lab: r[col] for col, lab in _SLAB if r[col] is not None}
        if oc:
            it["ankieta"] = oc                                  # skala -2..+2 (0 = przecietnie)
            it["ankieta_status"] = "potwierdzone przez Michala" if r["s_status"] == "ok" else "wstepne AI - niepewne"
        if audited:
            it["audyt"] = {x: v for x, v in (
                ("status", r["a_status"]), ("fit", r["a_fit"]), ("uzycie_2026", r["a_use"]), ("wysilek", r["a_effort"]),
                ("rola", r["a_role"]), ("deszcz_sprawdzony", r["a_rain"]), ("wiatr_ochrona", r["a_wind"]),
                ("mokra_wychladza", bool(int(r["a_wet_cold"] or 0))), ("wkladka_sprawdzona_h", _pad_eff(r) if k == "spodenki" else r["a_pad_h"]),
                ("wozenie_awaryjne", r["a_carry"]), ("komplety", r["a_pairs"]), ("uwagi", r["a_note"]),
                ("zrodlo", r["a_src"]), ("data", r["a_date"])) if v not in (None, "", False)}
        else:
            it.update({"sezon": r["season"], "ocena": r["rating"],
                       "material": (r["fabric"] or "")[:80], "notatka": re.sub(r"\s+", " ", notes)[:220]})
        out[k].append(it)
    for k in out:   # koszulka: wiecej kandydatow (dwa rozne tempa potrzebuja roznych koszulek)
        out[k] = sorted(out[k], key=lambda x: -x["_score"])[:(per_layer + 4 if k == "koszulka" else per_layer)]
    return {k: v for k, v in out.items() if v}


# ---------------- 3) historia jazd ----------------
def _v(x):
    return x.get("value") if isinstance(x, dict) and "value" in x else x


def historia_jazd(conn, limit: int = 12) -> list:
    """'W czym jechalem' + warunki z raportu z jazdy. Najnowsze najpierw."""
    try:
        g = sqlite3.connect(GARAGE_DB)
        g.row_factory = sqlite3.Row
        logs = g.execute("SELECT l.ride_key AS rk, l.slot, l.gear_id, l.value, l.updated_at, g.brand, g.model, g.category "
                         "FROM ride_gear_log l LEFT JOIN gear g ON g.id=l.gear_id ORDER BY l.updated_at DESC").fetchall()
        g.close()
    except Exception:
        return []
    rides, order = {}, []
    for r in logs:
        rk = r["rk"]
        if rk not in rides:
            rides[rk] = {"rzeczy": [], "_upd": r["updated_at"]}
            order.append(rk)
        d = rides[rk]
        if r["slot"].startswith("_"):
            d[r["slot"][1:]] = r["value"]
        elif r["gear_id"] is not None:
            d["rzeczy"].append({"id": r["gear_id"], "nazwa": ("%s %s" % (r["brand"] or "", r["model"] or "")).strip(),
                                "kategoria": r["category"]})
    order = order[:limit]
    w1 = {}
    if order:
        try:
            rows = conn.execute(
                "SELECT DISTINCT ON (ride_key) ride_key, w1_json->'weather' AS we, w1_json->'load' AS ld, "
                "w1_json->'ride' AS rd FROM qbot_v2.ride_report_data WHERE ride_key = ANY(%s) "
                "ORDER BY ride_key, schema_version DESC", (order,)).fetchall()
            conn.commit()
            for x in rows:
                x = _row(x, ("ride_key", "we", "ld", "rd"))
                w1[x["ride_key"]] = x
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
    # stare raporty bez sily wiatru / opadu -> dociagnij w tle (bedzie przy nastepnym doborze)
    try:
        from qbot3.rides.w1_weather_patch import patch_in_background
        miss = [k for k, x in w1.items() if not (_v((x.get("we") or {}).get("wind_ms")) and _v((x.get("we") or {}).get("precip_mm")))]
        if miss:
            patch_in_background(miss)
    except Exception:
        pass
    out = []
    for rk in order:
        d = rides[rk]
        x = w1.get(rk) or {}
        we, ld, rd = x.get("we") or {}, x.get("ld") or {}, x.get("rd") or {}
        dur = _f(_v(ld.get("dur_moving_s")))
        h = round(dur / 3600.0, 1) if dur else None
        typ = d.get("typ")
        e = {"data": rd.get("date"), "start": rd.get("time"), "dystans_km": rd.get("dist_km"), "typ": typ,
             "odczucie": d.get("odczucie"), "uwagi": d.get("uwagi"), "czas_ruchu_h": h,
             "IF": _v(ld.get("if")), "rzeczy": d["rzeczy"],
             "waga_komfortu": round(min(1.0, (h or 0) / 3.0), 2) if h else None,
             "rzeczy_licza_do_wyboru": typ in ("dluzsza", "wyprawa")}
        ap, tc = _v(we.get("apparent_c")), _v(we.get("temp_c"))
        if ap:
            e["odczuwalna"] = ap
        if tc:
            e["temp_licznik"] = tc
        if _v(we.get("wind_ms")):
            e["wiatr_ms"] = _v(we.get("wind_ms"))
        if _v(we.get("precip_mm")):
            e["opad"] = _v(we.get("precip_mm"))
        if _v(we.get("rh_pct")) is not None:
            e["wilgotnosc"] = _v(we.get("rh_pct"))
        if not x:
            e["warunki"] = "brak raportu z jazdy"
        out.append({k: v for k, v in e.items() if v not in (None, "", [])})
    return out


SIM_DT_C = 3.0             # podobna jazda: srednia temp. (Karoo) +-3 C od sredniej do ubioru
SIM_DWIND_MS = 2.5         # ... wiatr max +-2.5 m/s, sucho, odczucie ok, typ dluzsza/wyprawa


def _similar_ok(hist, war):
    """Najblizsza jazda 'ok' w podobnych warunkach -> punkt wyjscia doboru (decyzja Michala 2026-10-04)."""
    avg = _f((war.get("na_rowerze") or {}).get("srednia"))
    if avg is None or _rain_real(war):
        return None
    wmax = _f((war.get("wiatr_ms") or {}).get("max"), 0.0)
    best = None
    for e in hist:
        if not e.get("rzeczy_licza_do_wyboru") or (e.get("odczucie") or "ok") != "ok" or not e.get("rzeczy"):
            continue
        tc = e.get("temp_licznik")
        t = _f(tc.get("avg")) if isinstance(tc, dict) else _f(tc)
        if t is None or abs(t - avg) > SIM_DT_C:
            continue
        w = e.get("wiatr_ms")
        wm = _f(w.get("max") if isinstance(w, dict) else w, 0.0)
        if abs(wm - wmax) > SIM_DWIND_MS:
            continue
        op = e.get("opad")
        if _f(op.get("sum") if isinstance(op, dict) else op, 0.0) >= POCKET_RAIN_MM:
            continue
        d = abs(t - avg)
        if best is None or d < best[0]:
            best = (d, e, t, wm)
    if not best:
        return None
    _, e, t, wm = best
    return {"data": e.get("data"), "temp_srednia_karoo": t, "wiatr_max_ms": wm, "czas_ruchu_h": e.get("czas_ruchu_h"),
            "odczucie": "ok", "rzeczy": [it.get("nazwa") for it in e["rzeczy"]], "_ids": {int(it["id"]) for it in e["rzeczy"]},
            "co_z_tym": "PUNKT WYJSCIA: w podobnych warunkach ten zestaw byl ok - zacznij od niego (zestaw spokojniejszy). "
                       "Zmieniaj rzecz tylko z konkretnego powodu tej jazdy (dluzszy czas, dlugie postoje, brak slonca) i napisz jakiego."}


def _liked(hist) -> set:
    s = set()
    for e in hist:
        if e.get("rzeczy_licza_do_wyboru") and (e.get("odczucie") or "ok") == "ok":
            s.update(int(it["id"]) for it in e.get("rzeczy") or [])
    return s


# ---------------- 4) AI ----------------
SYS_FALLBACK = ("Jestes doswiadczonym kolarzem-doradca od ubioru na gravel. Piszesz po polsku, konkretnie. "
                "Dobierasz ubior WYLACZNIE z listy 'kandydaci' (pole id). Wiatr zawsze w m/s.")
SYS_FORMAT = ("\n\n## FORMAT ODPOWIEDZI\nZwracasz WYLACZNIE JSON. Jedna rzecz na warstwe w zestawie (pole 'warstwa' kandydata). "
              "Min. 4 rzeczy w zestawie. Rzeczy z warstwy 'spodnie' lub 'deszcz_dol' wymagaja rzeczy z warstwy 'spodenki' (z wkladka) w tym samym zestawie. "
              "Rzeczy 'do_kieszeni' tez tylko z kandydatow. Piszesz prostym jezykiem, zwracasz sie do Michala na TY ""(nie 'Michal woli', tylko 'wolisz').")


def _rules_text():
    try:
        return open(RULES_MD, encoding="utf-8").read()
    except Exception:
        return SYS_FALLBACK


def _zakres_txt(z):
    a, b = z
    if a <= -20 and b >= 40:
        return "bez ograniczen"
    if a <= -20:
        return "do %d C" % b
    if b >= 40:
        return "od %d C" % a
    return "%d..%d C" % (a, b)


def _prompt(war, kand, hist, rules):
    kk = {}
    for k, v in kand.items():
        kk[k] = []
        for it in v:
            d = {x: y for x, y in it.items() if not x.startswith("_") and x not in ("warstwa", "zakres_z", "zakres_c")}
            d["zestaw_uzywany_przy"] = _zakres_txt(it["zakres_c"])
            kk[k].append(d)
    return ("warunki (planowana jazda): " + json.dumps(war, ensure_ascii=False)
            + "\n\nkandydaci (warstwa -> rzeczy; 'audyt' = ocena Michala z audytu garderoby, 'zakres_c' = temperatura "
              "CALEGO zestawu w jakim rzecz byla uzywana - NIE uzasadniaj nia wyboru): " + json.dumps(kk, ensure_ascii=False)
            + "\n\nhistoria_jazd ('W czym jechalem' + warunki z raportu z jazdy, najnowsze najpierw): "
            + json.dumps(hist, ensure_ascii=False)
            + "\n\nreguly_ubioru (dodatkowe od uzytkownika): " + json.dumps(rules or [], ensure_ascii=False)
            + '\n\nZwroc JSON: {"warunki_krotko": "1-2 zdania o przebiegu warunkow w czasie jazdy",'
              ' "z_historii": "1 zdanie: co z Twoich jazd wplynelo na dobor (albo pusty)",'
              ' "zestawy": [{"tempo": "spokojniejsza" lub "szybsza", "nazwa": "krotka nazwa", "kiedy": "1 zdanie: kiedy ten zestaw",'
              ' "po_co": "1 zdanie: dlaczego te rzeczy przy TYM tempie (co daje wzgledem drugiego zestawu)",'
              ' "rzeczy": [{"id": liczba, "dlaczego": "1 zdanie z liczba", "zamienniki": [id, id] (opcjonalnie, 0-2, ta sama warstwa)}],'
              ' "do_kieszeni": [{"id": liczba, "dlaczego": "1 zdanie"}], "zdejmij": "co i kiedy zdjac / zalozyc (albo pusty)",'
              ' "kolory": "1 zdanie: jak zestaw uklada sie kolorystycznie",'
              ' "slaby_punkt": "1 zdanie: slaby punkt zestawu i co z nim zrobic"}]}'
              " - DOKLADNIE 2 zestawy: jeden tempo=spokojniejsza, drugi tempo=szybsza.")


def _valid(o, kand, war=None):
    if not isinstance(o, dict) or len(o.get("zestawy") or []) != 2:
        return "zle zestawy"
    ids = {it["id"]: it for v in kand.values() for it in v}
    tempa = sorted((z.get("tempo") or "") for z in o["zestawy"])
    if tempa != ["spokojniejsza", "szybsza"]:
        return "zestawy musza miec tempo: jeden 'spokojniejsza', drugi 'szybsza'"
    need = [k for k in ("buty", "skarpety", "rekawiczki") if kand.get(k)]
    dry = war is not None and (_f((war.get("deszcz") or {}).get("max_proc"), 0.0) < 10) and not war.get("dlugie_postoje")
    sets = []
    for z in o["zestawy"]:
        on = {int(it.get("id")) for it in (z.get("rzeczy") or []) if str(it.get("id", "")).lstrip("-").isdigit()}
        pk = {int(it.get("id")) for it in (z.get("do_kieszeni") or []) if str(it.get("id", "")).lstrip("-").isdigit()}
        if on & pk:
            return "ta sama rzecz na sobie i w kieszeni (id %s) - wybierz jedno" % ", ".join(str(i) for i in sorted(on & pk))
        layers_on = {ids[i]["warstwa"] for i in on if i in ids}
        miss = [k for k in need if k not in layers_on]
        if miss:
            return "brak w zestawie: %s" % ", ".join(miss)
        if dry and len(pk) > 1:
            return "sucha prognoza bez dlugich postojow: najwyzej 1 rzecz do kieszeni"
        if not (z.get("po_co") or "").strip():
            return "brak 'po_co' w zestawie"

        its = z.get("rzeczy") or []
        if len(its) < 4:
            return "za malo rzeczy w zestawie"
        seen = set()
        for it in its + (z.get("do_kieszeni") or []):
            try:
                i = int(it.get("id"))
            except Exception:
                return "zle id"
            if i not in ids:
                return "rzecz spoza kandydatow: %s" % i
            if it in its:
                lw = ids[i]["warstwa"]
                if lw in seen:
                    return "dwie rzeczy w jednej warstwie (%s)" % lw
                seen.add(lw)
            if not (it.get("dlaczego") or "").strip():
                return "brak uzasadnienia"
        if ("spodnie" in seen or "deszcz_dol" in seen) and "spodenki" not in seen:
            return "spodnie bez wkladki bez warstwy z wkladka (liner/bibsy)"
        sets.append({int(x["id"]) for x in its})
    if len(sets[0] ^ sets[1]) < 2:
        return "zestawy prawie takie same"
    return None


_ZAKRES_RE = re.compile(r"(zakres\w*|pasuj\w*|odpowiedni\w*|sprawdza\w*\s+si\w*|przewidzian\w*|uniwersaln\w*|u\u017cywan\w*|przy)"
                        r"[^.;]{0,40}\b(od|na|powy\u017cej|ponad)\s*-?\d+(\s*[\u2013-]\s*-?\d+)?\s*\u00b0\s*C"
                        r"|\bzakres\w*\s+(temperatur|od\s*-?\d)", re.I)


def _style(o):
    """Uzasadnienia 'zakresem temperatur rzeczy' sa zakazane (nic nie mowia) - wymus poprawke."""
    bad = []
    for z in (o or {}).get("zestawy") or []:
        for it in (z.get("rzeczy") or []) + (z.get("do_kieszeni") or []):
            if _ZAKRES_RE.search(it.get("dlaczego") or ""):
                bad.append(str(it.get("id")))
    return ("uzasadnienia zakresem temperatur (id: %s) - napisz, co ta rzecz daje w tych warunkach" % ", ".join(bad)) if bad else None


_WINTER_HEAD = re.compile(r"beanie|balaclava|skully|headband|kominiark|zimow", re.I)
_NEUTRAL = {"BLACK", "GREY", "NAVY"}


POCKET_RAIN_PROC = 30      # kurtka/spodnie deszczowe do kieszeni dopiero od tej szansy deszczu (albo prognozowane mm)
POCKET_RAIN_MM = 0.5       # ... albo od tylu mm w czasie jazdy (0.1 mm = szum prognozy, decyzja 2026-10-04)
POCKET_MAX_DRY = 2         # bez realnego deszczu najwyzej tyle rzeczy w kieszeni (decyzja Michala 2026-10-03)
WARM_ONE_MIN_C = 5         # od tej temp. do ubioru: najwyzej 1 warstwa od zimna/wiatru (na sobie + w kieszeni)


def _rain_real(war):
    r = (war or {}).get("deszcz") or {}
    return _f(r.get("max_proc"), 0.0) >= POCKET_RAIN_PROC or _f(r.get("suma_mm"), 0.0) >= POCKET_RAIN_MM


def _pocket_trim(o, kand, war):
    """Siatka bezpieczenstwa (decyzja Michala 2026-10-03): bez realnego deszczu nic deszczowego w kieszeni;
    najwyzej JEDNA warstwa od zimna/wiatru (kamizelka ALBO kurtka; przy dlugich postojach kurtka); bez deszczu max 2 rzeczy."""
    ids = {it["id"]: it for v in kand.values() for it in v}
    rain = _rain_real(war)
    stops = bool((war or {}).get("dlugie_postoje"))
    fixes = []
    for zi, z in enumerate(o.get("zestawy") or []):
        tag = "A" if zi == 0 else "B"
        pk = list(z.get("do_kieszeni") or [])
        lay = lambda it: (ids.get(int(it.get("id", -1))) or {}).get("warstwa")
        nm = lambda it: (ids.get(int(it.get("id", -1))) or {}).get("nazwa", str(it.get("id")))
        if not rain:
            for it in [i for i in pk if lay(i) in ("deszcz_gora", "deszcz_dol")]:
                pk.remove(it)
                fixes.append("%s: %s usunieta z kieszeni (szansa deszczu < %d%%, 0 mm)" % (tag, nm(it), POCKET_RAIN_PROC))
        warm = [i for i in pk if lay(i) in ("kamizelka", "kurtka")]
        if len(warm) > 1:
            pref = "kurtka" if stops else "kamizelka"
            keep = next((i for i in warm if lay(i) == pref), warm[0])
            for it in warm:
                if it is not keep:
                    pk.remove(it)
                    fixes.append("%s: %s usunieta z kieszeni (wystarczy %s)" % (tag, nm(it), nm(keep)))
        t_min = _f(((war or {}).get("na_rowerze") or {}).get("min"), 10.0)
        rz = z.get("rzeczy") or []
        worn = [i for i in rz if lay(i) in ("kamizelka", "kurtka")]
        pkw = [i for i in pk if lay(i) in ("kamizelka", "kurtka")]
        if worn and pkw and not rain and t_min >= WARM_ONE_MIN_C:
            for it in pkw:
                pk.remove(it)
                fixes.append("%s: %s usunieta z kieszeni (masz juz %s)" % (tag, nm(it), nm(worn[0])))
        # zimowa czapka przy >= 8 C -> czapka kolarska (regula 2026-09-25, AI ja ignorowalo)
        if t_min >= 8:
            for it in rz:
                c = ids.get(int(it.get("id", -1))) or {}
                if c.get("warstwa") == "glowa" and _WINTER_HEAD.search(c.get("nazwa", "")):
                    caps = sorted([x for x in kand.get("glowa", []) if not _WINTER_HEAD.search(x["nazwa"])], key=lambda x: -x["_score"])
                    if caps:
                        it.update({"id": caps[0]["id"], "zamienniki": [], "dlaczego": "Czapka kolarska pod kask - przy %.0f C zimowa niepotrzebna." % t_min})
                        fixes.append("%s: %s -> %s (za cieplo na zimowa czapke)" % (tag, c["nazwa"], caps[0]["nazwa"]))
        if not rain and len(pk) > POCKET_MAX_DRY:
            for it in pk[POCKET_MAX_DRY:]:
                fixes.append("%s: %s usunieta z kieszeni (limit %d rzeczy bez deszczu)" % (tag, nm(it), POCKET_MAX_DRY))
            pk = pk[:POCKET_MAX_DRY]
        z["do_kieszeni"] = pk
    return fixes


def _checks(o, kand, war, final=False):
    """Kontrole zestawu wymuszane w kodzie (decyzje Michala 2026-09-25). Zwraca liste uwag (pusta = ok)."""
    ids = {it["id"]: it for v in kand.values() for it in v}
    nb = war.get("na_rowerze") or {}
    t_min, t_max, t_avg = _f(nb.get("min"), 10.0), _f(nb.get("max"), 15.0), _f(nb.get("srednia"), 12.0)
    wind_need = bool(war.get("wiatr_ochrona_wymagana") or war.get("wiatr_ochrona_pod_reka"))
    reason_pocket = wind_need or bool(war.get("dlugie_postoje")) or t_min < 10 or _f((war.get("deszcz") or {}).get("max_proc"), 0) >= 30
    czas = _f(war.get("czas_h"), 0.0) or 0.0
    bad = []

    def pak(c):
        return _f((c.get("ankieta") or {}).get("pakownosc"), None)
    for zi, z in enumerate(o.get("zestawy") or []):
        tag = "zestaw %s" % ("A" if zi == 0 else "B")
        on = [ids[int(it["id"])] for it in z.get("rzeczy") or [] if int(it.get("id", -1)) in ids]
        onmap = {c["warstwa"]: c for c in on}
        dl = {int(it["id"]): (it.get("dlaczego") or "") for it in z.get("rzeczy") or []}
        pk = [ids[int(it["id"])] for it in z.get("do_kieszeni") or [] if int(it.get("id", -1)) in ids]
        # 1) komplet marki: gora marki X -> dol marki X, jesli jest odpowiedni
        top = onmap.get("koszulka") or onmap.get("kurtka")
        bot = onmap.get("spodenki")
        if top and bot and top.get("marka") and top["marka"].lower() != (bot.get("marka") or "").lower() \
                and "mieszam" not in dl.get(bot["id"], "").lower():
            ok_pad = (">6",) if czas >= 6 else ((">6", "4-6") if czas >= 4 else (">6", "4-6", "2-4"))
            same = [c for c in kand.get("spodenki", []) if (c.get("marka") or "").lower() == top["marka"].lower()
                    and ((c.get("audyt") or {}).get("wkladka_sprawdzona_h") in ok_pad)]
            if same:
                bad.append("%s: gora %s + dol %s - do gory tej marki jest dol %s (id %s); wez komplet albo napisz w 'dlaczego' "
                           "dolu slowo 'mieszam' i powod" % (tag, top["marka"], bot.get("marka"), same[0]["nazwa"], same[0]["id"]))
        # 2) warstwa wierzchnia na sobie przy cieplym dniu musi dac sie schowac
        if t_max >= 15:
            for c in on:
                if c["warstwa"] in ("kurtka", "kamizelka", "deszcz_gora") and (pak(c) is None or pak(c) < 1):
                    bad.append("%s: %s nie da sie schowac (pakownosc %s), a w dzien jest %.0f C do ubioru - nie planuj jej zdejmowania; "
                               "wybierz uklad z rzeczami do zdjecia i schowania (rekawki, kamizelka)" % (tag, c["nazwa"], pak(c), t_max))
        # 3) baza pod dlugi rekaw / bluze, ktorej nie da sie zdjac
        if onmap.get("baza_gora") and t_avg >= 13 and (onmap.get("kurtka") or (onmap.get("koszulka") or {}).get("dlugosc") == "dlugi"):
            bad.append("%s: baza pod dlugim rekawem/bluza przy sredniej %.0f C do ubioru - nie da sie jej zdjac w trasie" % (tag, t_avg))
        # 3b) koszulka techniczna (nie 'chetnie') z baza/rekawkami
        kc = onmap.get("koszulka")
        if kc and not (kc.get("warstwowanie") or "").startswith("chetnie") and (onmap.get("baza_gora") or onmap.get("rekawki")):
            bad.append("%s: %s nie jest do warstwowania - bez bazy i rekawkow; na chlodny start wez jersey kolarski 'chetnie'" % (tag, kc["nazwa"]))
        # 3c) wkladka > 6 h przy jezdzie >= 6 h
        sc_ = onmap.get("spodenki")
        if sc_ and czas >= 6 and (sc_.get("audyt") or {}).get("wkladka_sprawdzona_h") != ">6" and \
                any((c.get("audyt") or {}).get("wkladka_sprawdzona_h") == ">6" for c in kand.get("spodenki", [])):
            bad.append("%s: %s ma wkladke sprawdzona %s h, a jazda trwa %.1f h - wez spodenki z wkladka >6 h" %
                       (tag, sc_["nazwa"], (sc_.get("audyt") or {}).get("wkladka_sprawdzona_h"), czas))
        # 4) kamizelka w kieszeni tylko z powodem
        if not reason_pocket:
            for c in pk:
                if c["warstwa"] in ("kamizelka", "kurtka"):
                    bad.append("%s: %s w kieszeni bez powodu (slaby wiatr, bez dlugich postojow, start >= 10 C) - usun" % (tag, c["nazwa"]))
        # 4b) kieszen (decyzja Michala 2026-10-03): deszczowe tylko przy realnym deszczu, 1 warstwa ciepla, max 2 rzeczy
        rain_real = _rain_real(war)
        if not rain_real:
            for c in pk:
                if c["warstwa"] in ("deszcz_gora", "deszcz_dol"):
                    bad.append("%s: %s w kieszeni, a szansa deszczu < %d%% i 0 mm - usun" % (tag, c["nazwa"], POCKET_RAIN_PROC))
        warm_all = [c["nazwa"] for c in on + pk if c["warstwa"] in ("kamizelka", "kurtka")]
        if len(warm_all) > 1 and not rain_real and t_min >= WARM_ONE_MIN_C:
            bad.append("%s: %s - dwie warstwy od zimna/wiatru (zdjeta i tak laduje w kieszeni); zostaw JEDNA: przy dlugich "
                       "postojach ocieplana kurtka na zimny start i na postoje, inaczej kamizelka; dopasuj 'zdejmij'" % (tag, " + ".join(warm_all)))
        if not rain_real and len(pk) > POCKET_MAX_DRY:
            bad.append("%s: %d rzeczy w kieszeni bez deszczu - najwyzej %d" % (tag, len(pk), POCKET_MAX_DRY))
        # 5) nakrycie glowy wg temperatury
        g = onmap.get("glowa")
        if g and _WINTER_HEAD.search(g["nazwa"]) and t_min >= 8:
            caps = [c["nazwa"] for c in kand.get("glowa", []) if not _WINTER_HEAD.search(c["nazwa"])][:3]
            bad.append("%s: %s to czapka zimowa, a do ubioru jest >= 8 C - wez czapke kolarska (%s)" % (tag, g["nazwa"], ", ".join(caps)))
        # 6) kolory dodatkow w palecie zestawu - tylko PODPOWIEDZ dla AI (nie w gotowej poradzie)
        fams = _palette(z.get("rzeczy") or [], ids)
        for lay in (() if final else ("buty", "rekawiczki", "skarpety", "glowa")):
            c = onmap.get(lay)
            if not c:
                continue
            want = _want_fams(lay, fams)
            pool = [x for x in kand.get(lay, []) if x["id"] != c["id"]]
            target = next((fm for fm in want if _fam(c.get("kolor")) == fm or any(_fam(x.get("kolor")) == fm for x in pool)), "neutral")
            if _fam(c.get("kolor")) != target:
                bad.append("%s: podpowiedz - %s (%s) nie pasuje kolorem do zestawu (%s); zmien TYLKO jesli jest rzecz rownie dobra "
                           "funkcjonalnie w tych warunkach (temperatura, wentylacja, deszcz), inaczej zostaw" %
                           (tag, c["nazwa"], c.get("kolor"), ", ".join(want)))
    return bad


_TO_BAG = re.compile(r"w\u0142\u00f3\u017c do (torby|kieszeni|torebki)|do torby|do kieszeni|na post\u00f3j", re.I)


_THERMAL_SOCK = re.compile(r"thermolite|primaloft|winter|zimow|alpha|thermal|ultraz|merino reflective", re.I)
_FAM = {"BLACK": "neutral", "GREY": "neutral", "NAVY": "navy", "GREEN": "green", "OLIVE": "green", "BROWN": "brown",
        "BEIGE": "brown", "ORANGE": "orange", "RED": "red", "BLUE": "blue", "WHITE": "white", "MULTI": "multi"}


def _fam(color):
    return _FAM.get((color or "").upper(), "neutral")


def _palette(items, ids):
    """Rodziny kolorow glownych rzeczy zestawu (koszulka, spodenki, kurtka/kamizelka na sobie), bez neutralnych."""
    by = {}
    for i in items:
        c = ids.get(int(i["id"])) if isinstance(i, dict) else None
        if c and c["warstwa"] in ("koszulka", "spodenki", "spodnie", "kurtka", "kamizelka"):
            by.setdefault(c["warstwa"], _fam(c.get("kolor")))
    return by


def _want_fams(lay, by):
    """Kolejnosc rodzin dla dodatku: buty -> kolor dolu, reszta -> kolor gory; potem drugi kolor; na koncu neutralne."""
    top = by.get("koszulka") or by.get("kurtka") or by.get("kamizelka")
    bot = by.get("spodenki") or by.get("spodnie")
    if lay == "glowa":                       # czapka: neutralna, kolor tylko gdy brak neutralnej
        return ["neutral"] + [f for f in (top, bot) if f and f not in ("neutral", "multi")]
    order = [bot, top] if lay == "buty" else [top, bot]
    out = [f for f in order if f and f not in ("neutral", "multi")]
    return out + ["neutral"] if out else ["neutral"]


_PLC = {"BLACK": "czarny", "GREY": "szary", "NAVY": "granatowy", "BEIGE": "be\u017cowy", "OLIVE": "oliwkowy", "BROWN": "br\u0105zowy",
        "WHITE": "bia\u0142y", "GREEN": "zielony", "ORANGE": "pomara\u0144czowy", "RED": "czerwony", "BLUE": "niebieski", "MULTI": "wielokolorowy"}
_BASE_NEUTRAL = {"BLACK", "GREY", "NAVY", "BEIGE", "OLIVE", "BROWN"}


def _kolory(items):
    """Opis kolorow z FAKTYCZNEGO zestawu (po autokorekcie) - nie z tekstu AI."""
    neu, acc = [], []
    for it in items:
        k = (it.get("kolor") or "").upper()
        if not k:
            continue
        name = _PLC.get(k, k.lower())
        if k in _BASE_NEUTRAL:
            if name not in neu:
                neu.append(name)
        else:
            acc.append("%s (%s)" % (name, it.get("nazwa", "")[:28]))
    txt = "Baza: " + (", ".join(neu) if neu else "brak neutralnej bazy")
    if not acc:
        return txt + "; bez mocnych akcentow."
    if len({a.split(" (")[0] for a in acc}) == 1:
        return txt + "; jeden akcent: " + ", ".join(acc) + "."
    return txt + "; UWAGA - kilka akcentow: " + ", ".join(acc) + "."


def _dedupe(o, war):
    """Rzecz na sobie i w kieszeni naraz: przy wymaganej ochronie od wiatru zostaje na sobie, inaczej w kieszeni."""
    keep_on = bool((war or {}).get("wiatr_ochrona_wymagana"))
    for z in (o or {}).get("zestawy") or [] if isinstance(o, dict) else []:
        try:
            on = {int(i.get("id")) for i in z.get("rzeczy") or []}
            pk = {int(i.get("id")) for i in z.get("do_kieszeni") or []}
        except Exception:
            continue
        both = on & pk
        if not both:
            continue
        if keep_on:
            z["do_kieszeni"] = [i for i in z.get("do_kieszeni") or [] if int(i.get("id")) not in both]
        else:
            z["rzeczy"] = [i for i in z.get("rzeczy") or [] if int(i.get("id")) not in both]


def _autofix(o, kand, war):
    """Deterministyczne poprawki tam, gdzie AI ignoruje uwagi: komplet marki, neutralne dodatki, rzecz 'do torby'.
    Zwraca liste opisow poprawek."""
    ids = {it["id"]: it for v in kand.values() for it in v}
    czas = _f(war.get("czas_h"), 0.0) or 0.0
    ok_pad = (">6",) if czas >= 6 else ((">6", "4-6") if czas >= 4 else (">6", "4-6", "2-4"))
    fixes = []
    for zi, z in enumerate(o.get("zestawy") or []):
        tag = "A" if zi == 0 else "B"
        rz = z.get("rzeczy") or []
        # (a) koszulka niepreferowana do warstw + baza/rekawki -> jersey kolarski 'chetnie'
        cur = {(ids.get(int(i["id"])) or {}).get("warstwa"): i for i in rz}
        tk = cur.get("koszulka")
        tkc = ids.get(int(tk["id"])) if tk else None
        if tkc and not (tkc.get("warstwowanie") or "").startswith("chetnie") and (cur.get("baza_gora") or cur.get("rekawki")):
            alts = [c for c in kand.get("koszulka", []) if (c.get("warstwowanie") or "").startswith("chetnie") and c["id"] != tkc["id"]]
            alts.sort(key=lambda c: (0 if c.get("dlugosc") == tkc.get("dlugosc") else 1, -c["_score"]))
            if alts:
                n = alts[0]
                tk.update({"id": n["id"], "zamienniki": [], "dlaczego": "Jersey kolarski do warstw (rekawki/gilet) zamiast %s, "
                           "ktorej nie warstwujesz." % tkc["nazwa"]})
                fixes.append("%s: %s -> %s (koszulki technicznej nie warstwujesz)" % (tag, tkc["nazwa"], n["nazwa"]))
        # (b) wkladka przed marka: jazda >= 6 h -> tylko wkladki sprawdzone > 6 h
        sp = cur.get("spodenki")
        spc = ids.get(int(sp["id"])) if sp else None
        if spc and czas >= 6 and (spc.get("audyt") or {}).get("wkladka_sprawdzona_h") != ">6":
            topc = ids.get(int((cur.get("koszulka") or cur.get("kurtka") or {"id": -1})["id"])) or {}
            good = [c for c in kand.get("spodenki", []) if (c.get("audyt") or {}).get("wkladka_sprawdzona_h") == ">6"]
            good.sort(key=lambda c: (0 if (c.get("marka") or "").lower() == (topc.get("marka") or "").lower() else 1, -c["_score"]))
            if good:
                n = good[0]
                sp.update({"id": n["id"], "zamienniki": [], "dlaczego": "Wkladka sprawdzona >6 h na %.1f h jazdy (zamiast %s: %s h)." %
                           (czas, spc["nazwa"], (spc.get("audyt") or {}).get("wkladka_sprawdzona_h"))})
                fixes.append("%s: %s -> %s (wkladka >6 h na %.1f h)" % (tag, spc["nazwa"], n["nazwa"], czas))
        onmap = {}
        for it in rz:
            c = ids.get(int(it["id"]))
            if c:
                onmap[c["warstwa"]] = (it, c)
        # rzecz wierzchnia opisana "do torby / na postoj" -> do kieszeni
        for it in list(rz):
            c = ids.get(int(it["id"]))
            if c and c["warstwa"] in ("kamizelka", "kurtka") and _TO_BAG.search(it.get("dlaczego") or "") and \
                    not any(int(p.get("id", -1)) == c["id"] for p in z.get("do_kieszeni") or []):
                rz.remove(it)
                z.setdefault("do_kieszeni", []).append({"id": c["id"], "dlaczego": it.get("dlaczego")})
                fixes.append("%s: %s przeniesiona do kieszeni (opis mowi 'do torby')" % (tag, c["nazwa"]))
        # komplet marki
        top = (onmap.get("koszulka") or onmap.get("kurtka") or (None, None))[1]
        bot = onmap.get("spodenki")
        if top and bot and top.get("marka") and top["marka"].lower() != (bot[1].get("marka") or "").lower() \
                and "mieszam" not in (bot[0].get("dlaczego") or "").lower():
            same = sorted([c for c in kand.get("spodenki", []) if (c.get("marka") or "").lower() == top["marka"].lower()
                           and (c.get("audyt") or {}).get("wkladka_sprawdzona_h") in ok_pad], key=lambda c: -c["_score"])
            if same:
                n = same[0]
                old = bot[1]["nazwa"]
                bot[0].update({"id": n["id"], "zamienniki": [old_id for old_id in [bot[1]["id"]]],
                               "dlaczego": "Komplet z %s: wkladka sprawdzona %s h na %.1f h jazdy." % (
                                   top["nazwa"], (n.get("audyt") or {}).get("wkladka_sprawdzona_h"), czas)})
                fixes.append("%s: %s -> %s (komplet marki %s)" % (tag, old, n["nazwa"], top["marka"]))
        # dodatki w palecie zestawu (decyzja Michala 2026-09-25): zielona gora + brazowy dol -> brazowe buty,
        # zielone rekawiczki, oliwkowe/zielone skarpety; zestaw czarno-szary -> dodatki neutralne
        fams = _palette(rz, ids)
        for lay in ("buty", "rekawiczki", "skarpety", "glowa"):
            it = next((i for i in rz if (ids.get(int(i["id"])) or {}).get("warstwa") == lay), None)
            if not it:
                continue
            c = ids[int(it["id"])]
            want = _want_fams(lay, fams)
            winter_ok = _f((war.get("na_rowerze") or {}).get("min"), 10) < 8
            # TYLKO ten sam model w innym kolorze (funkcja bez zmian); inne modele wybiera AI (funkcja przed kolorem)
            pool = [x for x in kand.get(lay, []) if x["id"] != c["id"] and x["nazwa"] == c["nazwa"]]
            # pierwsza rodzina z listy, dla ktorej jest rzecz (obecna albo z puli) = docelowa
            target = next((fm for fm in want if _fam(c.get("kolor")) == fm or any(_fam(x.get("kolor")) == fm for x in pool)), "neutral")
            if _fam(c.get("kolor")) == target:
                continue
            best = None
            for fam in [target]:
                cand = sorted([x for x in pool if _fam(x.get("kolor")) == fam], key=lambda x: -x["_score"])
                if cand:
                    best = cand[0]
                    break
            if best:
                it.update({"id": best["id"], "zamienniki": [c["id"]]})
                fixes.append("%s: %s (%s) -> %s (%s) - kolor do zestawu" % (tag, c["nazwa"], c.get("kolor"), best["nazwa"], best.get("kolor")))
    # nazwy zestawow: marka dolu po autokorekcie (np. "POC + Albion" -> "POC + POC" -> "POC")
    for z in o.get("zestawy") or []:
        nm = z.get("nazwa") or ""
        for it in z.get("rzeczy") or []:
            c = ids.get(int(it["id"]))
            if not c or c["warstwa"] != "spodenki":
                continue
            for other in {x.get("marka") for x in kand.get("spodenki", []) if x.get("marka")}:
                if other and other != c.get("marka") and other in nm:
                    nm = nm.replace(other, c.get("marka") or other)
        nm = re.sub(r"\b(\w+)\s*\+\s*\1\b", r"\1", nm)      # "POC + POC" -> "POC"
        z["nazwa"] = nm.strip()
    return fixes


_TXT_Z = ("nazwa", "kiedy", "po_co", "zdejmij", "slaby_punkt")


def _retext(o, kand, fx):
    """Po autokorekcie (usuniete/zamienione rzeczy) teksty AI moga mowic o rzeczach, ktorych juz nie ma
    (np. 'kurtke zaloz na postoje'). Jedno krotkie wywolanie AI przepisuje TYLKO teksty pod koncowe listy.
    Zwraca None gdy OK, inaczej uwage do kontroli (teksty zostaja stare). Decyzja Michala 2026-10-04."""
    from qgpt_client import qgpt_json
    ids = {it["id"]: it for v in kand.values() for it in v}
    nm = lambda it: (ids.get(int(it.get("id", -1))) or {}).get("nazwa", "?")
    zs = o.get("zestawy") or []
    inp = {"zmiany_automatyczne": fx, "z_historii": o.get("z_historii") or "",
           "zestawy": [{"na_sobie": [nm(i) for i in z.get("rzeczy") or []],
                        "w_kieszeni": [nm(i) for i in z.get("do_kieszeni") or []],
                        **{k: z.get(k) or "" for k in _TXT_Z}} for z in zs]}
    prompt = ("Po automatycznej korekcie zestawow ubioru teksty moga wspominac rzeczy, ktorych juz NIE MA "
              "(usuniete z kieszeni albo zamienione). Popraw teksty tak, by mowily WYLACZNIE o rzeczach z list "
              "'na_sobie' i 'w_kieszeni'. Zdejmowanie rzeczy NOSZONEJ (np. kamizelki, nogawek) i chowanie jej do kieszeni jest OK - "
              "zostaw takie zdania. Nie wolno tylko kazac wyjmowac/zakladac rzeczy, ktorej nie ma w zadnej liscie. "
              "Zdanie o usunietej rzeczy zastap tym, co realnie masz (np. na postoj zaloz z powrotem zdjeta kamizelke). Nie zmieniaj list, sensu ani dlugosci bardziej niz trzeba; "
              "teksty bez problemu przepisz bez zmian. Po polsku.\n"
              "Zwroc TYLKO JSON: {\"z_historii\": \"...\", \"zestawy\": [{\"nazwa\": \"...\", \"kiedy\": \"...\", "
              "\"po_co\": \"...\", \"zdejmij\": \"...\", \"slaby_punkt\": \"...\"}]} w tej samej kolejnosci.\n\n"
              + json.dumps(inp, ensure_ascii=False))
    try:
        r = qgpt_json(prompt, system="Redaktor tekstow doradcy ubioru rowerowego. Tylko JSON.", max_tokens=1500, temperature=0.2)
        rz = r.get("zestawy") if isinstance(r, dict) else None
        if not isinstance(rz, list) or len(rz) != len(zs):
            return "teksty po autokorekcie nieprzepisane (zla odpowiedz AI) - moga wspominac usuniete rzeczy"
        for z, n in zip(zs, rz):
            for k in _TXT_Z:
                if isinstance(n, dict) and isinstance(n.get(k), str) and (n[k].strip() or not z.get(k)):
                    z[k] = n[k].strip()
        if isinstance(r.get("z_historii"), str):
            o["z_historii"] = r["z_historii"].strip()
        return None
    except Exception as e:
        return "teksty po autokorekcie nieprzepisane (%s) - moga wspominac usuniete rzeczy" % type(e).__name__


def advise(conn, data: dict, start: str, rules=None, model_name: str = "", long_stops: int = 0, long_stop_min: int = 0,
           route_id: str | None = None, ride_date: str | None = None) -> dict:
    from qgpt_client import qgpt_json
    t0 = time.perf_counter()
    war = warunki(data, start, long_stops, long_stop_min)
    hist = historia_jazd(conn)
    sim = _similar_ok(hist, war)
    if sim:
        war["podobna_jazda_ok"] = {k: v for k, v in sim.items() if not k.startswith("_")}
    kand = kandydaci(war, recent_ids(conn, skip=(route_id, ride_date)), liked=_liked(hist),
                     strong=sim["_ids"] if sim else None)
    if not kand:
        return {"ok": False, "blad": "brak pasujacych rzeczy w garazu"}
    system = _rules_text() + SYS_FORMAT
    o, err, fix = None, None, ""
    for attempt in range(2):
        try:
            o = qgpt_json(_prompt(war, kand, hist, rules) + fix, system=system, max_tokens=5000, temperature=0.5)
        except Exception as e:  # noqa
            o, err = None, "wyjatek: " + str(e)[:120]
        _dedupe(o, war)
        err = _valid(o, kand, war)
        if not err and attempt < 1:
            err = _style(o)
        if not err:
            ch = _checks(o, kand, war)
            if ch and attempt < 1:
                err = "; ".join(ch)
        if not err:
            break
        fix = "\n\nPOPRZEDNIA ODPOWIEDZ ODRZUCONA: " + err + ". Popraw i zwroc caly JSON."
    if err:
        return {"ok": False, "blad": err, "warunki": war}
    fx = _autofix(o, kand, war) + _pocket_trim(o, kand, war)
    if _valid(o, kand, war):          # poprawki nie moga zepsuc podstaw
        return {"ok": False, "blad": "autokorekta zepsula zestaw", "warunki": war}
    o["_kontrola_uwagi"] = ["poprawione automatycznie: " + f for f in fx] + _checks(o, kand, war, final=True)
    if fx:
        note = _retext(o, kand, fx)
        if note:
            o["_kontrola_uwagi"].append(note)
    ids = {it["id"]: it for v in kand.values() for it in v}
    for z in o["zestawy"]:
        for key in ("rzeczy", "do_kieszeni"):
            for it in z.get(key) or []:
                c = ids[int(it["id"])]
                it.update({"id": c["id"], "nazwa": c["nazwa"], "kategoria": c["kategoria"], "warstwa": c["warstwa"], "kolor": c["kolor"]})
                zm = []   # zamienniki: miekko - odrzucamy bledne (inna warstwa, spoza kandydatow, ta sama rzecz)
                for j in (it.get("zamienniki") if isinstance(it.get("zamienniki"), list) else [])[:2]:
                    try:
                        cj = ids.get(int(j))
                    except Exception:
                        cj = None
                    if cj and cj["warstwa"] == c["warstwa"] and cj["id"] != c["id"]:
                        zm.append({"id": cj["id"], "nazwa": cj["nazwa"], "kolor": cj["kolor"]})
                it["zamienniki"] = zm
        z["rzeczy"].sort(key=lambda x: LAYER_KEYS.index(x["warstwa"]))
        z["kolory"] = _kolory(z["rzeczy"])
    o["zestawy"].sort(key=lambda z: 0 if z.get("tempo") == "spokojniejsza" else 1)
    return {"ok": True, "wersja": VERSION, "model": model_name, "czas_s": round(time.perf_counter() - t0, 1),
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "warunki": war, "warunki_krotko": o.get("warunki_krotko"), "z_historii": o.get("z_historii"),
            "zestawy": o["zestawy"], "kandydatow": sum(len(v) for v in kand.values()), "jazd_w_historii": len(hist),
            "kontrola_uwagi": o.get("_kontrola_uwagi") or []}


# ---------------- zapis ----------------
def ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS qbot_v2.route_outfit (id bigserial PRIMARY KEY, route_id text NOT NULL, "
                 "ride_date date NOT NULL, start_time text, long_stops int, long_stop_min int, "
                 "created_at timestamptz NOT NULL DEFAULT now(), model text, proposal jsonb NOT NULL)")


def save(conn, route_id, date, start, n, m, prop):
    ensure(conn)
    conn.execute("INSERT INTO qbot_v2.route_outfit (route_id, ride_date, start_time, long_stops, long_stop_min, model, proposal) "
                 "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)", (route_id, date, start, n, m, prop.get("model"), json.dumps(prop, ensure_ascii=False)))
    conn.commit()


def load_last(conn, route_id, date):
    ensure(conn)
    r = conn.execute("SELECT proposal, start_time, long_stops, long_stop_min FROM qbot_v2.route_outfit WHERE route_id=%s AND ride_date=%s "
                     "ORDER BY created_at DESC LIMIT 1", (route_id, date)).fetchone()
    conn.commit()
    if not r:
        return None
    r = dict(r) if isinstance(r, dict) else dict(zip(("proposal", "start_time", "long_stops", "long_stop_min"), r))
    p = r["proposal"] if not isinstance(r["proposal"], str) else json.loads(r["proposal"])
    p["plan"] = {"start": r["start_time"], "long_stops": r["long_stops"], "long_stop_min": r["long_stop_min"]}
    return p
