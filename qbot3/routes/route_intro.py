"""Wprowadzenie AI do trasy (raz na trase; nie zalezy od daty ani formy -> takze dla gosci).

Fakty: region startu, miejscowosci po drodze, KRAJOBRAZ z calej trasy (WorldCover z warstwy
cienia: os drogi + 20 m w lewo/prawo, co 50 m), nawierzchnia, odcinki trudne, podjazdy,
zaopatrzenie, atrakcje (kanoniczne + warstwa POI, wstep z Wikipedii gdy jest artykul).
Zapis: qbot_v2.route_intro (route_id, geometry_hash) - nowy przebieg AI tylko po zmianie trasy
albo na zadanie (rebuild). Goscie tylko czytaja zapisany opis (zero AI po ich stronie).
"""
from __future__ import annotations

import datetime as _dt
import json
import time
import unicodedata

INTRO_VERSION = 1
WC_LABEL = {10: "zadrzewienia (lasy, sady, parki)", 20: "zarosla", 30: "laki i trawy", 40: "pola uprawne",
            50: "zabudowa", 60: "nieuzytki", 80: "woda", 90: "mokradla"}
LEG = {1: "asfalt", 2: "dobry gravel/szuter", 3: "zwykly gravel/grunt", 4: "trudna/wolna", 5: "ryzyko/piach"}
UA = "QBot-route-intro/1.0 (+https://albert.cytr.us/; private cycling route planner) python-requests"


def _ascii(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).replace("\u0142", "l")


def ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS qbot_v2.route_intro (route_id text PRIMARY KEY, geometry_hash text, "
                 "created_at timestamptz NOT NULL DEFAULT now(), model text, intro jsonb NOT NULL)")


def _tconn():
    import psycopg
    return psycopg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="")


def landscape(route_id: str) -> list:
    import qbot3.routes.route_meteo_engine as ME
    pc = ME._pg_connect()
    try:
        sh = ME._load_shade(pc, route_id)
    finally:
        pc.close()
    acc, tot = {}, 0.0
    for s in sh or []:
        L = max(0.0, float(s.get("km_to") or 0) - float(s.get("km_from") or 0))
        for k in ("class_center", "class_left_20", "class_right_20"):
            c = s.get(k)
            if c is None:
                continue
            acc[int(c)] = acc.get(int(c), 0.0) + L / 3.0
            tot += L / 3.0
    return [{"typ": WC_LABEL.get(k, "inne"), "proc": round(100.0 * v / tot)} for k, v in
            sorted(acc.items(), key=lambda x: -x[1]) if tot and round(100.0 * v / tot) >= 1]


def _wiki_intro(url: str) -> str:
    import requests, urllib.parse
    try:
        title = urllib.parse.unquote(url.rstrip("/").split("/wiki/")[-1])
        r = requests.get("https://pl.wikipedia.org/w/api.php", timeout=12, headers={"User-Agent": UA},
                         params={"action": "query", "format": "json", "formatversion": 2, "prop": "extracts",
                                 "exintro": 1, "explaintext": 1, "exsentences": 3, "titles": title, "redirects": 1})
        pages = (r.json().get("query") or {}).get("pages") or []
        return (pages[0].get("extract") or "").strip()[:500] if pages else ""
    except Exception:
        return ""


def attractions(route_id: str) -> list:
    from qbot3.routes import planer_opis as PO
    from qbot3.routes.route_attraction_store import get_route_attractions
    tc = _tconn()
    out, seen = [], set()
    try:
        base = PO._resolve_base(tc, route_id)
        try:
            can = get_route_attractions(tc, base["base_id"]) or []
        except Exception:
            can = []
        for r in can:
            n = (r.get("name") or "").strip()
            if not n or n.lower() in seen:
                continue
            seen.add(n.lower())
            ex = (r.get("extract") or "").strip()
            if r.get("wiki_url"):
                ex = _wiki_intro(r["wiki_url"]) or ex
            out.append({"km": r.get("km"), "nazwa": n, "rodzaj": r.get("category_label"),
                        "opis": ex if len(ex) > 25 else ""})
        rows = tc.execute("SELECT name, km_on_route FROM qbot_v2.route_poi_layer WHERE route_base_id=%s "
                          "AND category='attraction' AND (distance_from_route_m IS NULL OR distance_from_route_m <= 2000) "
                          "ORDER BY km_on_route", (base["base_id"],)).fetchall()
        for n, km in rows:
            n = (n or "").strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                out.append({"km": round(float(km or 0), 1), "nazwa": n, "rodzaj": None, "opis": ""})
    finally:
        tc.close()
    # drobnica (krzyze, kapliczki, parafie, wiaty...) nie jest "warta zobaczenia" - odsiew
    import re as _re
    NOISE = _re.compile(r"^(krzy\u017c|kapliczk|parafia|wiata|miejsce pami\u0119ci|pomnik przyrody$|diabe\u0142 le\u015bny|\u0142awk|tablica)", _re.I)
    out = [a for a in out if a.get("rodzaj") or not NOISE.search(a["nazwa"])]
    out.sort(key=lambda x: float(x.get("km") or 0))
    # rozloz po CALEJ trasie: kanoniczne zawsze, reszta rowno po km (max 24)
    MAX = 24
    if len(out) > MAX:
        keep = [a for a in out if a.get("rodzaj")]
        rest = [a for a in out if not a.get("rodzaj")]
        n = max(0, MAX - len(keep))
        if n and rest:
            step = len(rest) / float(n)
            keep += [rest[int(i * step)] for i in range(n)]
        out = sorted(keep, key=lambda x: float(x.get("km") or 0))[:MAX]
    return out


