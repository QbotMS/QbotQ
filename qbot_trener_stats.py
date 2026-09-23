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
    """daily: {date: (km, up_m)} -> serie dni >= min_km pod rzad.
    Punktem odniesienia dla wypraw jest NAJCIEZSZA seria >=3 dni (obciazenie = km + przewyzszenie/10), a nie najdluzsza:
    8 dni krotkich jazd wokol domu to nie wyprawa (blad z 2026-09-23: seria dojazdow/wakacyjnych petli wygrywala z Toskania).
    Najdluzsza seria jest zwracana osobno, tylko informacyjnie."""
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
    R = [{"start": r[0].isoformat(), "end": r[-1].isoformat(), "days": len(r), "km": sum(daily[x][0] for x in r), "up": sum(daily[x][1] for x in r)} for r in runs]
    for x in R:
        x["km_day"], x["up_day"], x["load"] = x["km"] / x["days"], x["up"] / x["days"], x["km"] + x["up"] / 10
    has_geo = any(len(v) >= 4 and v[2] and v[3] for v in daily.values())
    if has_geo:
        ex = expedition_chains(daily)
        chains_out = [{"start": x["start"], "end": x["end"], "days": x["days"], "per_day": x["per_day"]} for x in ex]
        ref = max(ex, key=lambda x: x["load"], default=None)
        longest = max(ex, key=lambda x: (x["days"], x["load"]), default=None)
    else:  # bez GPS: przyblizenie seriami dni (najciezsza >=3 dni)
        chains_out = []
        multi = [x for x in R if x["days"] >= 3]
        ref = max(multi, key=lambda x: x["load"], default=None)
        longest = max(R, key=lambda x: (x["days"], x["load"]), default=None)
    def pack(x):
        return None if not x else {"start": x["start"], "end": x["end"], "days": x["days"], "km": round(x["km"]), "up": round(x["up"]),
                                    "km_day": round(x["km_day"]), "up_day": round(x["up_day"])}
    return {"max_km_day": round(max((v[0] for v in daily.values()), default=0)),
            "max_up_day": round(max((v[1] for v in daily.values()), default=0)),
            "ref": pack(ref), "longest": pack(longest), "chains": chains_out}


def _hav(a: tuple, b: tuple) -> float:
    import math
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    return 2 * 6371 * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2))


def expedition_chains(daily: dict, link_km: float = 15.0, move_km: float = 10.0, max_gap_days: int = 1) -> list[dict]:
    """daily: {date: (km, up, start(lat,lon)|None, end(lat,lon)|None)}.
    WYPRAWA = dni jazdy z punktu do punktu: start dnia <= link_km od konca poprzedniego dnia jazdy I start przesuniety
    >= move_km wzgledem startu poprzedniego dnia. Petle z jednej bazy (Mazury, Sycylia) i jazdy wokol domu NIE sa wyprawa.
    Dozwolony 1 dzien przerwy w trakcie wyprawy (dzien bez jazdy). Zwraca lancuchy >= 2 dni jazdy."""
    ds = [d for d in sorted(daily) if daily[d][2] and daily[d][3]]
    chains, cur = [], []
    for d in ds:
        if cur:
            p = cur[-1]
            gap = (d - p).days - 1
            linked = gap <= max_gap_days and _hav(daily[d][2], daily[p][3]) <= link_km and _hav(daily[d][2], daily[p][2]) >= move_km
            if linked:
                cur.append(d)
                continue
            if len(cur) >= 2:
                chains.append(cur)
        cur = [d] if _hav(daily[d][2], daily[d][3]) >= move_km else []
    if len(cur) >= 2:
        chains.append(cur)
    out = []
    for ch in chains:
        km_ = sum(daily[x][0] for x in ch); up_ = sum(daily[x][1] for x in ch)
        out.append({"start": ch[0].isoformat(), "end": ch[-1].isoformat(), "days": len(ch), "km": round(km_), "up": round(up_),
                    "km_day": round(km_ / len(ch)), "up_day": round(up_ / len(ch)), "load": km_ + up_ / 10,
                    "per_day": [(x.isoformat(), daily[x][0], daily[x][1]) for x in ch]})
    return out


