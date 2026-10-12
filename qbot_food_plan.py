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
SHRINK_N = 2   # symboliczne sciaganie mediany dnia tygodnia do sredniej
HIST_DAYS = 365
BMR_DAYS = 14


def model(c) -> dict:
    """Spalanie dnia = SPOCZYNEK + RUCH CODZIENNY + TRENING (2026-10-12, uwaga Michala: nie mieszac aktywnych i spoczynkowych):
    - spoczynek = BMR Garmina (resting_kcal), mediana z ostatnich 14 pelnych dni -> spada razem z waga,
    - ruch codzienny = aktywne kcal Garmina - kcal treningow (dzien z treningiem: tylko gdy kazda sesja ma kcal),
      mediana WG DNIA TYGODNIA z calej historii (do 365 dni), symbolicznie sciagana do sredniej,
    - trening = mediana (calosc - spoczynek - ruch dnia tygodnia) / godzine treningu (90 dni)."""
    key = date.today().isoformat()
    if _MODEL.get("key") == key:
        return _MODEL["v"]
    rows = c.execute(
        "WITH t AS (SELECT date, sum(duration_s)/3600.0 h, sum(calories) cal, count(calories) n_cal, count(*) n "
        "FROM qbot_v2.training_sessions WHERE date >= current_date - %s GROUP BY date), "
        "e AS (SELECT date, COALESCE(total_kcal_eff,total_kcal) tot, resting_kcal rest, active_kcal act FROM qbot_v2.energy_daily "
        "WHERE date >= current_date - %s AND date < current_date AND quality_status<>'partial') "
        "SELECT e.date, e.tot, e.rest, e.act, COALESCE(t.h,0) h, t.cal, t.n_cal, t.n FROM e LEFT JOIN t USING (date) ORDER BY e.date",
        (HIST_DAYS, HIST_DAYS)).fetchall()
    rests = [float(r["rest"]) for r in rows if r["rest"]][-BMR_DAYS:]
    bmr = st.median(rests) if rests else 2300.0
    neat = []
    for r in rows:
        if r["act"] is None:
            continue
        if r["h"] < 0.25:
            neat.append((r["date"], float(r["act"])))
        elif r["n"] and r["n_cal"] == r["n"] and r["cal"] and float(r["cal"]) > 0:
            neat.append((r["date"], max(0.0, float(r["act"]) - float(r["cal"]))))
    nm = st.median([v for _, v in neat]) if len(neat) >= 7 else 150.0
    by_wd = {}
    for d, v in neat:
        by_wd.setdefault(d.weekday(), []).append(v)
    neat_wd = {}
    for wd in range(7):
        xs = by_wd.get(wd, [])
        neat_wd[wd] = round((len(xs) * st.median(xs) + SHRINK_N * nm) / (len(xs) + SHRINK_N)) if xs else round(nm)
    base_wd = {wd: round(bmr + neat_wd[wd]) for wd in range(7)}
    recent = [r for r in rows if r["date"] >= date.today() - timedelta(days=90)]
    per_h = [(float(r["tot"]) - float(r["rest"] or bmr) - neat_wd[r["date"].weekday()]) / float(r["h"])
             for r in recent if r["h"] > 0.5 and r["tot"]]
    v = {"bmr": round(bmr), "neat_wd": neat_wd, "base": round(bmr + nm), "base_wd": base_wd,
         "n_wd": {k: len(x) for k, x in sorted(by_wd.items())}, "per_h": round(st.median(per_h)) if len(per_h) >= 7 else 480,
         "n_days": len(neat), "n_ride": len(per_h), "since": min((d for d, _ in neat), default=None)}
    _MODEL.update(key=key, v=v)
    return v


def sessions(c, day: date) -> list[dict]:
    return c.execute("SELECT sport, name, start_time, dur_min, status FROM qbot_v2.trainer_session WHERE day=%s "
                     "AND status IN ('plan','done') AND username NOT LIKE '\\_%%' ORDER BY start_time NULLS LAST, id",
                     (day,)).fetchall()


