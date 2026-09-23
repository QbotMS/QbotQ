"""TRENER - Etap 4: bilans (logi / waga), statusy celow, czas (optimum vs wolne okna), pogoda auto z historii jazd.

Czyste funkcje (testy: tests/test_trener_stats.py) + funkcje z baza (c = kursor dict_row).
Nic tu nie zapisuje danych uzytkownika; jedyny zapis to cache pogody auto (trainer_auto_cache).
"""
from __future__ import annotations

import json
import statistics as st
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import qbot_trener_engine as E

KCAL_PER_KG = 7700.0


# ---------------- czyste funkcje ----------------

def lin_slope(pts: list[tuple[float, float]]) -> float | None:
    """Nachylenie prostej MNK (y na dzien)."""
    if len(pts) < 5:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if not sxx:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx


def balance(days: list[dict], smooth_days: int = 14, mode: int = 1) -> dict:
    """days: [{day, intake|None, expend|None, weight|None}] rosnaco, bez dzisiejszego (niepelnego) dnia.
    mode: 0 = tylko logi, 1 = logi -> waga (gdy logow < 70% dni), 2 = tylko waga."""
    win = days[-smooth_days:] if smooth_days else days
    exp = [d["expend"] for d in win if d.get("expend")]
    exp_avg = st.mean(exp) if exp else None
    logged = [d for d in win if d.get("intake") and d["intake"] > 500 and d.get("expend")]
    log_bal = st.mean(d["intake"] - d["expend"] for d in logged) if logged else None
    wpts = [(i, d["weight"]) for i, d in enumerate(win) if d.get("weight")]
    slope = lin_slope(wpts)
    w_bal = slope * KCAL_PER_KG if slope is not None else None
    share = len(logged) / len(win) if win else 0
    if mode == 0:
        src, bal = "logs", log_bal
    elif mode == 2:
        src, bal = "weight", w_bal
    else:
        src, bal = ("logs", log_bal) if (log_bal is not None and share >= 0.7) else ("weight", w_bal)
    if bal is None and src == "logs" and w_bal is not None and mode != 0:
        src, bal = "weight", w_bal
    intake_est = (exp_avg + w_bal) if (exp_avg is not None and w_bal is not None) else None
    return {"balance_kcal": None if bal is None else round(bal), "source": src if bal is not None else None,
            "days": len(win), "days_logged": len(logged), "log_share": round(share, 2),
            "expend_avg": None if exp_avg is None else round(exp_avg), "intake_log_avg": round(st.mean(d["intake"] for d in logged)) if logged else None,
            "intake_from_weight": None if intake_est is None else round(intake_est),
            "weight_slope_kg_wk": None if slope is None else round(slope * 7, 2),
            "balance_logs": None if log_bal is None else round(log_bal), "balance_weight": None if w_bal is None else round(w_bal)}


def smooth(vals: list, k: int = 7) -> list:
    out = []
    for i in range(len(vals)):
        w = [v for v in vals[max(0, i - k + 1): i + 1] if v is not None]
        out.append(round(st.mean(w), 2) if w else None)
    return out


def series_stats(daily: dict, min_km: float = 20.0) -> dict:
    """daily: {date: (km, up_m)} -> wszystkie maksymalne serie dni >= min_km + rekordy dnia.
    Najdluzsza seria (liczba dni) oraz najlepsza srednia km/dzien i m/dzien sposrod serii >= 3 dni."""
    ds = sorted(daily)
    runs, cur = [], []
    for d in ds:
        if daily[d][0] >= min_km and cur and d == cur[-1] + timedelta(days=1):
            cur.append(d)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = [d] if daily[d][0] >= min_km else []
    if len(cur) >= 2:
        runs.append(cur)
    R = [{"start": r[0].isoformat(), "days": len(r), "km": sum(daily[x][0] for x in r), "up": sum(daily[x][1] for x in r)} for r in runs]
    for x in R:
        x["km_day"], x["up_day"] = x["km"] / x["days"], x["up"] / x["days"]
    longest = max(R, key=lambda x: (x["days"], x["up"]), default=None)
    multi = [x for x in R if x["days"] >= 3]
    bk = max(multi, key=lambda x: x["km_day"], default=None)
    bu = max(multi, key=lambda x: x["up_day"], default=None)
    return {"max_km_day": round(max((v[0] for v in daily.values()), default=0)),
            "max_up_day": round(max((v[1] for v in daily.values()), default=0)),
            "series_days": longest["days"] if longest else 0, "series_start": longest["start"] if longest else None,
            "series_km": round(longest["km"]) if longest else 0, "series_up": round(longest["up"]) if longest else 0,
            "best_km_day": round(bk["km_day"]) if bk else 0, "best_km_series": (f"{bk['start']}, {bk['days']} dni" if bk else None),
            "best_up_day": round(bu["up_day"]) if bu else 0, "best_up_series": (f"{bu['start']}, {bu['days']} dni" if bu else None)}


