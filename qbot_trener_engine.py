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
    "yoga.hard_xss": 120, "yoga.long_h": 3, "regen.trip_rec_d": 3, "regen.pre_trip_d": 3,
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


# ---------------- Sezon (rok treningowy) ----------------
# Sezon Y: start = pierwszy dzien roboczy po swietach (od 27.12.Y-1, bez weekendow / 1.01 / 6.01) = start budowy BAZY;
# baza -> budowa + szczyty pod wyprawy A (taper / wyprawa / regeneracja) -> jazda sezonowa -> ROZTRENOWANIE (od 1.10
# albo po regeneracji ostatniej A) -> TOTALNY LUZ (od ok. 12.12) do dnia przed startem sezonu Y+1.
# Nadpisania per sezon: season.<Y>.start / .bz_end / .roz / .luz (RRRR-MM-DD). Globalne: season.taper_w / regen_w /
# light_every_w / volume.
PH_H.update({"sz": 7.0, "lz": 0.0})
PH_NAME.update({"sz": "Sezon — jazda", "lz": "Totalny luz"})


def first_workday_after_xmas(prev_year: int) -> date:
    d = date(prev_year, 12, 27)
    while d.weekday() >= 5 or (d.month == 1 and d.day in (1, 6)):
        d += timedelta(days=1)
    return d


def season_bounds(y: int, ov: dict, goals: list | None = None) -> dict:
    """Granice sezonu Y (z auto albo nadpisan). 'auto' mowi, ktore wartosci sa wyliczone."""
    start = _d(ov.get(f"season.{y}.start")) or first_workday_after_xmas(y - 1)
    nxt = _d(ov.get(f"season.{y + 1}.start")) or first_workday_after_xmas(y)
    luz = _d(ov.get(f"season.{y}.luz")) or date(y, 12, 12)
    A = sorted([_g for _g in (goals or []) if _g.get("kind") in ("trip", "long_ride") and _g.get("priority") == "A"
                and _g.get("date_from") and _g.get("status") not in ("dropped", "done") and start <= _d(_g["date_from"]) < nxt],
               key=lambda g: _d(g["date_from"]))
    regen = int(P(ov, "season.regen_w"))
    auto_bz = (_d(A[0]["date_from"]) - timedelta(weeks=10) - timedelta(days=1)) if A else date(y, 2, 28)
    auto_bz = max(auto_bz, start + timedelta(weeks=6))
    last_end = (_d(A[-1].get("date_to")) or _d(A[-1]["date_from"])) if A else None
    auto_roz = max(date(y, 10, 1), last_end + timedelta(weeks=regen, days=1)) if last_end else date(y, 10, 1)
    bz_end = _d(ov.get(f"season.{y}.bz_end")) or auto_bz
    roz = _d(ov.get(f"season.{y}.roz")) or auto_roz
    return {"year": y, "start": start, "bz_end": bz_end, "roz": min(roz, luz), "luz": luz, "end": nxt - timedelta(days=1),
            "auto": {"start": f"season.{y}.start" not in ov, "bz_end": f"season.{y}.bz_end" not in ov,
                     "roz": f"season.{y}.roz" not in ov, "luz": f"season.{y}.luz" not in ov},
            "a_goals": [g.get("name") for g in A]}


def season_of(d: date, ov: dict) -> int:
    nxt_start = _d(ov.get(f"season.{d.year + 1}.start")) or first_workday_after_xmas(d.year)
    return d.year + 1 if d >= nxt_start else d.year


