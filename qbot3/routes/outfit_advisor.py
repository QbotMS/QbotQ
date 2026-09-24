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
VERSION = 2
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
LAYER_KEYS = [k for k, _ in LAYERS]
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
_WEATHER_LAYERS = ("kurtka", "kamizelka", "spodnie", "rekawiczki", "buty", "nogawki", "ochraniacze")


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
    out = {"start": start, "meta": _fmt(meta) if meta is not None else None, "czas_h": _f(tm.get("total_h"))}
    if long_stops:
        out["dlugie_postoje"] = {"ile": int(long_stops), "min_kazdy": int(long_stop_min or 0)}
    if fe:
        lo = min(fe, key=lambda x: x[1]); hi = max(fe, key=lambda x: x[1])
        out["odczuwalna"] = {"start": fe[0][1], "koniec": fe[-1][1], "min": lo[1], "min_o": lo[0], "max": hi[1], "max_o": hi[0],
                             "rozrzut": round(hi[1] - lo[1], 1)}
        out["przebieg"] = [{"godz": o, "odczuwalna": v} for o, v in fe]
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


def recent_ids(conn, n=3) -> set:
    try:
        ensure(conn)
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


def _layer(r, cat2layer):
    cat = r["category"]
    if cat == _WARMERS:
        return "nogawki" if _LEG.search(r["model"] or "") else "rekawki"
    k = cat2layer.get(cat)
    if k == "spodnie" and r["a_pad_h"] not in (None, "", "0"):
        return "spodenki"                  # np. POC 179 (bibsy z wkladka w kategorii 'bez wkladki'), tights z wkladka
    return k


def _gear_rows():
    g = sqlite3.connect(GARAGE_DB)
    g.row_factory = sqlite3.Row
    have = {r["name"] for r in g.execute("PRAGMA table_info(gear)")}
    acols = [c for c in ("a_status", "a_fit", "a_use", "a_temp_min", "a_temp_max", "a_effort", "a_rain", "a_wind",
                         "a_wet_cold", "a_pad_h", "a_carry", "a_role", "a_pairs", "a_note", "a_out", "a_src", "a_date")]
    sel = ", ".join(c if c in have else "NULL AS %s" % c for c in acols)
    rows = g.execute("SELECT id, category, brand, model, color, season, rating, r_insul, r_wind, r_water, r_breath, fabric, notes, "
                     + sel + " FROM gear WHERE active=1").fetchall()
    g.close()
    return rows


