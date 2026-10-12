#!/usr/bin/env python3
"""Cel kcal dnia, dokladka do Brokula pod trening, plan weekendu, przypomnienie 21:30 (2026-10-12). Dok.: docs/BROKUL.md

Model spalania (z historii Michala, 90 dni, liczony raz dziennie):
  dzien bez treningu = mediana energy_daily w dni bez treningu (~2470 kcal),
  trening = mediana nadwyzki spalania na godzine treningu (~490 kcal/h) x czas x wspolczynnik sportu.
  Dzien miniony -> realne energy_daily.
Cel dnia = spalanie - kalibracja (rozbieznosc waga vs wpisy, gdy gotowa; max +-500) + cel bilansu z Trenera (aktywny etap).
Dolna granica 1800 kcal. Dokladka = cel - kcal Brokula tego dnia (0, gdy Brokul wystarcza).
Paliwo na rower: trening >= 75 min -> ok. 50 g wegli/h po pierwszych 45 min (tu jest miejsce na slodkie).
"""
from __future__ import annotations

import json
import statistics as st
import time
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
SPORT_F = {"rower": 1.0, "wiosl": 0.9, "sila": 0.6, "joga": 0.3}
FLOOR_KCAL = 1800
CALIB_MAX = 500
FUEL_MIN = 75
FUEL_G_H = 50
PROTEIN_G = 150
_MODEL: dict = {}


def _conn():
    from qbot_brokul_meals import _conn as c
    return c()


def _fmt(v) -> str:
    return "%.0f" % v if v is not None else "?"


def _hm(t: dtime | None) -> str:
    return t.strftime("%H:%M") if t else "?"


# ======================================================================= model spalania
def model(c) -> dict:
    key = date.today().isoformat()
    if _MODEL.get("key") == key:
        return _MODEL["v"]
    rows = c.execute(
        "WITH t AS (SELECT date, sum(duration_s)/3600.0 h FROM qbot_v2.training_sessions WHERE date >= current_date-90 GROUP BY date), "
        "e AS (SELECT date, COALESCE(total_kcal_eff,total_kcal) tot FROM qbot_v2.energy_daily WHERE date >= current_date-90 "
        "AND date < current_date AND quality_status<>'partial') SELECT e.date, e.tot, COALESCE(t.h,0) h FROM e LEFT JOIN t USING (date)").fetchall()
    rest = [float(r["tot"]) for r in rows if r["h"] < 0.25 and r["tot"]]
    base = st.median(rest) if len(rest) >= 7 else 2450.0
    per_h = [(float(r["tot"]) - base) / float(r["h"]) for r in rows if r["h"] > 0.5 and r["tot"]]
    v = {"base": round(base), "per_h": round(st.median(per_h)) if len(per_h) >= 7 else 480, "n_rest": len(rest), "n_ride": len(per_h)}
    _MODEL.update(key=key, v=v)
    return v


def sessions(c, day: date) -> list[dict]:
    return c.execute("SELECT sport, name, start_time, dur_min, status FROM qbot_v2.trainer_session WHERE day=%s "
                     "AND status IN ('plan','done') AND username NOT LIKE '\\_%%' ORDER BY start_time NULLS LAST, id",
                     (day,)).fetchall()


def expend(c, day: date) -> dict:
    """Przewidywane (albo realne) spalanie dnia."""
    if day < date.today():
        r = c.execute("SELECT COALESCE(total_kcal_eff,total_kcal) e FROM qbot_v2.energy_daily WHERE date=%s AND quality_status<>'partial'",
                      (day,)).fetchone()
        if r and r["e"]:
            return {"kcal": float(r["e"]), "src": "realne"}
    m = model(c)
    ses = sessions(c, day)
    act = c.execute("SELECT COALESCE(sum(duration_s),0)/3600.0 h FROM qbot_v2.training_sessions WHERE date=%s", (day,)).fetchone()["h"]
    plan_h = sum((s["dur_min"] or 0) / 60 * SPORT_F.get(s["sport"], 0.8) for s in ses if s["status"] == "plan")
    h = float(act) + plan_h
    return {"kcal": m["base"] + m["per_h"] * h, "src": "prognoza", "train_h": round(h, 2)}