def _lvl(ratios: list[float]) -> str:
    r = [x for x in ratios if x is not None]
    if not r:
        return "n"
    if min(r) >= 1:
        return "g"
    if min(r) < 0.5:
        return "r"
    return "y"


def status_trip(g: dict, hist: dict, ctl_now: float | None, ctl_max: float | None) -> dict:
    t = g.get("target") or {}
    days = 1 if g.get("kind") == "long_ride" else (t.get("days") or (((E._d(g.get("date_to")) - E._d(g.get("date_from"))).days + 1) if g.get("date_from") and g.get("date_to") else None))
    rows, ratios = [], []
    if t.get("km") and days:
        need = t["km"] / days
        have = hist["max_km_day"] if days == 1 else (hist["best_km_day"] or hist["max_km_day"])
        rows.append({"k": "dystans" if days == 1 else "km na dzień", "have": have, "need": round(need),
                     "note": "Twój rekord dnia" if days == 1 else ((f"najlepsza seria ≥3 dni ({hist['best_km_series']}); " if hist["best_km_series"] else "") + f"rekord dnia {hist['max_km_day']} km")}); ratios.append(have / need if need else None)
    if t.get("up_m") and days:
        need = t["up_m"] / days
        have = hist["max_up_day"] if days == 1 else (hist["best_up_day"] or hist["max_up_day"])
        rows.append({"k": "przewyższenie" if days == 1 else "przewyższenie na dzień", "have": have, "need": round(need),
                     "note": "Twój rekord dnia" if days == 1 else ((f"najlepsza seria ≥3 dni ({hist['best_up_series']}); " if hist["best_up_series"] else "") + f"rekord dnia {hist['max_up_day']} m")}); ratios.append(have / need if need else None)
    if days and days > 1:
        rows.append({"k": "dni pod rząd", "have": hist["series_days"], "need": days, "note": (f"seria od {hist['series_start']}: {hist['series_km']} km, {hist['series_up']} m" if hist["series_start"] else "")})
        ratios.append(hist["series_days"] / days)
    if ctl_now is not None:
        rows.append({"k": "forma (CTL)", "have": round(ctl_now), "need": None, "note": f"rekord z 18 mies.: {round(ctl_max) if ctl_max else '—'}"})
    lvl = _lvl(ratios)
    txt = {"g": "gotowy na obecne wymagania", "y": "wykonalne — są luki", "r": "duża luka", "n": "uzupełnij km / przewyższenie / dni"}[lvl]
    weak = min(rows[:3], key=lambda r: (r["have"] / r["need"]) if r.get("need") else 9, default=None) if rows else None
    if lvl in ("y", "r") and weak and weak.get("need"):
        txt += f"; główna luka: {weak['k']}"
    return {"level": lvl, "text": txt, "rows": rows}