def expend(c, day: date) -> dict:
    """Spalanie dnia: miniony = realne energy_daily; dzisiaj = Garmin do teraz + reszta dnia; przyszly = model dnia tygodnia."""
    if day < date.today():
        r = c.execute("SELECT COALESCE(total_kcal_eff,total_kcal) e FROM qbot_v2.energy_daily WHERE date=%s AND quality_status<>'partial'",
                      (day,)).fetchone()
        if r and r["e"]:
            return {"kcal": float(r["e"]), "src": "realne"}
    m = model(c)
    base = m["base_wd"].get(day.weekday(), m["base"])
    ses = sessions(c, day)
    plan_h = sum((s["dur_min"] or 0) / 60 * SPORT_F.get(s["sport"], 0.8) for s in ses if s["status"] == "plan")
    if day == date.today():
        g = c.execute("SELECT COALESCE(total_kcal_eff,total_kcal) e, updated_at FROM qbot_v2.energy_daily WHERE date=%s", (day,)).fetchone()
        if g and g["e"] and g["updated_at"]:
            up = g["updated_at"].astimezone(TZ)
            frac = min(1.0, max(0.0, (up.hour * 60 + up.minute) / 1440)) if up.date() == day else (1.0 if up.date() > day else 0.0)
            rest = base * (1 - frac) + m["per_h"] * plan_h
            return {"kcal": float(g["e"]) + rest, "src": "prognoza", "so_far": round(float(g["e"])),
                    "so_far_at": up.strftime("%H:%M"), "train_h": round(plan_h, 2),
                    "parts": {"bmr": m["bmr"], "neat": m["neat_wd"].get(day.weekday()), "train": round(m["per_h"] * plan_h)}}
    act = c.execute("SELECT COALESCE(sum(duration_s),0)/3600.0 h FROM qbot_v2.training_sessions WHERE date=%s", (day,)).fetchone()["h"]
    h = float(act) + plan_h
    return {"kcal": base + m["per_h"] * h, "src": "prognoza", "train_h": round(h, 2),
            "parts": {"bmr": m["bmr"], "neat": m["neat_wd"].get(day.weekday()), "train": round(m["per_h"] * h)}}


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


LIGHT_DEF = 300          # dzien lekki: deficyt (Brokul + przekaska ~200 kcal)
TRAIN_DEF_MIN, TRAIN_DEF_MAX = 300, 900
TRAIN_MIN = 45           # rower/wioslarz >= 45 min = dzien z jazda
_WEEK: dict = {}


def _train_kcal(c, d: date, m: dict) -> tuple[float, float]:
    ses = sessions(c, d)
    mins = sum((s["dur_min"] or 0) for s in ses if s["sport"] in ("rower", "wiosl"))
    kc = sum((s["dur_min"] or 0) / 60 * SPORT_F.get(s["sport"], 0.8) for s in ses) * m["per_h"]
    return mins, kc


def week_deficits(ws: date, actuals: bool) -> dict:
    """Deficyt kazdego dnia tygodnia pn-nd (kcal, dodatni). actuals=True: zamkniete dni minione licza sie realnie."""
    key = (ws, date.today(), actuals)
    hit = _WEEK.get(key)
    if hit and hit[0] > time.time() - 120:
        return hit[1]
    today = date.today()
    out, flex, fixed = {}, {}, 0.0
    with _conn() as c:
        m = model(c)
        weekly = -target_balance(c) * 7
        for i in range(7):
            d = ws + timedelta(days=i)
            mins, kc = _train_kcal(c, d, m)
            if actuals and d < today:
                cl = c.execute("SELECT closed_at FROM qbot_v2.food_day WHERE day=%s", (d,)).fetchone()
                ex = expend(c, d)
                if cl and cl["closed_at"] and ex["src"] == "realne":
                    r = c.execute("SELECT sum(i.kcal) k FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id "
                                  "WHERE l.date=%s", (d,)).fetchone()
                    if r and r["k"]:
                        out[d] = round(ex["kcal"] - float(r["k"]))
                        fixed += out[d]
                        continue
            if mins >= TRAIN_MIN:
                flex[d] = max(1.0, kc)
            else:
                out[d] = LIGHT_DEF
                fixed += LIGHT_DEF
    rem = weekly - fixed
    tot = sum(flex.values())
    for d, w in flex.items():
        out[d] = int(round(max(TRAIN_DEF_MIN, min(TRAIN_DEF_MAX, rem * w / tot)))) if tot else TRAIN_DEF_MIN
    _WEEK[key] = (time.time(), out)
    return out


def day_deficit(day: date) -> int:
    ws = day - timedelta(days=day.weekday())
    return int(week_deficits(ws, actuals=day >= date.today()).get(day, LIGHT_DEF))


def target_for(ex: dict, cal: float, bal: float, day: date | None = None) -> int:
    """Cel jedzenia dnia. Z 'day': plan bilansu = -deficyt dnia z budzetu tygodniowego (day_deficit), inaczej stale 'bal'.
    Dzien miniony (realne spalanie): bez zaokraglen; prognoza: zaokraglenie do 50 kcal."""
    if day is not None:
        bal = -day_deficit(day)
    v = ex["kcal"] - cal + bal
    return int(max(FLOOR_KCAL, round(v) if ex.get("src") == "realne" else round(v / 50) * 50))


