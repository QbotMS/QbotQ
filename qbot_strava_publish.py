# -*- coding: utf-8 -*-
"""Strava: automatyczny ROWER + OPIS-wizytowka "Albert . QBot" (2026-10-09, decyzje Michala).

Po kazdej nowej jezdzie (od START_FROM) QBot jednym PUT /activities/{id} ustawia na Stravie:
- gear_id  - rower rozpoznany po czujnikach: AXS 10625 = Grizl, AXS 27856 = Grail, brak AXS = Monster
             (qbot_v2.activity_device; mapowanie rower -> gear_id Stravy w qbot_v2.strava_gear_map,
             uzupelniane samo z GET /athlete po nazwach rowerow),
- description - ZAWSZE nadpisuje (Michal nie prowadzi notatek na Stravie).

Opis (rzeczowo, z ikonkami, bez danych zdrowotnych, bez okolic startu/mety):
  1) region + km + przewyzszenie + nawierzchnia: asfalt / szuter / ujeby (5 kategorii -> 3),
  2) wysilek z XSS i W'bal wzgledem WLASNEJ historii jazd: wpierdol / mocno, ale stabilnie / lekko / rowno,
  3) (opcjonalnie) nowe kwadraty (zoom 14, historia GPS QBota), atrakcja (0-2, ocenia AI), dluga przerwa,
  4) podpis "🤖 Albert · QBot".
AI (qgpt_json) WYBIERA tylko nazwe regionu i atrakcje z list przygotowanych przez QBota; liczby wstawia QBot.
Wynik AI jest sprawdzany (atrakcje = dokladnie z listy, region = tylko nazwy z danych); zle -> wariant bez AI.

Uruchomienie: watek w qbot-web (start w qbot_strava.build_router), co LOOP_S. Wylacznik: QBOT_STRAVA_PUBLISH=0.
Podglad bez wysylania:  .venv/bin/python3 qbot_strava_publish.py --dry <ride_key>   (trwa ~1 min - NIE przez dev_shell_exec)
Dok.: docs/STRAVA_PUBLISH.md
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

START_FROM = "2026-10-09"          # automat tylko dla jazd od wdrozenia (starszych nie przepisujemy)
SIGNATURE = "🤖 Albert · QBot"
UA = "QBot/3.0 (strava publish; qbot@olga181.mikrus.xyz)"
API = "https://www.strava.com/api/v3"
AXS_BIKE = {10625: "Grizl", 27856: "Grail"}
NO_AXS_BIKE = "Monster"
BIKE_KEYS = {"Grizl": ("grizl",), "Grail": ("grail",), "Monster": ("monster", "grand canyon")}
SURF_GROUP = {"twarda szybka": "asfalt", "dobry gravel": "szuter", "zwykly gravel": "szuter",
              "trudna/wolna": "ujeby", "ryzyko/niepewne": "ujeby"}
PRIVACY_KM = 3.0                    # nic w promieniu 3 km od startu i mety (okolice domu)
POI_MAX_M = 400                     # atrakcja maks. tyle od sladu
STOP_MIN_S = 15 * 60                # przerwa w opisie od 15 min
GEO_EVERY_KM = 8.0
WD_SEG_KM = 5.0
MAX_ATTEMPTS = 24                   # x LOOP_S = ok. 8 h czekania na czujniki / raport / W'bal
LOOP_S = 20 * 60
_SKIP_TYPE = re.compile(r"wieś|miasto|osada|kolonia|przysiółek|gmina|sołectwo|część|dzielnica|osiedle|stacja|przystanek|"
                        r"ulica|droga|most|rzeka|potok|kanał|jezioro|staw|szkoła|parafia|dekanat|powiat|województwo|"
                        r"kapliczka|krzyż|cmentarz|pomnik przyrody|drzewo|grób|mogiła", re.I)
_GENERIC = {"doli", "okol", "skra", "międ", "pogr", "ziem", "równ", "wzdł", "prze", "nad", "pod", "półn", "połu",
            "zach", "wsch", "pusz", "lasy", "wyso", "rozl", "brze", "pasm", "pagó", "poje", "pole", "pola"}

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.strava_publish (
  strava_id bigint PRIMARY KEY, ride_key text, status text, bike text, gear_id text, description text,
  facts jsonb, attempts int DEFAULT 0, last_error text, published_at timestamptz, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS qbot_v2.strava_gear_map (
  bike text PRIMARY KEY, gear_id text, strava_name text, updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS qbot_v2.geo_rev_cache (
  lat double precision, lon double precision, addr jsonb, PRIMARY KEY (lat, lon))"""


