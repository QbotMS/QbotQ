# -*- coding: utf-8 -*-
"""Strava: automatyczny ROWER + OPIS-wizytowka "Albert . QBot" (2026-10-09, decyzje Michala).

Po kazdej nowej jezdzie (od START_FROM) QBot jednym PUT /activities/{id} ustawia na Stravie:
- gear_id  - rower rozpoznany po czujnikach: AXS 10625 = Grizl, AXS 27856 = Grail, brak AXS = Monster
             (qbot_v2.activity_device; mapowanie rower -> gear_id Stravy w qbot_v2.strava_gear_map,
             uzupelniane samo z GET /athlete po nazwach rowerow),
- description - ZAWSZE nadpisuje (Michal nie prowadzi notatek na Stravie).

Opis (rzeczowo, z ikonkami, bez danych zdrowotnych, bez okolic startu/mety):
  1) region + km + przewyzszenie + nawierzchnia: asfalt / szuter / ujeby (5 kategorii -> 3),
  2) wysilek z intensywnosci (srednia moc/tetno) i obciazenia (XSS) wzgledem WLASNEJ historii: wpierdol / mocno / lekko / rowno.
     W'bal tylko wewnetrznie - NIGDY w tekscie (dane prywatne, decyzja 2026-10-09 b),
  MyBiom (lasy w okolicy, uczone z nazw na Stravie) -> region zawsze "Przepiękna Puszcza Słupecka"; do Mamy -> BEZ opisu,
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
BIKE_KEYS = {"Grizl": ("grizl",), "Grail": ("grail",), "Monster": ("monster", "grand canyon", "kloc")}   # na Stravie: Kloc MTB
SURF_GROUP = {"twarda szybka": "asfalt", "dobry gravel": "szuter", "zwykly gravel": "szuter",
              "trudna/wolna": "ujeby", "ryzyko/niepewne": "ujeby"}
PRIVACY_KM = 3.0                    # nic w promieniu 3 km od startu i mety (okolice domu)
POI_MAX_M = 400                     # atrakcja maks. tyle od sladu
STOP_MIN_S = 15 * 60                # przerwa w opisie od 15 min
GEO_EVERY_KM = 4.0                  # gesciej - tytul potrzebuje miasteczek po drodze
WD_SEG_KM = 5.0
MAX_ATTEMPTS = 24                   # x LOOP_S = ok. 8 h czekania na czujniki / raport / W'bal
LOOP_S = 20 * 60
_SKIP_TYPE = re.compile(r"wieś|miasto|osada|kolonia|przysiółek|gmina|sołectwo|część|dzielnica|osiedle|stacja|przystanek|"
                        r"ulica|droga|most|rzeka|potok|kanał|jezioro|staw|szkoła|parafia|dekanat|powiat|województwo|"
                        r"kapliczka|krzyż|cmentarz|pomnik przyrody|drzewo|grób|mogiła", re.I)
_SACRAL = re.compile(r"kości|bazylik|klasztor|kaplic|parafi|sanktuar|opact|cerk|synagog|meczet|kapliczk|krzyż|cmentarz|"
                     r"zakon|kolegiat|katedr|dzwonnic|plebani|wikariat|kalwari|figura|świątyni|dom zakonny", re.I)
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


def effort_class(e: dict, p: dict) -> str:
    """Wysilek z INTENSYWNOSCI i obciazenia wzgledem wlasnej historii (2026-10-09 b, po uwadze Michala do 08.10).
    W'bal liczony wewnetrznie, ale NIGDY nie trafia do tekstu (dane prywatne)."""
    minw, hr, pw = e.get("min_wbal"), e.get("avg_hr"), e.get("avg_pw")
    hi_int = (hr is not None and hr >= p["hr75"]) or (pw is not None and pw >= p["pw75"])
    if minw is not None and minw < 10 and (e.get("xss_h") or 0) >= p["h75"]:
        return "wpierdol"
    if hi_int or (e.get("xss") or 0) >= p["x75"]:
        return "mocno" if (minw is None or minw >= 25) else "mocno_akcenty"
    if (hr is None or hr < p["hr50"]) and (pw is None or pw < p["pw50"]) and (e.get("xss_h") or 0) < p["h50"]:
        return "lekko"
    return "rowno"