def kandydaci(war: dict, recent: set, per_layer: int = 7, liked: set | None = None) -> dict:
    fe = war.get("odczuwalna") or {}
    lo_t, hi_t = _f(fe.get("min"), 10.0), _f(fe.get("max"), 15.0)
    rain = war.get("deszcz") or {}
    wet = rain.get("max_proc", 0) >= 40
    heavy = _f(rain.get("suma_mm"), 0.0) >= 5
    czas = _f(war.get("czas_h"), 0.0) or 0.0
    cold_stops = bool(war.get("dlugie_postoje")) or czas >= 4 or bool(war.get("meta_po_zmroku"))
    windy = _f((war.get("wiatr_ms") or {}).get("max"), 0.0) >= 6 and lo_t < 15
    liked = liked or set()
    cat2layer = {c: k for k, cs in LAYERS for c in cs}
    out = {k: [] for k in LAYER_KEYS}
    for r in _gear_rows():
        k = _layer(r, cat2layer)
        if not k:
            continue
        audited = bool(r["a_date"])
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
        if ov <= 0 and k not in ("kamizelka", "kurtka", "rekawki", "nogawki"):
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
            if windy and k in ("kurtka", "kamizelka") and r["a_wind"] in ("mocna", "umiarkowana"):
                sc += 0.7
            if k == "spodenki" and r["a_pad_h"]:
                sc += (PAD_LONG if czas >= 5 else PAD_MID if czas >= 3 else {}).get(r["a_pad_h"], 0.0)
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
        if int(r["id"]) in liked:
            sc += 0.7                                            # noszone z 'ok' na dluzszej jezdzie
        if int(r["id"]) in recent:
            sc -= 0.7
        it = {"id": int(r["id"]), "warstwa": k, "kategoria": r["category"],
              "nazwa": ("%s %s" % (r["brand"] or "", r["model"] or "")).strip(), "kolor": r["color"],
              "zakres_c": [a, b], "zakres_z": src, "ostatnio_proponowane": int(r["id"]) in recent, "_score": round(sc, 2)}
        if audited:
            it["audyt"] = {x: v for x, v in (
                ("status", r["a_status"]), ("fit", r["a_fit"]), ("uzycie_2026", r["a_use"]), ("wysilek", r["a_effort"]),
                ("rola", r["a_role"]), ("deszcz_sprawdzony", r["a_rain"]), ("wiatr_ochrona", r["a_wind"]),
                ("mokra_wychladza", bool(int(r["a_wet_cold"] or 0))), ("wkladka_sprawdzona_h", r["a_pad_h"]),
                ("wozenie_awaryjne", r["a_carry"]), ("komplety", r["a_pairs"]), ("uwagi", r["a_note"]),
                ("zrodlo", r["a_src"]), ("data", r["a_date"])) if v not in (None, "", False)}
        else:
            it.update({"sezon": r["season"], "ocena": r["rating"],
                       "oceny": {k2: r[k2] for k2 in ("r_insul", "r_wind", "r_water", "r_breath") if r[k2] is not None},
                       "material": (r["fabric"] or "")[:80], "notatka": re.sub(r"\s+", " ", notes)[:220]})
        out[k].append(it)
    for k in out:
        out[k] = sorted(out[k], key=lambda x: -x["_score"])[:per_layer]
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
              "Min. 4 rzeczy w zestawie. Spodnie z warstwy 'spodnie' wymagaja rzeczy z warstwy 'spodenki' w tym samym zestawie. "
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
              ' "zestawy": [{"nazwa": "krotka nazwa, np. Lzejszy / Cieplejszy", "kiedy": "1 zdanie: kiedy ten zestaw",'
              ' "rzeczy": [{"id": liczba, "dlaczego": "1 zdanie z liczba"}],'
              ' "do_kieszeni": [{"id": liczba, "dlaczego": "1 zdanie"}], "zdejmij": "co i kiedy zdjac (albo pusty)",'
              ' "slaby_punkt": "1 zdanie: slaby punkt zestawu i co z nim zrobic"}]}'
              " - DOKLADNIE 2 zestawy.")


def _valid(o, kand):
    if not isinstance(o, dict) or len(o.get("zestawy") or []) != 2:
        return "zle zestawy"
    ids = {it["id"]: it for v in kand.values() for it in v}
    sets = []
    for z in o["zestawy"]:
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
        if "spodnie" in seen and "spodenki" not in seen:
            return "spodnie bez wkladki bez warstwy z wkladka (liner/bibsy)"
        sets.append({int(x["id"]) for x in its})
    if len(sets[0] ^ sets[1]) < 2:
        return "zestawy prawie takie same"
    return None


def advise(conn, data: dict, start: str, rules=None, model_name: str = "", long_stops: int = 0, long_stop_min: int = 0) -> dict:
    from qgpt_client import qgpt_json
    t0 = time.perf_counter()
    war = warunki(data, start, long_stops, long_stop_min)
    hist = historia_jazd(conn)
    kand = kandydaci(war, recent_ids(conn), liked=_liked(hist))
    if not kand:
        return {"ok": False, "blad": "brak pasujacych rzeczy w garazu"}
    system = _rules_text() + SYS_FORMAT
    o, err = None, None
    for _ in range(2):
        try:
            o = qgpt_json(_prompt(war, kand, hist, rules), system=system, max_tokens=5000, temperature=0.5)
        except Exception as e:  # noqa
            o, err = None, "wyjatek: " + str(e)[:120]
        err = _valid(o, kand)
        if not err:
            break
    if err:
        return {"ok": False, "blad": err, "warunki": war}
    ids = {it["id"]: it for v in kand.values() for it in v}
    for z in o["zestawy"]:
        for key in ("rzeczy", "do_kieszeni"):
            for it in z.get(key) or []:
                c = ids[int(it["id"])]
                it.update({"id": c["id"], "nazwa": c["nazwa"], "kategoria": c["kategoria"], "warstwa": c["warstwa"], "kolor": c["kolor"]})
        z["rzeczy"].sort(key=lambda x: LAYER_KEYS.index(x["warstwa"]))
    return {"ok": True, "wersja": VERSION, "model": model_name, "czas_s": round(time.perf_counter() - t0, 1),
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "warunki": war, "warunki_krotko": o.get("warunki_krotko"), "z_historii": o.get("z_historii"),
            "zestawy": o["zestawy"], "kandydatow": sum(len(v) for v in kand.values()), "jazd_w_historii": len(hist)}


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