def status_weight(g: dict, cur: float | None, start: float | None, slope_wk: float | None, today: date) -> dict:
    t = (g.get("target") or {}).get("weight_kg")
    if cur is None or not t:
        return {"level": "n", "text": "brak danych o wadze lub celu", "rows": []}
    due = E._d(g.get("date_to")) or E._d(g.get("date_from"))
    weeks = max(0.1, (due - today).days / 7) if due else None
    need = (t - cur) / weeks if weeks else None  # kg/tydz. (ujemne = spadek)
    prog = None
    if start and start != t:
        prog = max(0.0, min(1.0, (start - cur) / (start - t)))
    if slope_wk is None:
        lvl = "n"
    elif (t - cur) * slope_wk <= 0 and abs(cur - t) > 0.3:
        lvl = "r"
    elif need is None or abs(slope_wk) >= abs(need) * 0.9:
        lvl = "g"
    else:
        lvl = "y"
    txt = {"g": "tempo wystarczające", "y": "w dobrą stronę, ale za wolno", "r": "trend w złą stronę", "n": "za mało pomiarów wagi"}[lvl]
    rows = [{"k": "dziś (śr. 7 dni)", "have": round(cur, 1), "need": t, "note": f"start {round(start, 1) if start else '—'} kg"},
            {"k": "tempo (30 dni)", "have": slope_wk, "need": None if need is None else round(need, 2), "note": "kg/tydz.; potrzebne do terminu"}]
    return {"level": lvl, "text": txt, "rows": rows, "progress": None if prog is None else round(prog, 3)}


def status_linear(have: float, target: float, elapsed: float, label: str, unit: str) -> dict:
    exp = target * max(0.0, min(1.0, elapsed))
    ratio = have / exp if exp else None
    lvl = "n" if ratio is None else ("g" if ratio >= 0.95 else ("y" if ratio >= 0.8 else "r"))
    return {"level": lvl, "text": {"g": "zgodnie z planem", "y": "lekko w tyle", "r": "wyraźnie w tyle", "n": "za wcześnie na ocenę"}[lvl],
            "rows": [{"k": label, "have": round(have), "need": round(target), "note": f"na dziś powinno być ~{round(exp)} {unit}"}],
            "progress": round(have / target, 3) if target else None}


def weather_auto(rides: list[dict]) -> dict:
    """rides: [{h, feel, wind, gust, rain, snow_depth, month}] -> wartosci auto wx.* z opisem."""
    def pc(v, p):
        v = sorted(x for x in v if x is not None)
        return v[min(len(v) - 1, int(len(v) * p / 100))] if v else None
    n = len(rides)
    if n < 30:
        return {}
    long_ = [r for r in rides if r["h"] >= 2.5]
    winter = [r for r in rides if r["month"] in (10, 11, 12, 1, 2, 3)]
    out = {}
    w = pc([r["wind"] for r in (long_ or rides)], 95)
    if w is not None:
        out["wx.wind_ms"] = {"value": round(w * 2) / 2, "note": f"95% długich jazd przy wietrze ≤{round(w, 1)} m/s ({len(long_)} jazd; wiatr z modelu 10 m)"}
    g = pc([r["gust"] for r in rides], 95)
    if g is not None:
        out["wx.gust_ms"] = {"value": round(g), "note": f"95% jazd przy porywach ≤{round(g, 1)} m/s"}
    cl = pc([r["feel"] for r in long_], 5)
    if cl is not None:
        out["wx.cold_long_c"] = {"value": round(cl), "note": f"95% długich jazd powyżej {round(cl, 1)} °C odczuwalnej"}
    cs = pc([r["feel"] for r in winter], 10)
    if cs is not None:
        out["wx.cold_short_c"] = {"value": round(cs), "note": f"90% zimowych jazd powyżej {round(cs, 1)} °C odczuwalnej ({len(winter)} jazd)"}
    hh = pc([r["feel_max"] for r in long_], 95)
    if hh is not None:
        out["wx.heat_c"] = {"value": round(hh), "note": f"95% długich jazd poniżej {round(hh, 1)} °C odczuwalnej"}
    wet = sum(1 for r in rides if (r["rain"] or 0) > 0.5)
    out["wx.rain_mmh"] = {"value": 0.5 if wet / n < 0.1 else 1.0, "note": f"{wet} z {n} jazd z opadem >0,5 mm" + (" — deszcz wyraźnie omijasz" if wet / n < 0.1 else "")}
    sn = sum(1 for r in rides if (r["snow_depth"] or 0) > 0)
    out["wx.snow_cm"] = {"value": 10 if sn >= 10 else 3, "note": f"{sn} jazd przy leżącym śniegu"}
    return out