# ---------------------------------------------------------------- pomocnicze (czyste, testowane)

def hav_m(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(min(1.0, math.sqrt(h)))


def surface_split(types_pct: dict | None) -> dict | None:
    """5 kategorii raportu -> asfalt / szuter / ujeby (suma 100, metoda najwiekszych reszt)."""
    g = {"asfalt": 0.0, "szuter": 0.0, "ujeby": 0.0}
    for k, v in (types_pct or {}).items():
        grp = SURF_GROUP.get(k)
        if grp and v:
            g[grp] += float(v)
    tot = sum(g.values())
    if tot < 50:
        return None
    vals = {k: v * 100.0 / tot for k, v in g.items()}
    fl = {k: int(v) for k, v in vals.items()}
    for k in sorted(vals, key=lambda k: -(vals[k] - fl[k]))[: 100 - sum(fl.values())]:
        fl[k] += 1
    return fl


def effort_class(xss: float, minw: float, p: dict) -> str:
    """Progi wzgledem wlasnej historii (decyzja Michala 2026-10-09)."""
    xh = p.get("xss_h") or 0
    if minw < 10 and xh >= p["h75"]:
        return "wpierdol"
    if xss >= p["x75"] and minw >= 25:
        return "mocno"
    if xss < p["x50"] and minw > 50:
        return "lekko"
    return "rowno"


def hmm(sec: float) -> str:
    m = int(round(sec / 60.0))
    return "%d:%02d" % (m // 60, m % 60)


def effort_sentence(e: dict | None, moving_s: float) -> str:
    t = hmm(moving_s)
    if not e:
        return "⏱️ %s w ruchu." % t
    w = int(round(e["min_wbal"]))
    return {
        "wpierdol": "🥵 Wpierdol: %s w ruchu, bak (W′) zjechał do %d%%." % (t, w),
        "mocno": "💪 Mocno, ale stabilnie: %s w ruchu, a bak (W′) ani razu nie spadł poniżej %d%%." % (t, w),
        "lekko": "😌 Lekko: %s w ruchu, bak (W′) nie zszedł poniżej %d%%." % (t, w),
        "rowno": "⚡ Równa, solidna jazda: %s w ruchu, bak (W′) najniżej %d%%." % (t, w),
    }[e["cls"]]


def tiles_phrase(n: int) -> str:
    if n == 1:
        return "🟩 1 nowy kwadrat"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "🟩 %d nowe kwadraty" % n
    return "🟩 %d nowych kwadratów" % n


def vocab_of(facts: dict) -> set:
    words = []
    for s in (facts.get("towns") or []) + (facts.get("admin") or []) + [c["name"] for c in facts.get("candidates") or []]:
        words += re.findall(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ-]+", s or "")
    return {w.lower()[:4] for w in words if len(w) >= 3}


def region_ok(region: str | None, vocab: set) -> bool:
    if not region or len(region) > 80:
        return False
    for w in re.findall(r"[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż-]+", region):
        if w.lower()[:4] not in vocab and w.lower()[:4] not in _GENERIC:
            return False
    return True


def assemble(f: dict, region: str, attractions: list) -> str:
    l1 = "📍 %s: %d km i %d m w górę" % (region, round(f["km"]), round(f["elev_m"] or 0))
    s = f.get("surface")
    if s:
        l1 += " — 🛣️ %d%% asfaltu, 🌾 %d%% szutru, 🪨 %d%% ujebów" % (s["asfalt"], s["szuter"], s["ujeby"])
    l1 += "."
    extras = []
    if f.get("new_tiles"):
        extras.append(tiles_phrase(f["new_tiles"]))
    if attractions:
        extras.append("⭐ " + " · ".join(attractions))
    if f.get("stop"):
        extras.append("☕ przerwa: %s" % f["stop"]["place"])
    lines = [l1, effort_sentence(f.get("effort"), f["moving_s"])]
    if extras:
        lines.append(" · ".join(extras))
    lines.append(SIGNATURE)
    return "\n".join(lines)


# ---------------------------------------------------------------- baza

def _rows(c, sql, args=()):
    c.execute(sql, args)
    rs = c.fetchall()
    if rs and not isinstance(rs[0], dict):
        cols = [d[0] for d in c.description]
        rs = [dict(zip(cols, r)) for r in rs]
    return rs


def _one(c, sql, args=()):
    r = _rows(c, sql, args)
    return r[0] if r else None


def ensure(c):
    c.execute(DDL)
    c.connection.commit()


def bike_of(c, ride_key):
    devs = _rows(c, "SELECT manufacturer, device_type, ant_device_number FROM qbot_v2.activity_device WHERE external_id=%s", (ride_key,))
    if not devs:
        return None, "brak listy czujnikow"
    axs = [d for d in devs if d["manufacturer"] == "sram" and str(d["device_type"]) == "34"]
    if not axs:
        return NO_AXS_BIKE, "brak AXS"
    for d in axs:
        if d["ant_device_number"] in AXS_BIKE:
            return AXS_BIKE[d["ant_device_number"]], "AXS %s" % d["ant_device_number"]
    return None, "AXS o nieznanym numerze %s" % [d["ant_device_number"] for d in axs]


def _track(c, ride_key):
    return _rows(c, "SELECT ts, lat, lon, distance_m, speed_mps FROM qbot_v2.activity_record "
                    "WHERE external_id=%s AND lat IS NOT NULL ORDER BY ts", (ride_key,))


def _effort(c, ride_key):
    r = _one(c, "SELECT xss, xss_per_h, min_wbal_pct FROM qbot_v2.fitmodel_wbal_ride WHERE external_id=%s AND status='OK'", (ride_key,))
    if not r or r["xss"] is None or r["min_wbal_pct"] is None:
        return None
    p = _one(c, "SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY xss_per_h) h75, "
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY xss) x50, percentile_cont(0.75) WITHIN GROUP (ORDER BY xss) x75 "
                "FROM qbot_v2.fitmodel_wbal_ride WHERE status='OK' AND xss IS NOT NULL AND external_id<>%s", (ride_key,))
    p = {k: float(v) for k, v in p.items()}
    p["xss_h"] = float(r["xss_per_h"] or 0)
    return {"xss": round(float(r["xss"])), "xss_h": round(p["xss_h"], 1), "min_wbal": float(r["min_wbal_pct"]),
            "cls": effort_class(float(r["xss"]), float(r["min_wbal_pct"]), p), "progi": {k: round(v, 1) for k, v in p.items()}}


def _new_tiles(c, ride_key, tr):
    la = [r["lat"] for r in tr]; lo = [r["lon"] for r in tr]
    r = _one(c, """WITH t AS (SELECT DISTINCT floor((lon+180)/360*16384)::int x,
                  floor((1-ln(tan(radians(lat))+1/cos(radians(lat)))/pi())/2*16384)::int y
                  FROM qbot_v2.activity_record WHERE external_id=%s AND lat IS NOT NULL),
               prev AS (SELECT DISTINCT floor((lon+180)/360*16384)::int x,
                  floor((1-ln(tan(radians(lat))+1/cos(radians(lat)))/pi())/2*16384)::int y
                  FROM qbot_v2.activity_record WHERE external_id<>%s AND lat IS NOT NULL
                  AND ts < (SELECT min(ts) FROM qbot_v2.activity_record WHERE external_id=%s)
                  AND lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s)
               SELECT count(*) n FROM t WHERE NOT EXISTS (SELECT 1 FROM prev p WHERE p.x=t.x AND p.y=t.y)""",
             (ride_key, ride_key, ride_key, min(la) - 0.05, max(la) + 0.05, min(lo) - 0.05, max(lo) + 0.05))
    return int(r["n"]) if r else 0


def _stops(tr):
    """Przerwy z dziur w zapisie (auto-pauza zawsze wlaczona), sklejane w promieniu 500 m."""
    out = []
    for a, b in zip(tr, tr[1:]):
        gap = (b["ts"] - a["ts"]).total_seconds()
        if gap <= 30:
            continue
        pt = (a["lat"], a["lon"])
        if out and hav_m(out[-1]["pt"], pt) < 500:
            out[-1]["dur"] += gap
        else:
            out.append({"pt": pt, "dur": gap})
    return out


# ---------------------------------------------------------------- swiat zewnetrzny (Nominatim, Wikidata, AI)

_NOM_T = [0.0]


def revgeo(c, lat, lon) -> dict:
    la, lo = round(lat, 3), round(lon, 3)
    r = _one(c, "SELECT addr FROM qbot_v2.geo_rev_cache WHERE lat=%s AND lon=%s", (la, lo))
    if r:
        return r["addr"] or {}
    wait = 1.2 - (time.time() - _NOM_T[0])
    if wait > 0:
        time.sleep(wait)
    _NOM_T[0] = time.time()
    q = urllib.parse.urlencode({"format": "jsonv2", "lat": la, "lon": lo, "zoom": 14, "addressdetails": 1, "accept-language": "pl"})
    try:
        req = urllib.request.Request("https://nominatim.openstreetmap.org/reverse?" + q, headers={"User-Agent": UA})
        addr = (json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8")) or {}).get("address") or {}
    except Exception as e:
        print("[strava publish] nominatim: %s" % e)
        return {}
    c.execute("INSERT INTO qbot_v2.geo_rev_cache (lat, lon, addr) VALUES (%s,%s,%s::jsonb) ON CONFLICT DO NOTHING",
              (la, lo, json.dumps(addr, ensure_ascii=False)))
    c.connection.commit()
    return addr


def _place(addr):
    return addr.get("village") or addr.get("town") or addr.get("city") or addr.get("hamlet") or addr.get("suburb")


_WD_Q = """SELECT ?item ?label ?coord ?sl ?h ?typeLabel WHERE {
  SERVICE wikibase:box { ?item wdt:P625 ?coord .
    bd:serviceParam wikibase:cornerSouthWest "Point(%f %f)"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerNorthEast "Point(%f %f)"^^geo:wktLiteral . }
  ?item wikibase:sitelinks ?sl . ?item rdfs:label ?label . FILTER(LANG(?label)="pl")
  OPTIONAL { ?item wdt:P1435 ?h . }
  OPTIONAL { ?item wdt:P31 ?type . ?type rdfs:label ?typeLabel . FILTER(LANG(?typeLabel)="pl") }
} LIMIT 600"""


def wikidata_candidates(pts, ends):
    """Zabytki/obiekty z Wikidanych przy sladzie: rejestr zabytkow (P1435) albo >=2 wersje jezykowe Wikipedii."""
    segs, cur, last = [], [], None
    for p in pts:
        cur.append(p)
        if last is None:
            last = p
        elif hav_m(last, p) >= WD_SEG_KM * 1000:
            segs.append(cur); cur, last = [p], p
    if cur:
        segs.append(cur)
    items = {}
    for s in segs:
        la = [p[0] for p in s]; lo = [p[1] for p in s]
        q = _WD_Q % (min(lo) - 0.007, min(la) - 0.004, max(lo) + 0.007, max(la) + 0.004)
        try:
            req = urllib.request.Request("https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q, "format": "json"}),
                                         headers={"User-Agent": UA, "Accept": "application/sparql-results+json"})
            data = json.loads(urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))
        except Exception as e:
            print("[strava publish] wikidata: %s" % e)
            continue
        for b in data.get("results", {}).get("bindings", []):
            qid = b["item"]["value"].rsplit("/", 1)[-1]
            m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
            if not m:
                continue
            it = items.setdefault(qid, {"qid": qid, "name": b["label"]["value"], "pt": (float(m.group(2)), float(m.group(1))),
                                        "sitelinks": int(b["sl"]["value"]), "zabytek": False, "types": set()})
            it["zabytek"] = it["zabytek"] or "h" in b
            if "typeLabel" in b:
                it["types"].add(b["typeLabel"]["value"])
        time.sleep(1.0)
    out = []
    for it in items.values():
        if any(_SKIP_TYPE.search(t) for t in it["types"]) and not it["zabytek"]:
            continue
        if not it["zabytek"] and it["sitelinks"] < 2:
            continue
        if any(hav_m(it["pt"], e) < PRIVACY_KM * 1000 for e in ends):
            continue
        d = min(hav_m(it["pt"], p) for p in pts)
        if d > POI_MAX_M:
            continue
        out.append({"name": it["name"], "typ": ", ".join(sorted(it["types"]))[:80], "zabytek": it["zabytek"],
                    "wikipedie": it["sitelinks"], "od_sladu_m": int(d), "pt": it["pt"]})
    out.sort(key=lambda x: (-x["zabytek"], -x["wikipedie"]))
    return out[:15]


_SYS = ("Jestes Albertem z QBota. Przygotowujesz publiczny opis jazdy rowerowej na Strave - rzeczowo, bez zartow. "
        "Dostajesz WYLACZNIE fakty z danych. Zwracasz TYLKO JSON, bez komentarzy.")


def _prompt(facts):
    return (
        "FAKTY:\n" + json.dumps({"miejscowosci_po_drodze": facts["towns"], "jednostki_administracyjne": facts["admin"],
                                  "kandydaci_atrakcje": [{k: c[k] for k in ("name", "typ", "zabytek", "wikipedie", "od_sladu_m")}
                                                         for c in facts["candidates"]]}, ensure_ascii=False) +
        "\n\nZwroc JSON: {\"region\": \"...\", \"atrakcje\": [\"...\"]}\n"
        "- region: krotkie okreslenie, gdzie byla jazda (maks. 70 znakow), np. 'Mazowsze, między Wyszogrodem a Czerwińskiem nad Wisłą'. "
        "Uzywaj WYLACZNIE nazw wlasnych z list powyzej (mozesz dodac slowa ogolne: okolice, dolina, między, skraj). "
        "Polska odmiana poprawna, pelne polskie znaki.\n"
        "- atrakcje: 0, 1 albo 2 nazwy DOKLADNIE jak w kandydaci_atrakcje, tylko obiekty, ktorymi naprawde warto sie pochwalic: "
        "zamek, palac, bazylika, klasztor, znany zabytek, slynne miejsce. Zwykle koscioly wiejskie, rezerwaty, kapliczki, "
        "dworki bez znaczenia, schrony, pomniki - pomijaj. Nie wybieraj dwoch czesci tego samego zespolu "
        "(np. bazylika i klasztor w jednym miejscu) - wtedy jedna, najwazniejsza. Lepiej pusta lista niz atrakcja na sile.")


def ai_pick(facts):
    from qgpt_client import qgpt_json
    try:
        j = qgpt_json(_prompt(facts), system=_SYS, max_tokens=400)
    except Exception as e:
        return None, [], "AI: %s" % e
    names = {c["name"] for c in facts["candidates"]}
    atr = [a for a in (j.get("atrakcje") or []) if a in names][:2]
    reg = j.get("region")
    bad = [a for a in (j.get("atrakcje") or []) if a not in names]
    note = ("odrzucone atrakcje spoza listy: %s" % bad) if bad else None
    if not region_ok(reg, vocab_of(facts)):
        note = (note + "; " if note else "") + "region odrzucony: %r" % reg
        reg = None
    return reg, atr, note


# ---------------------------------------------------------------- fakty + opis

def build(c, ride_key, use_ai=True) -> dict:
    s = _one(c, "SELECT distance_m, elevation_m, started_at FROM qbot_v2.training_sessions WHERE external_id=%s", (ride_key,))
    tr = _track(c, ride_key)
    if not s or len(tr) < 60:
        raise RuntimeError("brak jazdy lub sladu GPS")
    rep = _one(c, "SELECT w1_json->'surface'->'value'->'types_pct' AS t FROM qbot_v2.ride_report_data WHERE ride_key=%s", (ride_key,))
    start, end = (tr[0]["lat"], tr[0]["lon"]), (tr[-1]["lat"], tr[-1]["lon"])
    pts = [(r["lat"], r["lon"]) for r in tr[::5]]
    f = {"ride_key": ride_key, "km": (s["distance_m"] or 0) / 1000.0, "elev_m": s["elevation_m"],
         "moving_s": sum(1 for r in tr if (r["speed_mps"] or 0) > 0.8),
         "surface": surface_split((rep or {}).get("t")), "effort": _effort(c, ride_key), "new_tiles": _new_tiles(c, ride_key, tr)}
    # miejscowosci i administracja (bez okolic startu/mety)
    towns, admin, nxt = [], [], 0.0
    for r in tr:
        dm = (r["distance_m"] or 0) / 1000.0
        if dm < nxt:
            continue
        nxt = dm + GEO_EVERY_KM
        pt = (r["lat"], r["lon"])
        if min(hav_m(pt, start), hav_m(pt, end)) < PRIVACY_KM * 1000:
            continue
        a = revgeo(c, *pt)
        p = _place(a)
        if p and p not in towns:
            towns.append(p)
        for k in ("municipality", "county", "state"):
            if a.get(k) and a[k] not in admin:
                admin.append(a[k])
    f["towns"], f["admin"] = towns, admin
    # najdluzsza przerwa >= 15 min (poza okolicami startu/mety)
    st = [x for x in _stops(tr) if x["dur"] >= STOP_MIN_S and min(hav_m(x["pt"], start), hav_m(x["pt"], end)) >= PRIVACY_KM * 1000]
    if st:
        b = max(st, key=lambda x: x["dur"])
        pl = _place(revgeo(c, *b["pt"]))
        if pl:
            f["stop"] = {"place": pl, "min": round(b["dur"] / 60)}
    f["candidates"] = wikidata_candidates(pts, (start, end))
    region, atr, note = (ai_pick(f) if use_ai else (None, [], "bez AI"))
    if not region:
        region = ("między %s a %s" % (towns[0], towns[-1])) if len(towns) >= 2 else (towns[0] if towns else (admin[-1] if admin else "Polska"))
    region = region[:1].upper() + region[1:]
    f["region"], f["attractions"], f["ai_note"] = region, atr, note
    f["description"] = assemble(f, region, atr)
    return f


# ---------------------------------------------------------------- Strava

def _put(tok, sid, data):
    req = urllib.request.Request(API + "/activities/%d" % sid, data=urllib.parse.urlencode(data).encode(), method="PUT")
    req.add_header("Authorization", "Bearer " + tok)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "null")