def facts(build_fn, conn, route_id: str) -> dict:
    import qbot3.routes.route_meteo_engine as ME
    day = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    d = build_fn(conn, route_id, day, "10:00", 0, 0, ai=False, day_table=True)
    conn.commit()
    det, st = d.get("details") or {}, d.get("start") or {}
    pc = ME._pg_connect()
    try:
        towns = ME._load_towns(pc, route_id) or []
    finally:
        pc.close()
    tn, seen = [], set()
    for t in towns:
        n = t.get("name") if isinstance(t, dict) else None
        if n and n not in seen:
            seen.add(n)
            tn.append({"nazwa": n, "km": t.get("km")})
    return {
        "trasa": {"dystans_km": (d.get("route") or {}).get("distance_km"), "przewyzszenie_m": (d.get("route") or {}).get("ascent_m")},
        "start": {k: st.get(k) for k in ("miejscowosc", "gmina", "powiat", "wojewodztwo")},
        "miejscowosci_po_drodze": tn[:45],
        "krajobraz_wzdluz_trasy": landscape(route_id),
        "nawierzchnia_udzial": [{"rodzaj": LEG.get(x.get("k")), "proc": x.get("pct"), "km": x.get("km")}
                                for x in ((det.get("surface") or {}).get("by_cat") or [])],
        "odcinki_trudne": [{"km": [r.get("a"), r.get("b")], "kategoria": LEG.get(r.get("k"))}
                           for r in ((det.get("surface") or {}).get("risk") or [])],
        "podjazdy": [{"km": [c.get("a_km"), c.get("b_km")], "dl_m": c.get("length_m"), "w_gore_m": c.get("gain_m"),
                      "sr_proc": c.get("avg_pct")} for c in ((det.get("climbs") or {}).get("list") or [])],
        "zaopatrzenie": [{"rejon_km": x.get("q_km"), "punkty": [{"km": p.get("km"), "nazwa": p.get("name"), "typ": p.get("cat")}
                                                               for p in (x.get("picks") or [])[:3]]}
                         for x in ((det.get("poi") or {}).get("resupply") or [])],
        "atrakcje": attractions(route_id),
    }


SYS = ("Jestes przewodnikiem rowerowym i krajoznawca. Piszesz po polsku, zywo i konkretnie, zyczliwie, bez patosu i wykrzyknikow. "
       "Piszesz WPROWADZENIE do jednodniowej trasy gravelowej dla osoby zaproszonej na te jazde: ma poczuc, gdzie jedzie i po co. "
       "ZASADY: (1) nazwy miejscowosci, obiektow i sklepow WYLACZNIE z danych; (2) liczby przepisuj z danych; "
       "(3) REGION: opisz go konkretnie - polozenie, charakter krajobrazu (krajobraz_wzdluz_trasy: UWAGA, 'zadrzewienia' to lasy "
       "ORAZ sady i parki - nie pisz, ze trasa biegnie glownie lasem, jesli region slynie z sadow), typowe cechy tego obszaru, z ktorych "
       "slynie. Mozesz uzyc OGOLNEJ wiedzy o regionie wyznaczonym przez gminy/powiat/wojewodztwo i miejscowosci z danych, ALE tylko rzeczy "
       "pewnych i szeroko znanych; zadnych dat, liczb ani szczegolowych faktow historycznych spoza danych. "
       "(4) 'wprowadzenie' bez kilometrow, procentow i szczegolow odcinkow - te sa w 'czego_sie_spodziewac'; nie powoluj sie na "
       "'dane' ani 'dane krajobrazowe' - po prostu opisuj. Liczby dziesietne z PRZECINKIEM (64,9 km). "
       "(5) 'dlaczego' przy atrakcji: konkretnie, na podstawie 'opis' z danych; gdy opisu brak - krotko czym obiekt jest (z 'rodzaj' lub nazwy), "
       "bez ogolnikow typu 'to jedna z atrakcji'. (6) NIE pisz o pogodzie, dacie, godzinach ani formie/mocy. "
       "(7) Pelne polskie znaki w tresci. Zwracasz WYLACZNIE JSON, klucze bez polskich znakow.")