def season_weeks(goals: list, ov: dict, s0: date, n: int = 70) -> list[dict]:
    ev = []
    for g in goals:
        if g.get("kind") in ("trip", "long_ride") and g.get("date_from") and g.get("status") not in ("dropped", "done"):
            a = _d(g["date_from"]); b = _d(g.get("date_to")) or a
            ev.append({"g": g, "a": a, "b": max(a, b), "pr": g.get("priority", "B")})
    ev.sort(key=lambda x: x["a"])
    A = [x for x in ev if x["pr"] == "A"]
    taper, regen = int(P(ov, "season.taper_w")), int(P(ov, "season.regen_w"))
    W = [{"s": s0 + timedelta(weeks=i), "ph": None, "h": 0.0, "ev": [], "lt": False, "bev": False, "pre": False, "season": None} for i in range(n)]
    SB: dict = {}

    def wk0(t: date) -> date:
        return s0 + timedelta(weeks=(t - s0).days // 7)
    for w in W:
        m = w["s"] + timedelta(days=3)
        y = season_of(m, ov)
        sb = SB.get(y) or SB.setdefault(y, season_bounds(y, ov, goals))
        w["season"] = y
        if m >= sb["luz"]:
            w["ph"] = "lz"
        elif m >= sb["roz"]:
            w["ph"] = "rt"
        elif m <= sb["bz_end"]:
            w["ph"] = "bz"
        else:
            w["ph"] = "bd"
    for x in A:
        ws, we = wk0(x["a"]), wk0(x["b"])
        for w in W:
            if w["ph"] in ("lz",):
                continue
            if ws - timedelta(weeks=taper) <= w["s"] < ws:
                w["ph"] = "tp"
            if ws <= w["s"] <= we:
                w["ph"] = "ev"
            if we < w["s"] <= we + timedelta(weeks=regen):
                w["ph"] = "rg"
    # po regeneracji ostatniej A w danym sezonie, a przed roztrenowaniem: jazda sezonowa (bez budowy pod nic)
    for y, sb in SB.items():
        lastA = [x for x in A if sb["start"] <= x["a"] <= sb["end"]]
        if not lastA:  # sezon bez wyprawy A: po bazie zwykla jazda sezonowa (nie ma pod co budowac szczytu)
            for w in W:
                if w["season"] == y and w["ph"] == "bd":
                    w["ph"] = "sz"
            continue
        lw = wk0(lastA[-1]["b"]) + timedelta(weeks=regen)
        for w in W:
            if w["season"] == y and w["s"] > lw and w["ph"] == "bd":
                w["ph"] = "sz"
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
        if w["ev"] and w["ev"][0]["pr"] != "A" and w["ph"] != "lz":
            w["h"] = max(base, od(w) * 5.0); w["bev"] = True
            continue
        nx = W[i + 1] if i + 1 < len(W) else None
        if nx and nx["ev"] and nx["ev"][0]["pr"] != "A" and w["ph"] not in ("tp", "lz"):
            base *= 0.8; w["pre"] = True
        w["h"] = base
    k = 0
    cyc, vol = int(P(ov, "season.light_every_w")), float(P(ov, "season.volume"))
    for w in W:
        if w["ph"] in ("rt", "bz", "bd", "sz"):
            k += 1
            if k % cyc == 0 and not w["bev"]:
                w["h"] *= 0.7; w["lt"] = True
        else:
            k = 0
        if w["ph"] not in ("ev", "lz") and not w["bev"]:
            w["h"] *= (1 + (vol - 5) * 0.06)
    return W


def seasons_summary(goals: list, ov: dict, today: date, n: int = 3) -> list[dict]:
    y0 = season_of(today, ov)
    out = []
    for y in range(y0, y0 + n):
        sb = season_bounds(y, ov, goals)
        out.append({k: (v.isoformat() if isinstance(v, date) else v) for k, v in sb.items()})
    return out


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
        elif c.get("id") in ctx.get("route_trip_ids", set()):
            info["type"] = "trip" if info["type"] in ("normal", "urlop", "short") else info["type"]; info["labels"].append("🗺️ " + (c.get("title") or "wyprawa"))
        elif kind == "event" and c.get("at_time") and c.get("id") not in ctx.get("route_entry_ids", set()):
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
    if ph == "lz":
        days_ = [ws + timedelta(days=i) for i in range(7)]
        return {"sessions": [], "notes": ["totalny luz — bez planu treningów (najwyżej luźny spacer / joga, jeśli masz ochotę)"],
                "phase": ph, "phase_name": PH_NAME[ph], "light": False, "target_h": 0.0, "planned_h": 0.0, "season": wk.get("season"),
                "days": {d.isoformat(): {"type": day_info(ctx, d)["type"], "labels": day_info(ctx, d)["labels"], "busy": [], "wx": (ctx.get("weather") or {}).get(d.isoformat())} for d in days_}}
    floor_h = float(ctx.get("km_floor_h") or 0)
    base_h = float(wk["h"])
    if floor_h > base_h:
        notes.append(f"cel kilometrów wymaga ~{floor_h:.1f} h/tydz. (okres: {base_h:.1f} h) — budżet podniesiony")
        base_h = floor_h
    target_min = int(min(base_h, float(P(ov, "load.budget_h"))) * 60)
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
    trip_n = sum(1 for d in days if infos[d]["type"] == "trip")
    if trip_n:
        target_min = int(target_min * (7 - trip_n) / 7)
        notes.append(f"wyprawa w tym tygodniu ({trip_n} dni) — liczona osobno; pozostałe dni: ~{target_min / 60:.1f} h")
    # (b) plynny przyrost: max +load.max_inc_pct wzgledem poprzedniego 'zwyklego' tygodnia (bez wyprawy / choroby / lzejszego)
    prev_h = ctx.get("prev_week_h")
    if prev_h and not trip_n and not wk.get("lt") and ctx.get("prev_week_normal"):
        cap = int(prev_h * 60 * (1 + float(P(ov, "load.max_inc_pct")) / 100))
        if target_min > cap:
            notes.append(f"przyrost ograniczony do +{P(ov, 'load.max_inc_pct')}% względem poprzedniego tygodnia ({prev_h:.1f} h → {cap / 60:.1f} h)")
            target_min = cap
    for s in ctx.get("keep", []):
        if s.get("status") == "skip" and s.get("sport") in cnt:  # usuniete/pominiete przez Ciebie: silnik nie wstawia zastepstwa
            cnt[s["sport"]] = max(0, cnt[s["sport"]] - 1)
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

    long_day = None
    long_h_cfg = float(P(ov, "yoga.long_h"))
    for rr in ctx.get("route_rides", []):
        d = _d(rr["day"])
        if d not in infos or d < today or infos[d]["type"] in ("rest", "ill", "del"):
            continue
        dur = int(rr["dur_min"])
        is_long = dur >= long_h_cfg * 60 * 0.8 or (rr.get("km") or 0) >= 80
        st = rr.get("at") or "08:00"
        srow = {"day": d.isoformat(), "sport": "rower", "name": rr["name"], "start_time": st, "dur_min": dur,
                "min_min": dur, "zone": 2, "is_long": is_long, "xss": rr.get("xss") or xss_of("rower", 2, dur),
                "status": "plan", "cut": False, "source": "auto",
                "note": "jazda z Kalendarza (trasa): " + ", ".join(x for x in (f"{rr['km']} km" if rr.get("km") else None, f"+{rr['up']} m" if rr.get("up") else None, f"~{rr['xss']} XSS" if rr.get("xss") else None) if x)}
        placed.append(srow); out.append(srow)
        if rr.get("multi"):
            target_min += dur  # neutralizacja odjecia ponizej: dni wyprawy liczone osobno
        st_m = hm(st)
        infos[d]["win"]["joga"] = [(max(5 * 60, st_m - 60), st_m)]   # joga przed jazda - przed startem
        if not rr.get("multi"):  # dzien wyprawy nie zabiera jazd z reszty tygodnia
            cnt["rower"] = max(0, cnt["rower"] - 1)
        target_min = max(0, target_min - dur)
        if is_long and (long_day is None or (rr.get("xss") or 0) > 0):
            long_day = d
        notes.append(f"{d.isoformat()}: Twoja jazda z Kalendarza „{rr['name']}” (~{dur // 60} h {dur % 60:02d}′) — plan ułożony wokół niej")
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

    pat = {k: set(v) for k, v in (ctx.get("prev_pattern") or {}).items()}   # dni tygodnia z poprzedniego tygodnia
    prev_last = set(ctx.get("prev_last_sports") or [])                      # sporty z niedzieli poprzedniego tygodnia
    fixed = cnt["sila"] * 40 + cnt["wiosl"] * 30 + cnt["joga"] * 20
    rower_total = max(0, target_min - fixed)
    long_h = float(P(ov, "yoga.long_h"))
    hard_xss = float(P(ov, "yoga.hard_xss"))
    heavy_gap_h = float(P(ov, "regen.heavy_gap_h"))
    hard_gap_d = int(P(ov, "int.hard_gap_days"))
    carry = [dict(c_, day=_d(c_["day"])) for c_ in ctx.get("carry", [])]

    def heavy_days() -> list:
        hs = [_d(p["day"]) for p in placed if p["sport"] == "rower" and (p.get("is_long") or float(p.get("xss") or 0) >= hard_xss)]
        return hs + [c_["day"] for c_ in carry if c_.get("is_long") or float(c_.get("xss") or 0) >= hard_xss]

    recovery = {_d(x["day"]): x for x in ctx.get("trip_recovery_days", [])}
    for d in days:  # dzien przed wyprawa (wielodniowa) = swiezosc na start
        nd_ = d + timedelta(days=1)
        if infos[d]["type"] != "trip" and nd_ in infos and infos[nd_]["type"] == "trip" and d not in recovery:
            recovery[d] = {"trip": (infos[nd_]["labels"][-1] if infos[nd_]["labels"] else "wyprawa").replace("🗺️ ", ""), "k": 0, "n": 0, "why": "dzień przed wyprawą — świeże nogi na start"}
    pre_n = int(P(ov, "regen.pre_trip_d"))
    trip_starts = [d for d in days if infos[d]["type"] == "trip" and (d - timedelta(days=1) not in infos or infos[d - timedelta(days=1)]["type"] != "trip")]
    if ctx.get("next_trip_start"):
        trip_starts.append(_d(ctx["next_trip_start"]))
    taper: dict = {}      # dzien -> start wyprawy (dni -2..-N: tylko jedna krotka luzna jazda)
    for S_ in trip_starts:
        for k in range(2, pre_n + 1):
            d = S_ - timedelta(days=k)
            if d in infos and infos[d]["type"] != "trip":
                taper.setdefault(d, S_)
    no_strength = {S_ - timedelta(days=k) for S_ in trip_starts for k in range(1, pre_n + 2)}
    for S_ in trip_starts:
        tl = sorted(d for d, v in taper.items() if v == S_ and d >= today)
        if tl:
            notes.append(f"{', '.join(x.isoformat() for x in tl)}: luz przed wyprawą ({S_.isoformat()}) — najwyżej jedna krótka, luźna jazda; bez siły")
    if ctx.get("next_trip_start"):  # wyprawa zaczyna sie w poniedzialek nastepnego tygodnia
        d = _d(ctx["next_trip_start"]) - timedelta(days=1)
        if d in infos and d not in recovery and infos[d]["type"] != "trip":
            recovery[d] = {"trip": ctx.get("next_trip_name") or "wyprawa", "k": 0, "n": 0, "why": "dzień przed wyprawą — świeże nogi na start"}
    for d, x in sorted(recovery.items()):
        if d in infos and d >= today:
            notes.append(f"{d.isoformat()}: " + (f"odpoczynek po wyprawie „{x['trip']}” (dzień {x['k']}/{x['n']}) — {x['why']}" if x["k"] else f"{x['why']} („{x['trip']}”)"))

    def in_heavy_gap(d: date) -> date | None:
        """Dzien d wypada w przerwie po ciezkiej jezdzie albo w odpoczynku po wyprawie (tez z poprzedniego tygodnia)."""
        if d in recovery:
            return d
        for h in heavy_days():
            if 0 < (d - h).days * 24 < heavy_gap_h:
                return h
        return None
    _seen_carry = set()
    for c_ in sorted(carry, key=lambda x: -float(x.get("xss") or 0)):
        if c_["day"] in _seen_carry:
            continue
        _seen_carry.add(c_["day"])
        if c_.get("is_long") or float(c_.get("xss") or 0) >= hard_xss:
            blocked = [d for d in plan_days if 0 < (d - c_["day"]).days * 24 < heavy_gap_h and infos[d]["type"] != "trip"
                       and not any(p["day"] == d.isoformat() and p["sport"] == "rower" for p in placed)]
            if blocked:
                notes.append(f"{', '.join(x.isoformat() for x in blocked)}: przerwa po ciężkiej jeździe {c_['day'].isoformat()} ({c_.get('name') or 'jazda'}, ~{int(float(c_.get('xss') or 0))} XSS) — bez roweru")
    # 1) dluga jazda (pomijana, gdy dluga jest juz w Kalendarzu)
    if long_day is None and cnt["rower"] >= 1 and ph not in ("ev", "rg") and rower_total >= 60:
        cands = [d for d in plan_days if open_day(d) and (d.weekday() >= 5 or infos[d]["type"] == "urlop") and not has(d, "rower") and not in_heavy_gap(d) and d not in taper]
        scored = []
        for d in cands:
            bad = wx_bad(infos[d]["wx"], ov, True)
            free = find_slot(infos[d], "rower", 600, placed, 60)
            scored.append((1 if bad else 0, 0 if d.weekday() in pat.get("long", set()) else 1, -(free[1] if free else 0), d, bad))
        scored.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
        if scored and scored[0][2] < 0:
            _, _, _, d, bad = scored[0]
            dur = int(max(60, min(rower_total * (0.45 if cnt["rower"] > 1 else 1.0), long_h * 60 * 1.3)))
            real_long = dur >= long_h * 60 * 0.5   # np. 60' w roztrenowaniu to nie 'dluga jazda'
            s = add(d, "rower", "Długa jazda" if real_long else "Rower dłużej", dur, 60, zone=2, is_long=real_long,
                    why="najdłuższa jazda tygodnia")
            if s:
                long_day = d if real_long else None
                rower_total -= s["dur_min"]; cnt["rower"] -= 1
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
                if in_heavy_gap(d):
                    continue
                if d in taper and any(p["sport"] == "rower" and _d(p["day"]) in taper and taper[_d(p["day"])] == taper[d] for p in placed):
                    continue
                bad = wx_bad(infos[d]["wx"], ov, False)
                rdays = [_d(p["day"]) for p in placed if p["sport"] == "rower"]
                dist = min([abs((d - x).days) for x in rdays], default=7)
                cands.append((1 if bad else 0, 0 if d.weekday() in pat.get("rower", set()) else 1, -dist, d, bad))
            if not cands:
                break
            cands.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
            _, _, _, d, bad = cands[0]
            if bad:
                if int(ov.get(f"mix.wiosl.{month}", MIXD["wiosl"][month - 1])) > 0 or cnt["wiosl"] > 0:
                    cnt["wiosl"] += 1
                    notes.append(f"{d.isoformat()}: {bad} — zamiast jazdy wioślarz w domu")
                else:
                    notes.append(f"{d.isoformat()}: {bad} — jazda pominięta (brak lepszego dnia)")
                break
            name, zone = ("Rower luźno", 1) if ph in ("rg", "tp") else ("Rower spokojnie", 2)
            dur_ = each
            if d in taper:
                name, zone, dur_ = "Rower luźno (przed wyprawą)", 1, min(each, 45)
            s = add(d, "rower", name, dur_, 30, zone=zone, why=("luz przed wyprawą — krótko i spokojnie" if d in taper else ""))
            if not s:
                continue
    # 3) mocny akcent
    if hard_n:
        gap = int(P(ov, "int.hard_gap_days"))
        for s in sorted([x for x in out if x["sport"] == "rower" and not x["is_long"]], key=lambda x: -x["dur_min"]):
            if hard_n <= 0:
                break
            d = _d(s["day"])
            if any(0 < abs((d - h).days) < gap for h in heavy_days() if h != d):
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
            if long_day and 0 <= (long_day - d).days <= 1:   # nie w dzien dlugiej jazdy ani w przeddzien
                continue
            if in_heavy_gap(d) or any(0 <= (h - d).days <= 1 for h in heavy_days()):  # ani w przerwie po ciezkiej, ani przed ciezka
                continue
            if d == ws and "sila" in prev_last:   # 48 h miedzy sila takze przez niedziele / poniedzialek
                continue
            if d in no_strength:                   # sila nie blizej niz N+1 dni przed wyprawa
                continue
            cands.append((0 if d.weekday() in pat.get("sila", set()) else 1, 1 if has(d, "rower") else 0, d))
        if not cands:
            break
        cands.sort()
        d = cands[0][2]
        if add(d, "sila", "Siła obwodowa", 40, 15):
            sila_i += 1
    # 5) wioslarz (chetnie w dni z zla pogoda)
    for _ in range(cnt["wiosl"]):
        cands = []
        for d in plan_days:
            if not open_day(d) or has(d, "wiosl") or d in recovery or d in no_strength:
                continue
            bad = wx_bad(infos[d]["wx"], ov, False)
            cands.append((0 if bad else 1, 1 if has(d, "rower") else 0, d))
        if not cands:
            break
        cands.sort()
        add(cands[0][2], "wiosl", "Wioślarz spokojnie", 30, 15)
    # 6) joga wg regul
    jn = cnt["joga"]
    for c_ in carry:
        nd = c_["day"] + timedelta(days=1)
        if (c_.get("is_long") or float(c_.get("xss") or 0) >= hard_xss) and nd in infos and nd >= today and open_day(nd) and not has(nd, "joga") and jn > 0:
            key = "rest_after_long"
            if int(ov.get(f"yoga.{key}.on", 1)) and add(nd, "joga", "Joga po długiej jeździe", int(ov.get(f"yoga.{key}.min", YOGA[key])), 10, why=f"dzień po długiej jeździe ({c_['day'].isoformat()})"):
                jn -= 1
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
    return {"sessions": out, "notes": notes, "phase": ph, "phase_name": PH_NAME.get(ph, ph), "light": bool(wk.get("lt")), "season": wk.get("season"),
            "target_h": round(min(base_h, float(P(ov, "load.budget_h"))), 1), "planned_h": round(total / 60, 1),
            "days": {d.isoformat(): {"type": infos[d]["type"], "labels": infos[d]["labels"],
                                     "busy": [{"a": t2(a), "b": t2(b), "label": l} for a, b, l in infos[d]["busy"] if a is not None],
                                     "wx": infos[d]["wx"]} for d in days}}


def check_rules_detailed(sessions: list, ov: dict, days_meta: dict | None = None) -> list[dict]:
    """Ostrzezenia tygodnia jako obiekty {key, text, session_id, acked}. key = typ:id_sesji -> mozna wyciszyc per sesja
    ("rozumiem, zostaw" -> trainer_session.acks). Dziala tez dla sesji recznych (silnik ich nie rusza)."""
    out = []
    hard = float((ov or {}).get("yoga.hard_xss", DEF["yoga.hard_xss"]))
    by: dict = {}
    for s in sessions:
        if s.get("status") == "skip":
            continue
        by.setdefault(str(s["day"])[:10], []).append(s)
    def is_long(x):
        return bool(x.get("is_long")) or float(x.get("xss") or 0) >= hard
    def add(kind, x, text):
        sid = x.get("id")
        key = f"{kind}:{sid}" if sid else kind
        out.append({"key": key, "text": text, "session_id": sid, "acked": key in (x.get("acks") or [])})
    for d in sorted(by):
        L = by[d]
        dd = f"{d[8:10]}.{d[5:7]}"
        nxt = (date.fromisoformat(d) + timedelta(days=1)).isoformat()
        nd = f"{nxt[8:10]}.{nxt[5:7]}"
        for x in [y for y in L if y["sport"] == "sila"]:
            if any(y["sport"] == "rower" and is_long(y) for y in L):
                add("sila_long", x, f"{dd}: siła w dniu długiej jazdy — nogi będą zmęczone na trasie")
            if nxt in by and any(y["sport"] == "rower" and is_long(y) for y in by[nxt]):
                add("sila_before_long", x, f"{dd}: siła w przeddzień długiej jazdy ({nd}) — nogi mogą być zmęczone")
            if nxt in by and any(y["sport"] == "sila" for y in by[nxt]):
                add("sila_seq", x, f"siła dzień po dniu ({dd} i {nd}) — zalecane 48 h przerwy")
        trip_pair = ((days_meta or {}).get(d) or {}).get("type") == "trip" and ((days_meta or {}).get(nxt) or {}).get("type") == "trip"
        if nxt in by and not trip_pair:
            for x in [y for y in L if y["sport"] == "rower" and is_long(y)]:
                if any(y["sport"] == "rower" and is_long(y) for y in by[nxt]):
                    add("long_seq", x, f"dwie długie / ciężkie jazdy pod rząd ({dd}, {nd})")
        dm = (days_meta or {}).get(d) or {}
        # przed wyprawa (dni typu trip): sila w 4 dniach przed / trening dzien przed
        for k in range(1, 5):
            td = (date.fromisoformat(d) + timedelta(days=k)).isoformat()
            tm = (days_meta or {}).get(td) or {}
            pm = (days_meta or {}).get((date.fromisoformat(td) - timedelta(days=1)).isoformat()) or {}
            if tm.get("type") == "trip" and pm.get("type") != "trip":
                for x in L:
                    if x["sport"] in ("sila", "wiosl") and x.get("status") == "plan":
                        add("pre_trip_strength", x, f"{dd}: {x['name']} {k} dni przed wyprawą ({td[8:10]}.{td[5:7]}) — nogi mają być świeże")
                    if k == 1 and x["sport"] == "rower" and x.get("status") == "plan":
                        add("pre_trip_ride", x, f"{dd}: jazda dzień przed wyprawą — lepiej wolne")
        if dm.get("type") in ("rest", "ill"):
            for x in L:
                if x["sport"] != "joga" and x.get("status") == "plan":
                    add("rest_day", x, f"{dd}: {x['name']} w dzień {'REST' if dm['type'] == 'rest' else 'choroby'}")
        for bz in dm.get("busy") or []:
            a0, b0 = hm(bz["a"]), hm(bz["b"])
            for x in L:
                if x.get("start_time") and x.get("status") == "plan":
                    s0 = hm(str(x["start_time"])[:5]); e0 = s0 + int(x["dur_min"])
                    if s0 < b0 and e0 > a0:
                        add("busy", x, f"{dd}: {x['name']} {str(x['start_time'])[:5]} koliduje z „{bz['label'].strip()}” {bz['a']}–{bz['b']}")
    return out


def check_rules(sessions: list, ov: dict, days_meta: dict | None = None) -> list[str]:
    """Teksty NIEwyciszonych ostrzezen (zgodnosc wsteczna)."""
    return [w["text"] for w in check_rules_detailed(sessions, ov, days_meta) if not w["acked"]]


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
    import re as _re
    route_rides, route_ids, route_trip_ids = [], set(), set()

    def _route_days(pa, pb):
        """Wydarzenia Kalendarza z podpieta trasa nachodzace na [pa, pb] -> lista jazd per dzien.
        Wydarzenie wielodniowe (end_day) z jedna trasa = wyprawa: km / m / XSS rozlozone rowno na dni
        (chyba ze Planer dal osobne trasy per dzien). Km i +m z notatki maja pierwszenstwo przed trasa."""
        c.execute("""SELECT e.id AS entry_id, e.day, e.end_day, e.at_time, e.note, e.title, r.day AS rday, r.route_id, r.route_name
                     FROM qbot_v2.calendar_entry e JOIN qbot_v2.calendar_day_route r ON r.entry_id = e.id
                     WHERE e.day <= %s AND COALESCE(e.end_day, e.day) >= %s""", (pb, pa))
        rows = c.fetchall()
        c.execute("SELECT COALESCE(SUM(distance_m),0)/1000.0 AS km, COALESCE(SUM(duration_s),0)/3600.0 AS h FROM qbot_v2.training_sessions "
                  "WHERE sport_type IN ('cycling','gravel_cycling') AND date > %s", (today - timedelta(days=120),))
        sp_ = c.fetchone()
        spd_ = (float(sp_["km"]) / float(sp_["h"])) if sp_ and sp_["h"] and float(sp_["h"]) > 5 else 20.0
        per_entry: dict = {}
        for r in rows:
            per_entry.setdefault(r["entry_id"], []).append(r)
        out_ = []
        for eid, rs in per_entry.items():
            e = rs[0]
            d0, d1 = _d(e["day"]), _d(e["end_day"]) or _d(e["day"])
            n = (d1 - d0).days + 1
            note = e["note"] or ""
            mk = _re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*km", note)
            mu = _re.search(r"\+\s*([0-9]+)\s*m\b", note) or _re.search(r"(?<![0-9k])([0-9]{3,5})\s*m(?![a-zł])", note)
            mx = _re.search(r"~\s*([0-9]+)\s*XSS", note)
            title = (e["title"] or e["route_name"] or "Jazda z Kalendarza").replace("[Q] ", "").split(" · ")[0]
            if len(rs) > 1 or n == 1:
                items = [(_d(r["rday"]), r) for r in rs]
                split = 1
            else:
                items = [(d0 + timedelta(days=i), rs[0]) for i in range(n)]
                split = n
            for i, (dday, r) in enumerate(sorted(items, key=lambda x: x[0])):
                km_ = float(mk.group(1).replace(",", ".")) / split if (mk and split > 1) else (float(mk.group(1).replace(",", ".")) if mk and n == 1 else None)
                if km_ is None:
                    c.execute("SELECT distance_m FROM qbot_v2.route_base WHERE route_id=%s ORDER BY updated_at DESC LIMIT 1", (r["route_id"],))
                    rb = c.fetchone(); km_ = round(float(rb["distance_m"]) / 1000 / split, 1) if rb and rb["distance_m"] else None
                up_ = int(int(mu.group(1)) / split) if mu else None
                xs_ = int(int(mx.group(1)) / split) if mx else None
                dur = int(round((km_ / spd_) * 60)) if km_ else 180
                out_.append({"entry_id": eid, "day": dday, "route_id": r["route_id"],
                             "name": title + (f" — dzień {i + 1}/{len(items)}" if len(items) > 1 else ""),
                             "at": e["at_time"].strftime("%H:%M") if e["at_time"] else None, "km": round(km_, 1) if km_ else None,
                             "up": up_, "xss": xs_, "dur_min": max(30, dur), "multi": n > 1})
        return out_
    try:
        for rr in _route_days(ws, we):
            if ws <= _d(rr["day"]) <= we:
                route_rides.append(rr)
            route_ids.add(rr["entry_id"])
            if rr["multi"]:
                route_trip_ids.add(rr["entry_id"])
    except Exception:
        route_rides, route_ids, route_trip_ids = [], set(), set()
    carry = []
    try:
        pa, pb = ws - timedelta(days=3), ws - timedelta(days=1)
        c.execute("SELECT day, sport, name, dur_min, xss, is_long FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s "
                  "AND status IN ('plan','done') AND sport='rower'", (user, pa, pb))
        for r in c.fetchall():
            carry.append({"day": r["day"], "name": r["name"], "xss": float(r["xss"] or 0), "is_long": bool(r["is_long"]), "src": "plan"})
        for rr in _route_days(pa, pb):
            if pa <= _d(rr["day"]) <= pb:
                carry.append({"day": rr["day"], "name": rr["name"], "xss": float(rr.get("xss") or xss_of("rower", 2, rr["dur_min"])),
                              "is_long": (rr.get("km") or 0) >= 80 or rr["dur_min"] >= float(P(ov, "yoga.long_h")) * 60 * 0.8, "src": "kalendarz"})
        c.execute("SELECT date, activity_name, duration_s, tss, sport_type FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (pa, pb))
        for r in c.fetchall():
            if SPORT_OF.get(r["sport_type"]) == "rower":
                carry.append({"day": r["date"], "name": r["activity_name"], "xss": float(r["tss"] or 0),
                              "is_long": (r["duration_s"] or 0) >= float(P(ov, "yoga.long_h")) * 3600 * 0.8, "src": "garmin"})
    except Exception:
        carry = []
    prev_pattern, prev_last, prev_h, prev_normal, rec_days, next_trip = {}, [], None, False, [], None
    try:
        pw0, pw1 = ws - timedelta(days=7), ws - timedelta(days=1)
        c.execute("SELECT day, sport, name, dur_min, is_long, note, status FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s "
                  "AND status IN ('plan','done')", (user, pw0, pw1))
        pr = c.fetchall()
        for r in pr:
            k = "long" if r["is_long"] else r["sport"]
            prev_pattern.setdefault(k, []).append(r["day"].weekday())
            if r["day"] == pw1:
                prev_last.append(r["sport"])
        prev_multi = any(" — dzień " in (r["name"] or "") for r in pr)
        c.execute("SELECT 1 FROM qbot_v2.calendar_entry WHERE kind='illness' AND day <= %s AND COALESCE(end_day, day) >= %s LIMIT 1", (pw1, pw0))
        ill = bool(c.fetchone())
        if pr:
            prev_h = sum(int(r["dur_min"]) for r in pr) / 60
            prev_normal = not prev_multi and not ill
        # wyprawy (cele + wielodniowe trasy z Kalendarza) konczace sie w ostatnich 8 dniach lub w tym tygodniu
        import qbot_trener_stats as _ST
        trec = _ST.trip_recovery_cached(c)
        n_rec = int(ov.get("regen.trip_rec_d", trec.get("value") or DEF["regen.trip_rec_d"]))
        why = ("ręcznie ustawione" if "regen.trip_rec_d" in ov else (trec.get("note") or "z danych"))
        trips = []
        for g in goals:
            if g.get("kind") == "trip" and g.get("date_from") and g.get("status") not in ("dropped", "done"):
                a_, b_ = _d(g["date_from"]), _d(g.get("date_to")) or _d(g["date_from"])
                if (b_ - a_).days >= 1:
                    trips.append((g["name"], b_))
        ends: dict = {}
        for rr in _route_days(ws - timedelta(days=10), we):
            if rr.get("multi"):
                ends[rr["entry_id"]] = max(ends.get(rr["entry_id"], (None, date.min)), (rr["name"].split(" — ")[0], _d(rr["day"])), key=lambda x: x[1])
        trips += list(ends.values())
        nxt_mon = we + timedelta(days=1)
        for g in goals:
            if g.get("kind") == "trip" and _d(g.get("date_from")) == nxt_mon and g.get("status") not in ("dropped", "done"):
                next_trip = (nxt_mon, g["name"])
        for rr in _route_days(nxt_mon, nxt_mon):
            if rr.get("multi") and _d(rr["day"]) == nxt_mon:
                next_trip = (nxt_mon, rr["name"].split(" — ")[0])
        for name, end in trips:
            if ws - timedelta(days=8) <= end <= we:
                for k in range(1, n_rec + 1):
                    rec_days.append({"day": end + timedelta(days=k), "trip": name, "k": k, "n": n_rec, "why": why})
    except Exception:
        pass
    km_floor_h = 0.0
    try:
        import calendar as _cal
        import qbot_trener_stats as ST
        for g in goals:
            t = g.get("target") or {}
            if g.get("kind") == "volume" and g.get("status") == "active" and t.get("km") and t.get("sport", "rower") == "rower":
                a_, b_ = _d(g.get("date_from")), _d(g.get("date_to"))
                if a_ and b_ and a_ <= ws + timedelta(days=3) <= b_:
                    m = ws + timedelta(days=3)
                    plan = {p["month"]: p["value"] for p in ST.volume_plan(a_, b_, float(t["km"]), ST.month_profile(c, "rower"))}
                    km_week = plan.get(m.strftime("%Y-%m"), 0) / (_cal.monthrange(m.year, m.month)[1] / 7)
                    c.execute("SELECT COALESCE(SUM(distance_m),0)/1000.0 AS km, COALESCE(SUM(duration_s),0)/3600.0 AS h FROM qbot_v2.training_sessions "
                              "WHERE sport_type IN ('cycling','gravel_cycling') AND date > %s", (today - timedelta(days=120),))
                    rr = c.fetchone()
                    spd = (float(rr["km"]) / float(rr["h"])) if rr and rr["h"] and float(rr["h"]) > 5 else 20.0
                    km_floor_h = max(km_floor_h, km_week / spd)
    except Exception:
        km_floor_h = 0.0
    return {"week_start": ws, "today": today, "ov": ov, "goals": goals, "rules": rules, "calendar": cal, "day_state": dstate, "km_floor_h": round(km_floor_h, 1),
            "route_rides": route_rides, "route_entry_ids": route_ids, "route_trip_ids": route_trip_ids, "carry": carry,
            "prev_pattern": prev_pattern, "prev_last_sports": prev_last, "prev_week_h": prev_h, "prev_week_normal": prev_normal,
            "trip_recovery_days": rec_days, "next_trip_start": next_trip[0] if next_trip else None, "next_trip_name": next_trip[1] if next_trip else None,
            "keep": keep, "activities_extra": extra, "readiness_today": rt, "readiness_threshold": thr, "weather": wx,
            "all_sessions": sess}