def gear_map(c, tok) -> dict:
    have = {r["bike"]: r["gear_id"] for r in _rows(c, "SELECT bike, gear_id FROM qbot_v2.strava_gear_map")}
    if all(have.get(b) for b in BIKE_KEYS):
        return have
    import qbot_strava as S
    ath, _ = S._http("GET", API + "/athlete", None, tok)
    bikes = (ath or {}).get("bikes") or []
    for bike, keys in BIKE_KEYS.items():
        if have.get(bike):
            continue
        hit = [g for g in bikes if any(k in ((g.get("name") or "") + " " + (g.get("nickname") or "")).lower() for k in keys)]
        if len(hit) == 1:
            c.execute("INSERT INTO qbot_v2.strava_gear_map (bike, gear_id, strava_name) VALUES (%s,%s,%s) ON CONFLICT (bike) DO UPDATE "
                      "SET gear_id=EXCLUDED.gear_id, strava_name=EXCLUDED.strava_name, updated_at=now()", (bike, hit[0]["id"], hit[0].get("name")))
            have[bike] = hit[0]["id"]
    c.connection.commit()
    missing = [b for b in BIKE_KEYS if not have.get(b)]
    if missing:
        _notif(c, "strava:gear", "Strava: nie dopasowałem rowerów %s" % ", ".join(missing),
               "Rowery na Stravie: %s" % (", ".join(g.get("name") or "?" for g in bikes) or "brak"))
    else:
        _resolve(c, "strava:gear")
    return have


