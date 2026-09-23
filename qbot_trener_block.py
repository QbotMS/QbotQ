"""TRENER - model bloku (cykle zamiast pojedynczych tygodni) + porownanie z obecnym silnikiem. TYLKO PODGLAD.

Idea: obciazenie sterowane forma i zmeczeniem (XSS -> CTL tau 42 dni, ATL tau 7 dni, TSB = CTL - ATL, jak w ModelQ),
liczone razem dla biezacego + 2 kolejnych tygodni:
  * cel formy wg okresu Sezonu: przyrost CTL na tydzien (RAMP),
  * potrzebne dzienne XSS ~= CTL + 6 * przyrost (rownanie CTL przy tau 42 dla 7 dni),
  * czesc tygodnia zajeta przez jazdy z Kalendarza / wyprawy / Twoje sesje jest "stala"; reszta -> godziny (~45 XSS/h),
    obcieta do budzetu dostepnego czasu,
  * dzien z TSB rano ponizej progu (TSB_FLOOR) = dzien zmeczenia: bez roweru / sily / wioslarza (joga ok),
  * nadwyzka z wyprawy nie zeruje nastepnego tygodnia - model liczy forme i zmeczenie dzien po dniu.
Obecny silnik (plan_week per tydzien) liczony obok na tych samych danych. Nic nie zapisuje.
Testy: tests/test_trener_block.py.
"""
from __future__ import annotations

from datetime import date, timedelta

import qbot_trener_engine as E

RAMP = {"bz": 3.0, "bd": 4.0, "sz": 0.0, "rt": -2.0, "tp": -5.0, "rg": -3.0, "ev": 0.0, "lz": -4.0}
TSB_FLOOR = -25.0
XSS_PER_H = 45.0
CTL_T, ATL_T = 42.0, 7.0


def step(ctl: float, atl: float, x: float) -> tuple[float, float]:
    return ctl + (x - ctl) / CTL_T, atl + (x - atl) / ATL_T


def simulate(ctl0: float, atl0: float, days: list[date], xss: dict) -> list[dict]:
    """Dzien po dniu: TSB RANO (przed treningiem) = CTL - ATL z dnia poprzedniego."""
    out, ctl, atl = [], ctl0, atl0
    for d in days:
        tsb_am = ctl - atl
        ctl, atl = step(ctl, atl, float(xss.get(d, 0)))
        out.append({"day": d.isoformat(), "xss": round(float(xss.get(d, 0))), "ctl": round(ctl, 1), "atl": round(atl, 1), "tsb_am": round(tsb_am, 1)})
    return out


def _xss_by_day(sessions: list) -> dict:
    x: dict = {}
    for s in sessions:
        if s.get("status") == "skip":
            continue
        d = E._d(s["day"])
        x[d] = x.get(d, 0.0) + float(s.get("xss") or E.xss_of(s["sport"], s.get("zone"), int(s["dur_min"])))
    return x


def _carry_from(sessions: list, ws: date, hard: float) -> list:
    out = []
    for s in sessions:
        d = E._d(s["day"])
        if s["sport"] == "rower" and s.get("status") != "skip" and ws - timedelta(days=3) <= d < ws:
            out.append({"day": d, "name": s["name"], "xss": float(s.get("xss") or 0), "is_long": bool(s.get("is_long"))})
    return out


def _fresh_ctx(c, user: str, ws: date) -> dict:
    ctx = E.build_context(c, user, ws)
    ctx["keep"] = [k for k in ctx.get("keep", []) if k.get("source") == "manual" or k.get("status") != "plan" or E._d(k["day"]) < ctx["today"]]
    return ctx


