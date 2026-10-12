#!/usr/bin/env python3
"""Pasy (streaki) jedzenia i okna zywieniowego + monitor rozbieznosci waga vs jedzenie (2026-10-12). Dok.: docs/BROKUL.md

🔥 Jedzenie: dzien zamkniety uczciwie (food_day.closed_at) do 12:00 nastepnego dnia. Przekroczenie kcal NIE zrywa.
🕗 Okno 10:00-20:00 (przed 10 tylko czarna kawa, po 20 nic): klik 'Okno dotrzymane' do 12:00 nastepnego dnia (zaufanie).
   Zwolnione (neutralne - ani nie rosnie, ani nie zrywa): trening >= 90 min (wykonany albo w planie Trenera),
   delegacja / urlop / wyprawa z Kalendarza. Wpis z pora poza oknem ('o 21:30') = zlamane, chyba ze klikniesz inaczej.
Mrozenie: za kazde 7 dni pasa +1 (max 2); dzien niezaliczony zuzywa mrozenie zamiast zerowac pas. Osobne pule.
Dni przed startem (LAUNCH) bez terminu - mozna je uzupelnic kiedykolwiek, niezaliczone sa neutralne.
"""
from __future__ import annotations

import statistics as st
import time
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
START = date(2026, 10, 10)          # pierwszy dzien z wpisami
LAUNCH = date(2026, 10, 13)         # od tego dnia obowiazuje termin 12:00 nastepnego dnia
WIN_FROM, WIN_TO = dtime(10, 0), dtime(20, 0)
EXEMPT_TRAINING_MIN = 90
MILESTONES = (3, 7, 14, 30, 50, 100, 150, 200, 365)
FREEZE_EVERY, FREEZE_MAX = 7, 2
KCAL_PER_KG = 7700.0


def _conn():
    from qbot_brokul_meals import _conn as c
    return c()


def deadline(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), dtime(12, 0), tzinfo=TZ)


def _past(day: date, now: datetime) -> bool:
    return day >= LAUNCH and now > deadline(day)


