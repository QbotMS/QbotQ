"""TRENER - poranna korekta planu z uwagi na pogode (2026-10-12).

Decyzje Michala: sprawdzenie RANO w dniu (w porannej wiadomosci 7:00), Trener tylko PROPONUJE (przyciski Zmien / Zostaw),
jazdy dodane recznie dostaja samo ostrzezenie.

Jak dziala:
  * prognoza godzinowa Open-Meteo dla "domu" (E.home_point) -> pogoda w OKNIE jazdy (start .. start + czas),
    a nie srednia 8-18 jak przy ukladaniu planu;
  * progi: E.wx_bad (Kalibracja wx.*; auto z historii jazd);
  * gdy jazda AUTO z planu przekracza prog -> propozycja w kolejnosci z Kalibracji wx.fallback
    (0 przesun godzine, 1 przesun dzien, 2 skroc, 3 zamien na dom = wioslarz), potem pozostale opcje;
  * propozycja zapisana w trainer_auto_cache (klucz wxprop:<id sesji>); "Zmien" wykonuje ja jako zmiane 'pogoda'
    w trainer_change (z przyciskiem Cofnij -> OPS.undo), "Zostaw" tylko odnotowuje.
Czyste funkcje (window_wx, candidates, pick) testowane w tests/test_trener_weather.py. Dokumentacja: docs/TRENER.md.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

import qbot_trener_engine as E

DAY_FROM, DAY_TO = 7 * 60, 20 * 60      # okno przesuwania godziny (min od polnocy)
STEP = 30
INDOOR_WORDS = ("trenaż", "trenaz", "indoor", "zwift", "rolki")
ORDER = ["hour", "day", "short", "home"]
DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]
_HCACHE: dict = {}


# ---------------- prognoza godzinowa ----------------

def hourly(lat: float, lon: float) -> dict[str, dict]:
    key = (lat, lon)
    if key in _HCACHE and _HCACHE[key][0] > time.time() - 3600:
        return _HCACHE[key][1]
    q = urllib.parse.urlencode(dict(latitude=lat, longitude=lon,
                                    hourly="wind_speed_10m,wind_gusts_10m,apparent_temperature,precipitation,"
                                           "precipitation_probability,snow_depth",
                                    wind_speed_unit="ms", forecast_days=8, timezone="Europe/Warsaw"))
    try:
        import qbot_wx as WX   # E4: wspolny transport/cache Open-Meteo
        j = WX.get_url("https://api.open-meteo.com/v1/forecast?" + q, timeout=8, ttl=600)["hourly"]
    except Exception:
        return {}
    out = {}
    for i, t in enumerate(j["time"]):
        out[t[:13]] = {"wind": j["wind_speed_10m"][i], "gust": j["wind_gusts_10m"][i], "feel": j["apparent_temperature"][i],
                       "rain": j["precipitation"][i], "prob": j["precipitation_probability"][i], "snow": j["snow_depth"][i]}
    _HCACHE[key] = (time.time(), out)
    return out


def window_wx(h: dict[str, dict], day: date, start_min: int, dur: int) -> dict | None:
    """Pogoda w oknie jazdy, w ksztalcie oczekiwanym przez E.wx_bad."""
    # 14.10.2026: rain/prob/gust z Open-Meteo dotycza GODZINY POPRZEDZAJACEJ -> dla godziny jazdy H..H+1 bierzemy znacznik H+1
    # (wczesniej H = godzina wczesniej). Wielkosci chwilowe (wind, feel, snow) ze znacznika H. Dok.: docs/POGODA_SILNIK.md
    from datetime import datetime as _dtm, timedelta as _td
    hrs, hrp = [], []
    m = (start_min // 60) * 60
    while m < start_min + dur:
        k = f"{day.isoformat()}T{m // 60:02d}"
        if m // 60 <= 23 and k in h:
            hrs.append(h[k])
        k2 = (_dtm(day.year, day.month, day.day) + _td(hours=m // 60 + 1)).strftime("%Y-%m-%dT%H")
        if k2 in h:
            hrp.append(h[k2])
        m += 60
    if not hrs:
        return None

    def vals(k, src=None):
        return [x[k] for x in (src if src is not None else hrs) if x.get(k) is not None]
    w, g, f, r, p, s = vals("wind"), vals("gust", hrp), vals("feel"), vals("rain", hrp), vals("prob", hrp), vals("snow")
    return {"wind": round(sum(w) / len(w), 1) if w else None, "gust": round(max(g), 1) if g else None,
            "feel_min": round(min(f), 1) if f else None, "feel_max": round(max(f), 1) if f else None,
            "rain_mmh": round(max(r), 1) if r else 0, "rain_prob": max(p) if p else None,
            "snow_cm": round(max(s) * 100, 1) if s else 0}


# ---------------- propozycja (czyste) ----------------

def pl(t: str) -> str:
    """Polski przecinek dziesietny w opisie pogody (2.8 m/s -> 2,8 m/s)."""
    import re
    return re.sub(r"(\d)\.(\d)", r"\1,\2", t)


def _overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and b0 < a1


def order_for(ov: dict) -> list[str]:
    try:
        first = ORDER[int(ov.get("wx.fallback", 0))]
    except (ValueError, IndexError):
        first = "hour"
    return [first] + [o for o in ORDER if o != first]


def candidates(s: dict, h: dict, ov: dict, today_sessions: list[dict], week_days: dict[date, list[dict]],
               now_min: int, daily: dict | None = None) -> list[dict]:
    """Mozliwe korekty jazdy s (dzis), w kolejnosci z Kalibracji. Kazda: kind, opis, nowe pola sesji."""
    day = s["day"]
    st = s["start_time"].hour * 60 + s["start_time"].minute
    dur = int(s["dur_min"])
    long_ = bool(s.get("is_long"))
    busy = [(x["start_time"].hour * 60 + x["start_time"].minute,
             x["start_time"].hour * 60 + x["start_time"].minute + int(x["dur_min"]))
            for x in today_sessions if x.get("id") != s.get("id") and x.get("start_time") and x.get("status") == "plan"]
    out: dict[str, dict] = {}

    # godzina: najblizszy start dzis z dobra pogoda, bez kolizji, nie wczesniej niz za 30 min
    best = None
    t = max(DAY_FROM, ((now_min + 30 + STEP - 1) // STEP) * STEP)
    while t + dur <= DAY_TO:
        if t != st and not any(_overlap(t, t + dur, b0, b1) for b0, b1 in busy):
            wx = window_wx(h, day, t, dur)
            if wx and not E.wx_bad(wx, ov, long_):
                if best is None or abs(t - st) < abs(best - st):
                    best = t
        t += STEP
    if best is not None:
        out["hour"] = {"kind": "hour", "start_time": E.t2(best),
                       "text": f"przesuń na {E.t2(best)}–{E.t2(best + dur)}"}

    # dzien: kolejny dzien tygodnia bez jazdy, z dobra pogoda o tej samej godzinie
    for d in sorted(week_days):
        if d <= day:
            continue
        if any(x["sport"] == "rower" and x["status"] == "plan" for x in week_days[d]):
            continue
        if daily is not None and E.wx_bad((daily or {}).get(d.isoformat()), ov, long_):
            continue
        wx = window_wx(h, d, st, dur)
        if wx and not E.wx_bad(wx, ov, long_):
            out["day"] = {"kind": "day", "day": d.isoformat(),
                          "text": f"przenieś na {DN[d.weekday()]} {d.strftime('%d.%m')} {E.t2(st)}"}
            break

    # skroc: wersja minimum o tej samej godzinie
    short = int(s.get("min_min") or max(30, dur // 2))
    if short < dur:
        wx = window_wx(h, day, st, short)
        if wx and not E.wx_bad(wx, ov, False):
            out["short"] = {"kind": "short", "dur_min": short, "text": f"skróć do {short}′ ({E.t2(st)}–{E.t2(st + short)})"}

    # dom: wioslarz
    hd = min(60, max(30, dur // 2))
    out["home"] = {"kind": "home", "dur_min": hd, "text": f"zamień na wioślarz w domu {hd}′"}

    return [out[k] for k in order_for(ov) if k in out]


def is_indoor(s: dict) -> bool:
    n = (s.get("name") or "").lower() + " " + (s.get("note") or "").lower()
    return any(w in n for w in INDOOR_WORDS)


# ---------------- z baza ----------------

def morning_check(c, user: str, today: date, now_min: int) -> dict:
    """Jazdy na dzis vs prognoza w ich oknie. Zwraca {'lines': [...], 'proposal': {...}|None} i zapisuje propozycje."""
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day=%s AND status='plan' ORDER BY start_time NULLS LAST, id",
              (user, today))
    todays = [dict(r) for r in c.fetchall()]
    rides = [s for s in todays if s["sport"] == "rower" and not is_indoor(s)]
    if not rides:
        return {"lines": [], "proposal": None}
    home = E.home_point(c)
    if not home:
        return {"lines": [], "proposal": None}
    h = hourly(*home)
    if not h:
        return {"lines": ["⚠️ Prognoza pogody niedostępna — jazda bez sprawdzenia."], "proposal": None}
    c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username=%s", (user,))
    r = c.fetchone()
    ov = dict(r["overrides"]) if r and r["overrides"] else {}
    ws = E.monday(today)
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s", (user, today, ws + timedelta(days=6)))
    week: dict[date, list[dict]] = {ws + timedelta(days=k): [] for k in range(7) if ws + timedelta(days=k) >= today}
    for x in c.fetchall():
        week.setdefault(x["day"], []).append(dict(x))
    lines, proposal = [], None
    for s in rides:
        if not s.get("start_time"):
            continue
        st = s["start_time"].hour * 60 + s["start_time"].minute
        wx = window_wx(h, today, st, int(s["dur_min"]))
        bad = E.wx_bad(wx, ov, bool(s.get("is_long")))
        if not bad:
            continue
        span = f"{E.t2(st)}–{E.t2(st + int(s['dur_min']))}"
        if s.get("source") != "auto":
            lines.append(f"⚠️ Pogoda w czasie Twojej jazdy {span}: {pl(bad)}. Rozważ zmianę.")
            continue
        cands = candidates(s, h, ov, todays, week, now_min, E.forecast(*home))
        if not cands or proposal:
            lines.append(f"⚠️ Pogoda w czasie jazdy {span}: {pl(bad)}.")
            continue
        p = cands[0]
        proposal = {"session_id": s["id"], "day": today.isoformat(), "reason": bad, "change": p,
                    "orig": {"start_time": E.t2(st), "dur_min": int(s["dur_min"]), "name": s["name"]}}
        ic = "🌧️" if bad.startswith("deszcz") else "💨" if bad.startswith(("wiatr", "porywy")) else "🥶" if bad.startswith("odczuwalna") else "❄️"
        lines.append(f"{ic} Pogoda w czasie jazdy {span}: {pl(bad)}. Propozycja: {p['text']}.")
        c.execute("INSERT INTO qbot_v2.trainer_auto_cache (key, value, computed_at) VALUES (%s, %s::jsonb, now()) "
                  "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, computed_at=now()",
                  (f"wxprop:{s['id']}", json.dumps(proposal, ensure_ascii=False)))
    return {"lines": lines, "proposal": proposal}


def buttons(proposal: dict | None) -> list:
    if not proposal:
        return []
    sid = proposal["session_id"]
    return [[{"text": "✅ Zmień", "callback_data": f"tr:wxok:{sid}"}, {"text": "✖️ Zostaw", "callback_data": f"tr:wxno:{sid}"}]]


def apply(c, user: str, sid: int) -> dict:
    """'Zmien': wykonaj zapisana propozycje jako zmiane 'pogoda' (Cofnij przez OPS.undo)."""
    import qbot_trener_ops as OPS
    c.execute("SELECT value FROM qbot_v2.trainer_auto_cache WHERE key=%s", (f"wxprop:{sid}",))
    r = c.fetchone()
    if not r:
        return {"ok": False, "error": "propozycja wygasła"}
    p = r["value"]
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE id=%s AND username=%s AND status='plan' AND source='auto'", (sid, user))
    s = c.fetchone()
    if not s or s["day"].isoformat() != p["day"]:
        return {"ok": False, "error": "jazda już zmieniona albo zrobiona"}
    s = dict(s)
    before = OPS._j(s)
    new = {k: s.get(k) for k in OPS.COLS}
    ch = p["change"]
    if ch["kind"] == "hour":
        new["start_time"] = ch["start_time"]
    elif ch["kind"] == "day":
        new["day"] = date.fromisoformat(ch["day"])
    elif ch["kind"] == "short":
        new["dur_min"] = ch["dur_min"]; new["cut"] = True
        new["xss"] = E.xss_of("rower", s.get("zone"), ch["dur_min"]); new["is_long"] = False
    elif ch["kind"] == "home":
        new.update(sport="wiosl", name="Wioślarz spokojnie", dur_min=ch["dur_min"], min_min=min(ch["dur_min"], 15), zone=None,
                   xss=E.xss_of("wiosl", None, ch["dur_min"]), is_long=False, cut=False)
    new["note"] = ((s.get("note") or "") + f" [pogoda: {p['reason']}]").strip()
    new["source"] = "auto"
    c.execute("DELETE FROM qbot_v2.trainer_session WHERE id=%s", (sid,))
    cols = ["username"] + OPS.COLS
    c.execute(f"INSERT INTO qbot_v2.trainer_session ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id",
              [user] + [new.get(k) for k in OPS.COLS])
    nid = c.fetchone()["id"]
    c.execute("INSERT INTO qbot_v2.trainer_change (username, week_start, action, payload, before, after, accepted) "
              "VALUES (%s,%s,'pogoda',%s::jsonb,%s::jsonb,%s::jsonb,true) RETURNING id",
              (user, E.monday(s["day"]), json.dumps({"after_ids": [nid], "reason": p["reason"], "proposal": ch}, ensure_ascii=False, default=str),
               json.dumps([before], ensure_ascii=False, default=str), json.dumps([new], ensure_ascii=False, default=str)))
    cid = c.fetchone()["id"]
    c.execute("DELETE FROM qbot_v2.trainer_auto_cache WHERE key=%s", (f"wxprop:{sid}",))
    return {"ok": True, "change_id": cid, "text": ch["text"]}


def dismiss(c, sid: int) -> None:
    c.execute("DELETE FROM qbot_v2.trainer_auto_cache WHERE key=%s", (f"wxprop:{sid}",))