def _lvl(ratios: list[float]) -> str:
    r = [x for x in ratios if x is not None]
    if not r:
        return "n"
    if min(r) >= 0.9:  # w granicach 10% = w praktyce to samo (dzien do dnia rozni sie bardziej)
        return "g"
    if min(r) < 0.5:
        return "r"
    return "y"


def _pl_date(iso_: str) -> str:
    y, m, d = iso_.split("-")
    return f"{d}.{m}.{y}"


def best_window(chains: list, n: int, need_km: float | None, need_up: float | None) -> dict | None:
    """Najlepsze okno min(n, dlugosc wyprawy) kolejnych dni jazdy na wyprawach: najpierw jak najdluzsze (do n),
    potem najlepsze wzgledem wymagan celu (min z km/dzien i m/dzien wzgledem potrzeb)."""
    best = None
    for ch in chains:
        pdays = ch["per_day"]
        w = min(n, len(pdays))
        for i in range(0, len(pdays) - w + 1):
            win = pdays[i:i + w]
            kd = sum(x[1] for x in win) / w
            ud = sum(x[2] for x in win) / w
            ratios = [r for r in ((kd / need_km) if need_km else None, (ud / need_up) if need_up else None) if r is not None]
            score = min(ratios) if ratios else kd + ud / 10
            key = (w, score)
            if best is None or key > best["key"]:
                best = {"key": key, "days": w, "km_day": round(kd), "up_day": round(ud), "start": win[0][0], "end": win[-1][0]}
    return best


def status_trip(g: dict, hist: dict, ctl_now: float | None, ctl_max: float | None) -> dict:
    t = g.get("target") or {}
    one_day = g.get("kind") == "long_ride"
    days = 1 if one_day else (t.get("days") or (((E._d(g.get("date_to")) - E._d(g.get("date_from"))).days + 1) if g.get("date_from") and g.get("date_to") else None))
    ref, lon = hist.get("ref"), hist.get("longest")
    rows, ratios = [], []
    need_km = (t["km"] / days) if (t.get("km") and days) else None
    need_up = (t["up_m"] / days) if (t.get("up_m") and days) else None
    win = None if one_day else best_window(hist.get("chains") or [], int(days or 1), need_km, need_up)
    if win:
        wtxt = f"najlepsze {win['days']} dni pod rząd na wyprawie: {_pl_date(win['start'])}–{_pl_date(win['end'])}"
    elif ref:  # bez danych dziennych (brak GPS) - cala najciezsza seria
        win = {"days": ref["days"], "km_day": ref["km_day"], "up_day": ref["up_day"]}
        wtxt = f"najcięższa seria: {_pl_date(ref['start'])}–{_pl_date(ref['end'])}"
    else:
        wtxt = "brak wyprawy (jazdy z punktu do punktu) w danych"
    if need_km:
        have = hist["max_km_day"] if one_day else (win["km_day"] if win else hist["max_km_day"])
        rows.append({"k": "dystans" if one_day else "km na dzień", "have": have, "need": round(need_km),
                     "note": "Twój rekord dnia" if one_day else f"{wtxt}; rekord dnia {hist['max_km_day']} km"})
        ratios.append(have / need_km)
    if need_up:
        have = hist["max_up_day"] if one_day else (win["up_day"] if win else hist["max_up_day"])
        rows.append({"k": "przewyższenie" if one_day else "przewyższenie na dzień", "have": have, "need": round(need_up),
                     "note": "Twój rekord dnia" if one_day else f"{wtxt}; rekord dnia {hist['max_up_day']} m"})
        ratios.append(have / need_up)
    if days and days > 1:
        have = (lon["days"] if lon else 0) if hist.get("chains") else (ref["days"] if ref else 0)
        rows.append({"k": "dni pod rząd", "have": have, "need": days,
                     "note": (f"najdłuższa wyprawa: {_pl_date(lon['start'])}–{_pl_date(lon['end'])}, {lon['km']} km, {lon['up']} m" if lon else wtxt)})
        ratios.append(have / days)
    if ctl_now is not None:
        rows.append({"k": "forma (CTL)", "have": round(ctl_now), "need": None, "note": f"rekord z 18 mies.: {round(ctl_max) if ctl_max else '—'}"})
    lvl = _lvl(ratios)
    txt = {"g": "robiłeś już taki wysiłek — gotowy", "y": "wykonalne — są luki", "r": "duża luka", "n": "uzupełnij km / przewyższenie / dni"}[lvl]
    scored = [r for r in rows if r.get("need") and isinstance(r.get("have"), (int, float))]
    weak = min(scored, key=lambda r: r["have"] / r["need"], default=None)
    if lvl in ("y", "r") and weak and weak["have"] / weak["need"] < 1:
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