def _done_xss(c, a: date, b: date) -> dict:
    c.execute("SELECT date, COALESCE(tss,0) AS t FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (a, b))
    x: dict = {}
    for r in c.fetchall():
        x[r["date"]] = x.get(r["date"], 0.0) + float(r["t"])
    return x


def compare(c, user: str, weeks: int = 3) -> dict:
    today = date.today()
    m0 = E.monday(today)
    c.execute("SELECT day, ctl_xss, atl_raw FROM qbot_v2.fitmodel_daily WHERE ctl_xss IS NOT NULL AND day < %s ORDER BY day DESC LIMIT 1", (today,))
    r = c.fetchone()
    ctl0, atl0 = (float(r["ctl_xss"]), float(r["atl_raw"])) if r else (50.0, 40.0)
    start_day = (r["day"] + timedelta(days=1)) if r else today
    days_all = [m0 + timedelta(days=i) for i in range(7 * weeks)]
    past = _done_xss(c, m0, today - timedelta(days=1))
    c.execute("SELECT day, ctl_xss, atl_raw, xss_daily FROM qbot_v2.fitmodel_daily WHERE day BETWEEN %s AND %s ORDER BY day", (m0 - timedelta(days=1), today - timedelta(days=1)))
    fr = [dict(x) for x in c.fetchall()]
    actual_past = []
    for i, x in enumerate(fr[1:], 1):
        pv = fr[i - 1]
        actual_past.append({"day": x["day"].isoformat(), "xss": round(float(x["xss_daily"] or 0)), "ctl": round(float(x["ctl_xss"]), 1),
                            "atl": round(float(x["atl_raw"]), 1), "tsb_am": round(float(pv["ctl_xss"]) - float(pv["atl_raw"]), 1), "actual": True})
    res = {"old": {"weeks": [], "sessions": []}, "new": {"weeks": [], "sessions": []}}
    for eng in ("old", "new"):
        prev_sessions: list = []
        ctl, atl = ctl0, atl0
        # przeskok modelu do poniedzialku biezacego tygodnia nie jest potrzebny: symulujemy od start_day
        for k in range(weeks):
            ws = m0 + timedelta(weeks=k)
            ctx = _fresh_ctx(c, user, ws)
            hard = float(E.P(ctx.get("ov") or {}, "yoga.hard_xss"))
            if k > 0:
                ctx["carry"] = _carry_from(prev_sessions, ws, hard)
            wk_notes, fatigue = [], []
            if eng == "new":
                pre = E.plan_week(dict(ctx, target_h_override=0.0))   # tylko sesje stale (Kalendarz / wyprawy / Twoje)
                fixed = pre["sessions"] + [dict(s_, day=E._d(s_["day"]).isoformat()) for s_ in ctx.get("keep", []) if s_.get("status") != "skip"]
                fixed_x = _xss_by_day(fixed)
                ph = pre["phase"]
                ramp = RAMP.get(ph, 0.0)
                days_w = [ws + timedelta(days=i) for i in range(7)]
                plan_days = [d for d in days_w if d >= today]
                x_day = max(0.0, ctl + 6 * ramp)
                need = x_day * len(plan_days)
                have = sum(v for d, v in fixed_x.items() if d in plan_days)
                free_h = min(max(0.0, need - have) / XSS_PER_H, float(E.P(ctx["ov"], "load.budget_h")))
                fixed_h = sum(int(s_["dur_min"]) for s_ in fixed if E._d(s_["day"]) in days_w and s_.get("status") != "skip" and s_["sport"] != "joga") / 60
                ctx["target_h_override"] = round(fixed_h + free_h, 1)
                wk_notes.append(f"blok: {E.PH_NAME.get(ph, ph)}, cel formy {ramp:+.0f} CTL/tydz. → ~{round(x_day)} XSS/dzień; "
                                f"stałe (Kalendarz/wyprawy/Twoje) {round(have)} XSS; do dołożenia ~{free_h:.1f} h")
                # dni zmeczenia: symulacja z samymi sesjami stalymi
                sim = simulate(ctl, atl, [d for d in days_w if d >= today], fixed_x)
                fatigue = [x["day"] for x in sim if x["tsb_am"] < TSB_FLOOR and E._d(x["day"]) >= today and not fixed_x.get(E._d(x["day"]))]
                ctx["fatigue_days"] = fatigue
                for f in fatigue:
                    t_ = next(x["tsb_am"] for x in sim if x["day"] == f)
                    wk_notes.append(f"{f}: dzień luzu — zmęczenie po poprzednich dniach (świeżość TSB rano {t_:+.0f}, próg {TSB_FLOOR:+.0f})")
            out = E.plan_week(ctx)
            ses = out["sessions"] + [dict(s_, day=E._d(s_["day"]).isoformat()) for s_ in ctx.get("keep", []) if E._d(s_["day"]) >= today and s_.get("status") != "skip"]
            # druga iteracja nowego modelu: jesli plan sam wpedza w zmeczenie, luzujemy te dni
            if eng == "new":
                sim2 = simulate(ctl, atl, [ws + timedelta(days=i) for i in range(7) if ws + timedelta(days=i) >= today], _xss_by_day(ses))
                extra = [x["day"] for x in sim2 if x["tsb_am"] < TSB_FLOOR and E._d(x["day"]) >= today and x["day"] not in fatigue
                         and not fixed_x.get(E._d(x["day"]))]
                if extra:
                    ctx["fatigue_days"] = fatigue + extra
                    for f in extra:
                        wk_notes.append(f"{f}: dzień luzu — plan tygodnia podbiłby zmęczenie ponizej progu")
                    out = E.plan_week(ctx)
                    ses = out["sessions"] + [dict(s_, day=E._d(s_["day"]).isoformat()) for s_ in ctx.get("keep", []) if E._d(s_["day"]) >= today and s_.get("status") != "skip"]
            days_w = [ws + timedelta(days=i) for i in range(7)]
            x_w = _xss_by_day(ses)
            sim = actual_past[:] if k == 0 else []
            sim += simulate(ctl, atl, [d for d in days_w if d >= today], x_w)
            ctl, atl = sim[-1]["ctl"], sim[-1]["atl"]
            x_w = {**{d: past.get(d, 0) for d in days_w if d < today}, **x_w}
            res[eng]["weeks"].append({"start": ws.isoformat(), "phase": out["phase_name"], "target_h": out["target_h"],
                                      "hours": round(sum(int(s_["dur_min"]) for s_ in ses) / 60, 1), "xss": round(sum(x_w.values())),
                                      "ctl_start": round(sim[0]["ctl"], 1),
                                      "ctl_end": sim[-1]["ctl"], "tsb_min": min(x["tsb_am"] for x in sim),
                                      "free_days": sum(1 for d in days_w if d >= today and not any(E._d(s_["day"]) == d and s_["sport"] != "joga" for s_ in ses)),
                                      "notes": (wk_notes + out["notes"]), "sim": sim})
            res[eng]["sessions"] += [{"day": E._d(s_["day"]).isoformat(), "sport": s_["sport"], "name": s_["name"], "start": (str(s_.get("start_time"))[:5] if s_.get("start_time") else None),
                                      "dur": int(s_["dur_min"]), "xss": round(float(s_.get("xss") or 0)), "long": bool(s_.get("is_long"))} for s_ in ses]
            prev_sessions = ses
    # roznice dzien po dniu
    def sig(eng, d):
        return sorted((s_["sport"], s_["dur"] // 15) for s_ in res[eng]["sessions"] if s_["day"] == d)
    diff_days = [d.isoformat() for d in days_all if d >= today and sig("old", d.isoformat()) != sig("new", d.isoformat())]
    ow, nw = res["old"]["weeks"], res["new"]["weeks"]
    bullets = []
    for i in range(weeks):
        bullets.append(f"tydz. {ow[i]['start'][8:10]}.{ow[i]['start'][5:7]}: obecny {ow[i]['hours']} h / {ow[i]['xss']} XSS, dni wolne {ow[i]['free_days']}, "
                       f"najniższa świeżość {ow[i]['tsb_min']:+.0f} · nowy {nw[i]['hours']} h / {nw[i]['xss']} XSS, dni wolne {nw[i]['free_days']}, "
                       f"najniższa świeżość {nw[i]['tsb_min']:+.0f}")
    bullets.append(f"forma (CTL) po {weeks} tygodniach: obecny {ow[-1]['ctl_end']} · nowy {nw[-1]['ctl_end']} (start {round(ctl0, 1)})")
    return {"today": today.isoformat(), "start": m0.isoformat(), "days": [d.isoformat() for d in days_all], "ctl0": round(ctl0, 1), "atl0": round(atl0, 1),
            "tsb_floor": TSB_FLOOR, "ramp": RAMP, "old": res["old"], "new": res["new"], "diff_days": diff_days, "bullets": bullets}