def _hm(minutes: float) -> str:
    m = int(round(minutes))
    return "%d:%02d h" % (m // 60, m % 60)


# ======================================================================= okno
def exempt_reason(c, day: date) -> str | None:
    r = c.execute("SELECT event_type, title FROM qbot_v2.calendar_entry WHERE kind='event' AND %s BETWEEN day AND COALESCE(end_day, day) "
                  "AND (event_type IN ('delegacja','urlop') OR title ~* 'wyprawa') ORDER BY day LIMIT 1", (day,)).fetchone()
    if r:
        return {"delegacja": "delegacja", "urlop": "urlop"}.get(r["event_type"] or "", "wyprawa") + \
               ((": " + r["title"][:30]) if r.get("title") else "")
    r = c.execute("SELECT COALESCE(sum(duration_s),0) s, COALESCE(max(duration_s),0) m FROM qbot_v2.training_sessions WHERE date=%s",
                  (day,)).fetchone()
    if r and r["m"] >= EXEMPT_TRAINING_MIN * 60:
        return "trening " + _hm(r["m"] / 60)
    r = c.execute("SELECT max(dur_min) m FROM qbot_v2.trainer_session WHERE day=%s AND status IN ('plan','done') "
                  "AND username NOT LIKE '\\_%%'", (day,)).fetchone()
    if r and (r["m"] or 0) >= EXEMPT_TRAINING_MIN:
        return "plan: trening " + _hm(r["m"])
    return None


def _outside(t: dtime | None) -> bool:
    return t is not None and (t < WIN_FROM or t >= WIN_TO)


def window_status(c, day: date) -> tuple[str, str | None]:
    """('ok'|'broken'|'exempt'|'pending', opis)."""
    ex = exempt_reason(c, day)
    if ex:
        return "exempt", ex
    fd = c.execute("SELECT window_ok, window_set_at FROM qbot_v2.food_day WHERE day=%s", (day,)).fetchone()
    if fd and fd["window_ok"] is not None:
        if day >= LAUNCH and fd["window_set_at"] and fd["window_set_at"] > deadline(day):
            return "pending", "potwierdzone po terminie"
        return ("ok", None) if fd["window_ok"] else ("broken", "zgłoszone")
    bad = c.execute("SELECT id, eaten_time FROM qbot_v2.food_entries WHERE day=%s AND status='logged' AND eaten_time IS NOT NULL "
                    "AND (eaten_time < %s OR eaten_time >= %s) ORDER BY eaten_time LIMIT 1", (day, WIN_FROM, WIN_TO)).fetchone()
    if bad:
        return "broken", "#%d o %s" % (bad["id"], bad["eaten_time"].strftime("%H:%M"))
    return "pending", None


def set_window(day: date, ok: bool, now: datetime | None = None) -> str:
    now = now or datetime.now(TZ)
    if _past(day, now):
        return "late"
    with _conn() as c:
        c.execute("INSERT INTO qbot_v2.food_day (day, window_ok, window_set_at) VALUES (%s,%s,%s) ON CONFLICT (day) "
                  "DO UPDATE SET window_ok=EXCLUDED.window_ok, window_set_at=EXCLUDED.window_set_at, updated_at=now()",
                  (day, ok, now))
        c.commit()
    return "ok"


# ======================================================================= pasy
def _run(results: list[tuple[date, str]]) -> dict:
    """results: (dzien, 'ok'|'fail'|'neutral') rosnaco -> {n, freezes, since}."""
    n, fr, since, used = 0, 0, None, 0
    for d, r in results:
        if r == "ok":
            if n == 0:
                since = d
            n += 1
            if n % FREEZE_EVERY == 0 and fr < FREEZE_MAX:
                fr += 1
        elif r == "fail":
            if fr > 0:
                fr -= 1
                used += 1
            else:
                n, since = 0, None
    return {"n": n, "freezes": fr, "since": since, "used": used}


def streaks(now: datetime | None = None) -> dict:
    now = now or datetime.now(TZ)
    today = now.date()
    food, win = [], []
    with _conn() as c:
        fds = {r["day"]: r for r in c.execute("SELECT * FROM qbot_v2.food_day WHERE day >= %s", (START,)).fetchall()}
        d = START
        while d <= today:
            fd = fds.get(d)
            closed = fd and fd["closed_at"] and (d < LAUNCH or fd["closed_at"] <= deadline(d))
            food.append((d, "ok" if closed else ("fail" if _past(d, now) else "neutral")))
            ws, _ = window_status(c, d)
            win.append((d, {"ok": "ok", "exempt": "neutral", "broken": "fail"}.get(ws, "fail" if _past(d, now) else "neutral")))
            d += timedelta(days=1)
    return {"food": _run(food), "window": _run(win)}


def header_line(s: dict | None = None) -> str:
    s = s or streaks()
    f, w = s["food"], s["window"]
    return "🔥 Jedzenie %d · 🕗 Okno %d%s" % (f["n"], w["n"],
                                           (" · ❄️ %d/%d" % (f["freezes"], w["freezes"])) if (f["freezes"] or w["freezes"]) else "")


def check_milestones(s: dict | None = None) -> None:
    """Krotka wiadomosc przy 3/7/14/30/... dniach - raz na dany pas."""
    import qbot_brokul as B
    import qbot_food_log as F
    s = s or streaks()
    st_ = B.state()
    for kind, emo, txt in (("food", "🔥", "dni z rzędu z uczciwie zamkniętym jedzeniem"),
                           ("window", "🕗", "dni z rzędu w oknie 10–20")):
        x = s[kind]
        if x["n"] in MILESTONES and x["since"]:
            key = "ms_%s_%s_%d" % (kind, x["since"].isoformat(), x["n"])
            if not st_.get(key):
                nxt = next((m for m in MILESTONES if m > x["n"]), None)
                F.tg_send("%s %d %s!%s" % (emo, x["n"], txt, (" Następny cel: %d." % nxt) if nxt else ""))
                B._state_update(**{key: time.strftime("%Y-%m-%d %H:%M:%S")})


# ======================================================================= waga vs jedzenie
def _slope(pts: list[tuple[float, float]]) -> float | None:
    if len(pts) < 2:
        return None
    mx, my = st.mean(p[0] for p in pts), st.mean(p[1] for p in pts)
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx if sxx else None


def discrepancy(today: date | None = None, days: int = 14) -> dict:
    """Bilans z wpisow (zamkniete dni, spalanie z energy_daily) vs bilans z trendu PRAWDZIWYCH wazen (body_measurements).
    rozbieznosc = bilans_z_wagi - bilans_z_wpisow [kcal/dzien]; > 0 = waga rosnie szybciej niz tlumacza wpisy."""
    today = today or datetime.now(TZ).date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    first_ok = START + timedelta(days=7)          # 1. tydzien diety = woda, nie oceniamy
    out = {"start": start, "end": end, "ready": False, "first_result": first_ok + timedelta(days=days)}
    with _conn() as c:
        fd = {r["day"] for r in c.execute("SELECT day FROM qbot_v2.food_day WHERE closed_at IS NOT NULL AND day BETWEEN %s AND %s",
                                          (start, end)).fetchall()}
        itk = {r["date"]: float(r["k"]) for r in c.execute(
            "SELECT l.date, sum(i.kcal) k FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id "
            "WHERE l.date BETWEEN %s AND %s GROUP BY l.date", (start, end)).fetchall() if r["k"]}
        exp = {r["date"]: float(r["e"]) for r in c.execute(
            "SELECT date, COALESCE(total_kcal_eff, total_kcal) e FROM qbot_v2.energy_daily WHERE date BETWEEN %s AND %s "
            "AND quality_status <> 'partial'", (start, end)).fetchall() if r["e"]}
        ws = c.execute("SELECT date, avg(weight_kg) w FROM qbot_v2.body_measurements WHERE weight_kg IS NOT NULL "
                       "AND date BETWEEN %s AND %s GROUP BY date ORDER BY date", (start - timedelta(days=3), end)).fetchall()
    good = [d for d in fd if d in itk and d in exp]
    out.update({"closed": len(good), "weighings": len(ws)})
    span = (ws[-1]["date"] - ws[0]["date"]).days if len(ws) >= 2 else 0
    if start < first_ok or len(good) < round(days * 0.8) or len(ws) < 4 or span < 10:
        return out
    logged = st.mean(itk[d] - exp[d] for d in good)
    sl = _slope([((r["date"] - start).days, float(r["w"])) for r in ws])
    actual = sl * KCAL_PER_KG
    out.update({"ready": True, "logged_bal": round(logged), "actual_bal": round(actual), "disc": round(actual - logged),
                "kg_expected": round(logged * days / KCAL_PER_KG, 1), "kg_actual": round(sl * days, 1)})
    return out


def discrepancy_line(today: date | None = None) -> str:
    d = discrepancy(today)
    if not d["ready"]:
        return ("🍽 Waga vs jedzenie: za mało danych (zamknięte dni %d/%d, ważenia %d/4). Pierwszy wynik najwcześniej %s."
                % (d.get("closed", 0), 12, d.get("weighings", 0), d["first_result"].strftime("%d.%m")))
    x = d["disc"]
    lamp = "🟢" if abs(x) <= 150 else ("🟡" if abs(x) <= 400 else "🔴")
    why = "" if abs(x) <= 150 else (" – niezalogowane/zaniżone jedzenie albo Garmin zawyża spalanie" if x > 0
                                    else " – wpisy zawyżone albo Garmin zaniża spalanie")
    return ("🍽 Waga vs jedzenie (%s–%s): wpisy %+d kcal/dz → oczekiwane %+.1f kg, waga %+.1f kg → rozbieżność %+d kcal/dz %s%s"
            % (d["start"].strftime("%d.%m"), d["end"].strftime("%d.%m"), d["logged_bal"], d["kg_expected"], d["kg_actual"],
               x, lamp, why))
