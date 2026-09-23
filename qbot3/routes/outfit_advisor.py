"""Dobor ubioru na jazde z garazu (garage.db gear) dla KONKRETNEGO planu (godzina + przerwy).

1) warunki(plan)   - przebieg warunkow W CZASIE jazdy (okna 30 min z warstwy planu, bez AI)
2) kandydaci(...)  - cala szafa oceniona dla tej jazdy: zakres temp z notatki (albo z sezonu/ocieplenia),
                     znaczniki (GLOWNA/ULUBIONY +, RZADKO/NIE TESTOWANA -, WYCOFANA/ZA MALA/WISI/ZAGUBIONA out),
                     ocena, rotacja (ostatnio proponowane lekko w dol). Do AI: top 6 na warstwe.
3) AI              - 2 rozne zestawy wylacznie z kandydatow; kazda rzecz z uzasadnieniem liczba z warunkow.
Zapis: qbot_v2.route_outfit (historia propozycji -> rotacja, wyswietlanie).
Historia 'W czym jechalem' (ride_gear_log) - podpinana w kolejnym kroku.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import re
import sqlite3
import time

GARAGE_DB = "/opt/qbot/app/data/garage.db"
VERSION = 1
LAYERS = [
    ("baza_gora", ["Bielizna termoaktywna \u2014 g\u00f3ra"]),
    ("koszulka", ["Koszulka kr\u00f3tki r\u0119kaw", "Koszulka d\u0142ugi r\u0119kaw", "Koszulka techniczna"]),
    ("kamizelka", ["Kamizelka"]),
    ("kurtka", ["Kurtka"]),
    ("baza_dol", ["Bielizna termoaktywna \u2014 d\u00f3\u0142"]),
    ("dol", ["Spodenki z wk\u0142adk\u0105", "Spodnie rowerowe (bez wk\u0142adki)", "Spodnie termiczne"]),
    ("rekawki", ["R\u0119kawki i nogawki"]),
    ("rekawiczki", ["R\u0119kawiczki"]),
    ("glowa", ["Nakrycie g\u0142owy"]),
    ("szyja", ["Komin i chusta"]),
    ("skarpety", ["Skarpety"]),
    ("ochraniacze", ["Ochraniacze na buty"]),
]
SEASON_RANGE = {"lato": (16, 30), "przejsciowy": (6, 18), "zima": (-10, 6)}
_WARM = re.compile(r"primaloft|insulat|ocieplan|thermal|termiczn|puch|down|winter|zimow|fleece|polar|alpha|hoodie", re.I)
_TEMP = re.compile(r"(-?\+?\d{1,2})\s*(?:\u00b0C)?\s*(?:\u2026|\.\.\.|\u2013|-|do)\s*\+?(-?\d{1,2})\s*\u00b0\s*C", re.I)
_OUT = re.compile(r"WYCOFAN|ZA MA[\u0141L][AEY]|WISI W SZAFIE|NIE WYBIERA|ZAGUBION", re.I)
_PLUS2 = re.compile(r"G[\u0141L]\u00d3WN[AY]", re.I)
_PLUS1 = re.compile(r"ULUBION", re.I)
_MINUS1 = re.compile(r"RZADKO|\u0179LE LE\u017bY|ZLE LEZY|RZADKO WYBIERAN", re.I)
_MINUS05 = re.compile(r"NIE TESTOWAN|NIE SPRAWDZON|JESZCZE NIE", re.I)


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


# ---------------- 1) warunki ----------------
def warunki(d: dict, start: str) -> dict:
    det = d.get("details") or {}
    w = det.get("weather") or {}
    win = w.get("windows") or []
    ch = (d.get("chart") or {}).get("weather") or []
    tm = d.get("time") or {}
    st = _hm(start)
    meta = st + int(round(float(tm.get("total_h") or 0) * 60)) if st is not None else None
    fe = [(x.get("okno"), _f(x.get("feels"))) for x in win if _f(x.get("feels")) is not None]
    out = {"start": start, "meta": _fmt(meta) if meta is not None else None, "czas_h": _f(tm.get("total_h"))}
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


def kandydaci(war: dict, recent: set, per_layer: int = 6) -> dict:
    fe = war.get("odczuwalna") or {}
    lo_t, hi_t = _f(fe.get("min"), 10.0), _f(fe.get("max"), 15.0)
    wet = (war.get("deszcz") or {}).get("max_proc", 0) >= 40
    g = sqlite3.connect(GARAGE_DB)
    g.row_factory = sqlite3.Row
    rows = g.execute("SELECT id, category, brand, model, color, season, rating, r_insul, r_wind, r_water, r_breath, fabric, notes "
                     "FROM gear WHERE active=1").fetchall()
    g.close()
    cat2layer = {c: k for k, cs in LAYERS for c in cs}
    out = {k: [] for k, _ in LAYERS}
    for r in rows:
        k = cat2layer.get(r["category"])
        if not k:
            continue
        notes = r["notes"] or ""
        if _OUT.search(notes):
            continue
        rng, src = _range(r["season"], r["r_insul"], notes)
        if not rng:
            continue
        a, b = rng
        ov = max(0.0, min(b, hi_t + 2) - max(a, lo_t - 2))       # zachodzenie na przebieg jazdy
        if ov <= 0 and k not in ("kamizelka", "kurtka", "rekawki"):
            continue
        # warstwy zdejmowane / do kieszeni moga lezec troche nizej niz max jazdy
        if ov <= 0 and a > hi_t + 2:
            continue
        mid_i, mid_r = (a + b) / 2.0, (lo_t + hi_t) / 2.0
        fit = max(0.0, 3.0 - abs(mid_i - mid_r) / 3.0)          # jak dobrze srodek zakresu trafia w te jazde
        sc = float(r["rating"] or 3) + fit + (0.5 if src == "notatka" else 0.0)
        warm_item = bool(_WARM.search(" ".join(str(x or "") for x in (r["model"], r["fabric"], notes)))) or (_f(r["r_insul"], 0) >= 3)
        if hi_t >= 18 and warm_item and k not in ("kurtka",):
            sc -= 3.0                                            # ocieplane w cieply dzien
        if hi_t >= 18 and k == "kurtka" and warm_item:
            sc -= 3.0
        sc += 2.0 if _PLUS2.search(notes) else 0.0
        sc += 1.0 if _PLUS1.search(notes) else 0.0
        sc -= 1.0 if _MINUS1.search(notes) else 0.0
        sc -= 0.5 if _MINUS05.search(notes) else 0.0
        if wet and _f(r["r_water"], 0) >= 3:
            sc += 1.0
        if int(r["id"]) in recent:
            sc -= 0.7
        out[k].append({"id": int(r["id"]), "warstwa": k, "kategoria": r["category"],
                       "nazwa": ("%s %s" % (r["brand"] or "", r["model"] or "")).strip(),
                       "kolor": r["color"], "zakres_c": [a, b], "zakres_z": src, "sezon": r["season"], "ocena": r["rating"],
                       "oceny": {k2: r[k2] for k2 in ("r_insul", "r_wind", "r_water", "r_breath") if r[k2] is not None},
                       "material": (r["fabric"] or "")[:80], "notatka": re.sub(r"\s+", " ", notes)[:220],
                       "ostatnio_proponowane": int(r["id"]) in recent, "_score": round(sc, 2)})
    for k in out:
        out[k] = sorted(out[k], key=lambda x: -x["_score"])[:per_layer]
    return {k: v for k, v in out.items() if v}


# ---------------- 3) AI ----------------
SYS = ("Jestes doswiadczonym kolarzem-doradca od ubioru na gravel. Piszesz po polsku, konkretnie, bez lania wody. "
       "Dobierasz ubior WYLACZNIE z listy 'kandydaci' (uzywasz pola id). Wiatr zawsze w m/s. "
       "ZASADY: (1) KAZDA rzecz ma 'dlaczego': warunek z LICZBA (np. 'start 7 C, wiatr do 5 m/s') + CECHA tej rzeczy "
       "(material, oddychalnosc, wiatroszczelnosc, wodoodpornosc, uwaga z notatki). NIE uzasadniaj zakresem temperatur rzeczy "
       "('miesci sie w zakresie X-Y C' jest zakazane) - to nic nie mowi. "
       "(2) Uwzglednij PRZEBIEG dnia: jesli rozrzut odczuwalnej >= 6 C - warstwy zdejmowane (rekawki, kamizelka) i napisz, "
       "KIEDY je zdjac: godzina z 'warunki.przebieg', gdy odczuwalna przekracza ok. 17-18 C ALBO wzrasta o >= 5 C od startu "
       "(co nastapi pierwsze) - NIE godzina maksimum. Nie proponuj kurtki na dzien bez deszczu z odczuwalna >= 14 C (co najwyzej wiatrowka do kieszeni). (3) Deszcz max_proc >= 40 -> warstwa przeciwdeszczowa "
       "(na sobie albo do kieszeni). (4) Orientacyjne progi dla wysilku endurance: odczuwalna >= 20 C krotki rekaw; 15-20 krotki + "
       "rekawki/kamizelka na start; 10-15 dlugi rekaw albo krotki+rekawki + kamizelka, dlugie palce opcjonalnie; 5-10 baza + dlugi "
       "rekaw + kamizelka/kurtka, dlugie rekawiczki, nogawki/spodnie; < 5 zimowo. Na zjazdach i postojach jest chlodniej. "
       "(5) Uwzglednij notatki rzeczy (komplety, marka, 'do torebki'), oceny i to, ze 'ostatnio_proponowane' przy "
       "rownych szansach warto zamienic na inna. (6) Jedna rzecz na warstwe w zestawie. (7) Dwa zestawy maja sie REALNIE roznic "
       "(np. lzejszy/cieplejszy albo sucho/na deszcz) - min. 2 inne rzeczy. Zwracasz WYLACZNIE JSON.")


def _prompt(war, kand, rules):
    kk = {k: [{x: it[x] for x in ("id", "kategoria", "nazwa", "kolor", "zakres_c", "sezon", "ocena", "oceny", "material", "notatka",
                                  "ostatnio_proponowane")} for it in v] for k, v in kand.items()}
    return ("warunki (Twoja jazda): " + json.dumps(war, ensure_ascii=False) + "\n\nkandydaci (warstwa -> rzeczy): "
            + json.dumps(kk, ensure_ascii=False) + "\n\nreguly_ubioru (od uzytkownika): " + json.dumps(rules or [], ensure_ascii=False)
            + '\n\nZwroc JSON: {"warunki_krotko": "1-2 zdania o przebiegu warunkow w czasie jazdy",'
            ' "zestawy": [{"nazwa": "krotka nazwa, np. Lzejszy / Cieplejszy", "kiedy": "1 zdanie: kiedy ten zestaw",'
            ' "rzeczy": [{"id": liczba, "dlaczego": "1 zdanie z liczba"}],'
            ' "do_kieszeni": [{"id": liczba, "dlaczego": "1 zdanie"}], "zdejmij": "co i kiedy zdjac (albo pusty)"}]}'
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
        sets.append({int(x["id"]) for x in its})
    if len(sets[0] ^ sets[1]) < 2:
        return "zestawy prawie takie same"
    return None


def advise(conn, data: dict, start: str, rules=None, model_name: str = "") -> dict:
    from qgpt_client import qgpt_json
    t0 = time.perf_counter()
    war = warunki(data, start)
    kand = kandydaci(war, recent_ids(conn))
    if not kand:
        return {"ok": False, "blad": "brak pasujacych rzeczy w garazu"}
    o, err = None, None
    for _ in range(2):
        try:
            o = qgpt_json(_prompt(war, kand, rules), system=SYS, max_tokens=4000, temperature=0.5)
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
        z["rzeczy"].sort(key=lambda x: [k for k, _ in LAYERS].index(x["warstwa"]))
    return {"ok": True, "wersja": VERSION, "model": model_name, "czas_s": round(time.perf_counter() - t0, 1),
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "warunki": war, "warunki_krotko": o.get("warunki_krotko"), "zestawy": o["zestawy"],
            "kandydatow": sum(len(v) for v in kand.values())}


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