def calibration(c) -> int:
    try:
        import qbot_food_streaks as S
        d = S.discrepancy()
        if d.get("ready"):
            return int(max(-CALIB_MAX, min(CALIB_MAX, d["disc"])))
    except Exception:
        pass
    return 0


def target_balance(c) -> int:
    import qbot_trener_stats as ST
    goals = [dict(g) for g in c.execute("SELECT * FROM qbot_v2.trainer_goal WHERE status='active' AND username NOT LIKE '\\_%%'").fetchall()]
    r = c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username NOT LIKE '\\_%%' LIMIT 1").fetchone()
    return int(ST.compute_balance(c.cursor(), dict(r["overrides"]) if r else {}, goals)["target_balance_kcal"])  # trener_stats chce kursora


def brokul_kcal(c, day: date) -> float | None:
    r = c.execute("SELECT sum(kcal) k, count(*) n FROM qbot_v2.brokul_meals WHERE day=%s AND status<>'cancelled'", (day,)).fetchone()
    return float(r["k"]) if r and r["n"] else None


def day_plan(day: date, c=None) -> dict:
    own = c is None
    c = c or _conn()
    try:
        ex = expend(c, day)
        cal = calibration(c)
        bal = target_balance(c)
        tgt = max(FLOOR_KCAL, round((ex["kcal"] - cal + bal) / 50) * 50)
        bk = brokul_kcal(c, day)
        extra = max(0, tgt - bk) if bk else None
        ses = sessions(c, day)
        fuel_g = 0
        for s in ses:
            if s["sport"] == "rower" and (s["dur_min"] or 0) >= FUEL_MIN:
                fuel_g += int(round(((s["dur_min"] - 45) / 60 * FUEL_G_H) / 10) * 10)
        onbike = min(extra if extra is not None else tgt, fuel_g * 4) if fuel_g else 0
        return {"day": day, "target": tgt, "expend": round(ex["kcal"]), "expend_src": ex["src"], "calib": cal, "balance": bal,
                "brokul": bk, "extra": extra, "fuel_g": fuel_g, "onbike_kcal": onbike,
                "post_kcal": max(0, (extra or 0) - onbike), "sessions": [dict(s) for s in ses]}
    finally:
        if own:
            c.close()


def _meal_times(p: dict) -> str | None:
    """Pory posilkow Brokula pod pierwszy trening z godzina, z oknem 10-20.
    Trening przed 10:00 i < 90 min -> na czczo (czarna kawa); >= 90 min -> dzien zwolniony, cos lekkiego przed jazda."""
    s = next((x for x in p["sessions"] if x.get("start_time") and x["sport"] in ("rower", "wiosl", "sila")), None)
    if not s or not p["brokul"]:
        return None
    d = p["day"]
    st_ = datetime.combine(d, s["start_time"])
    dur = s["dur_min"] or 60
    end = st_ + timedelta(minutes=dur)
    w0, w1 = datetime.combine(d, dtime(10, 0)), datetime.combine(d, dtime(19, 45))
    long_ = dur >= 90
    post = end + timedelta(minutes=30)
    if not long_:
        post = min(max(post, w0), w1)
    if st_ < w0 and not long_:
        return "trening przed 10:00 – na czczo (czarna kawa); Potreningowy ok. %s" % post.strftime("%H:%M")
    pre = st_ - timedelta(minutes=150)
    if long_ and pre < w0:
        return ("przed jazdą coś lekkiego ok. %s (dzień zwolniony z okna – trening ≥1,5 h); Potreningowy ok. %s"
                % ((st_ - timedelta(minutes=60)).strftime("%H:%M"), post.strftime("%H:%M")))
    pre = max(pre, w0)
    txt = "Przedtreningowy ok. %s, Potreningowy ok. %s" % (pre.strftime("%H:%M"), post.strftime("%H:%M"))
    if st_ - pre < timedelta(minutes=75):
        txt += " (mało czasu przed treningiem – Przedtreningowy lżej)"
    if end > w1 and long_:
        txt += " (koniec po 20:00 – dzień zwolniony z okna)"
    elif end > w1:
        txt += " (koniec blisko 20:00 – Potreningowy zjedz zaraz po)"
    return txt