def hmm(sec: float) -> str:
    m = int(round(sec / 60.0))
    return "%d:%02d" % (m // 60, m % 60)


def effort_sentence(e: dict | None, moving_s: float) -> str:
    t = hmm(moving_s)
    if not e:
        return "⏱️ %s w ruchu." % t
    return {
        "wpierdol": "🥵 Wpierdol: %s w ruchu na granicy możliwości." % t,
        "mocno": "💪 Mocno, ale stabilnie: %s w ruchu, równe tempo w ramach sił." % t,
        "mocno_akcenty": "💪 Mocno: %s w ruchu, z ostrymi akcentami." % t,
        "lekko": "😌 Lekko: %s spokojnej jazdy." % t,
        "rowno": "⚡ Równa, solidna jazda: %s w ruchu." % t,
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


# ---------------------------------------------------------------- tytul (2026-10-09 e, decyzje Michala)
# Tylko w miejsce DOMYSLNEJ nazwy. MyBiom -> "MyBIOM", do Mamy -> "do Mamy" (bez [Qbot]); pozostale:
# "[Qbot] A – B · <etykieta> <ikona jazdy> <pogoda>". Bez km (sa w polu Stravy), bez poetyki (zostaje Michalowi).
# etykieta: bikepacking Dn (kolejne dni ze startem > 80 km od Warszawy) / wyprawa (>= 80 km) / gravel / szosa / mix.
KIND_TITLE = {"mybiom": "MyBIOM", "domamy": "do Mamy"}
EFFORT_ICON = {"wpierdol": "🥵", "mocno": "💪", "mocno_akcenty": "💪", "rowno": "⚡", "lekko": "😌"}
HOME = (52.23, 21.01)
AWAY_KM = 80.0
EXPED_KM = 80.0
_DEFAULT_NAME = re.compile(
    r"^\W*((morning|afternoon|evening|night|lunch)( gravel| mountain| road)? ride|"
    r"(poranna|popołudniowa|wieczorna|nocna|południowa|przedpołudniowa) (jazda|przejażdżka)( rowerowa| na rowerze)?|"
    r"jazda( rowerowa| na rowerze)?|ride|.{0,40} kolarstwo( gravelowe| szosowe| górskie)?)\W*$", re.I)


def is_default_name(name: str | None) -> bool:
    return bool(name) and bool(_DEFAULT_NAME.match(name.strip()))


def weather_icons(w: dict | None) -> list:
    """Z bloku pogody raportu z jazdy: niebo (opad / zachmurzenie) + najwyzej jedno ostrzezenie (wiatr / upal / mroz)."""
    if not w:
        return []
    def v(k):
        x = w.get(k) or {}
        return x.get("value") if isinstance(x, dict) else None
    pr, t, cl, wi = v("precip_mm") or {}, v("temp_c") or {}, v("cloud_pct"), v("wind_ms") or {}
    out = []
    if (pr.get("wet_h") or 0) >= 1 or (pr.get("sum") or 0) >= 1.0:
        out.append("❄️" if (t.get("avg") is not None and t["avg"] <= 1) else "🌧️")
    elif cl is not None:
        out.append("☀️" if cl < 25 else ("🌤️" if cl < 70 else "☁️"))
    if (wi.get("max") or 0) >= 8:
        out.append("💨")
    elif t.get("max") is not None and t["max"] >= 28:
        out.append("🔥")
    elif t.get("min") is not None and t["min"] <= 0:
        out.append("🥶")
    return out[:2]


def ride_label(km: float, surface: dict | None, bp_day: int | None) -> str | None:
    if bp_day:
        return "bikepacking D%d" % bp_day
    if km >= EXPED_KM:
        return "wyprawa"
    if not surface:
        return None
    if surface["szuter"] + surface["ujeby"] > 30:
        return "gravel"
    if surface["asfalt"] > 85:
        return "szosa"
    return "mix"


def title_places(towns: list, ranks: dict) -> list:
    """Dwa najwazniejsze punkty: najpierw miasta, potem miasteczka, potem wsie; pierwszy i ostatni w kolejnosci jazdy."""
    if not towns:
        return []
    top = max(ranks.get(t, 0) for t in towns)
    sel = [t for t in towns if ranks.get(t, 0) == top]
    if len(sel) == 1:
        rest = [t for t in towns if t != sel[0] and ranks.get(t, 0) == max([ranks.get(x, 0) for x in towns if x != sel[0]] or [0])]
        return [sel[0]] + ([rest[-1]] if rest else [])
    return [sel[0], sel[-1]]


def build_title(kind: str | None, places: list, label: str | None, eff_cls: str | None, wx: list) -> str:
    if kind in KIND_TITLE:
        return KIND_TITLE[kind]
    head = "[Qbot] " + (" – ".join(places) if places else "Jazda")
    tail = " ".join(x for x in [label, EFFORT_ICON.get(eff_cls or "")] + list(wx) if x)
    return head + (" · " + tail if tail else "")


def bikepacking_day(c, ride_key, start_pt, day) -> int | None:
    """Dzien wyprawy: start > 80 km od Warszawy i poprzedni dzien (lub dni) tez tak. Pierwszy dzien = 'wyprawa'/etc,
    bo w dniu jazdy QBot nie wie jeszcze, ze bedzie nastepny."""
    if hav_m(start_pt, HOME) < AWAY_KM * 1000:
        return None
    rows = _rows(c, "SELECT t.date, r.lat, r.lon FROM qbot_v2.training_sessions t JOIN LATERAL ("
                    "SELECT lat, lon FROM qbot_v2.activity_record r WHERE r.external_id=t.external_id AND r.lat IS NOT NULL "
                    "ORDER BY ts LIMIT 1) r ON true WHERE t.date BETWEEN %s::date - 30 AND %s::date - 1 AND t.external_id<>%s",
                 (day, day, ride_key))
    away = {r["date"] for r in rows if hav_m((r["lat"], r["lon"]), HOME) >= AWAY_KM * 1000}
    n, d = 1, day - timedelta(days=1)
    while d in away:
        n += 1
        d -= timedelta(days=1)
    return n if n >= 2 else None


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
    s = _one(c, "SELECT avg_hr_bpm, avg_power_w FROM qbot_v2.training_sessions WHERE external_id=%s", (ride_key,)) or {}
    r = _one(c, "SELECT xss, xss_per_h, min_wbal_pct FROM qbot_v2.fitmodel_wbal_ride WHERE external_id=%s AND status='OK'", (ride_key,)) or {}
    if r.get("xss") is None and not s.get("avg_hr_bpm") and not s.get("avg_power_w"):
        return None
    p = _one(c, "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY xss_per_h) h50, percentile_cont(0.75) WITHIN GROUP (ORDER BY xss_per_h) h75, "
                "percentile_cont(0.75) WITHIN GROUP (ORDER BY xss) x75 "
                "FROM qbot_v2.fitmodel_wbal_ride WHERE status='OK' AND xss IS NOT NULL AND external_id<>%s", (ride_key,))
    q = _one(c, "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY avg_hr_bpm) hr50, percentile_cont(0.75) WITHIN GROUP (ORDER BY avg_hr_bpm) hr75, "
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY avg_power_w) pw50, percentile_cont(0.75) WITHIN GROUP (ORDER BY avg_power_w) pw75 "
                "FROM qbot_v2.training_sessions WHERE duration_s >= 1800 AND avg_power_w > 0 AND date >= '2025-01-01' AND external_id<>%s", (ride_key,))
    p = {k: float(v) for k, v in dict(p, **q).items() if v is not None}
    e = {"xss": float(r["xss"]) if r.get("xss") is not None else None, "xss_h": float(r.get("xss_per_h") or 0),
         "min_wbal": float(r["min_wbal_pct"]) if r.get("min_wbal_pct") is not None else None,
         "avg_hr": float(s["avg_hr_bpm"]) if s.get("avg_hr_bpm") else None, "avg_pw": float(s["avg_power_w"]) if s.get("avg_power_w") else None}
    e["cls"] = effort_class(e, p)
    e["progi"] = {k: round(v, 1) for k, v in p.items()}
    return e


SNAP_DIR = "/opt/qbot/artifacts/tiles/snap"
NO_ATTR_KM = 25.0                   # decyzja Michala: dla Warszawy i okolic bez atrakcji


def tiles_snapshot(force: bool = False) -> str | None:
    """Migawka kafelkow StatsHunters (cala historia) z data pobrania. Raz na dobe; trzymamy 14 ostatnich."""
    import glob, json as _j
    os.makedirs(SNAP_DIR, exist_ok=True)
    snaps = sorted(glob.glob(SNAP_DIR + "/*.json"))
    if snaps and not force and time.time() - os.path.getmtime(snaps[-1]) < 20 * 3600:
        return snaps[-1]
    try:
        sys.path.insert(0, "/opt/qbot/app/tools")
        from tools.tile_store import fetch_tiles, _env
        share = os.getenv("STATSHUNTERS_SHARE_ID", _env().get("STATSHUNTERS_SHARE_ID", ""))
        if not share:
            return None
        d = fetch_tiles(share, force=True)
        if d.get("_error") or not d.get("tiles"):
            print("[strava publish] statshunters: %s" % d.get("_error"))
            return None
        name = SNAP_DIR + "/%s.json" % datetime.fromisoformat(d["fetched_at"]).strftime("%Y%m%d%H%M")
        with open(name, "w") as h:
            _j.dump({"fetched_at": d["fetched_at"], "tiles": d["tiles"]}, h)
        for old in sorted(glob.glob(SNAP_DIR + "/*.json"))[:-14]:
            os.remove(old)
        return name
    except Exception as e:
        print("[strava publish] migawka kafelkow: %s" % e)
        return None


def _snapshot_before(start_ts) -> set | None:
    """Najnowsza migawka pobrana PRZED startem jazdy (czas lokalny serwera)."""
    import glob, json as _j
    best = None
    for p in sorted(glob.glob(SNAP_DIR + "/*.json")):
        try:
            fa = datetime.strptime(os.path.basename(p)[:12], "%Y%m%d%H%M")
        except ValueError:
            continue
        if fa < start_ts.astimezone().replace(tzinfo=None):
            best = p
    if not best:
        return None
    return {tuple(t) for t in _j.load(open(best))["tiles"]}


def _new_tiles(c, ride_key, tr):
    """Nowe kwadraty (zoom 14) = nie ma ich ani w historii GPS QBota sprzed jazdy, ani w migawce StatsHunters sprzed jazdy.
    Brak migawki sprzed jazdy -> None (linijki nie ma; nie zgadujemy). Squadratinhos (zoom 17) nie liczymy."""
    base = _snapshot_before(tr[0]["ts"])
    if base is None:
        return None
    la = [r["lat"] for r in tr]; lo = [r["lon"] for r in tr]
    rows = _rows(c, """WITH t AS (SELECT DISTINCT floor((lon+180)/360*16384)::int x,
                  floor((1-ln(tan(radians(lat))+1/cos(radians(lat)))/pi())/2*16384)::int y
                  FROM qbot_v2.activity_record WHERE external_id=%s AND lat IS NOT NULL),
               prev AS (SELECT DISTINCT floor((lon+180)/360*16384)::int x,
                  floor((1-ln(tan(radians(lat))+1/cos(radians(lat)))/pi())/2*16384)::int y
                  FROM qbot_v2.activity_record WHERE external_id<>%s AND lat IS NOT NULL
                  AND ts < (SELECT min(ts) FROM qbot_v2.activity_record WHERE external_id=%s)
                  AND lat BETWEEN %s AND %s AND lon BETWEEN %s AND %s)
               SELECT t.x, t.y FROM t WHERE NOT EXISTS (SELECT 1 FROM prev p WHERE p.x=t.x AND p.y=t.y)""",
             (ride_key, ride_key, ride_key, min(la) - 0.05, max(la) + 0.05, min(lo) - 0.05, max(lo) + 0.05))
    return len({(r["x"], r["y"]) for r in rows} - base)


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



# ---------------------------------------------------------------- MyBiom / do Mamy (2026-10-09 b)
# Uczone z nazw Michala na Stravie: nazwa ~ "mam" = do Mamy, ~ "biom" = MyBiom. Kafelki zoom 15 sladow GPS.
KIND_MAX_KM = 45.0
MYBIOM_REGION = "Przepiękna Puszcza Słupecka"
_KIND_CACHE = {"t": 0.0, "m": None}
_Z15 = ("floor((r.lon+180)/360*32768)::int AS x, "
        "floor((1-ln(tan(radians(r.lat))+1/cos(radians(r.lat)))/pi())/2*32768)::int AS y")


def kind_model(c) -> dict:
    if _KIND_CACHE["m"] is not None and time.time() - _KIND_CACHE["t"] < 6 * 3600:
        return _KIND_CACHE["m"]
    rows = _rows(c, "WITH lab AS (SELECT DISTINCT ride_key, CASE WHEN name ~* 'mam' THEN 'domamy' ELSE 'mybiom' END k "
                    "FROM qbot_v2.strava_activity WHERE ride_key IS NOT NULL AND (name ~* 'mam' OR name ~* 'biom')) "
                    "SELECT DISTINCT l.k, l.ride_key, " + _Z15 + " FROM qbot_v2.activity_record r JOIN lab l ON r.external_id=l.ride_key "
                    "WHERE r.lat IS NOT NULL")
    m = {"domamy": {}, "mybiom": {}}
    for r in rows:
        m[r["k"]].setdefault(r["ride_key"], set()).add((r["x"], r["y"]))
    _KIND_CACHE.update(t=time.time(), m=m)
    return m


def kind_scores(tiles: set, model: dict, exclude: str | None = None) -> dict:
    out = {}
    for k, rides in model.items():
        rides = {rk: s for rk, s in rides.items() if rk != exclude}
        cnt = {}
        for s in rides.values():
            for t in s:
                cnt[t] = cnt.get(t, 0) + 1
        core = {t for t, v in cnt.items() if v >= 0.6 * max(1, len(rides))}
        out[k] = {"core_hit": round(len(tiles & core) / len(core), 2) if core else 0.0,
                  "cov": round(len(tiles & set(cnt)) / len(tiles), 2) if tiles else 0.0}
    return out


def kind_decide(km: float, sc: dict) -> str | None:
    """Progi z walidacji 09.10 (88 jazd do 45 km): prawdziwe do Mamy core_hit 0,65-1,0, inne jazdy <= 0,17;
    do Mamy wymaga tez >= 60% sladu na znanych drogach (odpada szosa obok). MyBiom: wiekszosc rdzenia lasow + prawie caly slad
    w znanych kafelkach; ponizej 10 km (testy przerzutki, dojazdy) - nic."""
    if km > KIND_MAX_KM or km < 10:
        return None
    if sc["domamy"]["core_hit"] >= 0.6 and sc["domamy"]["cov"] >= 0.6:
        return "domamy"
    if sc["mybiom"]["core_hit"] >= 0.6 and sc["mybiom"]["cov"] >= 0.8:
        return "mybiom"
    return None


def ride_kind(c, ride_key, km, exclude_self=True):
    t = {(r["x"], r["y"]) for r in _rows(c, "SELECT DISTINCT " + _Z15 + " FROM qbot_v2.activity_record r "
                                            "WHERE r.external_id=%s AND r.lat IS NOT NULL", (ride_key,))}
    sc = kind_scores(t, kind_model(c), ride_key if exclude_self else None)
    return kind_decide(km, sc), sc

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
        if hav_m(it["pt"], HOME) < NO_ATTR_KM * 1000:   # Warszawa i okolice - bez atrakcji
            continue
        if _SACRAL.search(it["name"]) or any(_SACRAL.search(t) for t in it["types"]):   # decyzja Michala: zadnych odniesien religijnych
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
        "zamek, palac, twierdza, znany zabytek swiecki, slynne miejsce. NIGDY obiekty religijne. Rezerwaty, "
        "dworki bez znaczenia, schrony, pomniki - pomijaj. Nie wybieraj dwoch czesci tego samego zespolu "
        "- wtedy jedna, najwazniejsza. Lepiej pusta lista niz atrakcja na sile.")


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
    s = _one(c, "SELECT distance_m, elevation_m, started_at, date FROM qbot_v2.training_sessions WHERE external_id=%s", (ride_key,))
    tr = _track(c, ride_key)
    if not s or len(tr) < 60:
        raise RuntimeError("brak jazdy lub sladu GPS")
    rep = _one(c, "SELECT w1_json->'surface'->'value'->'types_pct' AS t, w1_json->'weather' AS w "
                  "FROM qbot_v2.ride_report_data WHERE ride_key=%s", (ride_key,))
    start, end = (tr[0]["lat"], tr[0]["lon"]), (tr[-1]["lat"], tr[-1]["lon"])
    km = (s["distance_m"] or 0) / 1000.0
    kind, ksc = ride_kind(c, ride_key, km)
    if kind == "domamy":     # decyzja Michala: jazda do Mamy - bez komentarza
        return {"ride_key": ride_key, "kind": kind, "kind_scores": ksc, "km": km, "description": "", "title": KIND_TITLE[kind]}
    pts = [(r["lat"], r["lon"]) for r in tr[::5]]
    f = {"ride_key": ride_key, "kind": kind, "kind_scores": ksc, "km": km, "elev_m": s["elevation_m"],
         "moving_s": sum(1 for r in tr if (r["speed_mps"] or 0) > 0.8),
         "surface": surface_split((rep or {}).get("t")), "effort": _effort(c, ride_key), "new_tiles": _new_tiles(c, ride_key, tr)}
    # miejscowosci i administracja (bez okolic startu/mety)
    towns, admin, ranks, nxt = [], [], {}, 0.0
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
            ranks[p] = 2 if a.get("city") else (1 if a.get("town") else 0)
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
    if kind == "mybiom":      # decyzja Michala: MyBiom ma zawsze ta lokalizacje
        region = MYBIOM_REGION
    if not region:
        region = ("między %s a %s" % (towns[0], towns[-1])) if len(towns) >= 2 else (towns[0] if towns else (admin[-1] if admin else "Polska"))
    region = region[:1].upper() + region[1:]
    f["region"], f["attractions"], f["ai_note"] = region, atr, note
    f["description"] = assemble(f, region, atr)
    bp = bikepacking_day(c, ride_key, start, s["date"])
    f["title"] = build_title(kind, title_places(towns, ranks), ride_label(km, f.get("surface"), bp),
                             (f.get("effort") or {}).get("cls"), weather_icons((rep or {}).get("w")))
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
        todo = _rows(c, "SELECT a.strava_id, a.ride_key, a.start_date, a.name, COALESCE(p.attempts,0) attempts FROM qbot_v2.strava_activity a "
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
                if f.get("title") and is_default_name(t.get("name")):   # tylko w miejsce domyslnej nazwy
                    data["name"] = f["title"]
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
                tiles_snapshot()
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
            for x in fx.get("candidates", []):
                x.pop("pt", None)
            print(json.dumps({k: v for k, v in fx.items() if k != "description"}, ensure_ascii=False, indent=1, default=str))
            print("\n===== TYTUL (gdy nazwa domyslna) =====\n" + str(fx.get("title")))
            print("\n===== OPIS =====\n" + (fx["description"] or "(bez opisu - pole opisu na Stravie zostanie wyczyszczone)"))
        finally:
            cn.close()
    elif a.once:
        print(run_publish())