# ---------------- z baza ----------------

def load_days(c, n: int = 60, today: date | None = None) -> list[dict]:
    today = today or date.today()
    d0 = today - timedelta(days=n)
    c.execute("SELECT date, COALESCE(total_kcal_eff, total_kcal) AS e, quality_status FROM qbot_v2.energy_daily WHERE date >= %s AND date < %s", (d0, today))
    exp = {r["date"]: float(r["e"]) for r in c.fetchall() if r["e"] and r["quality_status"] != "partial"}
    c.execute("SELECT l.date, SUM(i.kcal) AS k FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id WHERE l.date >= %s AND l.date < %s GROUP BY l.date", (d0, today))
    itk = {r["date"]: float(r["k"]) for r in c.fetchall() if r["k"]}
    c.execute("SELECT day, weight_kg FROM qbot_v2.fitmodel_daily WHERE day >= %s AND day < %s AND weight_kg IS NOT NULL", (d0, today))
    wt = {r["day"]: float(r["weight_kg"]) for r in c.fetchall()}
    return [{"day": (d0 + timedelta(days=i)).isoformat(), "intake": itk.get(d0 + timedelta(days=i)), "expend": exp.get(d0 + timedelta(days=i)),
             "weight": wt.get(d0 + timedelta(days=i))} for i in range(n)]


def compute_balance(c, ov: dict, goals: list) -> dict:
    days = load_days(c, 60)
    sd = int(ov.get("food.smooth_days", 14))
    mode = int(ov.get("food.source", 1))
    b = balance(days, sd, mode)
    b30 = balance(days, 30, 2)
    wg = next((g for g in goals if g["kind"] == "weight" and g["status"] == "active"), None)
    loss = float(ov.get("food.loss_kg_wk", 0.25))
    tgt_src = "suwak tempa"
    if wg and (wg.get("target") or {}).get("weight_kg"):
        ws = [d["weight"] for d in days[-7:] if d["weight"]]
        cur = st.mean(ws) if ws else None
        due = E._d(wg.get("date_to")) or E._d(wg.get("date_from"))
        if cur and due and due > date.today():
            need = (cur - wg["target"]["weight_kg"]) / ((due - date.today()).days / 7)
            loss = max(0.0, min(1.0, need)); tgt_src = f"cel „{wg['name']}”"
    wv = [d["weight"] for d in days]
    return {"window": b, "trend30": {"weight_slope_kg_wk": b30["weight_slope_kg_wk"], "balance_weight": b30["balance_weight"]},
            "target_balance_kcal": round(-loss * KCAL_PER_KG / 7), "target_loss_kg_wk": round(loss, 2), "target_source": tgt_src,
            "series": [{"day": d["day"], "intake": d["intake"], "expend": d["expend"], "weight": d["weight"], "weight_s": s}
                       for d, s in zip(days[-30:], smooth(wv)[-30:])]}


def _daily_km_up(c, since: date) -> dict:
    c.execute("SELECT date, SUM(distance_m)/1000.0 AS km, SUM(elevation_m) AS up FROM qbot_v2.training_sessions "
              "WHERE sport_type IN ('cycling','gravel_cycling') AND date >= %s GROUP BY date", (since,))
    return {r["date"]: (float(r["km"] or 0), float(r["up"] or 0)) for r in c.fetchall()}