SMALL_EXTRA = 150


def morning_text(day: date) -> str | None:
    """Blok do porannej wiadomosci Trenera (dni z treningiem)."""
    p = day_plan(day)
    if not p["sessions"]:
        return None
    L = ["🍽 Jedzenie: cel ~%s kcal (spalisz ~%s, bilans %+d%s)." % (_fmt(p["target"]), _fmt(p["expend"]), p["balance"],
                                                                   (", korekta %+d" % -p["calib"]) if p["calib"] else "")]
    if p["brokul"]:
        L.append("Brokuł %s + dokładka ~%s kcal:" % (_fmt(p["brokul"]), _fmt(p["extra"])) if (p["extra"] or 0) >= SMALL_EXTRA else
                 "Brokuł %s kcal wystarczy – bez dokładki." % _fmt(p["brokul"]))
    else:
        L.append("Bez diety – celuj w ~%s kcal." % _fmt(p["target"]))
    if p["fuel_g"]:
        L.append("• na rower: ~%d g węgli (~%s kcal) – batony, żele, żelki; tu jest miejsce na słodkie 🍬" % (p["fuel_g"], _fmt(p["onbike_kcal"])))
    if p["post_kcal"] >= SMALL_EXTRA:
        L.append("• po treningu: ~%s kcal – białko + węgle (np. skyr z owocami, kanapka, makaron)" % _fmt(p["post_kcal"]))
    mt = _meal_times(p)
    if mt:
        L.append("• " + mt)
    return "\n".join(L)


def evening_line(day: date) -> str:
    """Linia do wiadomosci dnia (20:00): cel vs zjedzone."""
    import qbot_food_log as F
    p = day_plan(day)
    eaten = F.day_totals(day)["kcal"] or 0
    left = p["target"] - eaten
    tail = ("zostało ~%s" % _fmt(left)) if left > 0 else ("ponad cel o ~%s" % _fmt(-left))
    return "🎯 Cel dnia ~%s kcal · zjedzone %s · %s" % (_fmt(p["target"]), _fmt(eaten), tail)


# ======================================================================= weekend (piatek rano)
_WK_PROMPT = """Jesteś dietetykiem sportowym. Użytkownik (mężczyzna ~104 kg, redukcja, kolarz gravel) w weekend NIE ma cateringu:
je głównie na mieście, czasem gotuje proste rzeczy w domu. Dostajesz plan dni (cel kcal, trening, wydarzenia).
Zwróć WYŁĄCZNIE JSON: {"days": [{"day": "sb", "zamawiaj": "...", "unikaj": "...", "rower": "..."}], "zakupy": ["..."]}
- "zamawiaj": 1-2 zdania, konkretne typy dań na mieście pasujące do celu dnia (białko, porcja), po polsku, prosto.
- "unikaj": krótko, co rozwala cel (np. podwójne frytki, słodkie napoje).
- "rower": tylko gdy jest trening >= 75 min: co zabrać i zjeść na rowerze (zmieść podaną ilość węgli), inaczej "".
- "zakupy": 6-10 prostych produktów do domu i na rower (bez gotowania lub proste gotowanie), konkretnie.
Liczby kcal i węgli są ustalone – nie zmieniaj ich, nie pisz własnych wyliczeń."""