def _prompt(f):
    return ("Dane trasy:\n" + json.dumps(f, ensure_ascii=False) + "\n\nZwroc DOKLADNIE taki JSON (klucze dokladnie jak ponizej):\n"
            '{"tytul": "trafny tytul trasy (3-7 slow), oddaje region i charakter, bez kropki",\n'
            ' "wprowadzenie": "jeden akapit 5-7 zdan: gdzie lezy trasa i jaki to region, jak wyglada krajobraz, jaki jest charakter jazdy i dla kogo",\n'
            ' "czego_sie_spodziewac": ["3-5 krotkich punktow praktycznych z km: nawierzchnia i trudne odcinki, podjazdy, zaopatrzenie"],\n'
            ' "warto_zobaczyc": [{"nazwa": "dokladnie z listy atrakcji", "km": liczba, "dlaczego": "1-2 konkretne zdania"}]}\n'
            "warto_zobaczyc: 3-6 pozycji rozlozonych po calej trasie, tylko z listy atrakcji.")


def _norm(o):
    if not isinstance(o, dict):
        return None
    return {_ascii(k): v for k, v in o.items()}


def _valid(o, f):
    if not o:
        return "brak JSON"
    for k in ("tytul", "wprowadzenie", "czego_sie_spodziewac", "warto_zobaczyc"):
        if not o.get(k):
            return "brak pola " + k
    names = {a["nazwa"] for a in f.get("atrakcje") or []}
    bad = [x.get("nazwa") for x in o["warto_zobaczyc"] if isinstance(x, dict) and x.get("nazwa") not in names]
    if bad:
        return "atrakcje spoza danych: " + ", ".join(map(str, bad))
    return None


def build(build_fn, conn, route_id: str, model_name: str = "") -> dict:
    from qgpt_client import qgpt_json
    t0 = time.perf_counter()
    f = facts(build_fn, conn, route_id)
    err, o = None, None
    for _ in range(2):
        try:
            o = _norm(qgpt_json(_prompt(f), system=SYS, max_tokens=3500, temperature=0.5))
        except Exception as e:  # noqa
            o, err = None, "wyjatek: " + str(e)[:120]
        err = _valid(o, f)
        if not err:
            break
    if err:
        return {"ok": False, "blad": err}
    return {"ok": True, "wersja": INTRO_VERSION, "model": model_name, "czas_s": round(time.perf_counter() - t0, 1),
            "created_at": __import__("qbot_time").iso_local(),
            "tytul": o["tytul"], "wprowadzenie": o["wprowadzenie"], "czego_sie_spodziewac": o["czego_sie_spodziewac"],
            "warto_zobaczyc": o["warto_zobaczyc"], "krajobraz": f["krajobraz_wzdluz_trasy"]}


def _geom_hash(conn, route_id):
    r = conn.execute("SELECT geometry_hash FROM qbot_v2.route_base WHERE route_id=%s "
                     "ORDER BY (status='active') DESC, route_updated_at DESC NULLS LAST LIMIT 1", (route_id,)).fetchone()
    if not r:
        return None
    return (r["geometry_hash"] if isinstance(r, dict) else r[0])


def load(conn, route_id: str):
    ensure(conn)
    r = conn.execute("SELECT intro, geometry_hash FROM qbot_v2.route_intro WHERE route_id=%s", (route_id,)).fetchone()
    gh = _geom_hash(conn, route_id)
    conn.commit()
    if not r:
        return None
    r = dict(r) if isinstance(r, dict) else {"intro": r[0], "geometry_hash": r[1]}
    it = r["intro"] if not isinstance(r["intro"], str) else json.loads(r["intro"])
    it["aktualny"] = (r["geometry_hash"] == gh)
    return it


def save(conn, route_id: str, intro: dict):
    ensure(conn)
    conn.execute("INSERT INTO qbot_v2.route_intro (route_id, geometry_hash, created_at, model, intro) VALUES (%s, %s, now(), %s, %s::jsonb) "
                 "ON CONFLICT (route_id) DO UPDATE SET geometry_hash=EXCLUDED.geometry_hash, created_at=now(), model=EXCLUDED.model, intro=EXCLUDED.intro",
                 (route_id, _geom_hash(conn, route_id), intro.get("model"), json.dumps(intro, ensure_ascii=False)))
    conn.commit()