def compute_goal_status(c, goals: list) -> dict:
    today = date.today()
    out = {}
    hist = series_stats(_daily_km_up(c, today - timedelta(days=548)))
    c.execute("SELECT ctl_xss FROM qbot_v2.fitmodel_daily WHERE ctl_xss IS NOT NULL ORDER BY day DESC LIMIT 1")
    r = c.fetchone(); ctl_now = float(r["ctl_xss"]) if r else None
    c.execute("SELECT MAX(ctl_xss) AS m FROM qbot_v2.fitmodel_daily WHERE day >= %s", (today - timedelta(days=548),))
    r = c.fetchone(); ctl_max = float(r["m"]) if r and r["m"] else None
    days = load_days(c, 45)
    ws7 = [d["weight"] for d in days[-7:] if d["weight"]]
    cur_w = st.mean(ws7) if ws7 else None
    slope30 = balance(days, 30, 2)["weight_slope_kg_wk"]
    c.execute("SELECT ftp_est_w FROM qbot_v2.fitmodel_daily WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1")
    r = c.fetchone(); ftp_now = float(r["ftp_est_w"]) if r else None
    for g in goals:
        if g["status"] not in ("active", "paused"):
            continue
        k, t = g["kind"], g.get("target") or {}
        try:
            if k in ("trip", "long_ride"):
                s = status_trip(g, hist, ctl_now, ctl_max)
            elif k == "weight":
                c.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE weight_kg IS NOT NULL AND day >= %s ORDER BY day LIMIT 1", (g["created_at"].date() - timedelta(days=3),))
                r = c.fetchone()
                s = status_weight(g, cur_w, float(r["weight_kg"]) if r else cur_w, slope30, today)
            elif k == "volume":
                a_ = E._d(g.get("date_from")) or date(today.year, 1, 1)
                b_ = E._d(g.get("date_to")) or date(a_.year, 12, 31)
                sp = t.get("sport", "rower")
                c.execute("SELECT sport_type, COALESCE(distance_m,0) AS m, COALESCE(duration_s,0) AS s FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (a_, min(b_, today)))
                rows = [r for r in c.fetchall() if E.SPORT_OF.get(r["sport_type"]) == sp]
                el = (today - a_).days / max(1, (b_ - a_).days + 1)
                if t.get("km"):
                    s = status_linear(sum(float(r["m"]) for r in rows) / 1000, float(t["km"]), el, "km", "km")
                elif t.get("h"):
                    s = status_linear(sum(float(r["s"]) for r in rows) / 3600, float(t["h"]), el, "godziny", "h")
                elif t.get("sessions"):
                    s = status_linear(len(rows), float(t["sessions"]), el, "sesje", "sesji")
                else:
                    s = {"level": "n", "text": "podaj km, godziny albo liczbę sesji", "rows": []}
                if el <= 0:
                    s["level"], s["text"] = "n", "okres jeszcze się nie zaczął"
                weeks = max(1.0, ((b_ - a_).days + 1) / 7)
                for key, unit in (("km", "km"), ("h", "h"), ("sessions", "sesji")):
                    if t.get(key):
                        s["rows"].append({"k": "średnio na tydzień", "have": None, "need": round(float(t[key]) / weeks, 1), "note": f"{unit} / tydz. w całym okresie"})
            elif k == "power":
                if t.get("wkg") and not t.get("ftp_w") and cur_w:
                    t = dict(t, ftp_w=round(float(t["wkg"]) * cur_w))
                if not t.get("ftp_w") or ftp_now is None:
                    s = {"level": "n", "text": "brak FTP lub celu", "rows": []}
                else:
                    c.execute("SELECT ftp_est_w FROM qbot_v2.fitmodel_daily WHERE ftp_est_w IS NOT NULL AND day <= %s ORDER BY day DESC LIMIT 1", (g["created_at"].date(),))
                    r = c.fetchone(); f0 = float(r["ftp_est_w"]) if r else ftp_now
                    due = E._d(g.get("date_to")) or E._d(g.get("date_from"))
                    el = ((today - g["created_at"].date()).days / max(1, (due - g["created_at"].date()).days)) if due else 1
                    gain = ftp_now - f0; need = float(t["ftp_w"]) - f0
                    s = status_linear(max(0.0, gain), need, el, "przyrost FTP", "W") if need > 0 else {"level": "g", "text": "cel osiągnięty", "rows": []}
                    if need > 0 and el < 0.1 and due:
                        months = max(0.5, (due - today).days / 30.4)
                        pm = need / f0 / months * 100
                        s["level"] = "g" if pm <= 1.0 else ("y" if pm <= 2.0 else "r")
                        s["text"] = f"potrzeba +{round(need / months, 1)} W/mies. ({pm:.1f}%/mies.) — " + {"g": "realne", "y": "ambitne", "r": "mało realne"}[s["level"]]
                    s["rows"].insert(0, {"k": "FTP teraz", "have": round(ftp_now), "need": t["ftp_w"], "note": f"na starcie celu {round(f0)} W"})
            elif k == "habit":
                sp = t.get("sport", "rower"); per = float(t.get("per_week") or 0); kmw = float(t.get("km_week") or 0)
                c.execute("SELECT date, sport_type, COALESCE(distance_m,0) AS m FROM qbot_v2.training_sessions WHERE date >= %s", (E.monday(today) - timedelta(weeks=4),))
                wk = defaultdict(lambda: [0, 0.0])
                for r in c.fetchall():
                    if E.SPORT_OF.get(r["sport_type"]) == sp:
                        x = wk[E.monday(r["date"])]; x[0] += 1; x[1] += float(r["m"]) / 1000
                weeks = [E.monday(today) - timedelta(weeks=i) for i in range(1, 5)]
                def met(w):
                    return (wk[w][1] >= kmw) if kmw else (wk[w][0] >= per)
                okw = sum(1 for w in weeks if met(w))
                lvl = "g" if okw >= 3 else ("y" if okw >= 2 else "r")
                cur = wk[E.monday(today)]
                s = {"level": lvl, "text": f"{okw} z 4 ostatnich tygodni ✓",
                     "rows": [{"k": "w tym tygodniu", "have": round(cur[1]) if kmw else cur[0], "need": kmw or per, "note": "km" if kmw else "sesji"}]}
            else:
                s = {"level": "n", "text": "", "rows": []}
        except Exception as e:
            s = {"level": "n", "text": f"błąd liczenia: {str(e)[:80]}", "rows": []}
        out[str(g["id"])] = s
    return out


def compute_time(c, user: str, today: date | None = None) -> dict:
    today = today or date.today()
    ws = E.monday(today)
    ctx = E.build_context(c, user, ws, today)
    ctx["weather"] = {}
    free = []
    for i in range(7):
        d = ws + timedelta(days=i)
        info = E.day_info(ctx, d)
        wins = set()
        for s in ("rower", "sila", "wiosl", "joga"):
            for a, b in info["win"][s]:
                wins.update(range(a, b, 15))
        for a, b, _ in info["busy"]:
            if a is not None:
                wins.difference_update(range(a, b, 15))
        mins = 0 if info["type"] in ("rest", "ill", "trip") else len(wins) * 15
        if info["type"] == "del":
            mins = min(mins, 30)
        if info.get("flex_cap"):
            mins = min(mins, info["flex_cap"] + (0 if d.weekday() < 5 else mins))
        free.append({"day": d.isoformat(), "type": info["type"], "free_min": mins})
    W = E.season_weeks(ctx["goals"], ctx["ov"], ws, 60)
    by_m = defaultdict(list)
    for w in W:
        by_m[(w["s"] + timedelta(days=3)).strftime("%Y-%m")].append(w["h"])
    months = [{"month": m, "h_min": round(min(v), 1), "h_max": round(max(v), 1), "h_avg": round(st.mean(v), 1)} for m, v in sorted(by_m.items())][:13]
    wk = W[0]
    return {"week_start": ws.isoformat(), "target_h": round(wk["h"], 1), "phase": wk["ph"], "phase_name": E.PH_NAME.get(wk["ph"]),
            "budget_h": float(E.P(ctx["ov"], "load.budget_h")), "free": free, "free_h": round(sum(f["free_min"] for f in free) / 60, 1),
            "months": months}


# ---------------- pogoda auto (dlugie liczenie w tle, cache w bazie) ----------------
_LOCK = threading.Lock()
_RUNNING = {"on": False}


def _weather_rides(c) -> list[dict]:
    c.execute("""WITH s AS (SELECT external_id, date, started_at, duration_s FROM qbot_v2.training_sessions
                 WHERE sport_type IN ('cycling','gravel_cycling') AND duration_s >= 1800 AND started_at IS NOT NULL AND date >= %s)
                 SELECT DISTINCT ON (r.external_id) s.date, s.started_at, s.duration_s, r.lat, r.lon
                 FROM qbot_v2.activity_record r JOIN s USING (external_id) WHERE r.lat IS NOT NULL ORDER BY r.external_id, r.sec""",
              (date.today() - timedelta(days=730),))
    rides = c.fetchall()
    G = defaultdict(list)
    for r in rides:
        G[(round(float(r["lat"]) * 4) / 4, round(float(r["lon"]) * 4) / 4)].append(r)
    out = []
    for n, ((la, lo), rs) in enumerate(sorted(G.items(), key=lambda kv: -len(kv[1]))):
        if n >= 80:
            break
        d0 = min(r["date"] for r in rs); d1 = min(max(r["date"] for r in rs) + timedelta(days=1), date.today() - timedelta(days=6))
        if d1 < d0:
            continue
        q = urllib.parse.urlencode(dict(latitude=la, longitude=lo, start_date=str(d0), end_date=str(d1),
                                        hourly="apparent_temperature,wind_speed_10m,wind_gusts_10m,precipitation,snow_depth", wind_speed_unit="ms", timezone="UTC"))
        try:
            with urllib.request.urlopen("https://archive-api.open-meteo.com/v1/archive?" + q, timeout=40) as f:
                j = json.load(f)["hourly"]
        except Exception:
            continue
        idx = {t: i for i, t in enumerate(j["time"])}
        for r in rs:
            s0 = r["started_at"].astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)
            hrs = max(1, int(round(r["duration_s"] / 3600)))
            ii = [idx.get((s0 + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M")) for k in range(hrs)]
            ii = [i for i in ii if i is not None]
            if not ii:
                continue
            def vals(k):
                return [j[k][i] for i in ii if j[k][i] is not None]
            f_, w_, g_, p_, s_ = vals("apparent_temperature"), vals("wind_speed_10m"), vals("wind_gusts_10m"), vals("precipitation"), vals("snow_depth")
            out.append({"h": r["duration_s"] / 3600, "month": r["date"].month, "feel": st.mean(f_) if f_ else None, "feel_max": max(f_) if f_ else None,
                        "wind": st.mean(w_) if w_ else None, "gust": max(g_) if g_ else None, "rain": sum(p_) if p_ else 0, "snow_depth": max(s_) if s_ else 0})
        time.sleep(0.2)
    return out


def refresh_weather_auto(db_conn) -> None:
    with _LOCK:
        if _RUNNING["on"]:
            return
        _RUNNING["on"] = True
    try:
        conn = db_conn()
        try:
            c = conn.cursor()
            rides = _weather_rides(c)
            val = weather_auto(rides)
            val["_n"] = len(rides)
            c.execute("INSERT INTO qbot_v2.trainer_auto_cache (key, value, computed_at) VALUES ('weather', %s::jsonb, now()) "
                      "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, computed_at=now()", (json.dumps(val, ensure_ascii=False),))
            conn.commit()
        finally:
            conn.close()
    finally:
        _RUNNING["on"] = False


def weather_auto_cached(c, db_conn, max_age_days: int = 7) -> dict:
    c.execute("SELECT value, computed_at FROM qbot_v2.trainer_auto_cache WHERE key='weather'")
    r = c.fetchone()
    stale = (not r) or (datetime.now(r["computed_at"].tzinfo) - r["computed_at"] > timedelta(days=max_age_days))
    if stale and not _RUNNING["on"]:
        threading.Thread(target=refresh_weather_auto, args=(db_conn,), daemon=True).start()
    out = dict(r["value"]) if r else {}
    out["_computed_at"] = r["computed_at"].isoformat(timespec="seconds") if r else None
    out["_computing"] = bool(_RUNNING["on"] or stale)
    return out