_DAILY_CACHE: dict = {}


def _daily_km_up(c, since: date) -> dict:
    """{date: (km, up, start(lat,lon), end(lat,lon))} dla jazd rowerowych od 'since'. Cache 10 min (podglad celu liczy sie przy kazdej zmianie pola)."""
    hit = _DAILY_CACHE.get(since)
    if hit and hit[0] > time.time() - 600:
        return hit[1]
    res = _daily_km_up_db(c, since)
    _DAILY_CACHE.clear(); _DAILY_CACHE[since] = (time.time(), res)
    return res


def _daily_km_up_db(c, since: date) -> dict:
    c.execute("""WITH s AS (SELECT external_id, date, started_at, distance_m, elevation_m FROM qbot_v2.training_sessions
                 WHERE sport_type IN ('cycling','gravel_cycling') AND date >= %s),
      f AS (SELECT DISTINCT ON (r.external_id) r.external_id, r.lat, r.lon FROM qbot_v2.activity_record r JOIN s USING (external_id)
            WHERE r.lat IS NOT NULL ORDER BY r.external_id, r.sec),
      l AS (SELECT DISTINCT ON (r.external_id) r.external_id, r.lat, r.lon FROM qbot_v2.activity_record r JOIN s USING (external_id)
            WHERE r.lat IS NOT NULL ORDER BY r.external_id, r.sec DESC)
      SELECT s.date, s.started_at, s.distance_m, s.elevation_m, f.lat AS fa, f.lon AS fo, l.lat AS la, l.lon AS lo
      FROM s LEFT JOIN f USING (external_id) LEFT JOIN l USING (external_id) ORDER BY s.date, s.started_at NULLS LAST""", (since,))
    out: dict = {}
    for r in c.fetchall():
        km_, up_, st_, en_ = out.get(r["date"], (0.0, 0.0, None, None))
        km_ += float(r["distance_m"] or 0) / 1000; up_ += float(r["elevation_m"] or 0)
        if r["fa"] is not None:
            if st_ is None:
                st_ = (float(r["fa"]), float(r["fo"]))
            en_ = (float(r["la"]), float(r["lo"]))
        out[r["date"]] = (km_, up_, st_, en_)
    return out


_PROFILE: dict = {}


def month_profile(c, sport: str = "rower") -> list[float]:
    """Udzial km (rower) albo godzin (inne) w miesiacach I..XII z ostatnich 2 lat - Twoj rytm roku. Cache 1 h."""
    hit = _PROFILE.get(sport)
    if hit and hit[0] > time.time() - 3600:
        return hit[1]
    c.execute("SELECT EXTRACT(MONTH FROM date)::int AS m, sport_type, COALESCE(distance_m,0) AS d, COALESCE(duration_s,0) AS s "
              "FROM qbot_v2.training_sessions WHERE date >= CURRENT_DATE - 730")
    tot = [0.0] * 12
    for r in c.fetchall():
        if E.SPORT_OF.get(r["sport_type"]) == sport:
            tot[r["m"] - 1] += float(r["d"]) if sport == "rower" else float(r["s"])
    sm = sum(tot)
    prof = [x / sm for x in tot] if sm else [1 / 12] * 12
    _PROFILE[sport] = (time.time(), prof)
    return prof