def _notif(c, key, title, body=None, kind="system", url="/strava.html"):
    try:
        import qbot_notif as N
        N.push(c, key, kind, title, body, url)
        c.connection.commit()
    except Exception as e:
        print("[strava publish] notif: %s" % e)


def _resolve(c, key):
    try:
        import qbot_notif as N
        N.resolve(c, key)
        c.connection.commit()
    except Exception:
        pass


def _save(c, sid, **kw):
    cols = ", ".join(kw)
    c.execute("INSERT INTO qbot_v2.strava_publish (strava_id, %s) VALUES (%%s, %s) ON CONFLICT (strava_id) DO UPDATE SET %s, updated_at=now()"
              % (cols, ", ".join(["%s"] * len(kw)), ", ".join("%s=EXCLUDED.%s" % (k, k) for k in kw)),
              (sid, *[json.dumps(v, ensure_ascii=False, default=str) if k == "facts" else v for k, v in kw.items()]))
    c.connection.commit()


def run_publish(db_conn=None) -> dict:
    import qbot_strava as S
    conn = db_conn() if db_conn else S._dict_conn()
    out = {"ok": 0, "czeka": 0, "bledy": 0}
    try:
        c = conn.cursor(); S.ensure_tables(c); ensure(c)
        a = S._get(c)
        if not a.get("refresh_token"):
            return {"pominiete": "Strava niepolaczona"}
        if "activity:write" not in (a.get("scope") or ""):
            _notif(c, "strava:scope", "Strava: połącz ponownie, żeby QBot ustawiał rower i opis",
                   "Na stronie Strava kliknij „Połącz ze Stravą” i zatwierdź nowe uprawnienia.")
            return {"pominiete": "brak activity:write"}
        _resolve(c, "strava:scope")
        tok = S._token(c)
        acts, _ = S._http("GET", API + "/athlete/activities", {"after": int(time.time() - 3 * 86400), "per_page": 30}, tok)
        for x in acts or []:
            S._upsert_activity(c, x)
        conn.commit()
        todo = _rows(c, "SELECT a.strava_id, a.ride_key, a.start_date, COALESCE(p.attempts,0) attempts FROM qbot_v2.strava_activity a "
                        "LEFT JOIN qbot_v2.strava_publish p ON p.strava_id=a.strava_id WHERE a.start_date >= %s AND a.ride_key IS NOT NULL "
                        "AND a.sport_type ~* 'ride' AND (p.status IS NULL OR (p.status IN ('czeka','blad') AND p.attempts < %s)) "
                        "ORDER BY a.start_date", (START_FROM, MAX_ATTEMPTS))
        gmap = gear_map(c, tok) if todo else {}
        for t in todo:
            sid, rk, att = t["strava_id"], t["ride_key"], t["attempts"] + 1
            last = att >= MAX_ATTEMPTS
            try:
                bike, why = bike_of(c, rk)
                ready = _one(c, "SELECT (SELECT count(*) FROM qbot_v2.ride_report_data WHERE ride_key=%s) r, "
                                "(SELECT count(*) FROM qbot_v2.fitmodel_wbal_ride WHERE external_id=%s) w", (rk, rk))
                if (not bike or not ready["r"] or not ready["w"]) and not last:
                    _save(c, sid, ride_key=rk, status="czeka", attempts=att, last_error="rower: %s; raport: %s; W'bal: %s" % (why, ready["r"], ready["w"]))
                    out["czeka"] += 1
                    continue
                f = build(c, rk)
                data = {"description": f["description"]}
                if bike and gmap.get(bike):
                    data["gear_id"] = gmap[bike]
                _put(S._token(c), sid, data)
                _save(c, sid, ride_key=rk, status="ok", bike=bike, gear_id=data.get("gear_id"), description=f["description"],
                      facts=f, attempts=att, last_error=None if data.get("gear_id") else "rower nieustawiony: %s" % why,
                      published_at=datetime.now(timezone.utc))
                _notif(c, "strava:%d" % sid, "Strava: opis%s ustawiony" % (" i rower (%s)" % bike if data.get("gear_id") else ""),
                       f["description"].split("\n")[0], kind="jazda", url="https://www.strava.com/activities/%d" % sid)
                if not data.get("gear_id"):
                    _notif(c, "strava:bike:%d" % sid, "Strava: nie ustawiłem roweru", why, kind="rower",
                           url="https://www.strava.com/activities/%d" % sid)
                out["ok"] += 1
            except Exception as e:
                _save(c, sid, ride_key=rk, status="blad", attempts=att, last_error=str(e)[:300])
                if last:
                    _notif(c, "strava:err:%d" % sid, "Strava: nie udało się opisać jazdy", str(e)[:200])
                out["bledy"] += 1
        return out
    finally:
        conn.close()


