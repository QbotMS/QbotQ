"""Sprzet na jazde (Analiza trasy -> Sprzet): pogoda wstecz, stan nawierzchni, rower, lampki, blotniki.

Decyzje Michala 2026-10-10:
- kluczowe dla wyboru sprzetu: co dzialo sie z pogoda przez ostatnie 7 dni, a zwlaszcza 24 h przed startem
  (Open-Meteo, opady godzinowe w kilku punktach trasy) -> stan nawierzchni: sucho / wilgotno / mokro / bloto;
  ten stan idzie tez do doboru ubioru (outfit_advisor.warunki: 'nawierzchnia_po_opadach'),
- rower: AI wybiera z Garazu (Grizl / Grail / Monster; bez 'Rower Goski') wg nawierzchni trasy (asfalt / szuter / ujeby),
  stanu po opadach, dlugosci, opon na kolach, zadan serwisowych; + drugi wybor,
- lampki (regula w kodzie): start przed wschodem, meta po zachodzie lub < 30 min przed nim, slaba widocznosc (mgla) ->
  konkretne lampki z Garazu (Nawigacja i swiatla),
- blotniki: przy mokro / bloto / deszczu w czasie jazdy; Michal je ma i dopisze do Garazu (szukane w equipment/components).
Dok.: docs/OUTFIT_FAVORITES.md (sekcja Sprzet: rower i akcesoria)
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sqlite3
import time

GARAGE_DB = "/opt/qbot/app/data/garage.db"
EXCLUDE_BIKES = re.compile(r"go\u015bk|goski", re.I)          # rower partnerki - nie proponowac
UNPAVED_CATS = {2: "szuter", 3: "szuter", 4: "ujeby", 5: "ujeby"}
DUSK_MARGIN_MIN = 30
# Zasady wyboru roweru od Michala (2026-10-10) - twarde, przed ocena AI:
BIKE_RULES = [
    "Monster (Canyon Grand Canyon) to rower na ZIM\u0118 i na NAPRAWD\u0118 ci\u0119\u017ckie warunki (\u015bnieg, mr\u00f3z, g\u0142\u0119bokie b\u0142oto) -"
    " NIE wybieraj go na zwyk\u0142e trasy ok. 80 km i d\u0142u\u017csze, nawet gdy jest mokro albo s\u0105 odcinki piachu.",
    "Bie\u017c\u0105ce zadania serwisowe NIE wp\u0142ywaj\u0105 na wyb\u00f3r roweru (serwis ogarnia Micha\u0142).",
    "Wybory_michala to jego r\u0119czne decyzje na wcze\u015bniejszych trasach - traktuj je jako wzorzec (podobna trasa i warunki -> ten sam rower).",
]
_CACHE: dict = {}
_TTL_S = 1800


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


# ---------------- pogoda wstecz ----------------
def _sample(coords, n=4):
    if not coords:
        return []
    if len(coords) <= n:
        return coords
    step = (len(coords) - 1) / float(n - 1)
    return [coords[int(round(i * step))] for i in range(n)]


def past_weather(coords, day: str, start: str, total_h: float | None = None) -> dict:
    """Opady godzinowe z 7 dni przed startem (+ widocznosc w czasie jazdy) dla kilku punktow trasy (Open-Meteo)."""
    pts = _sample(coords or [], 4)
    if not pts:
        return {"ok": False, "blad": "brak geometrii trasy"}
    key = (tuple((round(p[0], 2), round(p[1], 2)) for p in pts), day, start)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL_S:
        return hit[1]
    import httpx
    d0 = _dt.date.fromisoformat(day)
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&hourly=precipitation,visibility"
           "&start_date=%s&end_date=%s&timezone=Europe%%2FWarsaw" % (
               ",".join("%.4f" % p[0] for p in pts), ",".join("%.4f" % p[1] for p in pts),
               (d0 - _dt.timedelta(days=7)).isoformat(), d0.isoformat()))
    try:
        with httpx.Client(timeout=12.0) as c:
            r = c.get(url)
            r.raise_for_status()
            js = r.json()
    except Exception as e:  # noqa
        return {"ok": False, "blad": "Open-Meteo: %s" % str(e)[:120]}
    if isinstance(js, dict):
        js = [js]
    st = _hm(start) or 600
    t0 = _dt.datetime.combine(d0, _dt.time(st // 60, st % 60))
    t_end = t0 + _dt.timedelta(hours=float(total_h or 4.0))
    per = []
    vis_min = None
    for loc in js:
        h = loc.get("hourly") or {}
        tt, pp, vv = h.get("time") or [], h.get("precipitation") or [], h.get("visibility") or []
        s24 = s48 = s72 = s7 = 0.0
        last_rain = None
        for i, ts in enumerate(tt):
            try:
                t = _dt.datetime.fromisoformat(ts)
            except Exception:
                continue
            p = _f(pp[i] if i < len(pp) else None, 0.0) or 0.0
            if t < t0:
                dh = (t0 - t).total_seconds() / 3600.0
                if dh <= 168:
                    s7 += p
                if dh <= 72:
                    s72 += p
                if dh <= 48:
                    s48 += p
                if dh <= 24:
                    s24 += p
                if p >= 0.2 and (last_rain is None or t > last_rain):
                    last_rain = t
            elif t <= t_end:
                v = _f(vv[i] if i < len(vv) else None)
                if v is not None:
                    vis_min = v if vis_min is None else min(vis_min, v)
        per.append({"24h": round(s24, 1), "48h": round(s48, 1), "72h": round(s72, 1), "7d": round(s7, 1),
                    "ostatni_deszcz_h": round((t0 - last_rain).total_seconds() / 3600.0) if last_rain else None})
    if not per:
        return {"ok": False, "blad": "brak danych Open-Meteo"}
    mx = {k: max(x[k] for x in per) for k in ("24h", "48h", "72h", "7d")}
    av = {k: round(sum(x[k] for x in per) / len(per), 1) for k in ("24h", "48h", "72h", "7d")}
    lr = [x["ostatni_deszcz_h"] for x in per if x["ostatni_deszcz_h"] is not None]
    out = {"ok": True, "punktow": len(per), "opady_mm_max": mx, "opady_mm_srednio": av,
           "ostatni_deszcz_h_temu": min(lr) if lr else None, "widocznosc_min_m": vis_min,
           "zrodlo": "Open-Meteo, opady godzinowe w %d punktach trasy, 7 dni przed startem %s %s" % (len(per), day, start)}
    _CACHE[key] = (time.time(), out)
    return out


def unpaved_pct(data: dict) -> dict:
    by = ((data.get("details") or {}).get("surface") or {}).get("by_cat") or []
    tot = sum(_f(x.get("km"), 0.0) for x in by) or 0.0
    res = {"asfalt": 0.0, "szuter": 0.0, "ujeby": 0.0}
    for x in by:
        k = int(x.get("k") or 0)
        res[UNPAVED_CATS.get(k, "asfalt")] += _f(x.get("km"), 0.0)
    if not tot:
        return {}
    return {k: round(v / tot * 100) for k, v in res.items()}


def surface_state(pw: dict, unp: dict, ride_rain: dict | None) -> dict:
    """sucho / wilgotno / mokro / bloto (+ powod). Progi: decyzja 2026-10-10 (do kalibracji na jazdach)."""
    if not pw or not pw.get("ok"):
        return {"stan": "nieznany", "powod": (pw or {}).get("blad") or "brak danych"}
    m = pw["opady_mm_max"]
    rr = ride_rain or {}
    r_mm, r_pr = _f(rr.get("suma_mm"), 0.0) or 0.0, _f(rr.get("max_proc"), 0.0) or 0.0
    off = (unp.get("szuter", 0) + unp.get("ujeby", 0)) if unp else 50
    why = ("opady: 24 h %.1f mm, 48 h %.1f mm, 7 dni %.1f mm" % (m["24h"], m["48h"], m["7d"])).replace(".", ",").replace("opady,", "opady:")
    if pw.get("ostatni_deszcz_h_temu") is not None:
        why += "; ostatni deszcz ok. %d h przed startem" % pw["ostatni_deszcz_h_temu"]
    if off >= 25 and (m["24h"] >= 8 or m["48h"] >= 15 or (m["7d"] >= 25 and m["48h"] >= 5)):
        st = "bloto"
    elif m["24h"] >= 3 or m["48h"] >= 8 or r_mm >= 1 or r_pr >= 50:
        st = "mokro"
    elif m["7d"] >= 10 or m["24h"] >= 0.5:
        st = "wilgotno"
    else:
        st = "sucho"
    if r_mm >= 1 or r_pr >= 50:
        why += "; w czasie jazdy prognoza deszczu (%d%%, %s mm)" % (r_pr, ("%.1f" % r_mm).replace(".", ","))
    opis = {"sucho": "sucho" + (" — na szutrze możliwy sypki piach i kurz" if m["7d"] < 2 and off >= 25 else ""),
            "wilgotno": "wilgotno — szuter zwięzły, miejscami kałuże",
            "mokro": "mokro — chlapie spod kół, kałuże, śliskie korzenie i bruk",
            "bloto": "błoto na drogach gruntowych — ciężko, oblepia napęd i opony"}[st]
    return {"stan": st, "opis": opis, "powod": why, "nieutwardzone_pct": off}


# ---------------- garaz ----------------
def _g():
    g = sqlite3.connect(GARAGE_DB)
    g.row_factory = sqlite3.Row
    return g


def bikes() -> list:
    g = _g()
    try:
        rows = g.execute("SELECT id, name, nickname, type, notes FROM bikes WHERE active=1").fetchall()
        out = []
        for b in rows:
            if EXCLUDE_BIKES.search("%s %s" % (b["name"] or "", b["nickname"] or "")):
                continue
            ty = g.execute("SELECT t.brand, t.model, t.width_mm, t.type, t.position FROM tires t JOIN wheel_mounts w "
                           "ON w.wheel_id=t.wheel_id AND w.to_at IS NULL WHERE w.bike_id=? AND (t.status IS NULL OR t.status LIKE 'zamont%')",
                           (b["id"],)).fetchall()
            out.append({"id": int(b["id"]), "nazwa": b["name"], "ksywa": b["nickname"], "typ": b["type"],
                        "opony": ["%s %s %s mm%s" % (t["brand"] or "", t["model"] or "", t["width_mm"] or "?",
                                                     (" (%s)" % t["position"]) if t["position"] else "") for t in ty],
                        "notatki": (b["notes"] or "")[:300]})
        return out
    finally:
        g.close()


def _equip(pattern):
    g = _g()
    try:
        out = []
        for r in g.execute("SELECT id, category, brand, model, mount FROM equipment WHERE active=1").fetchall():
            if re.search(pattern, "%s %s %s" % (r["category"] or "", r["brand"] or "", r["model"] or ""), re.I):
                out.append({"id": int(r["id"]), "nazwa": ("%s %s" % (r["brand"] or "", r["model"] or "")).strip(),
                            "kategoria": r["category"], "mocowanie": r["mount"], "zrodlo": "equipment"})
        for r in g.execute("SELECT id, category, brand, model, bike_id FROM components WHERE active=1").fetchall():
            if re.search(pattern, "%s %s %s" % (r["category"] or "", r["brand"] or "", r["model"] or ""), re.I):
                out.append({"id": int(r["id"]), "nazwa": ("%s %s" % (r["brand"] or "", r["model"] or "")).strip(),
                            "kategoria": r["category"], "rower_id": r["bike_id"], "zrodlo": "components"})
        return out
    finally:
        g.close()


def lights_list() -> dict:
    items = [x for x in _equip(r"\u015bwiat|swiatl|lamp|light|czo\u0142\u00f3wk") if not re.search(r"karoo|garmin|wahoo", x["nazwa"], re.I)]
    przod, tyl, inne = [], [], []
    for x in items:
        n = x["nazwa"].lower()
        if "czo\u0142\u00f3wk" in n or "headlamp" in n:
            inne.append(x)
        elif "rear" in n or "tyl" in n or (x.get("mocowanie") or "") in ("rama", "bagaznik", "sztyca"):
            tyl.append(x)
        else:
            przod.append(x)
    tyl.sort(key=lambda x: 0 if "rear" in x["nazwa"].lower() else 1)
    return {"przod": przod, "tyl": tyl, "inne": inne}


# ---------------- akcesoria (reguly w kodzie) ----------------
def accessories(data: dict, start: str, pw: dict, stan: dict) -> dict:
    w = (data.get("details") or {}).get("weather") or {}
    sl = w.get("slonce") or {}
    st, th = _hm(start), _f((data.get("time") or {}).get("total_h"))
    meta = st + int(round(th * 60)) if st is not None and th else None
    sun_r, sun_s = _hm(sl.get("wschod")), _hm(sl.get("zachod"))
    why, need = [], None
    if st is not None and sun_r is not None and st < sun_r:
        why.append("start %s przed wschodem słońca (%s)" % (_fmt(st), sl.get("wschod")))
        need = "wymagane"
    if meta is not None and sun_s is not None and meta > sun_s - DUSK_MARGIN_MIN:
        why.append("meta ok. %s %s zachodem słońca (%s)" % (_fmt(meta), "po" if meta > sun_s else "tuż przed", sl.get("zachod")))
        need = "wymagane"
    vis = (pw or {}).get("widocznosc_min_m")
    if vis is not None and vis < 1000:
        why.append("mgła: widoczność spada do ok. %d m" % vis)
        need = "wymagane"
    elif vis is not None and vis < 3000:
        why.append("ograniczona widoczność (ok. %s km)" % ("%.1f" % (vis / 1000.0)).replace(".", ","))
        need = need or "zalecane"
    L = lights_list()
    lamp = {"potrzeba": need or "niepotrzebne", "powod": "; ".join(why) or "jazda w pełnym dniu, dobra widoczność",
            "meta": _fmt(meta) if meta is not None else None, "zachod": sl.get("zachod"), "wschod": sl.get("wschod")}
    if need:
        lamp["wez"] = (L["przod"][:1] if need == "wymagane" else []) + L["tyl"][:1]
        if need == "wymagane" and L["inne"]:
            lamp["zapas"] = L["inne"][:1]
    wet = (stan or {}).get("stan") in ("mokro", "bloto")
    fe = _equip(r"b\u0142otnik|blotnik|fender|mudguard")
    bl = {"potrzeba": "zalecane" if wet else "niepotrzebne",
          "powod": (stan or {}).get("opis") or "", "w_garazu": fe}
    if wet and not fe:
        bl["uwaga"] = "nie ma ich w Gara\u017cu - dopisz, wtedy wska\u017c\u0119 konkretne"
    return {"lampki": lamp, "blotniki": bl}


# ---------------- rower (AI) ----------------
def context(data: dict, stan: dict, unp: dict) -> dict:
    r = data.get("route") or {}
    return {"km": r.get("distance_km"), "przewyzszenie_m": r.get("ascent_m"), "czas_h": (data.get("time") or {}).get("total_h"),
            "nawierzchnia_pct": unp, "stan": (stan or {}).get("stan")}


def manual_history(conn, n=12) -> list:
    """Reczne wybory roweru Michala (wzorzec dla AI)."""
    try:
        ensure(conn)
        rows = conn.execute("SELECT route_id, ride_date, payload FROM qbot_v2.route_kit WHERE payload->>'recznie'='true' "
                            "ORDER BY created_at DESC LIMIT %s", (n,)).fetchall()
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []
    out, seen = [], set()
    for x in rows:
        x = dict(x) if isinstance(x, dict) else dict(zip(("route_id", "ride_date", "payload"), x))
        k = (x["route_id"], str(x["ride_date"]))
        if k in seen:
            continue
        seen.add(k)
        pl = x["payload"] if not isinstance(x["payload"], str) else json.loads(x["payload"])
        out.append({"rower": ((pl.get("rower") or {}).get("nazwa")), "trasa": pl.get("kontekst")})
    return out


def manual_bike(bike_id: int, kontekst: dict | None = None) -> dict:
    by = {b["id"]: b for b in bikes()}
    if int(bike_id) not in by:
        return {"ok": False, "blad": "rower spoza Garazu"}
    b = by[int(bike_id)]
    return {"ok": True, "recznie": True, "rower": {"id": b["id"], "nazwa": b["nazwa"], "ksywa": b["ksywa"], "opony": b["opony"],
            "dlaczego": "Tw\u00f3j wyb\u00f3r."}, "kontekst": kontekst or {},
            "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}


def choose_bike(data: dict, stan: dict, unp: dict, pw: dict, conn=None) -> dict:
    from qgpt_client import qgpt_json
    bs = bikes()
    if not bs:
        return {"ok": False, "blad": "brak rowerow w Garazu"}
    r = data.get("route") or {}
    sf = (data.get("details") or {}).get("surface") or {}
    sand = sum(1 for x in sf.get("risk") or [] if "piach" in json.dumps(x, ensure_ascii=False).lower() or "sand" in json.dumps(x).lower())
    inp = {"trasa": {"km": r.get("distance_km"), "przewyzszenie_m": r.get("ascent_m"), "czas_h": (data.get("time") or {}).get("total_h"),
                     "nawierzchnia_pct": unp, "odcinki_ryzykowne": len(sf.get("risk") or []), "odcinki_z_ryzykiem_piachu": sand},
           "stan_po_opadach": stan, "opady_mm": (pw or {}).get("opady_mm_max"), "rowery": bs,
           "zasady_michala": BIKE_RULES, "wybory_michala": manual_history(conn) if conn is not None else []}
    prompt = ("Wybierz rower na te jazde z listy 'rowery' (pole id) i podaj drugi wybor. NAJPIERW 'zasady_michala' (twarde) i "
              "'wybory_michala' (wzorzec), potem: udzial asfaltu / szutru / ujebow (trudny teren), stan nawierzchni po opadach, "
              "dlugosc i czas jazdy (dlugo po asfalcie -> szybszy, lzejszy rower), opony zamontowane na kolach. "
              "Piszesz po polsku z polskimi znakami, na TY, konkretnie, z liczbami.\n\n"
              + json.dumps(inp, ensure_ascii=False)
              + '\n\nZwroc TYLKO JSON: {"rower_id": id, "dlaczego": "1-2 zdania", "drugi_id": id, "drugi_dlaczego": "1 zdanie: kiedy lepszy drugi",'
                ' "opony_uwaga": "1 zdanie o oponach/cisnieniu w tych warunkach albo pusty"}')
    try:
        o = qgpt_json(prompt, system="Doradca sprzetu gravelowego QBota. Tylko JSON.", max_tokens=900, temperature=0.3)
    except Exception as e:  # noqa
        return {"ok": False, "blad": "AI: %s" % str(e)[:120]}
    by = {b["id"]: b for b in bs}
    try:
        rid = int(o.get("rower_id"))
    except Exception:
        rid = None
    if rid not in by:
        return {"ok": False, "blad": "AI wskazalo rower spoza Garazu"}
    try:
        did = int(o.get("drugi_id"))
    except Exception:
        did = None
    out = {"ok": True, "rower": {"id": rid, "nazwa": by[rid]["nazwa"], "ksywa": by[rid]["ksywa"], "opony": by[rid]["opony"],
                                 "dlaczego": (o.get("dlaczego") or "").strip()},
           "opony_uwaga": (o.get("opony_uwaga") or "").strip(),
           "kontekst": context(data, stan, unp), "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
    if did in by and did != rid:
        out["drugi"] = {"id": did, "nazwa": by[did]["nazwa"], "ksywa": by[did]["ksywa"], "dlaczego": (o.get("drugi_dlaczego") or "").strip()}
    return out


def ensure(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS qbot_v2.route_kit (id bigserial PRIMARY KEY, route_id text NOT NULL, ride_date date NOT NULL, "
                 "created_at timestamptz NOT NULL DEFAULT now(), payload jsonb NOT NULL)")


def save_bike(conn, route_id, day, payload):
    ensure(conn)
    conn.execute("INSERT INTO qbot_v2.route_kit (route_id, ride_date, payload) VALUES (%s,%s,%s::jsonb)",
                 (route_id, day, json.dumps(payload, ensure_ascii=False)))
    conn.commit()


def load_bike(conn, route_id, day):
    ensure(conn)
    r = conn.execute("SELECT payload FROM qbot_v2.route_kit WHERE route_id=%s AND ride_date=%s ORDER BY created_at DESC LIMIT 1",
                     (route_id, day)).fetchone()
    conn.commit()
    if not r:
        return None
    p = r["payload"] if isinstance(r, dict) else r[0]
    return json.loads(p) if isinstance(p, str) else p


# ---------------- calosc ----------------
def ride_rain(data: dict) -> dict:
    win = ((data.get("details") or {}).get("weather") or {}).get("windows") or []
    if not win:
        return {}
    return {"max_proc": max(_f(x.get("opad_prob"), 0.0) for x in win), "suma_mm": round(sum(_f(x.get("opad_mm"), 0.0) for x in win), 1)}


def build(data: dict, coords, day: str, start: str) -> dict:
    pw = past_weather(coords, day, start, _f((data.get("time") or {}).get("total_h")))
    unp = unpaved_pct(data)
    stan = surface_state(pw, unp, ride_rain(data))
    return {"pogoda_wstecz": pw, "nawierzchnia_pct": unp, "stan": stan, "akcesoria": accessories(data, start, pw, stan)}