def weekend_text(friday: date) -> str | None:
    days = [friday + timedelta(days=1), friday + timedelta(days=2)]
    plans = []
    with _conn() as c:
        for d in days:
            p = day_plan(d, c)
            ev = [r["title"] for r in c.execute(
                "SELECT title FROM qbot_v2.calendar_entry WHERE kind='event' AND %s BETWEEN day AND COALESCE(end_day, day)", (d,)).fetchall() if r["title"]]
            plans.append({"day": ["pn", "wt", "śr", "cz", "pt", "sb", "nd"][d.weekday()], "date": d.strftime("%d.%m"), "cel_kcal": p["target"],
                          "bialko_g": PROTEIN_G, "brokul": bool(p["brokul"]), "wegle_na_rower_g": p["fuel_g"],
                          "treningi": ["%s %s %d min%s" % (s["sport"], s["name"], s["dur_min"] or 0,
                                                            (" start " + _hm(s["start_time"])) if s.get("start_time") else "") for s in p["sessions"]],
                          "wydarzenia": ev})
    import qbot_food_log as F
    try:
        j = F._ai_json(_WK_PROMPT, [{"type": "text", "text": json.dumps(plans, ensure_ascii=False)}])
    except Exception:
        j = {}
    L = ["🗓 Weekend %s–%s: plan jedzenia" % (plans[0]["date"], plans[1]["date"]), ""]
    by = {x.get("day"): x for x in (j.get("days") or [])}
    for p in plans:
        a = by.get(p["day"]) or {}
        head = "%s %s · cel ~%s kcal · białko ~%d g" % (p["day"], p["date"], _fmt(p["cel_kcal"]), PROTEIN_G)
        if p["brokul"]:
            head += " · jest Brokuł"
        L.append(head)
        if p["treningi"]:
            L.append("  🚲 " + "; ".join(p["treningi"]))
        if p["wegle_na_rower_g"]:
            L.append("  🍬 na rower ~%d g węgli%s" % (p["wegle_na_rower_g"], (": " + a["rower"]) if a.get("rower") else ""))
        if a.get("zamawiaj"):
            L.append("  🍽 " + a["zamawiaj"])
        if a.get("unikaj"):
            L.append("  ✋ " + a["unikaj"])
        L.append("")
    if j.get("zakupy"):
        L.append("🛒 Do domu i na rower: " + ", ".join(str(x) for x in j["zakupy"][:10]))
    L.append("Okno 10–20 obowiązuje, chyba że trening ≥1,5 h.")
    return "\n".join(L)


# ======================================================================= tick (wolane z qbot_brokul_meals.tick)
def tick(now: datetime) -> list[str]:
    import qbot_brokul as B
    import qbot_food_log as F
    log = []
    st_ = B.state()
    # piatek 7:00-9:59: plan weekendu (raz)
    if now.weekday() == 4 and 7 <= now.hour < 10:
        key = "weekend_%s" % now.date().isoformat()
        if not st_.get(key):
            txt = weekend_text(now.date())
            if txt and F.tg_send(txt):
                B._state_update(**{key: time.strftime("%Y-%m-%d %H:%M:%S")})
                log.append("plan weekendu wyslany")
    # 21:30-21:59: dzien jeszcze otwarty -> jedno przypomnienie
    if now.hour == 21 and now.minute >= 30:
        key = "open_%s" % now.date().isoformat()
        if not st_.get(key):
            cs = F.close_state(now.date())
            if not cs["closed"]:
                import qbot_food_streaks as S
                n = S.streaks(now)["food"]["n"]
                F.tg_send("⏳ Dzień %s jeszcze otwarty%s. Zamknij go w wiadomości dnia (albo jutro do 12:00)."
                          % (now.strftime("%d.%m"), (" – 🔥 pas %d dni" % n) if n else ""))
                log.append("przypomnienie 21:30")
            B._state_update(**{key: time.strftime("%Y-%m-%d %H:%M:%S")})
    return log