_STARTED = [False]


def start_loop(db_conn) -> None:
    if _STARTED[0] or os.environ.get("QBOT_STRAVA_PUBLISH", "1") == "0":
        return
    _STARTED[0] = True

    def loop():
        time.sleep(300)
        while True:
            try:
                if 6 <= datetime.now().hour <= 23:
                    print("[strava publish]", run_publish(db_conn))
            except Exception as e:
                print("[strava publish] blad: %s" % e)
            time.sleep(LOOP_S)
    threading.Thread(target=loop, daemon=True, name="strava-publish").start()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", metavar="RIDE_KEY", help="podglad opisu bez wysylania na Strave")
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--once", action="store_true", help="jeden przebieg automatu (wysyla!)")
    a = ap.parse_args()
    if a.dry:
        import qbot_strava as S
        cn = S._dict_conn()
        try:
            cu = cn.cursor(); ensure(cu)
            b, why = bike_of(cu, a.dry)
            fx = build(cu, a.dry, use_ai=not a.no_ai)
            fx["bike"], fx["bike_why"] = b, why
            for x in fx["candidates"]:
                x.pop("pt", None)
            print(json.dumps({k: v for k, v in fx.items() if k != "description"}, ensure_ascii=False, indent=1, default=str))
            print("\n===== OPIS =====\n" + fx["description"])
        finally:
            cn.close()
    elif a.once:
        print(run_publish())
