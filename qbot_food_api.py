#!/usr/bin/env python3
"""API strony Jedzenie (/jedzenie.html) - /api/jedzenie/* (2026-10-12). Dok.: docs/BROKUL.md

Odczyt: days (karty dni), streaks (pasy + mapy dni), balance (bilans, rozbieznosc, wykres wagi), menu (Brokul do przodu + lodowka).
Zapis (tylko pelna sesja wlasciciela, demo = odczyt): Brokul (status), okno, 'nic poza dieta', szybkie przyciski,
wpisy (dodaj tekstem z AI, wybor porcji, skala, poprawka slowami, przeniesienie dnia, usuniecie).
Kazda zmiana odswieza tez wiadomosc dnia na Telegramie (qbot_food_log.refresh_day) - jedno zrodlo prawdy: baza.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request

TZ = ZoneInfo("Europe/Warsaw")


def _d(v) -> date:
    try:
        return date.fromisoformat(str(v)[:10])
    except Exception:
        raise HTTPException(status_code=400, detail="zła data")


def _ser(x):
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    if hasattr(x, "isoformat"):
        return x.isoformat()
    return x


def _row(r: dict, keys=None) -> dict:
    return {k: _ser(v) for k, v in r.items() if keys is None or k in keys}


MEAL_KEYS = ("id", "day", "meal_type", "meal_order", "name", "kcal", "protein_g", "carbs_g", "fat_g", "sugars_g",
             "sat_fat_g", "salt_g", "ingredients", "allergen_notice", "status", "eaten_day")
ENTRY_KEYS = ("id", "day", "kind", "status", "raw_text", "items", "options", "question", "scale", "kcal", "protein_g",
              "carbs_g", "fat_g", "eaten_time", "created_at", "error")


# ======================================================================= odczyt
def day_card(day: date, plan_ctx: dict) -> dict:
    import qbot_food_log as F
    import qbot_brokul_meals as M
    import qbot_food_streaks as S
    import qbot_food_plan as FP
    meals = [_row(m, MEAL_KEYS) for m in M.day_meals(day)]
    fridge = [_row(m, MEAL_KEYS) for m in M.fridge_for(day)]
    with F._conn() as c:
        ents = c.execute("SELECT * FROM qbot_v2.food_entries WHERE day=%s AND status IN ('logged','asking','failed','new') ORDER BY id",
                         (day,)).fetchall()
        ws, wd = S.window_status(c, day)
        ex = FP.expend(c, day)
        ses = [_row(s) for s in FP.sessions(c, day)]
    cs = F.close_state(day)
    tot = F.day_totals(day)
    tgt = FP.target_for(ex, plan_ctx["calib"], plan_ctx["balance"], day)
    bk = sum(m["kcal"] or 0 for m in meals) if meals else None
    return {"day": day.isoformat(), "weekday": F.DNI[day.weekday()], "has_diet": bool(meals), "meals": meals, "fridge": fridge,
            "entries": [_row(e, ENTRY_KEYS) for e in ents], "closed": cs["closed"], "none": cs["none"], "pending": cs["pending"],
            "window": {"state": ws, "detail": wd}, "totals": {k: round(v or 0) for k, v in tot.items()},
            "target": tgt, "expend": round(ex["kcal"]), "expend_src": ex["src"], "so_far": ex.get("so_far"), "so_far_at": ex.get("so_far_at"), "so_far_lag_h": ex.get("so_far_lag_h"), "expend_parts": ex.get("parts"), "brokul_kcal": bk,
            "extra": max(0, tgt - bk) if bk else None, "sessions": ses,
            "deadline": S.deadline(day).isoformat(), "late": S._past(day, datetime.now(TZ))}


SWEET_RE = r"(czekolad|żelk|zelk|baton|ciast|lody|lód |wafel|wafl|cukierk|pączk|paczk|drożdżów|rwaniec|słodycz|slodycz|ciastk|deser|nutell|góralk|goralk|snickers|twix|prince polo)"


def analysis(day: date) -> dict:
    """Analiza dnia i tygodnia (liczby liczy QBot). Dzis: cel, zjedzone + zaplanowany Brokul, co jeszcze zjesc.
    Tydzien (7 dni do 'day'): srednie vs normy, slodycze, okno, dni zamkniete, cukry/sol/nasycone z Brokula."""
    import re as _re
    import qbot_food_log as F
    import qbot_food_plan as FP
    import qbot_food_streaks as S
    now = datetime.now(TZ)
    with FP._conn() as c:
        p = FP.day_plan(day, c)
        nm = FP.norms(p["target"])
        bro = c.execute("SELECT status, eaten_day, day, meal_type, name, kcal, protein_g, carbs_g, fat_g, sugars_g, sat_fat_g, salt_g "
                        "FROM qbot_v2.brokul_meals WHERE (day=%s AND status<>'cancelled') OR (status='eaten' AND eaten_day=%s)", (day, day)).fetchall()
    eat = F.day_totals(day)
    eaten = {k: float(eat[k] or 0) for k in ("kcal", "protein_g", "carbs_g", "fat_g")}
    pend = [m for m in bro if m["status"] == "pending" and m["day"] == day]
    pk = {k: sum(float(m[k] or 0) for m in pend) for k in ("kcal", "protein_g", "carbs_g", "fat_g")}
    proj = {k: eaten[k] + pk[k] for k in eaten}
    bro_in = [m for m in bro if (m["status"] == "eaten" and (m["eaten_day"] or m["day"]) == day) or m in pend]
    sug = sum(float(m["sugars_g"] or 0) for m in bro_in)
    salt = sum(float(m["salt_g"] or 0) for m in bro_in)
    sat = sum(float(m["sat_fat_g"] or 0) for m in bro_in)
    left = p["target"] - proj["kcal"]
    pl = nm["protein_g"] - proj["protein_g"]
    recs = []
    if left >= FP.SMALL_EXTRA:
        recs.append("Po wszystkich posiłkach Brokuła zostaje ~%d kcal" % round(left) + (
            " – zjedz białko: %s (brakuje ~%d g)" % (FP._protein_tip(pl), round(pl)) if pl >= 10 else " – węgle/tłuszcz wg ochoty, białko już jest"))
    elif left <= -FP.SMALL_EXTRA:
        recs.append("Z zaplanowanym jedzeniem jesteś ponad cel o ~%d kcal – dziś bez dokładek" % round(-left))
    else:
        recs.append("Plan dnia trafia w cel – nic nie dokładaj" + (", ale białka mało (brakuje ~%d g)" % round(pl) if pl >= 15 else ""))
    if sug >= 0.9 * nm["sugars_max_g"]:
        recs.append("Cukry z diety %d/%d g – słodycze dziś odpuść" % (round(sug), nm["sugars_max_g"]))
    if salt > FP.SALT_MAX:
        recs.append("Sól z diety %.0f g (norma 5) – bez słonych przekąsek, pij wodę" % salt)
    if p["fuel_g"]:
        recs.append("Na rower ~%d g węgli – tu zmieszczą się słodkie (żelki, batony)" % p["fuel_g"])
    if day == now.date() and now.hour >= 17 and left >= 300:
        recs.append("Do końca okna (20:00) zostało ~%d h" % max(0, 20 - now.hour))
    today_part = {"day": day.isoformat(), "target": p["target"], "expend": p["expend"], "balance": p["balance"], "norms": nm,
                  "eaten": {k: round(v) for k, v in eaten.items()}, "pending": {k: round(v) for k, v in pk.items()},
                  "pending_meals": [m["meal_type"] for m in pend], "projected": {k: round(v) for k, v in proj.items()},
                  "left_kcal": round(left), "protein_left": round(pl), "sugars_diet": round(sug, 1), "salt_diet": round(salt, 1),
                  "sat_diet": round(sat, 1), "fuel_g": p["fuel_g"], "sessions": [s["name"] + " %d′" % (s["dur_min"] or 0) for s in p["sessions"]],
                  "recs": recs}
    # ---- tydzien
    a = day - timedelta(days=day.weekday())  # tydzien = pn-nd (do dnia analizy), 2026-10-12
    rows = []
    with FP._conn() as c:
        cal, bal = FP.calibration(c), FP.target_balance(c)
        for i in range((day - a).days + 1):
            d = a + timedelta(days=i)
            if d < S.START:
                continue
            t = F.day_totals(d)
            ex = FP.expend(c, d)
            fd = c.execute("SELECT closed_at, window_ok FROM qbot_v2.food_day WHERE day=%s", (d,)).fetchone()
            ws_, _ = S.window_status(c, d)
            b2 = c.execute("SELECT sum(sugars_g) su, sum(salt_g) sl, sum(sat_fat_g) sa FROM qbot_v2.brokul_meals WHERE status='eaten' "
                           "AND COALESCE(eaten_day, day)=%s", (d,)).fetchone()
            sw = c.execute("SELECT count(*) n FROM qbot_v2.food_entries e WHERE e.day=%s AND e.status='logged' AND "
                           "(e.raw_text ~* %s OR e.items::text ~* %s)", (d, SWEET_RE, SWEET_RE)).fetchone()["n"]
            rows.append({"day": d.isoformat(), "closed": bool(fd and fd["closed_at"]), "kcal": round(float(t["kcal"] or 0)),
                         "protein_g": round(float(t["protein_g"] or 0)), "carbs_g": round(float(t["carbs_g"] or 0)), "fat_g": round(float(t["fat_g"] or 0)),
                         "target": FP.target_for(ex, cal, bal, d), "expend": round(ex["kcal"]),
                         "window": ws_, "sweets": sw, "sugars_diet": round(float(b2["su"] or 0)), "salt_diet": round(float(b2["sl"] or 0), 1),
                         "sat_diet": round(float(b2["sa"] or 0))})
    cl = [r for r in rows if r["closed"]]
    def av(k, src):
        return round(sum(r[k] for r in src) / len(src)) if src else None
    week = {"from": a.isoformat(), "to": (a + timedelta(days=6)).isoformat(), "upto": day.isoformat(), "days": rows, "closed": len(cl), "n": len(rows),
            "avg": {k: av(k, cl) for k in ("kcal", "protein_g", "carbs_g", "fat_g", "target", "expend")},
            "avg_balance": round(sum(r["kcal"] - r["expend"] for r in cl) / len(cl)) if cl else None, "balance_target": bal,
            "sweets_days": sum(1 for r in rows if r["sweets"]), "window_ok": sum(1 for r in rows if r["window"] == "ok"),
            "window_broken": sum(1 for r in rows if r["window"] == "broken"), "over_target_days": sum(1 for r in cl if r["kcal"] > r["target"] + 150),
            "salt_diet_avg": round(sum(r["salt_diet"] for r in rows if r["salt_diet"]) / max(1, sum(1 for r in rows if r["salt_diet"])), 1)}
    wrec = []
    if week["closed"] < week["n"]:
        wrec.append("Zamknięte %d z %d dni – bez pełnych danych bilans jest niepewny" % (week["closed"], week["n"]))
    if week["avg"]["protein_g"] is not None and week["avg"]["protein_g"] < FP.PROTEIN_TARGET * 0.85:
        wrec.append("Białko średnio %d g/dz (cel 160) – dokładaj skyr/jajka/twaróg codziennie" % week["avg"]["protein_g"])
    if week["avg_balance"] is not None:
        diff = week["avg_balance"] - bal
        if diff > 250:
            wrec.append("Średni bilans %+d kcal/dz zamiast %+d – za dużo jedzenia o ~%d kcal dziennie" % (week["avg_balance"], bal, diff))
        elif diff < -300:
            wrec.append("Deficyt %+d kcal/dz – za mocny, grozi głodem i napadem na słodkie; jedz trochę więcej" % week["avg_balance"])
    if week["sweets_days"] >= 3:
        wrec.append("Słodycze w %d dniach tego tygodnia – przenieś je na rower (paliwo) albo zaplanuj 1–2 dni" % week["sweets_days"])
    if week["salt_diet_avg"] > FP.SALT_MAX:
        wrec.append("Sól z samej diety ~%.0f g/dz (norma 5) – resztę dnia bez słonego" % week["salt_diet_avg"])
    if week["window_broken"]:
        wrec.append("Okno 10–20 złamane %d× – kolacja przed 20:00" % week["window_broken"])
    week["recs"] = wrec
    return {"today": today_part, "week": week, "generated_at": now.isoformat()}


def _closed_real(c, FP, d):
    """(zjedzone, spalone, cel) dla zamknietego dnia z realnym spalaniem, inaczej None."""
    cl = c.execute("SELECT closed_at FROM qbot_v2.food_day WHERE day=%s", (d,)).fetchone()
    if not (cl and cl["closed_at"]):
        return None
    ex = FP.expend(c, d)
    if ex["src"] != "realne":
        return None
    k = c.execute("SELECT sum(i.kcal) k, sum(i.protein_g) p, sum(i.carbs_g) cb, sum(i.fat_g) f FROM qbot_v2.intake_logs l "
                  "JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id WHERE l.date=%s", (d,)).fetchone()
    if not k or not k["k"]:
        return None
    return {"kcal": float(k["k"]), "protein_g": float(k["p"] or 0), "carbs_g": float(k["cb"] or 0), "fat_g": float(k["f"] or 0),
            "expend": float(ex["kcal"]), "target": FP.target_for(ex, FP.calibration(c), FP.target_balance(c), d)}


def week_analysis(ws: date) -> dict:
    """Analiza tygodnia pn-nd: budzet deficytu (plan vs realizacja), skladniki, wzorce z 4 tygodni, top produkty spoza diety."""
    import qbot_food_plan as FP
    import qbot_food_streaks as S
    today = datetime.now(TZ).date()
    ws = ws - timedelta(days=ws.weekday())
    we = ws + timedelta(days=6)
    plan0 = FP.week_deficits(ws, actuals=False)
    days, real_sum, left_days = [], 0.0, 0
    with FP._conn() as c:
        for i in range(7):
            d = ws + timedelta(days=i)
            pd = int(plan0.get(d, 0))
            cr = _closed_real(c, FP, d) if d < today else None
            st, ad = None, None
            if cr:
                ad = round(cr["expend"] - cr["kcal"])
                real_sum += ad
                st = "over" if ad < pd - 150 else ("under" if ad > pd + 300 else "ok")
            elif d >= today or not c.execute("SELECT 1 FROM qbot_v2.food_day WHERE day=%s AND closed_at IS NOT NULL", (d,)).fetchone():
                if d >= today:
                    left_days += 1
                st = "open" if d < today else "future"
            sw = c.execute("SELECT count(*) n FROM qbot_v2.food_entries e WHERE e.day=%s AND e.status='logged' AND (e.raw_text ~* %s OR e.items::text ~* %s)",
                           (d, SWEET_RE, SWEET_RE)).fetchone()["n"]
            wsn, _ = S.window_status(c, d) if d >= S.START and d <= today else (None, None)
            days.append({"day": d.isoformat(), "plan_def": pd, "act_def": ad, "status": st, "sweets": sw, "window": wsn,
                         "protein_g": round(cr["protein_g"]) if cr else None, "kcal": round(cr["kcal"]) if cr else None,
                         "carbs_g": round(cr["carbs_g"]) if cr else None, "fat_g": round(cr["fat_g"]) if cr else None})
        plan_total = sum(v for k, v in plan0.items() if k >= S.START)   # dni sprzed startu logowania nie wchodza do budzetu
        closed = [x for x in days if x["act_def"] is not None]
        rem = plan_total - real_sum
        # poprzedni tydzien (realizacja)
        pws, prev_sum, prev_n = ws - timedelta(days=7), 0.0, 0
        pplan = FP.week_deficits(pws, actuals=False)
        for i in range(7):
            cr = _closed_real(c, FP, pws + timedelta(days=i))
            if cr:
                prev_sum += cr["expend"] - cr["kcal"]
                prev_n += 1
        # skladniki z diety (cukry, sol) - tylko dni z Brokulem
        bro = c.execute("SELECT COALESCE(eaten_day, day) d, sum(sugars_g) su, sum(salt_g) sl, sum(sat_fat_g) sa FROM qbot_v2.brokul_meals "
                        "WHERE status='eaten' AND COALESCE(eaten_day, day) BETWEEN %s AND %s GROUP BY 1", (ws, we)).fetchall()
        # wzorce: 28 dni do konca tygodnia (lub dzis)
        pe = min(we, today - timedelta(days=1))
        pa = pe - timedelta(days=27)
        rows = []
        d = max(pa, S.START)
        while d <= pe:
            cr = _closed_real(c, FP, d)
            if cr:
                mins, _ = FP._train_kcal(c, d, FP.model(c))
                sl = c.execute("SELECT sleep_score FROM qbot_v2.qbot_sleep_daily WHERE date=%s AND sleep_score IS NOT NULL ORDER BY imported_at DESC LIMIT 1", (d,)).fetchone()
                fd = c.execute("SELECT window_ok FROM qbot_v2.food_day WHERE day=%s", (d,)).fetchone()
                rows.append({"day": d, "dev": cr["kcal"] - cr["target"], "ride": mins >= FP.TRAIN_MIN, "weekend": d.weekday() >= 5,
                             "sleep": float(sl["sleep_score"]) if sl else None, "win_broken": bool(fd and fd["window_ok"] is False)})
            d += timedelta(days=1)
        ents = c.execute("SELECT items, scale FROM qbot_v2.food_entries WHERE status='logged' AND day BETWEEN %s AND %s", (pa, pe)).fetchall()
    def grp(label_a, fa, label_b, fb):
        A0 = [r["dev"] for r in rows if fa(r)]
        B0 = [r["dev"] for r in rows if fb(r)]
        ok = len(A0) >= 3 and len(B0) >= 3
        return {"a": label_a, "b": label_b, "na": len(A0), "nb": len(B0), "ok": ok,
                "dev_a": round(sum(A0) / len(A0)) if A0 else None, "dev_b": round(sum(B0) / len(B0)) if B0 else None}
    patterns = [grp("dni robocze", lambda r: not r["weekend"], "weekend", lambda r: r["weekend"]),
                grp("dni z jazdą", lambda r: r["ride"], "bez jazdy", lambda r: not r["ride"]),
                grp("po dobrej nocy (sen ≥ 70)", lambda r: r["sleep"] is not None and r["sleep"] >= 70, "po słabej nocy (sen < 70)",
                    lambda r: r["sleep"] is not None and r["sleep"] < 70)]
    tops = {}
    for e in ents:
        sc = float(e["scale"] or 1)
        for it in (e["items"] or []):
            nm = (it.get("short") or it.get("name") or "?").strip().lower()[:40]
            t = tops.setdefault(nm, {"name": it.get("short") or it.get("name") or "?", "kcal": 0.0, "n": 0})
            t["kcal"] += float(it.get("kcal") or 0) * sc
            t["n"] += 1
    top = sorted(tops.values(), key=lambda x: -x["kcal"])[:6]
    av = lambda k: round(sum(x[k] for x in closed) / len(closed)) if closed else None
    return {"week": ws.isoformat(), "week_end": we.isoformat(), "today": today.isoformat(),
            "prev": (ws - timedelta(days=7)).isoformat(), "next": (ws + timedelta(days=7)).isoformat() if ws + timedelta(days=7) <= today else None,
            "budget": {"plan": int(plan_total), "real": round(real_sum), "remaining": round(rem), "left_days": left_days,
                       "per_day": round(rem / left_days) if left_days else None, "closed": len(closed),
                       "prev_real": round(prev_sum), "prev_plan": int(sum(v for k, v in pplan.items() if k >= S.START)), "prev_closed": prev_n},
            "days": days,
            "nutr": {"protein": av("protein_g"), "carbs": av("carbs_g"), "fat": av("fat_g"), "kcal": av("kcal"), "protein_target": FP.PROTEIN_TARGET,
                     "diet_days": len(bro), "sugars_diet": round(sum(float(b["su"] or 0) for b in bro) / len(bro)) if bro else None,
                     "salt_diet": round(sum(float(b["sl"] or 0) for b in bro) / len(bro), 1) if bro else None,
                     "sweets_days": sum(1 for x in days if x["sweets"]), "window_ok": sum(1 for x in days if x["window"] == "ok"),
                     "window_broken": sum(1 for x in days if x["window"] == "broken")},
            "patterns": {"from": pa.isoformat(), "to": pe.isoformat(), "n_days": len(rows), "groups": patterns,
                         "win_broken": sum(1 for r in rows if r["win_broken"]), "top": [{"name": t["name"], "kcal": round(t["kcal"]), "n": t["n"]} for t in top]}}


def week_ai(ws: date, force: bool = False) -> dict | None:
    """Zalecenia AI tygodnia (na policzonych liczbach). Zapis w food_week_ai; bez force zwraca istniejace."""
    import qbot_food_log as F
    ws = ws - timedelta(days=ws.weekday())
    with F._conn() as c:
        row = c.execute("SELECT payload, created_at FROM qbot_v2.food_week_ai WHERE week=%s", (ws,)).fetchone()
    if row and not force:
        return dict(row["payload"], created_at=row["created_at"].isoformat())
    res = json.loads(json.dumps(week_analysis(ws), default=_ser))
    prompt = ("Jesteś dietetykiem sportowym. Użytkownik: mężczyzna ~104 kg, redukcja do 90 kg (budżet tygodniowy deficytu), kolarz gravel, "
              "catering Brokuł w dni robocze, weekend na mieście. Dostajesz POLICZONE dane tygodnia i wzorce z 4 tygodni (nie licz własnych liczb). "
              "Zwróć WYŁĄCZNIE JSON: {\"tydzien\": [\"...\"], \"wzorce\": [\"...\"], \"nastepny\": [\"...\"]}. "
              "tydzien: maks. 3 krótkie wnioski o tym tygodniu; wzorce: maks. 2 (tylko gdy dane wystarczają, inaczej pusta lista); "
              "nastepny: maks. 3 konkretne działania na kolejny tydzień. Prosty język, bez moralizowania.")
    j = F._ai_json(prompt, [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}])
    pay = {k: [str(x)[:300] for x in (j.get(k) or [])][:3] for k in ("tydzien", "wzorce", "nastepny")}
    with F._conn() as c:
        c.execute("INSERT INTO qbot_v2.food_week_ai (week, payload) VALUES (%s,%s) ON CONFLICT (week) DO UPDATE SET payload=EXCLUDED.payload, created_at=now()",
                  (ws, json.dumps(pay, ensure_ascii=False)))
        c.commit()
    return dict(pay, created_at=datetime.now(TZ).isoformat())


def plan_ctx() -> dict:
    import qbot_food_plan as FP
    with FP._conn() as c:
        return {"calib": FP.calibration(c), "balance": FP.target_balance(c)}


def build_router(current_user, owner_user) -> APIRouter:
    r = APIRouter(prefix="/api/jedzenie")

    def need_user(request):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")

    def need_owner(request):
        if not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko odczyt (sesja demo)")

    @r.get("/days")
    def days(request: Request, start: str | None = None, end: str | None = None):
        need_user(request)
        import qbot_brokul_meals as M
        today = datetime.now(TZ).date()
        import qbot_food_streaks as S
        a = _d(start) if start else max(today - timedelta(days=6), S.START)
        last = M.delivery_end()
        b = _d(end) if end else max(today, min(last, today + timedelta(days=6)) if last else today)
        if (b - a).days > 31:
            raise HTTPException(status_code=400, detail="maks. 31 dni")
        ctx = plan_ctx()
        out, d = [], a
        while d <= b:
            out.append(day_card(d, ctx))
            d += timedelta(days=1)
        return {"today": today.isoformat(), "balance": ctx["balance"], "calib": ctx["calib"], "days": out}

    @r.get("/day")
    def one_day(request: Request, day: str):
        need_user(request)
        return day_card(_d(day), plan_ctx())

    @r.get("/streaks")
    def streaks(request: Request):
        need_user(request)
        import qbot_food_streaks as S
        s = S.streaks()
        nxt = {k: next((m for m in S.MILESTONES if m > s[k]["n"]), None) for k in ("food", "window", "train", "reduce")}
        return {"streaks": json.loads(json.dumps(s, default=_ser)), "next": nxt, "milestones": list(S.MILESTONES),
                "start": S.START.isoformat(), "launch": S.LAUNCH.isoformat()}

    @r.get("/balance")
    def balance(request: Request, days: int = 45, start: str | None = None, end: str | None = None):
        need_user(request)
        import qbot_food_plan as FP
        import qbot_food_streaks as S
        import qbot_trener_stats as ST
        today = datetime.now(TZ).date()
        if start:
            a, today = _d(start), min(_d(end) if end else today, datetime.now(TZ).date())
            if a > today or (today - a).days > 366:
                raise HTTPException(status_code=400, detail="zakres: maks. 366 dni, od <= do")
        else:
            days = max(7, min(366, days))
            a = today - timedelta(days=days)
        with FP._conn() as c:
            cal, bal = FP.calibration(c), FP.target_balance(c)
            itk = {x["date"]: float(x["k"]) for x in c.execute(
                "SELECT l.date, sum(i.kcal) k FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id "
                "WHERE l.date BETWEEN %s AND %s GROUP BY l.date", (a, today)).fetchall() if x["k"]}
            closed = {x["day"] for x in c.execute("SELECT day FROM qbot_v2.food_day WHERE closed_at IS NOT NULL AND day BETWEEN %s AND %s",
                                                  (a, today)).fetchall()}
            rest = {x["date"]: float(x["r"]) for x in c.execute(
                "SELECT date, resting_kcal r FROM qbot_v2.energy_daily WHERE date BETWEEN %s AND %s AND resting_kcal IS NOT NULL "
                "AND quality_status<>'partial'", (a, today)).fetchall()}
            series, d = [], a
            while d <= today:
                ex = FP.expend(c, d)
                # podzial spalania: spoczynek (BMR) + aktywne; dzien realny z Garmina, prognoza z modelu
                rr = rest.get(d) if ex["src"] == "realne" else (ex.get("parts") or {}).get("bmr")
                series.append({"day": d.isoformat(), "rest": round(rr) if rr else None,
                               "active": round(ex["kcal"] - rr) if rr else None,
                               "intake": round(itk[d]) if d in itk else None, "expend": round(ex["kcal"]),
                               "expend_src": ex["src"], "closed": d in closed,
                               "target": FP.target_for(ex, cal, bal, d)})
                d += timedelta(days=1)
            cur = c.cursor()
            cur.execute("SELECT * FROM qbot_v2.trainer_goal WHERE kind='weight' AND status='active' AND username NOT LIKE '\\_%%' ORDER BY id LIMIT 1")
            g = cur.fetchone()
            goal = None
            if g:
                gs = ST.compute_goal_status(cur, [dict(g)])
                goal = gs.get(g["id"]) or gs.get(str(g["id"]))
                if goal:
                    goal = json.loads(json.dumps(dict(goal, name=g["name"]), default=_ser))
        weeks = {}
        for x in series:
            if x["closed"] and x["intake"] is not None and x["expend_src"] == "realne":
                ws = (date.fromisoformat(x["day"]) - timedelta(days=date.fromisoformat(x["day"]).weekday())).isoformat()
                weeks.setdefault(ws, []).append(x["intake"] - x["expend"])
        wk = [{"week": k, "days": len(v), "avg_balance": round(sum(v) / len(v))} for k, v in sorted(weeks.items())]
        with FP._conn() as c:
            wts = [[x["date"].isoformat(), round(float(x["w"]), 2)] for x in c.execute(
                "SELECT date, avg(weight_kg) w FROM qbot_v2.body_measurements WHERE weight_kg IS NOT NULL AND date BETWEEN %s AND %s "
                "GROUP BY date ORDER BY date", (a, today)).fetchall()]
        disc = json.loads(json.dumps(S.discrepancy(), default=_ser))
        return {"series": series, "weights": wts, "start": a.isoformat(), "end": today.isoformat(), "weeks": wk, "balance_target": bal, "calib": cal, "discrepancy": disc,
                "discrepancy_line": S.discrepancy_line(), "goal": goal}

    @r.get("/menu")
    def menu(request: Request, week: str | None = None):
        """Menu Brokula tygodniami (pn-nd) + podsumowanie dni i tygodnia vs normy. Historia od 12.10.2026 (panel nie daje starszych)."""
        need_user(request)
        import qbot_brokul_meals as M
        import qbot_brokul as B
        import qbot_food_plan as FP
        today = datetime.now(TZ).date()
        ws = _d(week) if week else today
        ws = ws - timedelta(days=ws.weekday())
        we = ws + timedelta(days=6)
        with M._conn() as c:
            meals = c.execute("SELECT * FROM qbot_v2.brokul_meals WHERE day BETWEEN %s AND %s AND status <> 'cancelled' ORDER BY day, meal_order",
                              (ws, we)).fetchall()
            fridge = c.execute("SELECT * FROM qbot_v2.brokul_meals WHERE status='fridge' ORDER BY day, meal_order").fetchall()
            rng = c.execute("SELECT min(day) a, max(day) b FROM qbot_v2.brokul_meals WHERE status <> 'cancelled'").fetchone()
        K = ("kcal", "protein_g", "carbs_g", "fat_g", "sugars_g", "sat_fat_g", "salt_g")
        days = {}
        for m in meals:
            d = days.setdefault(m["day"].isoformat(), {k: 0.0 for k in K})
            for k in K:
                d[k] += float(m[k] or 0)
        week_sum = {k: round(sum(d[k] for d in days.values()), 1) for k in K}
        n = len(days)
        avg = {k: round(week_sum[k] / n, 1) for k in K} if n else None
        def judge(v):
            if not v:
                return None
            return {"protein_g": "ok" if v["protein_g"] >= FP.PROTEIN_TARGET * 0.9 else "low",
                    "sugars_g": "ok" if v["sugars_g"] <= v["kcal"] * FP.SUGAR_MAX_PCT / 4 else "high",
                    "sat_fat_g": "ok" if v["sat_fat_g"] <= v["kcal"] * FP.SAT_MAX_PCT / 9 else "high",
                    "salt_g": "ok" if v["salt_g"] <= FP.SALT_MAX else "high",
                    "fat_g": "ok" if v["fat_g"] >= FP.FAT_MIN else "low"}
        st = B.state()
        return {"week": ws.isoformat(), "week_end": we.isoformat(),
                "prev": (ws - timedelta(days=7)).isoformat() if rng and rng["a"] and rng["a"] < ws else None,
                "next": (ws + timedelta(days=7)).isoformat() if rng and rng["b"] and rng["b"] > we else None,
                "meals": [_row(m, MEAL_KEYS) for m in meals], "fridge": [_row(m, MEAL_KEYS) for m in fridge],
                "days": {k: {kk: round(vv, 1) for kk, vv in v.items()} for k, v in days.items()},
                "days_judge": {k: judge(v) for k, v in days.items()},
                "week_sum": week_sum, "week_avg": avg, "week_judge": judge(avg), "n_days": n,
                "norms": {"protein_g": FP.PROTEIN_TARGET, "fat_min_g": FP.FAT_MIN, "salt_max_g": FP.SALT_MAX,
                          "sugars_pct": FP.SUGAR_MAX_PCT, "sat_pct": FP.SAT_MAX_PCT},
                "order_end": _ser(M.delivery_end()), "session_alive": bool(st.get("alive")),
                "last_import": st.get("last_import"), "access_url": "/brokul-dostep", "history_from": "2026-10-12"}

    @r.get("/body")
    def body_comp(request: Request, days: int = 365):
        """Sklad ciala z Withings/Garmin (body_measurements): waga, % tluszczu, kg tluszczu, kg miesni, woda.
        Przelom serii: 12.10.2026 Withings 'Athlete mode' (inny algorytm -> skok, nie zmiana ciala).
        Podejrzane: dzien po jezdzie >= 3 h albo skok % tluszczu > 1,5 pkt wzgledem poprzedniego pomiaru w tym samym trybie."""
        need_user(request)
        import qbot_food_plan as FP
        days = max(30, min(730, days))
        BREAK = date(2026, 10, 12)
        with FP._conn() as c:
            rows = c.execute("SELECT date, weight_kg, body_fat_pct, muscle_mass_kg, body_water_pct, bone_mass_kg, source_type "
                             "FROM qbot_v2.body_measurements WHERE weight_kg IS NOT NULL AND date >= current_date - %s ORDER BY date",
                             (days,)).fetchall()
            long_rides = {x["date"] for x in c.execute("SELECT date FROM qbot_v2.training_sessions WHERE date >= current_date - %s - 1 "
                                                       "GROUP BY date HAVING max(duration_s) >= 10800", (days,)).fetchall()}
        out, prev = [], {}
        for r0 in rows:
            mode = "athlete" if r0["date"] >= BREAK else "normal"
            fp = float(r0["body_fat_pct"]) if r0["body_fat_pct"] is not None else None
            w = float(r0["weight_kg"])
            sus = []
            if (r0["date"] - timedelta(days=1)) in long_rides:
                sus.append("dzień po jeździe ≥3 h")
            if fp is not None and prev.get(mode) is not None and abs(fp - prev[mode]) > 1.5:
                sus.append("skok %+.1f pkt" % (fp - prev[mode]))
            if fp is not None:
                prev[mode] = fp
            out.append({"date": r0["date"].isoformat(), "weight": round(w, 2), "fat_pct": fp,
                        "fat_kg": round(w * fp / 100, 1) if fp is not None else None,
                        "muscle_kg": round(float(r0["muscle_mass_kg"]), 1) if r0["muscle_mass_kg"] is not None else None,
                        "water_pct": float(r0["body_water_pct"]) if r0["body_water_pct"] is not None else None,
                        "bone_kg": round(float(r0["bone_mass_kg"]), 2) if r0["bone_mass_kg"] is not None else None,
                        "mode": mode, "suspect": sus, "source": r0["source_type"]})
        comp = [x for x in out if x["fat_pct"] is not None]
        def avg(xs, k):
            v = [x[k] for x in xs if x[k] is not None]
            return round(sum(v) / len(v), 1) if v else None
        summ = {}
        for mode in ("normal", "athlete"):
            xs = [x for x in comp if x["mode"] == mode and not x["suspect"]]
            if xs:
                summ[mode] = {"n": len(xs), "last3_fat_pct": avg(xs[-3:], "fat_pct"), "last3_fat_kg": avg(xs[-3:], "fat_kg"),
                              "last3_muscle_kg": avg(xs[-3:], "muscle_kg"), "first": xs[0]["date"], "last": xs[-1]["date"],
                              "d_fat_kg": round(xs[-1]["fat_kg"] - xs[0]["fat_kg"], 1) if len(xs) > 1 else None,
                              "d_muscle_kg": round((xs[-1]["muscle_kg"] or 0) - (xs[0]["muscle_kg"] or 0), 1) if len(xs) > 1 else None}
        with FP._conn() as c:
          circ = [{k: (float(v) if k != "date" and v is not None else (v.isoformat() if k == "date" else None)) for k, v in x.items()}
                    for x in c.execute("SELECT date, waist_cm, hips_cm, chest_cm, thigh_cm, arm_cm, neck_cm FROM qbot_v2.body_circumference "
                                       "WHERE date >= current_date - %s ORDER BY date", (days,)).fetchall()]
        return {"points": out, "break": BREAK.isoformat(), "summary": summ, "height_cm": 177, "circ": circ}

    @r.get("/circ")
    def circ_get(request: Request, days: int = 730):
        """Obwody ciala (cm) do wykresow (Forma -> Trendy -> Wellness)."""
        need_user(request)
        import qbot_food_plan as FP
        with FP._conn() as c:
            rows = c.execute("SELECT date, waist_cm, hips_cm, chest_cm, thigh_cm, arm_cm, neck_cm FROM qbot_v2.body_circumference "
                             "WHERE date >= current_date - %s ORDER BY date", (max(30, min(1500, days)),)).fetchall()
        return {"circ": [{k: (float(v) if k != "date" and v is not None else (v.isoformat() if k == "date" else None)) for k, v in x.items()} for x in rows],
                "height_cm": 177}

    @r.post("/circ")
    async def circ_post(request: Request):
        """Zapis obwodow na dzien (nadpisuje). Talia wymagana; wszystkie puste = usuniecie wpisu z tego dnia."""
        need_owner(request)
        b = await body(request)
        d = _d(b.get("date")) if b.get("date") else datetime.now(TZ).date()
        vals = {}
        for k in ("waist_cm", "hips_cm", "chest_cm", "thigh_cm", "arm_cm", "neck_cm"):
            v = b.get(k)
            if v in (None, ""):
                vals[k] = None
                continue
            try:
                v = round(float(str(v).replace(",", ".")), 1)
            except ValueError:
                raise HTTPException(status_code=400, detail="%s: to nie liczba" % k)
            if not 15 <= v <= 250:
                raise HTTPException(status_code=400, detail="%s: poza zakresem 15-250 cm" % k)
            vals[k] = v
        import qbot_food_plan as FP
        with FP._conn() as c:
            if all(v is None for v in vals.values()):
                c.execute("DELETE FROM qbot_v2.body_circumference WHERE date=%s", (d,))
                c.commit()
                return {"ok": True, "deleted": d.isoformat()}
            if vals["waist_cm"] is None:
                raise HTTPException(status_code=400, detail="talia jest wymagana")
            c.execute("INSERT INTO qbot_v2.body_circumference (date, waist_cm, hips_cm, chest_cm, thigh_cm, arm_cm, neck_cm) "
                      "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (date) DO UPDATE SET waist_cm=EXCLUDED.waist_cm, hips_cm=EXCLUDED.hips_cm, "
                      "chest_cm=EXCLUDED.chest_cm, thigh_cm=EXCLUDED.thigh_cm, arm_cm=EXCLUDED.arm_cm, neck_cm=EXCLUDED.neck_cm, updated_at=now()",
                      (d, vals["waist_cm"], vals["hips_cm"], vals["chest_cm"], vals["thigh_cm"], vals["arm_cm"], vals["neck_cm"]))
            c.commit()
        return {"ok": True, "date": d.isoformat(), **vals}

    @r.get("/week")
    def week_get(request: Request, week: str | None = None):
        """Analiza tygodnia (pn-nd) + zapisane zalecenia AI tygodnia."""
        need_user(request)
        ws = _d(week) if week else datetime.now(TZ).date()
        res = week_analysis(ws)
        try:
            res["ai"] = week_ai(_d(res["week"]), force=False) if False else None
            import qbot_food_log as F
            with F._conn() as c:
                row = c.execute("SELECT payload, created_at FROM qbot_v2.food_week_ai WHERE week=%s", (_d(res["week"]),)).fetchone()
            res["ai"] = dict(row["payload"], created_at=row["created_at"].isoformat()) if row else None
        except Exception:
            res["ai"] = None
        return json.loads(json.dumps(res, default=_ser))

    @r.post("/week/ai")
    async def week_ai_post(request: Request):
        need_owner(request)
        b = await body(request)
        try:
            return {"ok": True, "ai": week_ai(_d(b.get("week")) if b.get("week") else datetime.now(TZ).date(), force=True)}
        except Exception as ex:
            raise HTTPException(status_code=502, detail="AI niedostępne: %s" % type(ex).__name__)

    @r.get("/rides_day")
    def rides_day(request: Request, start: str, end: str):
        """Jazdy rowerowe dzien po dniu (suma): km, czas, przewyzszenie, liczba - do dymka w Forma -> Trendy."""
        need_user(request)
        import qbot_food_plan as FP
        a, b = _d(start), _d(end)
        if (b - a).days > 800:
            raise HTTPException(status_code=400, detail="maks. 800 dni")
        with FP._conn() as c:
            rows = c.execute("SELECT date, count(*) n, sum(distance_m) m, sum(duration_s) s, sum(elevation_m) e FROM qbot_v2.training_sessions "
                             "WHERE date BETWEEN %s AND %s AND sport_type IN ('cycling','gravel_cycling','road_biking','mountain_biking','indoor_cycling','virtual_ride') "
                             "GROUP BY date", (a, b)).fetchall()
        return {"days": {r["date"].isoformat(): {"n": r["n"], "km": round(float(r["m"] or 0) / 1000, 1), "h": round(float(r["s"] or 0) / 3600, 2),
                                                  "elev": round(float(r["e"] or 0))} for r in rows}}

    @r.get("/hrr")
    def hrr(request: Request, days: int = 365):
        """Tetno odpoczynku po akcentach (HRR60) z jazd: per jazda + norma roku + ostatnie 28 dni (qbot_hrr.py)."""
        need_user(request)
        import qbot_hrr as H
        return H.summary(max(30, min(800, days)))

    @r.get("/alcohol")
    def alcohol(request: Request, start: str, end: str):
        """Dni z alkoholem (znaczniki 🍷 na wykresach)."""
        need_user(request)
        import qbot_food_plan as FP
        a, b = _d(start), _d(end)
        if (b - a).days > 800:
            raise HTTPException(status_code=400, detail="maks. 800 dni")
        with FP._conn() as c:
            return {"days": sorted(d.isoformat() for d in FP.alcohol_days(c, a, b))}

    @r.get("/heart_plus")
    def heart_plus(request: Request):
        """Zdrowie -> Serce: HRV (norma z roku, ostatnie 28 dni) + serce a jedzenie/waga
        (cisnienie rano po dniu z duza iloscia soli z diety / po duzym deficycie / vs waga; HRV po duzym deficycie)."""
        need_user(request)
        import statistics as stt
        import qbot_food_plan as FP
        today = datetime.now(TZ).date()
        with FP._conn() as c:
            hrv = [(x["date"], float(x["h"])) for x in c.execute(
                "SELECT date, avg(hrv_ms) h FROM qbot_v2.qbot_sleep_daily WHERE hrv_ms IS NOT NULL AND date >= %s GROUP BY date ORDER BY date",
                (today - timedelta(days=440),)).fetchall()]   # [GARMIN-DANE] +75 dni na norme 60 nocy
            bp = c.execute("SELECT measured_local, systolic, diastolic FROM qbot_v2.blood_pressure ORDER BY measured_local").fetchall()
            salt = {x["d"]: float(x["s"] or 0) for x in c.execute(
                "SELECT COALESCE(eaten_day, day) d, sum(salt_g) s FROM qbot_v2.brokul_meals WHERE status='eaten' GROUP BY 1").fetchall()}
            wts = [(x["date"], float(x["weight_kg"])) for x in c.execute(
                "SELECT date, weight_kg FROM qbot_v2.body_measurements WHERE weight_kg IS NOT NULL ORDER BY date").fetchall()]
            bal = {}
            for x in c.execute("SELECT l.date, sum(i.kcal) k FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id "
                               "JOIN qbot_v2.food_day f ON f.day=l.date AND f.closed_at IS NOT NULL GROUP BY l.date").fetchall():
                ex = FP.expend(c, x["date"])
                if x["k"] and ex["src"] == "realne":
                    bal[x["date"]] = float(x["k"]) - ex["kcal"]
        # [GARMIN-DANE] Etap 3 (2026-10-14): status HRV QBota -- 7 nocy vs norma 60 nocy +-0.5 SD (fitmodel/hrv_status.py)
        from fitmodel.hrv_status import compute_series as _hrv_cs, LABELS as _HL, LEVEL as _HV
        _hs = _hrv_cs(hrv)
        _cut = (today - timedelta(days=365)).isoformat()
        hrv_band = [[r["date"], r["avg7"], r["lo"], r["hi"], r["status"]] for r in _hs if r["date"] >= _cut]
        _last = next((r for r in reversed(_hs) if r["status"]), None)
        hrv_status7 = {**_last, "label": _HL[_last["status"]], "level": _HV[_last["status"]]} if _last else None
        hrv = [(d, h) for d, h in hrv if (today - d).days <= 365]
        old = [h for d, h in hrv if (today - d).days > 28]
        rec = [h for d, h in hrv if (today - d).days <= 28]
        norm = stt.median(old) if len(old) >= 30 else None
        recent = sum(rec) / len(rec) if rec else None
        delta = recent - norm if recent is not None and norm else None
        pct = delta / norm * 100 if delta is not None else None
        st_ = None if pct is None else ("bad" if pct <= -12 else "warn" if pct <= -7 else "good" if pct >= 3 else "good")
        hmap = dict(hrv)
        # HRV po duzym deficycie (nastepny dzien) vs po pozostalych dniach z bilansem - odchylenie od mediany 28 dni
        def dev(d):
            v = hmap.get(d)
            base = [hmap[d - timedelta(days=k)] for k in range(1, 29) if (d - timedelta(days=k)) in hmap]
            return v - stt.median(base) if v is not None and len(base) >= 8 else None
        big = [dev(d + timedelta(days=1)) for d, v in bal.items() if v < -700]
        oth = [dev(d + timedelta(days=1)) for d, v in bal.items() if v >= -700]
        big, oth = [x for x in big if x is not None], [x for x in oth if x is not None]
        with FP._conn() as c:
            alc = FP.alcohol_days(c, today - timedelta(days=365), today)
            rhr = {x["date"]: float(x["r"]) for x in c.execute("SELECT date, avg(resting_hr_bpm) r FROM qbot_v2.qbot_sleep_daily WHERE resting_hr_bpm IS NOT NULL "
                                                                "AND date >= %s GROUP BY date", (today - timedelta(days=400),)).fetchall()}
            slp = {x["date"]: float(x["s"]) for x in c.execute("SELECT date, avg(sleep_score) s FROM qbot_v2.qbot_sleep_daily WHERE sleep_score IS NOT NULL "
                                                                "AND date >= %s GROUP BY date", (today - timedelta(days=400),)).fetchall()}
        def devm(mp, d):
            v = mp.get(d)
            base = [mp[d - timedelta(days=k)] for k in range(1, 29) if (d - timedelta(days=k)) in mp and (d - timedelta(days=k + 1)) not in alc]
            return v - stt.median(base) if v is not None and len(base) >= 8 else None
        def avgl(xs):
            xs = [x for x in xs if x is not None]
            return round(sum(xs) / len(xs), 1) if xs else None
        nights = [d + timedelta(days=1) for d in alc]
        alc_stat = {"n": len(alc), "hrv": avgl([devm(hmap, d) for d in nights]), "rhr": avgl([devm(rhr, d) for d in nights]),
                    "sen": avgl([devm(slp, d) for d in nights]), "ostatni": max(alc).isoformat() if alc else None}
        links = {"alkohol": alc_stat, "hrv_po_deficycie": {"n_duzy": len(big), "n_inne": len(oth),
                                      "duzy": round(sum(big) / len(big), 1) if big else None, "inne": round(sum(oth) / len(oth), 1) if oth else None}}
        # cisnienie rano vs sol/deficyt dnia poprzedniego i waga
        mbp = []
        for m in bp:
            lt = m["measured_local"]
            if lt and lt.hour < 12:
                d = lt.date()
                w = next((v for dd, v in reversed(wts) if dd <= d), None)
                mbp.append({"d": d, "sys": m["systolic"], "dia": m["diastolic"], "salt_prev": salt.get(d - timedelta(days=1)),
                            "bal_prev": bal.get(d - timedelta(days=1)), "weight": w})
        def grp(f):
            a = [x["sys"] for x in mbp if f(x) is True]
            b = [x["sys"] for x in mbp if f(x) is False]
            return {"n_a": len(a), "n_b": len(b), "a": round(sum(a) / len(a)) if a else None, "b": round(sum(b) / len(b)) if b else None}
        links["cisnienie"] = {"pomiary_rano": len(mbp), "pomiary_wszystkie": len(bp),
                              "sol": grp(lambda x: None if x["salt_prev"] is None else x["salt_prev"] >= 8),
                              "deficyt": grp(lambda x: None if x["bal_prev"] is None else x["bal_prev"] < -500)}
        return {"hrv": {"series": [[d.isoformat(), round(h, 1)] for d, h in hrv], "norm": round(norm, 1) if norm else None,
                        "recent": round(recent, 1) if recent is not None else None, "delta": round(delta, 1) if delta is not None else None,
                        "pct": round(pct, 1) if pct is not None else None, "status": st_,
                        "status7": hrv_status7, "band": hrv_band},
                "links": links}

    @r.get("/calendar")
    def calendar(request: Request, start: str, end: str):
        """Kafelki kalendarza Trenera: zjedzone vs cel i zamkniecie dnia (tylko dni od startu jedzenia)."""
        need_user(request)
        import qbot_food_plan as FP
        import qbot_food_streaks as S
        a, b = max(_d(start), S.START), min(_d(end), datetime.now(TZ).date())
        out = {}
        if a > b or (b - a).days > 62:
            return {"days": out}
        with FP._conn() as c:
            cal, bal = FP.calibration(c), FP.target_balance(c)
            itk = {x["date"]: float(x["k"]) for x in c.execute(
                "SELECT l.date, sum(i.kcal) k FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id "
                "WHERE l.date BETWEEN %s AND %s GROUP BY l.date", (a, b)).fetchall() if x["k"]}
            closed = {x["day"] for x in c.execute("SELECT day FROM qbot_v2.food_day WHERE closed_at IS NOT NULL AND day BETWEEN %s AND %s",
                                                  (a, b)).fetchall()}
            d = a
            while d <= b:
                ex = FP.expend(c, d)
                out[d.isoformat()] = {"kcal": round(itk.get(d, 0)), "target": FP.target_for(ex, cal, bal, d),
                                      "closed": d in closed, "expend": round(ex["kcal"]), "real": ex["src"] == "realne",
                                      "plan_balance": round(bal - cal)}
                d += timedelta(days=1)
        return {"days": out}

    @r.get("/analysis")
    def analysis_get(request: Request, day: str | None = None):
        need_user(request)
        d = _d(day) if day else datetime.now(TZ).date()
        res = analysis(d)
        import qbot_food_log as F
        with F._conn() as c:
            row = c.execute("SELECT payload, created_at FROM qbot_v2.food_analysis WHERE day=%s", (d,)).fetchone()
        res["ai"] = (dict(row["payload"], created_at=row["created_at"].isoformat()) if row else None)
        return json.loads(json.dumps(res, default=_ser))

    @r.post("/analysis/ai")
    async def analysis_ai(request: Request):
        """Zalecenia AI na podstawie policzonych liczb (AI ich nie zmienia). Zapis per dzien."""
        need_owner(request)
        b = await body(request)
        d = _d(b.get("day")) if b.get("day") else datetime.now(TZ).date()
        res = json.loads(json.dumps(analysis(d), default=_ser))
        import qbot_food_log as F
        prompt = ("Jesteś dietetykiem sportowym. Użytkownik: mężczyzna ~104 kg, redukcja do 90 kg, kolarz gravel, catering Brokuł w dni robocze, "
                  "w weekend je na mieście. Dostajesz POLICZONE dane dnia i tygodnia (nie zmieniaj liczb, nie licz własnych). "
                  "Zwróć WYŁĄCZNIE JSON: {\"dzis\": [\"...\"], \"tydzien\": [\"...\"], \"weekend\": [\"...\"]}. "
                  "Każda lista maks. 3 krótkie, konkretne zalecenia po polsku (co zjeść / czego unikać / co zmienić), prosty język, bez moralizowania. "
                  "\"weekend\" tylko w czwartek-niedzielę: co zamawiać na mieście, inaczej pusta lista.")
        try:
            j = F._ai_json(prompt, [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}])
        except Exception as ex:
            raise HTTPException(status_code=502, detail="AI niedostępne: %s" % type(ex).__name__)
        pay = {k: [str(x)[:300] for x in (j.get(k) or [])][:3] for k in ("dzis", "tydzien", "weekend")}
        with F._conn() as c:
            c.execute("INSERT INTO qbot_v2.food_analysis (day, payload) VALUES (%s,%s) ON CONFLICT (day) DO UPDATE SET payload=EXCLUDED.payload, created_at=now()",
                      (d, json.dumps(pay, ensure_ascii=False)))
            c.commit()
        return {"ok": True, "ai": pay}

    # ------------------------------------------------------------------ zapis
    async def body(request) -> dict:
        try:
            b = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="zły JSON")
        if not isinstance(b, dict):
            raise HTTPException(status_code=400, detail="zły JSON")
        return b

    def refresh(*days):
        import qbot_food_log as F
        for d in {x for x in days if x}:
            F.refresh_day(d)

    @r.post("/brokul")
    async def brokul_set(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_brokul_meals as M
        st = str(b.get("status") or "")
        if st not in ("eaten", "skipped", "pending", "fridge", "discarded"):
            raise HTTPException(status_code=400, detail="zły status")
        ed = _d(b["eaten_day"]) if b.get("eaten_day") else None
        res = M.set_status(int(b.get("id")), st, eaten_day=ed)
        refresh(res["day"], ed)
        return {"ok": True}

    @r.post("/brokul/all")
    async def brokul_all(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_brokul_meals as M
        day = _d(b.get("day"))
        st = "eaten" if b.get("action") == "eaten" else "fridge"
        n = 0
        for m in M.day_meals(day):
            if m["status"] == "pending":
                M.set_status(m["id"], st)
                n += 1
        refresh(day)
        return {"ok": True, "n": n}

    @r.post("/window")
    async def window(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_food_streaks as S
        day = _d(b.get("day"))
        res = S.set_window(day, bool(b.get("ok")))
        if res == "late":
            raise HTTPException(status_code=409, detail="Termin minął (12:00 następnego dnia)")
        refresh(day)
        return {"ok": True}

    @r.post("/none")
    async def none_(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_food_log as F
        day = _d(b.get("day"))
        with F._conn() as c:
            c.execute("INSERT INTO qbot_v2.food_day (day, extras_none) VALUES (%s, %s) ON CONFLICT (day) DO UPDATE "
                      "SET extras_none=EXCLUDED.extras_none, updated_at=now()", (day, bool(b.get("value", True))))
            c.commit()
        refresh(day)
        return {"ok": True}

    @r.post("/quick")
    async def quick(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_food_log as F
        day, code = _d(b.get("day")), str(b.get("code") or "")
        if code not in F.QUICK:
            raise HTTPException(status_code=400, detail="zły kod")
        lab, k, pr, cb, ft = F.QUICK[code]
        eid = F.create_entry("quick", day, raw_text=lab, items=[{"name": lab, "portion": "szacunek", "kcal": k, "protein_g": pr,
                                                                 "carbs_g": cb, "fat_g": ft, "conf": "zgrubne", "src": "szacunek",
                                                                 "short": lab[:24]}])
        with F._conn() as c:
            F._write_intake(c, F._get(c, eid))
            c.commit()
        refresh(day)
        return {"ok": True, "id": eid}

    @r.post("/entry")
    async def entry_add(request: Request):
        """Dodaj wpis tekstem (AI). Gdy porcja niejasna -> status 'asking' + options (wybor: /entry/option)."""
        need_owner(request)
        b = await body(request)
        import qbot_food_log as F
        text = str(b.get("text") or "").strip()[:1000]
        if len(text) < 2:
            raise HTTPException(status_code=400, detail="pusty wpis")
        day = _d(b.get("day")) if b.get("day") else F.parse_day(text, datetime.now(TZ))
        eid = F.create_entry("text", day, raw_text=text)
        try:
            res = F.estimate(text, None, F.history_refs(text), F.off_refs(text))
        except Exception as ex:
            with F._conn() as c:
                c.execute("UPDATE qbot_v2.food_entries SET status='failed', error=%s WHERE id=%s", (str(ex)[:500], eid))
                c.commit()
            raise HTTPException(status_code=502, detail="Wpis zapisany (#%d), ale AI nie policzyło kcal – spróbuje ponownie samo." % eid)
        with F._conn() as c:
            if res.get("not_food"):
                c.execute("UPDATE qbot_v2.food_entries SET status='not_food' WHERE id=%s", (eid,))
                c.commit()
                raise HTTPException(status_code=422, detail="To chyba nie jedzenie – nic nie zapisano.")
            if res.get("ambiguous"):
                c.execute("UPDATE qbot_v2.food_entries SET status='asking', question=%s, options=%s, eaten_time=COALESCE(%s::time, eaten_time) WHERE id=%s",
                          (res["question"], json.dumps(res["options"], ensure_ascii=False), res.get("time"), eid))
            else:
                c.execute("UPDATE qbot_v2.food_entries SET items=%s, eaten_time=COALESCE(%s::time, eaten_time) WHERE id=%s",
                          (json.dumps(res["items"], ensure_ascii=False), res.get("time"), eid))
                F._write_intake(c, F._get(c, eid))
            c.commit()
            e = F._get(c, eid)
        refresh(day)
        return {"ok": True, "entry": _row(e, ENTRY_KEYS)}

    def _entry(c, eid):
        import qbot_food_log as F
        e = F._get(c, eid)
        if not e or e["status"] in ("deleted", "not_food"):
            raise HTTPException(status_code=404, detail="nie ma takiego wpisu")
        return e

    @r.post("/entry/option")
    async def entry_option(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_food_log as F
        with F._conn() as c:
            e = _entry(c, int(b.get("id")))
            opts = e["options"] or []
            i = int(b.get("idx", -1))
            if e["status"] != "asking" or not (0 <= i < len(opts)):
                raise HTTPException(status_code=400, detail="zły wariant")
            c.execute("UPDATE qbot_v2.food_entries SET items=%s, scale=1 WHERE id=%s", (json.dumps(opts[i]["items"], ensure_ascii=False), e["id"]))
            F._write_intake(c, F._get(c, e["id"]))
            F._learn(c, F._get(c, e["id"]))
            c.commit()
        refresh(e["day"])
        return {"ok": True}

    @r.post("/entry/scale")
    async def entry_scale(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_food_log as F
        with F._conn() as c:
            e = _entry(c, int(b.get("id")))
            if e["status"] != "logged":
                raise HTTPException(status_code=400, detail="wpis nie jest policzony")
            step = F.SCALE_STEP if b.get("dir") == "up" else -F.SCALE_STEP
            sc = max(0.25, round((e["scale"] or 1) + step, 2))
            c.execute("UPDATE qbot_v2.food_entries SET scale=%s WHERE id=%s", (sc, e["id"]))
            F._write_intake(c, F._get(c, e["id"]))
            c.commit()
        refresh(e["day"])
        return {"ok": True, "scale": sc}

    @r.post("/entry/fix")
    async def entry_fix(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_food_log as F
        fix = str(b.get("text") or "").strip()[:500]
        if len(fix) < 2:
            raise HTTPException(status_code=400, detail="pusta poprawka")
        with F._conn() as c:
            e = _entry(c, int(b.get("id")))
            if e["status"] != "logged":
                raise HTTPException(status_code=400, detail="wpis nie jest policzony")
            sc = e["scale"] or 1
            base = [dict(i, kcal=round(i["kcal"] * sc, 1), protein_g=round(i["protein_g"] * sc, 1),
                         carbs_g=round(i["carbs_g"] * sc, 1), fat_g=round(i["fat_g"] * sc, 1)) for i in e["items"]]
            try:
                items = F.correct_items(base, fix)
            except Exception:
                raise HTTPException(status_code=502, detail="AI nie zastosowało poprawki – wpis bez zmian")
            c.execute("UPDATE qbot_v2.food_entries SET items=%s, scale=1 WHERE id=%s", (json.dumps(items, ensure_ascii=False), e["id"]))
            F._write_intake(c, F._get(c, e["id"]))
            c.commit()
        refresh(e["day"])
        return {"ok": True}

    @r.post("/entry/move")
    async def entry_move(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_food_log as F
        nd = _d(b.get("day"))
        with F._conn() as c:
            e = _entry(c, int(b.get("id")))
            c.execute("UPDATE qbot_v2.food_entries SET day=%s WHERE id=%s", (nd, e["id"]))
            if e["status"] == "logged":
                F._write_intake(c, F._get(c, e["id"]))
            c.commit()
        refresh(e["day"], nd)
        return {"ok": True}

    @r.post("/entry/delete")
    async def entry_delete(request: Request):
        need_owner(request)
        b = await body(request)
        import qbot_food_log as F
        import qbot_brokul_meals as M
        with F._conn() as c:
            e = _entry(c, int(b.get("id")))
            M.remove_intake(c, e["intake_log_id"])
            c.execute("UPDATE qbot_v2.food_entries SET status='deleted', intake_log_id=NULL, updated_at=now() WHERE id=%s", (e["id"],))
            c.commit()
        refresh(e["day"])
        return {"ok": True}

    return r
