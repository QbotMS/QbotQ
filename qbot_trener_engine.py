"""TRENER - silnik planu tygodnia (Etap 3).

Czysta funkcja plan_week(ctx) -> sesje auto + notatki (testy: tests/test_trener_engine.py, bez bazy).
build_context(conn, user, week_start) zbiera dane z bazy (cele, wpisy, nadpisania, Kalendarz, gotowosc,
sesje zachowane) + prognoze Open-Meteo dla "domu" (najczestszy start jazd).
Zasady (docs/TRENER.md): okres z Sezonu (port logiki z trener.js), Mix miesiaca, okna i zajetosci,
Kalendarz (rest/choroba/delegacja/urlop/wyprawy z celow), pogoda (progi wx.*), gotowosc (prog auto),
przerwa po ciezkiej jezdzie, sila nie dzien po dniu, min. dni wolnych, joga wg regul.
Sesje edytowane recznie (source=manual) oraz zrobione/pominiete NIE sa ruszane przy przeliczeniu.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

# ---------------- domyslne parametry (lustrzane do tablicy G w trener.js) ----------------
DEF: dict[str, Any] = {
    "load.budget_h": 8, "load.progress": 3, "load.max_inc_pct": 7, "load.min_rest_days": 1, "load.missed": 1,
    "int.easy_pct": 80, "int.hard_per_week": 1, "int.hard_gap_days": 2,
    "regen.sensitivity": 5, "regen.min_pct": 15, "regen.heavy_gap_h": 48, "regen.after_illness": 0,
    "wx.wind_ms": 8, "wx.gust_ms": 13, "wx.forest_bonus_ms": 1, "wx.cold_long_c": 0, "wx.cold_short_c": -10,
    "wx.heat_c": 30, "wx.rain_mmh": 0.5, "wx.rain_prob": 40, "wx.wet24_mm": 10, "wx.snow_cm": 10,
    "yoga.hard_xss": 120, "yoga.long_h": 3,
    "season.taper_w": 2, "season.regen_w": 2, "season.light_every_w": 4, "season.volume": 5,
}
MIXD = {"rower": [3, 3, 4, 4, 5, 5, 5, 5, 4, 4, 3, 3], "sila": [3, 3, 2, 1, 1, 1, 1, 1, 1, 1, 2, 2],
        "wiosl": [2, 2, 1, 0, 0, 0, 0, 0, 0, 0, 1, 2], "joga": [2, 2, 2, 2, 3, 3, 3, 3, 2, 2, 2, 2]}
YOGA = {"before_trip": 15, "after_hard": 15, "rest_after_long": 40, "rest": 30, "low_form": 20, "trip_work": 15}
PH_H = {"rt": 5.0, "bz": 6.5, "bd": 8.0, "tp": 4.5, "rg": 4.5}
PH_NAME = {"rt": "Roztrenowanie", "bz": "Baza + siła", "bd": "Budowa", "tp": "Taper", "ev": "Wyprawa", "rg": "Regeneracja"}
XSS_PER_MIN = {("rower", 1): 0.55, ("rower", 2): 0.75, ("rower", 3): 1.0, ("sila", None): 0.3, ("wiosl", None): 0.6, ("joga", None): 0.0}
SPORT_OF = {"cycling": "rower", "gravel_cycling": "rower", "road_biking": "rower", "mountain_biking": "rower",
            "indoor_cycling": "rower", "virtual_ride": "rower", "strength_training": "sila", "indoor_rowing": "wiosl",
            "rowing": "wiosl", "yoga": "joga", "pilates": "joga"}
DEFAULT_WIN = (7 * 60, 20 * 60)          # weekend / urlop
DEFAULT_WIN_WD = (9 * 60, 20 * 60)       # dni robocze bez zdefiniowanego okna


def P(ov: dict, k: str):
    return ov[k] if k in ov else DEF[k]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def hm(t: str | None) -> int | None:
    if not t:
        return None
    p = str(t).split(":")
    return int(p[0]) * 60 + int(p[1])


def t2(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _d(v) -> date | None:
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


# ---------------- Sezon (port rSeason z trener.js) ----------------

def season_weeks(goals: list, ov: dict, s0: date, n: int = 70) -> list[dict]:
    ev = []
    for g in goals:
        if g.get("kind") in ("trip", "long_ride") and g.get("date_from") and g.get("status") not in ("dropped", "done"):
            a = _d(g["date_from"]); b = _d(g.get("date_to")) or a
            ev.append({"g": g, "a": a, "b": max(a, b), "pr": g.get("priority", "B")})
    ev.sort(key=lambda x: x["a"])
    W = [{"s": s0 + timedelta(weeks=i), "ph": None, "h": 0.0, "ev": [], "lt": False, "bev": False, "pre": False} for i in range(n)]
    if not ev:
        for w in W:
            w["ph"], w["h"] = "bz", PH_H["bz"]
        return W
    A = [x for x in ev if x["pr"] == "A"]

    def wk0(t: date) -> date:
        return s0 + timedelta(weeks=(t - s0).days // 7)
    first_a = wk0(A[0]["a"]) if A else wk0(ev[0]["a"])
    rt_e = _d(ov.get("season.rt_end")) or min(s0 + timedelta(days=55), first_a - timedelta(weeks=12))
    bz_e = _d(ov.get("season.bz_end")) or (first_a - timedelta(weeks=10) - timedelta(days=1))
    taper, regen = int(P(ov, "season.taper_w")), int(P(ov, "season.regen_w"))
    for w in W:
        m = w["s"] + timedelta(days=3)
        w["ph"] = "rt" if m <= rt_e else ("bz" if m <= bz_e else "bd")
    for x in A:
        ws, we = wk0(x["a"]), wk0(x["b"])
        for w in W:
            if ws - timedelta(weeks=taper) <= w["s"] < ws:
                w["ph"] = "tp"
            if ws <= w["s"] <= we:
                w["ph"] = "ev"
            if we < w["s"] <= we + timedelta(weeks=regen):
                w["ph"] = "rg"
    if A:
        lw = wk0(A[-1]["b"])
        for w in W:
            if w["s"] > lw + timedelta(weeks=regen):
                w["ph"] = "rt"
    for x in ev:
        for w in W:
            if x["a"] < w["s"] + timedelta(days=7) and x["b"] >= w["s"]:
                w["ev"].append(x)

    def od(w):
        n_ = 0
        for e in w["ev"]:
            a1, b1 = max(e["a"], w["s"]), min(e["b"], w["s"] + timedelta(days=6))
            if b1 >= a1:
                n_ += (b1 - a1).days + 1
        return n_
    run = 0
    for i, w in enumerate(W):
        if w["ph"] == "ev":
            w["h"] = max(3.0, od(w) * 5.0); run = 0
            continue
        base = PH_H.get(w["ph"], 5.0)
        if w["ph"] == "bd":
            run += 1; base += min(1.5, run * 0.08)
        if w["ev"] and w["ev"][0]["pr"] != "A":
            w["h"] = max(base, od(w) * 5.0); w["bev"] = True
            continue
        nx = W[i + 1] if i + 1 < len(W) else None
        if nx and nx["ev"] and nx["ev"][0]["pr"] != "A" and w["ph"] != "tp":
            base *= 0.8; w["pre"] = True
        w["h"] = base
    k = 0
    cyc, vol = int(P(ov, "season.light_every_w")), float(P(ov, "season.volume"))
    for w in W:
        if w["ph"] in ("rt", "bz", "bd"):
            k += 1
            if k % cyc == 0 and not w["bev"]:
                w["h"] *= 0.7; w["lt"] = True
        else:
            k = 0
        if w["ph"] != "ev" and not w["bev"]:
            w["h"] *= (1 + (vol - 5) * 0.06)
    return W


# ---------------- reguly i dni ----------------

def rule_applies(r: dict, d: date) -> bool:
    if r.get("active") is False:
        return False
    p = r.get("period") or {"m": "all"}
    if p.get("m") == "all":
        return True
    if p.get("m") == "once":
        return _d(p["f"]) <= d <= _d(p["t"])
    def mmdd(s):
        dd, mm = s.split(".")
        return int(mm) * 100 + int(dd)
    k, f, t = d.month * 100 + d.day, mmdd(p["f"]), mmdd(p["t"])
    return (f <= k <= t) if f <= t else (k >= f or k <= t)


def day_info(ctx: dict, d: date) -> dict:
    """Typ dnia + zajetosci + okna per sport."""
    dow = d.weekday()
    info = {"date": d, "type": "normal", "busy": [], "win": {}, "labels": []}
    for c in ctx.get("calendar", []):
        a, b = _d(c["day"]), _d(c.get("end_day")) or _d(c["day"])
        if not (a <= d <= b):
            continue
        et, kind = c.get("event_type"), c.get("kind")
        if kind == "illness":
            info["type"] = "ill"; info["labels"].append("🤒 choroba")
        elif et == "rest":
            info["type"] = "rest" if info["type"] == "normal" else info["type"]; info["labels"].append("😴 REST DAY")
        elif et == "delegacja":
            info["type"] = "del" if info["type"] in ("normal", "urlop") else info["type"]; info["labels"].append("🧳 delegacja")
        elif et == "urlop":
            info["type"] = "urlop" if info["type"] == "normal" else info["type"]; info["labels"].append("🏖️ " + (c.get("title") or "urlop"))
        elif kind == "event" and c.get("at_time"):
            s = hm(str(c["at_time"])[:5]); info["busy"].append((s, min(s + 150, 23 * 60), "📅 " + (c.get("title") or "wydarzenie")))
    for g in ctx.get("goals", []):
        if g.get("kind") in ("trip", "long_ride") and g.get("date_from") and g.get("status") not in ("dropped", "done"):
            a = _d(g["date_from"]); b = _d(g.get("date_to")) or a
            if a <= d <= b:
                info["type"] = "trip"; info["labels"].append("🗺️ " + g["name"])
    if ctx.get("day_state", {}).get(d) == "short" and info["type"] == "normal":
        info["type"] = "short"; info["labels"].append("⏱ brak czasu")
    pref = {s: [] for s in ("rower", "sila", "wiosl", "joga")}
    flex_cap = None
    for r in ctx.get("rules", []):
        if not rule_applies(r, d):
            continue
        for w in r.get("windows", []):
            if not w["d"][dow]:
                continue
            if r["kind"] == "busy":
                if w["k"] == "h":
                    info["busy"].append((hm(w["a"]), hm(w["b"]), r.get("icon", "") + " " + r["name"]))
                elif w["k"] == "all" and w["d"][dow] == 1:
                    info["busy"].append((0, 24 * 60, r.get("icon", "") + " " + r["name"]))
                # 'var': godziny z Kalendarza (wydarzenia z at_time powyzej)
            elif r["kind"] == "pref":
                a, b = (hm(w["a"]), hm(w["b"])) if w["k"] == "h" else DEFAULT_WIN
                for s in (w.get("ac") or list(pref)):
                    pref[s].append((a, b))
            elif r["kind"] == "flex" and r.get("max_min"):
                flex_cap = max(flex_cap or 0, int(r["max_min"]))
    for s in pref:
        info["win"][s] = pref[s] or [DEFAULT_WIN if dow >= 5 else DEFAULT_WIN_WD]
    if info["type"] == "urlop":
        info["win"] = {s: [DEFAULT_WIN] for s in pref}
    info["flex_cap"] = flex_cap if dow < 5 and info["type"] == "normal" else None
    info["wx"] = (ctx.get("weather") or {}).get(d.isoformat())
    return info


def find_slot(info: dict, sport: str, dur: int, placed: list, min_dur: int | None = None) -> tuple[str, int] | None:
    busy = list(info["busy"]) + [(hm(p["start_time"]), hm(p["start_time"]) + p["dur_min"], "") for p in placed if p.get("start_time") and p["day"] == info["date"].isoformat()]
    best = None
    for a, b in info["win"].get(sport, [DEFAULT_WIN]):
        s = a
        while s + (min_dur or dur) <= b:
            e_full = min(s + dur, b)
            ok_len = e_full - s
            clash = [x for x in busy if s < x[1] and s + ok_len > x[0]]
            if clash:
                cut = min(x[0] for x in clash) - s
                if cut >= (min_dur or dur) and (best is None or cut > best[1]):
                    best = (t2(s), cut)
                s = max(x[1] for x in clash)
                s = ((s + 14) // 15) * 15
                continue
            if ok_len >= dur:
                return (t2(s), dur)
            if ok_len >= (min_dur or dur) and (best is None or ok_len > best[1]):
                best = (t2(s), ok_len)
            s += 15
    return best


def wx_bad(wx: dict | None, ov: dict, long: bool, forest: bool = True) -> str | None:
    if not wx:
        return None
    lim = float(P(ov, "wx.wind_ms")) + (float(P(ov, "wx.forest_bonus_ms")) if forest else 0) + (0 if long else 2)
    if wx.get("rain_mmh") is not None and wx["rain_mmh"] > float(P(ov, "wx.rain_mmh")) and (wx.get("rain_prob") or 100) >= float(P(ov, "wx.rain_prob")):
        return f"deszcz {wx['rain_mmh']} mm/h"
    if wx.get("wind") is not None and wx["wind"] > lim:
        return f"wiatr {wx['wind']} m/s"
    if wx.get("gust") is not None and wx["gust"] > float(P(ov, "wx.gust_ms")) + (0 if long else 3):
        return f"porywy {wx['gust']} m/s"
    cold = float(P(ov, "wx.cold_long_c" if long else "wx.cold_short_c"))
    if wx.get("feel_min") is not None and wx["feel_min"] < cold:
        return f"odczuwalna {wx['feel_min']} °C"
    if wx.get("snow_cm") is not None and wx["snow_cm"] > float(P(ov, "wx.snow_cm")):
        return f"śnieg {wx['snow_cm']} cm"
    return None


def xss_of(sport: str, zone: int | None, dur: int) -> float:
    k = (sport, zone) if sport == "rower" else (sport, None)
    return round(XSS_PER_MIN.get(k, 0.5) * dur, 0)


# ---------------- planowanie ----------------

def plan_week(ctx: dict) -> dict:
    ov, ws, today = ctx.get("ov", {}), ctx["week_start"], ctx["today"]
    notes: list[str] = []
    W = season_weeks(ctx.get("goals", []), ov, monday(today))
    wk = next((w for w in W if w["s"] == ws), None) or {"ph": "bz", "h": PH_H["bz"], "lt": False, "ev": [], "pre": False}
    ph = wk["ph"]
    target_min = int(min(float(wk["h"]), float(P(ov, "load.budget_h"))) * 60)
    month = (ws + timedelta(days=3)).month
    cnt = {s: int(ov.get(f"mix.{s}.{month}", MIXD[s][month - 1])) for s in MIXD}
    if ph == "rg":
        cnt["rower"] = min(cnt["rower"], 2); cnt["sila"] = 0; cnt["wiosl"] = 0; cnt["joga"] += 1
    if ph == "tp":
        cnt["sila"] = min(cnt["sila"], 1)
    hard_n = int(P(ov, "int.hard_per_week")) if ph == "bd" else 0
    days = [ws + timedelta(days=i) for i in range(7)]
    infos = {d: day_info(ctx, d) for d in days}
    plan_days = [d for d in days if d >= today]
    keep = [s for s in ctx.get("keep", []) if s.get("status") != "skip"]
    for s in keep:
        if s["sport"] in cnt:
            cnt[s["sport"]] = max(0, cnt[s["sport"]] - 1)
        target_min -= int(s["dur_min"])
    # czesc budzetu juz "zjedzona" przez przeszle dni tygodnia (zrobione aktywnosci poza planem)
    for a in ctx.get("activities_extra", []):
        target_min -= int(a.get("dur_min", 0))
        sp = a.get("sport")
        if sp in cnt:
            cnt[sp] = max(0, cnt[sp] - 1)
    target_min = max(0, target_min)
    placed: list[dict] = [dict(s, day=_d(s["day"]).isoformat()) for s in keep]
    out: list[dict] = []

    def open_day(d: date) -> bool:
        return infos[d]["type"] in ("normal", "urlop", "short")

    def has(d: date, sport: str) -> bool:
        return any(p["day"] == d.isoformat() and p["sport"] == sport for p in placed)

    def add(d: date, sport: str, name: str, dur: int, mn: int, zone=None, is_long=False, why="") -> dict | None:
        info = infos[d]
        cap = info.get("flex_cap")
        if cap and sport != "joga":
            dur = min(dur, cap)
        slot = find_slot(info, sport, dur, placed, mn)
        if not slot:
            return None
        st, real = slot
        s = {"day": d.isoformat(), "sport": sport, "name": name, "start_time": st, "dur_min": int(real),
             "min_min": int(min(mn, real)), "zone": zone, "is_long": is_long, "xss": xss_of(sport, zone, real),
             "status": "plan", "cut": False, "source": "auto", "note": why or None}
        placed.append(s); out.append(s)
        return s

    # dni wyprawy / delegacji: tylko krotka joga (reguly jogi)
    for d in plan_days:
        t = infos[d]["type"]
        if t == "trip" and int(ov.get("yoga.before_trip.on", 1)):
            add(d, "joga", "Joga przed jazdą", int(ov.get("yoga.before_trip.min", YOGA["before_trip"])), 10, why="dzień wyprawy")
        if t == "del" and int(ov.get("yoga.trip_work.on", 1)):
            infos[d]["win"]["joga"] = [(6 * 60 + 30, 9 * 60)]
            add(d, "joga", "Joga hotelowa", int(ov.get("yoga.trip_work.min", YOGA["trip_work"])), 10, why="delegacja — tylko krótka")
    for d in plan_days:
        if infos[d]["type"] == "ill":
            for k in (1, 2):
                nd = d + timedelta(days=k)
                if nd in infos and infos[nd]["type"] == "normal":
                    infos[nd]["type"] = "short"; infos[nd]["labels"].append("po chorobie — lżej")

    fixed = cnt["sila"] * 40 + cnt["wiosl"] * 30 + cnt["joga"] * 20
    rower_total = max(0, target_min - fixed)
    long_h = float(P(ov, "yoga.long_h"))
    hard_xss = float(P(ov, "yoga.hard_xss"))
    long_day = None
    # 1) dluga jazda
    if cnt["rower"] >= 1 and ph not in ("ev", "rg") and rower_total >= 60:
        cands = [d for d in plan_days if open_day(d) and (d.weekday() >= 5 or infos[d]["type"] == "urlop") and not has(d, "rower")]
        scored = []
        for d in cands:
            bad = wx_bad(infos[d]["wx"], ov, True)
            free = find_slot(infos[d], "rower", 600, placed, 60)
            scored.append((1 if bad else 0, -(free[1] if free else 0), d, bad))
        scored.sort(key=lambda x: (x[0], x[1], x[2]))
        if scored and scored[0][1] < 0:
            _, _, d, bad = scored[0]
            dur = int(max(60, min(rower_total * (0.45 if cnt["rower"] > 1 else 1.0), long_h * 60 * 1.3)))
            s = add(d, "rower", "Długa jazda", dur, 60, zone=2, is_long=True, why="najdłuższa jazda tygodnia")
            if s:
                long_day = d; rower_total -= s["dur_min"]; cnt["rower"] -= 1
                if bad:
                    notes.append(f"{d.isoformat()}: długa jazda mimo pogody ({bad}) — brak lepszego dnia w weekend")
    # 2) pozostale jazdy
    n_r = cnt["rower"]
    if n_r > 0 and rower_total >= 30:
        each = int(max(30, min(120, rower_total / n_r)))
        heavy_gap_days = max(1, int(float(P(ov, "regen.heavy_gap_h")) // 24))
        for _ in range(n_r):
            cands = []
            for d in plan_days:
                if not open_day(d) or has(d, "rower"):
                    continue
                if long_day and 0 < (d - long_day).days < heavy_gap_days and (placed and any(p.get("is_long") and (p.get("xss") or 0) >= hard_xss for p in placed)):
                    continue
                bad = wx_bad(infos[d]["wx"], ov, False)
                rdays = [_d(p["day"]) for p in placed if p["sport"] == "rower"]
                dist = min([abs((d - x).days) for x in rdays], default=7)
                cands.append((1 if bad else 0, -dist, d, bad))
            if not cands:
                break
            cands.sort(key=lambda x: (x[0], x[1], x[2]))
            _, _, d, bad = cands[0]
            if bad:
                if int(ov.get(f"mix.wiosl.{month}", MIXD["wiosl"][month - 1])) > 0 or cnt["wiosl"] > 0:
                    cnt["wiosl"] += 1
                    notes.append(f"{d.isoformat()}: {bad} — zamiast jazdy wioślarz w domu")
                else:
                    notes.append(f"{d.isoformat()}: {bad} — jazda pominięta (brak lepszego dnia)")
                break
            name, zone = ("Rower luźno", 1) if ph in ("rg", "tp") else ("Rower spokojnie", 2)
            s = add(d, "rower", name, each, 30, zone=zone)
            if not s:
                continue
    # 3) mocny akcent
    if hard_n:
        gap = int(P(ov, "int.hard_gap_days"))
        for s in sorted([x for x in out if x["sport"] == "rower" and not x["is_long"]], key=lambda x: -x["dur_min"]):
            if hard_n <= 0:
                break
            d = _d(s["day"])
            if long_day and abs((d - long_day).days) < gap:
                continue
            s.update(name="Podjazdy / tempo", zone=3, xss=xss_of("rower", 3, s["dur_min"]), note="mocny akcent tygodnia (Budowa)")
            hard_n -= 1
    # 4) sila
    sila_i = 0
    for _ in range(cnt["sila"]):
        cands = []
        for d in plan_days:
            if not open_day(d) or has(d, "sila"):
                continue
            if any(has(d + timedelta(days=k), "sila") for k in (-1, 1)):
                continue
            if long_day and (long_day - d).days == 1:
                continue
            cands.append((1 if has(d, "rower") else 0, d))
        if not cands:
            break
        cands.sort()
        d = cands[0][1]
        if add(d, "sila", "Siła " + "AB"[sila_i % 2], 40, 15):
            sila_i += 1
    # 5) wioslarz (chetnie w dni z zla pogoda)
    for _ in range(cnt["wiosl"]):
        cands = []
        for d in plan_days:
            if not open_day(d) or has(d, "wiosl"):
                continue
            bad = wx_bad(infos[d]["wx"], ov, False)
            cands.append((0 if bad else 1, 1 if has(d, "rower") else 0, d))
        if not cands:
            break
        cands.sort()
        add(cands[0][2], "wiosl", "Wioślarz spokojnie", 30, 15)
    # 6) joga wg regul
    jn = cnt["joga"]
    if long_day and jn > 0:
        nd = long_day + timedelta(days=1)
        if nd in infos and nd >= today and open_day(nd) and not has(nd, "joga"):
            train = any(p["day"] == nd.isoformat() and p["sport"] != "joga" for p in placed)
            key = "after_hard" if train else "rest_after_long"
            if int(ov.get(f"yoga.{key}.on", 1)):
                if add(nd, "joga", "Joga po długiej jeździe", int(ov.get(f"yoga.{key}.min", YOGA[key])), 10, why="dzień po długiej jeździe"):
                    jn -= 1
    for d in plan_days:
        if jn <= 0:
            break
        if open_day(d) and not any(p["day"] == d.isoformat() for p in placed) and int(ov.get("yoga.rest.on", 1)):
            if add(d, "joga", "Joga mobilność", int(ov.get("yoga.rest.min", YOGA["rest"])), 10, why="dzień bez treningu"):
                jn -= 1
    # 7) min. dni wolnych od treningu (joga nie liczy sie jako trening)
    min_rest = int(P(ov, "load.min_rest_days"))
    def trains(d):
        return any(p["day"] == d.isoformat() and p["sport"] != "joga" for p in placed)
    free_days = [d for d in days if not trains(d)]
    while len(free_days) < min_rest:
        cand = sorted([d for d in plan_days if trains(d) and d != long_day],
                      key=lambda d: sum(p["dur_min"] for p in placed if p["day"] == d.isoformat() and p["sport"] != "joga"))
        if not cand:
            break
        d = cand[0]
        for s in [x for x in out if x["day"] == d.isoformat() and x["sport"] != "joga"]:
            out.remove(s); placed.remove(s)
        notes.append(f"{d.isoformat()}: dzień wolny (min. {min_rest} w tygodniu)")
        free_days = [d for d in days if not trains(d)]
    # 8) brak czasu / gotowosc dzis
    thr, rt = ctx.get("readiness_threshold"), ctx.get("readiness_today")
    low_today = thr is not None and rt is not None and rt < thr and int(P(ov, "regen.sensitivity")) > 0
    for s in out:
        d = _d(s["day"])
        if infos[d]["type"] == "short" or (low_today and d == today and s["sport"] != "joga"):
            if s["min_min"] and s["min_min"] < s["dur_min"]:
                s["dur_min"] = s["min_min"]; s["cut"] = True; s["xss"] = xss_of(s["sport"], s["zone"], s["dur_min"])
    if low_today and today in infos:
        notes.append(f"gotowość dziś {round(rt, 2)} < próg {round(thr, 2)} — dziś wersje minimum")
    total = sum(s["dur_min"] for s in out) + sum(int(s["dur_min"]) for s in keep)
    return {"sessions": out, "notes": notes, "phase": ph, "phase_name": PH_NAME.get(ph, ph), "light": bool(wk.get("lt")),
            "target_h": round(min(float(wk["h"]), float(P(ov, "load.budget_h"))), 1), "planned_h": round(total / 60, 1),
            "days": {d.isoformat(): {"type": infos[d]["type"], "labels": infos[d]["labels"],
                                     "busy": [{"a": t2(a), "b": t2(b), "label": l} for a, b, l in infos[d]["busy"] if a is not None],
                                     "wx": infos[d]["wx"]} for d in days}}


def check_rules(sessions: list, ov: dict) -> list[str]:
    """Ostrzezenia dla recznie ulozonego tygodnia (sila dzien po dniu, dwie dlugie pod rzad)."""
    out = []
    by = {}
    for s in sessions:
        if s.get("status") == "skip":
            continue
        by.setdefault(str(s["day"])[:10], []).append(s)
    ds = sorted(by)
    for a, b in zip(ds, ds[1:]):
        if (_d(b) - _d(a)).days != 1:
            continue
        if any(x["sport"] == "sila" for x in by[a]) and any(x["sport"] == "sila" for x in by[b]):
            out.append(f"siła dzień po dniu ({a[5:]} i {b[5:]}) — zalecane 48 h przerwy")
        if any(x.get("is_long") for x in by[a]) and any(x.get("is_long") for x in by[b]):
            out.append(f"dwie długie jazdy pod rząd ({a[5:]}, {b[5:]})")
    return out


# ---------------- pogoda + "dom" ----------------
_WX_CACHE: dict = {}
_HOME: dict = {}


def home_point(c) -> tuple[float, float] | None:
    if _HOME.get("t", 0) > time.time() - 86400:
        return _HOME.get("p")
    c.execute("""WITH s AS (SELECT external_id FROM qbot_v2.training_sessions WHERE sport_type IN ('cycling','gravel_cycling')
                 ORDER BY date DESC LIMIT 60)
                 SELECT DISTINCT ON (r.external_id) r.lat, r.lon FROM qbot_v2.activity_record r JOIN s USING (external_id)
                 WHERE r.lat IS NOT NULL ORDER BY r.external_id, r.sec""")
    pts = {}
    for row in c.fetchall():
        k = (round(float(row["lat"]), 1), round(float(row["lon"]), 1))
        pts[k] = pts.get(k, 0) + 1
    p = max(pts, key=pts.get) if pts else None
    _HOME.update(t=time.time(), p=p)
    return p


def forecast(lat: float, lon: float) -> dict:
    key = (lat, lon)
    if key in _WX_CACHE and _WX_CACHE[key][0] > time.time() - 3600:
        return _WX_CACHE[key][1]
    q = urllib.parse.urlencode(dict(latitude=lat, longitude=lon, hourly="wind_speed_10m,wind_gusts_10m,apparent_temperature,precipitation,precipitation_probability,snow_depth,weather_code",
                                    wind_speed_unit="ms", forecast_days=10, past_days=1, timezone="Europe/Warsaw"))
    out = {}
    try:
        with urllib.request.urlopen("https://api.open-meteo.com/v1/forecast?" + q, timeout=8) as f:
            j = json.load(f)["hourly"]
    except Exception:
        return {}
    T = j["time"]
    for i, t in enumerate(T):
        d, h = t[:10], int(t[11:13])
        if not 8 <= h <= 18:
            continue
        o = out.setdefault(d, {"_w": [], "_g": [], "_f": [], "_r": [], "_p": [], "_s": [], "_c": []})
        for kk, src in (("_w", "wind_speed_10m"), ("_g", "wind_gusts_10m"), ("_f", "apparent_temperature"), ("_r", "precipitation"),
                        ("_p", "precipitation_probability"), ("_s", "snow_depth"), ("_c", "weather_code")):
            v = j[src][i]
            if v is not None:
                o[kk].append(v)
    res = {}
    for d, o in out.items():
        if not o["_w"]:
            continue
        idx = T.index(d + "T10:00") if (d + "T10:00") in T else None
        wet = round(sum(x or 0 for x in j["precipitation"][max(0, idx - 24):idx]), 1) if idx else None
        rmax = max(o["_r"]) if o["_r"] else 0
        storm = any(c_ >= 95 for c_ in o["_c"])
        wind = round(sum(o["_w"]) / len(o["_w"]), 1)
        icon = "⛈️" if storm else ("🌧️" if rmax > 0.5 else ("❄️" if (max(o["_s"]) if o["_s"] else 0) > 0.01 else ("💨" if wind > 7 else "⛅")))
        res[d] = {"wind": wind, "gust": round(max(o["_g"]), 1) if o["_g"] else None,
                  "feel_min": round(min(o["_f"]), 1) if o["_f"] else None, "feel_max": round(max(o["_f"]), 1) if o["_f"] else None,
                  "rain_mmh": round(rmax, 1), "rain_prob": max(o["_p"]) if o["_p"] else None,
                  "snow_cm": round(max(o["_s"]) * 100, 1) if o["_s"] else 0, "wet24": wet, "storm": storm, "icon": icon}
    _WX_CACHE[key] = (time.time(), res)
    return res


# ---------------- kontekst z bazy ----------------

def build_context(c, user: str, week_start: date, today: date | None = None, keep_ids_exclude: bool = True) -> dict:
    today = today or date.today()
    ws = monday(week_start)
    we = ws + timedelta(days=6)
    c.execute("SELECT * FROM qbot_v2.trainer_goal WHERE username=%s", (user,))
    goals = [dict(r) for r in c.fetchall()]
    c.execute("SELECT * FROM qbot_v2.trainer_rule WHERE username=%s AND active", (user,))
    rules = [dict(r) for r in c.fetchall()]
    c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username=%s", (user,))
    row = c.fetchone()
    ov_user = dict(row["overrides"]) if row else {}
    # wartosci auto (pogoda z historii jazd, cache Etapu 4) jako baza; reczne nadpisania wygrywaja
    ov = {}
    try:
        c.execute("SELECT value FROM qbot_v2.trainer_auto_cache WHERE key='weather'")
        wr = c.fetchone()
        if wr:
            ov.update({k: v["value"] for k, v in dict(wr["value"]).items() if k.startswith("wx.") and isinstance(v, dict) and "value" in v})
    except Exception:
        pass
    ov.update(ov_user)
    c.execute("SELECT id, day, end_day, kind, event_type, title, at_time, note FROM qbot_v2.calendar_entry WHERE day <= %s AND COALESCE(end_day, day) >= %s", (we, ws))
    cal = [dict(r) for r in c.fetchall()]
    c.execute("SELECT day, state FROM qbot_v2.trainer_day WHERE username=%s AND day BETWEEN %s AND %s", (user, ws, we))
    dstate = {r["day"]: r["state"] for r in c.fetchall()}
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s", (user, ws, we))
    sess = [dict(r) for r in c.fetchall()]
    keep = [s for s in sess if s["source"] == "manual" or s["status"] != "plan" or s["day"] < today]
    for s in keep:
        s["start_time"] = s["start_time"].strftime("%H:%M") if s.get("start_time") else None
    c.execute("SELECT id, date, sport_type, duration_s FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (ws, we))
    linked = {s["training_session_id"] for s in sess if s.get("training_session_id")}
    extra = [{"sport": SPORT_OF.get(r["sport_type"]), "dur_min": int((r["duration_s"] or 0) / 60)} for r in c.fetchall() if r["id"] not in linked and r["date"] < today]
    c.execute("SELECT readiness_effective FROM qbot_v2.fitmodel_daily WHERE day=%s", (today,))
    r = c.fetchone()
    rt = float(r["readiness_effective"]) if r and r["readiness_effective"] is not None else None
    thr = None
    try:
        c.execute("SELECT readiness_effective AS v FROM qbot_v2.fitmodel_daily WHERE readiness_effective IS NOT NULL AND day > %s", (today - timedelta(days=365),))
        vals = sorted(float(x["v"]) for x in c.fetchall())
        pct = int(ov.get("regen.min_pct", DEF["regen.min_pct"]))
        if len(vals) >= 30 and pct > 0:
            thr = vals[min(len(vals) - 1, int(len(vals) * pct / 100))]
    except Exception:
        thr = None
    wx = {}
    try:
        hp = home_point(c)
        if hp and we >= today:
            wx = forecast(*hp)
    except Exception:
        wx = {}
    return {"week_start": ws, "today": today, "ov": ov, "goals": goals, "rules": rules, "calendar": cal, "day_state": dstate,
            "keep": keep, "activities_extra": extra, "readiness_today": rt, "readiness_threshold": thr, "weather": wx,
            "all_sessions": sess}
