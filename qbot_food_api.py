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
    tgt = max(FP.FLOOR_KCAL, round((ex["kcal"] - plan_ctx["calib"] + plan_ctx["balance"]) / 50) * 50)
    bk = sum(m["kcal"] or 0 for m in meals) if meals else None
    return {"day": day.isoformat(), "weekday": F.DNI[day.weekday()], "has_diet": bool(meals), "meals": meals, "fridge": fridge,
            "entries": [_row(e, ENTRY_KEYS) for e in ents], "closed": cs["closed"], "none": cs["none"], "pending": cs["pending"],
            "window": {"state": ws, "detail": wd}, "totals": {k: round(v or 0) for k, v in tot.items()},
            "target": tgt, "expend": round(ex["kcal"]), "expend_src": ex["src"], "brokul_kcal": bk,
            "extra": max(0, tgt - bk) if bk else None, "sessions": ses,
            "deadline": S.deadline(day).isoformat(), "late": S._past(day, datetime.now(TZ))}


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
    def balance(request: Request, days: int = 42):
        need_user(request)
        import qbot_food_plan as FP
        import qbot_food_streaks as S
        import qbot_trener_stats as ST
        days = max(7, min(120, days))
        today = datetime.now(TZ).date()
        a = today - timedelta(days=days)
        with FP._conn() as c:
            cal, bal = FP.calibration(c), FP.target_balance(c)
            itk = {x["date"]: float(x["k"]) for x in c.execute(
                "SELECT l.date, sum(i.kcal) k FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id "
                "WHERE l.date BETWEEN %s AND %s GROUP BY l.date", (a, today)).fetchall() if x["k"]}
            closed = {x["day"] for x in c.execute("SELECT day FROM qbot_v2.food_day WHERE closed_at IS NOT NULL AND day BETWEEN %s AND %s",
                                                  (a, today)).fetchall()}
            series, d = [], a
            while d <= today:
                ex = FP.expend(c, d)
                series.append({"day": d.isoformat(), "intake": round(itk[d]) if d in itk else None, "expend": round(ex["kcal"]),
                               "expend_src": ex["src"], "closed": d in closed,
                               "target": max(FP.FLOOR_KCAL, round((ex["kcal"] - cal + bal) / 50) * 50)})
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
        disc = json.loads(json.dumps(S.discrepancy(), default=_ser))
        return {"series": series, "weeks": wk, "balance_target": bal, "calib": cal, "discrepancy": disc,
                "discrepancy_line": S.discrepancy_line(), "goal": goal}

    @r.get("/menu")
    def menu(request: Request):
        need_user(request)
        import qbot_brokul_meals as M
        import qbot_brokul as B
        today = datetime.now(TZ).date()
        with M._conn() as c:
            meals = c.execute("SELECT * FROM qbot_v2.brokul_meals WHERE day >= %s AND status <> 'cancelled' ORDER BY day, meal_order",
                              (today,)).fetchall()
            fridge = c.execute("SELECT * FROM qbot_v2.brokul_meals WHERE status='fridge' ORDER BY day, meal_order").fetchall()
            dd = [x["day"].isoformat() for x in c.execute("SELECT DISTINCT day FROM qbot_v2.brokul_delivery_days WHERE day >= %s ORDER BY day",
                                                           (today - timedelta(days=14),)).fetchall()]
        st = B.state()
        return {"meals": [_row(m, MEAL_KEYS) for m in meals], "fridge": [_row(m, MEAL_KEYS) for m in fridge],
                "delivery_days": dd, "order_end": _ser(M.delivery_end()), "session_alive": bool(st.get("alive")),
                "last_import": st.get("last_import"), "access_url": "/brokul-dostep"}

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