def volume_plan(a_: date, b_: date, total: float, prof: list[float]) -> list[dict]:
    """Rozklad celu objetosci na miesiace okresu wg profilu roku (czesciowe miesiace proporcjonalnie do dni)."""
    import calendar
    months, d = [], date(a_.year, a_.month, 1)
    while d <= b_:
        dim = calendar.monthrange(d.year, d.month)[1]
        m0, m1 = max(a_, d), min(b_, date(d.year, d.month, dim))
        frac = ((m1 - m0).days + 1) / dim
        months.append([d, prof[d.month - 1] * frac])
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    w = sum(x[1] for x in months) or 1
    return [{"month": m.strftime("%Y-%m"), "value": round(total * v / w)} for m, v in months]


def plan_expected(plan: list[dict], today: date) -> float:
    import calendar
    exp = 0.0
    for p in plan:
        y, m = map(int, p["month"].split("-"))
        dim = calendar.monthrange(y, m)[1]
        if (y, m) < (today.year, today.month):
            exp += p["value"]
        elif (y, m) == (today.year, today.month):
            exp += p["value"] * today.day / dim
    return exp


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
    MN_PL = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
    ovs = {}
    try:
        uname = next((g.get("username") for g in goals if g.get("username")), None)
        if uname:
            c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username=%s", (uname,))
            r_ = c.fetchone(); ovs = dict(r_["overrides"]) if r_ else {}
    except Exception:
        ovs = {}
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
                key, unit = (("km", "km") if t.get("km") else (("h", "h") if t.get("h") else (("sessions", "sesji") if t.get("sessions") else (None, ""))))
                if not key:
                    s = {"level": "n", "text": "podaj km, godziny albo liczbę sesji", "rows": []}
                else:
                    prof = month_profile(c, "rower" if key == "km" else sp)
                    plan = volume_plan(a_, b_, float(t[key]), prof)
                    c.execute("SELECT sport_type, COALESCE(distance_m,0) AS m, COALESCE(duration_s,0) AS s FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (a_, min(b_, today)))
                    rows_ = [r for r in c.fetchall() if E.SPORT_OF.get(r["sport_type"]) == sp]
                    have = (sum(float(r["m"]) for r in rows_) / 1000) if key == "km" else ((sum(float(r["s"]) for r in rows_) / 3600) if key == "h" else len(rows_))
                    exp = plan_expected(plan, today)
                    ptxt = " · ".join(f"{MN_PL[int(p['month'][5:]) - 1]} {p['value']}" for p in plan)
                    if today < a_:
                        W = E.season_weeks(goals, ovs, E.monday(today), 1)
                        s = {"level": "n", "text": f"start {a_.strftime('%d.%m.%Y')} (za {(a_ - today).days} dni) · teraz: {E.PH_NAME.get(W[0]['ph'], '')} sezonu {W[0]['season']}",
                             "rows": [{"k": "pierwszy miesiąc", "have": None, "need": plan[0]["value"] if plan else None, "note": f"plan {unit} na miesiące wg Twojego rytmu roku: {ptxt}"}]}
                    else:
                        ratio = have / exp if exp else None
                        lvl = "n" if ratio is None else ("g" if ratio >= 0.95 else ("y" if ratio >= 0.8 else "r"))
                        s = {"level": lvl, "text": {"g": "zgodnie z planem", "y": "lekko w tyle", "r": "wyraźnie w tyle", "n": "za wcześnie na ocenę"}[lvl],
                             "rows": [{"k": unit, "have": round(have), "need": round(float(t[key])), "note": f"wg planu miesięcznego na dziś ~{round(exp)} {unit}"},
                                      {"k": "plan na miesiące", "have": None, "need": None, "note": ptxt}],
                             "progress": round(have / float(t[key]), 3)}
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