def day_plan(day: date, c=None) -> dict:
    own = c is None
    c = c or _conn()
    try:
        ex = expend(c, day)
        cal = calibration(c)
        bal = -day_deficit(day)          # 2026-10-12: budzet tygodniowy (dzien lekki -300, jazda: reszta tygodnia, maks. -900)
        tgt = target_for(ex, cal, bal)
        bk = brokul_kcal(c, day)
        extra = max(0, tgt - bk) if bk else None
        ses = sessions(c, day)
        fuel_g = 0
        for s in ses:
            if s["sport"] == "rower" and (s["dur_min"] or 0) >= FUEL_MIN:
                fuel_g += int(round(((s["dur_min"] - 45) / 60 * FUEL_G_H) / 10) * 10)
        onbike = min(extra if extra is not None else tgt, fuel_g * 4) if fuel_g else 0
        mins, _ = _train_kcal(c, day, model(c))
        return {"day": day, "target": tgt, "expend": round(ex["kcal"]), "expend_src": ex["src"], "calib": cal, "balance": bal,
                "train_day": mins >= TRAIN_MIN,
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
    if day < date.today() and p["expend_src"] == "realne":  # dzien miniony: jezyk bilansu (zjedzone - spalone) vs plan
        bal = eaten - p["expend"]
        d = bal - (p["balance"] - p["calib"])
        tail = ("%s ponad plan" % _fmt(d)) if d > 150 else (("deficyt za mocny o %s ⚠️" % _fmt(-d)) if d < -300 else "w planie")
        return "🎯 bilans %+d kcal (plan %+d) · %s" % (round(bal), p["balance"] - p["calib"], tail)
    tail = ("zostało ~%s" % _fmt(left)) if left > 0 else ("ponad cel o ~%s" % _fmt(-left))
    return "🎯 %s/%s kcal · %s" % (_fmt(eaten), _fmt(p["target"]), tail)


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


# ======================================================================= normy skladnikow + rekomendacja poranna
# Wegle NIE maja osobnej normy: wypelniaja kcal po bialku i minimum tluszczu (spojne z deficytem).
PROTEIN_TARGET = 160          # g (1,8 g/kg wagi docelowej 90 kg)
FAT_MIN = 70                  # g
SUGAR_MAX_PCT = 0.10          # cukry maks. 10% energii (WHO)
SAT_MAX_PCT = 0.10            # tluszcze nasycone maks. 10% energii
SALT_MAX = 5.0                # g (WHO)


def norms(target_kcal: float) -> dict:
    carbs = max(0, (target_kcal - PROTEIN_TARGET * 4 - FAT_MIN * 9) / 4)
    return {"kcal": target_kcal, "protein_g": PROTEIN_TARGET, "fat_min_g": FAT_MIN, "carbs_g": round(carbs),
            "sugars_max_g": round(target_kcal * SUGAR_MAX_PCT / 4), "sat_max_g": round(target_kcal * SAT_MAX_PCT / 9),
            "salt_max_g": SALT_MAX}


def brokul_nutrients(c, day: date) -> dict | None:
    r = c.execute("SELECT count(*) n, sum(kcal) kcal, sum(protein_g) p, sum(carbs_g) cb, sum(fat_g) f, sum(sugars_g) su, "
                  "sum(sat_fat_g) sa, sum(salt_g) sl FROM qbot_v2.brokul_meals WHERE day=%s AND status<>'cancelled'", (day,)).fetchone()
    if not r or not r["n"]:
        return None
    return {"kcal": float(r["kcal"] or 0), "protein_g": float(r["p"] or 0), "carbs_g": float(r["cb"] or 0), "fat_g": float(r["f"] or 0),
            "sugars_g": float(r["su"] or 0), "sat_g": float(r["sa"] or 0), "salt_g": float(r["sl"] or 0)}


def _protein_tip(gap: float) -> str:
    if gap >= 35:
        return "skyr 300 g + 2 jajka"
    if gap >= 20:
        return "skyr 300 g"
    return "skyr 150 g"


def food_lines(day: date) -> list[str]:
    """Rekomendacja jedzenia na dzis - maks. 4 krotkie linie (rano: Brokul + plan treningu)."""
    with _conn() as c:
        p = day_plan(day, c)
        bn = brokul_nutrients(c, day)
    nm = norms(p["target"])
    L = []
    if bn:
        ex = p["extra"] or 0
        head = "🍽 Cel ~%s kcal · Brokuł %s" % (_fmt(p["target"]), _fmt(bn["kcal"]))
        light_snack = not p.get("train_day") and ex >= 80
        if light_snack:
            pg0 = nm["protein_g"] - bn["protein_g"]
            head += " + 🍏 przekąska ~%s ok. 16:00 (%s)" % (_fmt(round(ex / 10) * 10), "skyr 150 g + owoc" if pg0 >= 10 else "owoc + garść orzechów")
        else:
            head += (" → dołóż ~%s po treningu" % _fmt(ex)) if ex >= SMALL_EXTRA else " – wystarczy"
        L.append(head)
        tips = []
        pg = nm["protein_g"] - bn["protein_g"]
        if pg >= 10 and not light_snack:
            tips.append("białko %s/%d g → %s" % (_fmt(bn["protein_g"]), nm["protein_g"], _protein_tip(pg)))
        cg = nm["carbs_g"] - bn["carbs_g"]
        if p.get("train_day") and cg >= 30 and ex >= SMALL_EXTRA:
            tips.append("węgle +%d g po treningu" % int(round(cg / 10) * 10))
        if tips:
            L.append("   " + " · ".join(tips))
        warn = []
        if bn["sugars_g"] >= 0.9 * nm["sugars_max_g"]:
            warn.append("cukry %s/%d g" % (_fmt(bn["sugars_g"]), nm["sugars_max_g"]))
        if bn["salt_g"] > SALT_MAX:
            warn.append("sól %s g (norma 5)" % ("%.0f" % bn["salt_g"]))
        if warn:
            L.append("   ⚠️ " + ", ".join(warn) + " → " + ("bez słodkiego i słonego" if len(warn) == 2 else
                                                         ("bez słodkiego" if warn[0].startswith("cukry") else "bez słonych przekąsek")))
    else:
        L.append("🍽 Cel ~%s kcal (bez diety, deficyt %d) · białko ~%d g" % (_fmt(p["target"]), -p["balance"], nm["protein_g"]))
    extra = []
    if p["fuel_g"]:
        extra.append("na rower ~%d g węgli (słodkie OK)" % p["fuel_g"])
    mt = _meal_times(p)
    if mt:
        extra.append(mt.replace("Przedtreningowy", "przedtr.").replace("Potreningowy", "potr."))
    if extra:
        L.append("   🚲 " + " · ".join(extra))
    return L[:4]


def weekend_lines(friday: date) -> list[str]:
    out = []
    with _conn() as c:
        for d in (friday + timedelta(days=1), friday + timedelta(days=2)):
            p = day_plan(d, c)
            ses = [s for s in p["sessions"] if s["sport"] == "rower"]
            t = "%s ~%s kcal" % (["pn", "wt", "śr", "cz", "pt", "sb", "nd"][d.weekday()], _fmt(p["target"]))
            if ses:
                t += " (jazda %d′%s)" % (ses[0]["dur_min"] or 0, (", ~%d g węgli na rower" % p["fuel_g"]) if p["fuel_g"] else "")
            out.append(t)
    return ["🗓 Weekend: " + " · ".join(out) + ". Co zamawiać: strona Jedzenie → Analiza."]


def morning_digest(day: date, train_lines: list[str] | None = None) -> str | None:
    """JEDNA poranna wiadomosc: trening, wazenie, jedzenie, przypomnienia. Zwiezle."""
    import qbot_food_log as F
    import qbot_food_streaks as S
    import qbot_brokul_meals as M
    L = ["☀️ %s %s" % (F.DNI[day.weekday()], day.strftime("%d.%m"))]
    for t in train_lines or []:
        L.append("💪 " + t)
    try:
        with _conn() as c:
            wl = S.weigh_line(c, day)
        if wl:
            L.append(wl)
    except Exception:
        pass
    try:
        L += food_lines(day)
    except Exception as e:
        L.append("🍽 (rekomendacja niedostępna: %s)" % type(e).__name__)
    y = day - timedelta(days=1)
    if y >= S.START:
        try:
            if not F.close_state(y)["closed"]:
                L.append("⏳ Wczoraj otwarty – zamknij do 12:00")
        except Exception:
            pass
    end = M.delivery_end()
    if end and 0 <= (end - day).days <= 2:
        L.append("📅 Brokuł kończy się %s %s – przedłużone?" % (F.DNI[end.weekday()], end.strftime("%d.%m")))
    if day.weekday() == 4:
        try:
            L += weekend_lines(day)
        except Exception:
            pass
    return "\n".join(L) if len(L) > 1 else None


# ======================================================================= tick (wolane z qbot_brokul_meals.tick)
def tick(now: datetime) -> list[str]:
    """2026-10-12: brak wlasnych wysylek. Plan weekendu i koniec diety sa w porannej wiadomosci (morning_digest),
    przypomnienie 21:30 zastapione linia 'Wczoraj otwarty' rano. Zostawione jako punkt zaczepienia."""
    return []
