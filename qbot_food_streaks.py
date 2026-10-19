#!/usr/bin/env python3
"""Pasy (streaki) jedzenia i okna zywieniowego + monitor rozbieznosci waga vs jedzenie (2026-10-12). Dok.: docs/BROKUL.md

🔥 Jedzenie: dzien zamkniety uczciwie (food_day.closed_at) do 12:00 nastepnego dnia. Przekroczenie kcal NIE zrywa.
🕗 Okno 10:00-20:00 (przed 10 tylko czarna kawa, po 20 nic): klik 'Okno dotrzymane' do 12:00 nastepnego dnia (zaufanie).
   2026-10-19: godziny okna mozna skorygowac dla danego dnia (food_day.window_from/window_to): start 8:00-12:00,
   koniec 18:00-22:00, co 15 min (decyzja Michala: +/-2 h od 10 i 20). NULL = domyslne 10-20.
   Zwolnione (neutralne - ani nie rosnie, ani nie zrywa): trening >= 90 min (wykonany albo w planie Trenera),
   delegacja / urlop / wyprawa z Kalendarza. Wpis z pora poza oknem ('o 21:30') = zlamane, chyba ze klikniesz inaczej.
Mrozenie: za kazde 7 ZALICZONYCH dni passy +1 (max 2; dni neutralne i uratowane sie nie licza); dzien niezaliczony
zuzywa mrozenie zamiast zerowac pas. Osobne pule.
2026-10-19 (decyzja Michala): wszystkie passy licza od PONIEDZIALKU - 🔥/🕗/📉 od STREAK_START (pn 12.10.2026),
💪 od pierwszego poniedzialku w Trenerze. Dni przed startem passy nie wchodza do licznika.
Dni przed startem (LAUNCH) bez terminu - mozna je uzupelnic kiedykolwiek, niezaliczone sa neutralne.
"""
from __future__ import annotations

import statistics as st
import time
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
START = date(2026, 10, 10)          # pierwszy dzien z wpisami (dane, monitor wagi)
STREAK_START = date(2026, 10, 12)   # 2026-10-19: passy od poniedzialku (pierwszy pn od START)
LAUNCH = date(2026, 10, 13)         # od tego dnia obowiazuje termin 12:00 nastepnego dnia
WIN_FROM, WIN_TO = dtime(10, 0), dtime(20, 0)   # domyslne okno
WIN_SHIFT_MIN, WIN_STEP_MIN = 120, 15          # korekta dnia: +/-2 h od domyslnych, co 15 min
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


def _outside(t: dtime | None, f: dtime = WIN_FROM, to: dtime = WIN_TO) -> bool:
    return t is not None and (t < f or t >= to)


def hm(t: dtime) -> str:
    return "%d:%02d" % (t.hour, t.minute)


def day_window(c, day: date) -> tuple[dtime, dtime, bool]:
    """Godziny okna dnia: (od, do, czy_skorygowane). Brak korekty = 10:00-20:00."""
    r = c.execute("SELECT window_from, window_to FROM qbot_v2.food_day WHERE day=%s", (day,)).fetchone()
    if r and r["window_from"] and r["window_to"]:
        return r["window_from"], r["window_to"], True
    return WIN_FROM, WIN_TO, False


def window_label(c, day: date) -> str:
    f, t, _ = day_window(c, day)
    return "%s–%s" % (hm(f), hm(t))


def _len_hm(f: dtime, t: dtime) -> str:
    m = (t.hour * 60 + t.minute) - (f.hour * 60 + f.minute)
    return "%d:%02d" % (m // 60, m % 60)


def confirm_window(day: date, f: dtime, t: dtime, now: datetime | None = None) -> str:
    """2026-10-19: ZATWIERDZ = godziny okna dnia + potwierdzenie. 'ok' | 'late' | 'bad'."""
    r = set_window_hours(day, f, t, now)
    if r != "ok":
        return r
    return set_window(day, True, now)


def label_for(day: date) -> str:
    with _conn() as c:
        return window_label(c, day)


def _valid_shift(t: dtime, base: dtime) -> bool:
    m, b = t.hour * 60 + t.minute, base.hour * 60 + base.minute
    return t.second == 0 and abs(m - b) <= WIN_SHIFT_MIN and m % WIN_STEP_MIN == 0


def set_window_hours(day: date, f: dtime, t: dtime, now: datetime | None = None) -> str:
    """Korekta godzin okna dla dnia. 'ok' | 'late' (po terminie) | 'bad' (poza zakresem / nie co 15 min)."""
    now = now or datetime.now(TZ)
    if _past(day, now):
        return "late"
    if not (_valid_shift(f, WIN_FROM) and _valid_shift(t, WIN_TO)):
        return "bad"
    vf, vt = (None, None) if (f, t) == (WIN_FROM, WIN_TO) else (f, t)
    with _conn() as c:
        c.execute("INSERT INTO qbot_v2.food_day (day, window_from, window_to) VALUES (%s,%s,%s) ON CONFLICT (day) "
                  "DO UPDATE SET window_from=EXCLUDED.window_from, window_to=EXCLUDED.window_to, updated_at=now()",
                  (day, vf, vt))
        c.commit()
    return "ok"


def window_status(c, day: date) -> tuple[str, str | None]:
    """('ok'|'broken'|'exempt'|'pending', opis)."""
    ex = exempt_reason(c, day)
    if ex:
        return "exempt", ex
    fd = c.execute("SELECT window_ok, window_set_at FROM qbot_v2.food_day WHERE day=%s", (day,)).fetchone()
    if fd and fd["window_ok"] is not None:
        if day >= LAUNCH and fd["window_set_at"] and fd["window_set_at"] > deadline(day):
            return "pending", "potwierdzone po terminie"
        if not fd["window_ok"]:
            return "broken", "zgłoszone"
        # 2026-10-19: zatwierdzone godziny -> wpis z pora poza nimi = zlamane (QBot liczy sam)
        wf, wt, _ = day_window(c, day)
        bad = c.execute("SELECT id, eaten_time FROM qbot_v2.food_entries WHERE day=%s AND status='logged' AND eaten_time IS NOT NULL "
                        "AND (eaten_time < %s OR eaten_time >= %s) ORDER BY eaten_time LIMIT 1", (day, wf, wt)).fetchone()
        if bad:
            return "broken", "#%d o %s – poza oknem %s" % (bad["id"], bad["eaten_time"].strftime("%H:%M"), window_label(c, day))
        return "ok", "okno trwało %s h" % _len_hm(wf, wt)
    bad = c.execute("SELECT id, eaten_time FROM qbot_v2.food_entries WHERE day=%s AND status='logged' AND eaten_time IS NOT NULL "
                    "AND (eaten_time < %s OR eaten_time >= %s) ORDER BY eaten_time LIMIT 1", (day,) + day_window(c, day)[:2]).fetchone()
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
    n, fr, since, used, days = 0, 0, None, 0, []
    for d, r in results:
        out = r
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
                out = "frozen"
            else:
                n, since = 0, None
        days.append([d.isoformat(), out])
    return {"n": n, "freezes": fr, "since": since, "used": used, "days": days}


def streaks(now: datetime | None = None) -> dict:
    now = now or datetime.now(TZ)
    today = now.date()
    food, win = [], []
    with _conn() as c:
        fds = {r["day"]: r for r in c.execute("SELECT * FROM qbot_v2.food_day WHERE day >= %s", (STREAK_START,)).fetchall()}
        d = STREAK_START
        while d <= today:
            fd = fds.get(d)
            closed = fd and fd["closed_at"] and (d < LAUNCH or fd["closed_at"] <= deadline(d))
            food.append((d, "ok" if closed else ("fail" if _past(d, now) else "neutral")))
            ws, _ = window_status(c, d)
            win.append((d, {"ok": "ok", "exempt": "neutral", "broken": "fail"}.get(ws, "fail" if _past(d, now) else "neutral")))
            d += timedelta(days=1)
    return {"food": _run(food), "window": _run(win), "train": _run(train_results(now)), "reduce": reduce_streak(now)}


def header_line(s: dict | None = None) -> str:
    s = s or streaks()
    f, w, t, r = s["food"], s["window"], s["train"], s["reduce"]
    fr = sum(x["freezes"] for x in (f, w, t))
    return "🔥 %d · 🕗 %d · 💪 %d · 📉 %d tyg.%s" % (f["n"], w["n"], t["n"], r["n"], (" · ❄️ %d" % fr) if fr else "")


# ======================================================================= 💪 Trening (dzienny)
def train_results(now: datetime) -> list[tuple[date, str]]:
    """Dzien zgodny z planem Trenera (od PIERWSZEGO dnia w Trenerze, nie od startu jedzenia - 2026-10-12):
    - brak sesji 'plan' (wykonane, zmienione przyciskiem, odpoczynek) = ok,
    - sesja 'plan' o tej samej nazwie co wykonana tego dnia = duplikat, liczy sie jak wykonana,
    - choroba albo delegacja/urlop/wyprawa w Kalendarzu = neutralnie,
    - sesja 'plan' po terminie (12:00 nastepnego dnia) = niezaliczony; dzis i do terminu = w toku."""
    today = now.date()
    out = []
    with _conn() as c:
        rows = c.execute("SELECT day, status, name FROM qbot_v2.trainer_session WHERE day <= %s AND username NOT LIKE '\\_%%'",
                         (today,)).fetchall()
        if not rows:
            return out
        t0 = min(r["day"] for r in rows)
        t0 = t0 + timedelta(days=(7 - t0.weekday()) % 7)   # 2026-10-19: od pierwszego poniedzialku w Trenerze
        cal = c.execute("SELECT day, COALESCE(end_day, day) e FROM qbot_v2.calendar_entry WHERE COALESCE(end_day, day) >= %s AND "
                        "(kind='illness' OR (kind='event' AND (event_type IN ('delegacja','urlop') OR title ~* 'wyprawa')))",
                        (t0,)).fetchall()
    by = {}
    for r in rows:
        by.setdefault(r["day"], []).append(r)
    d = t0
    while d <= today:
        ses = by.get(d, [])
        done = {x["name"] for x in ses if x["status"] == "done"}
        open_ = [x for x in ses if x["status"] == "plan" and x["name"] not in done]
        if any(i["day"] <= d <= i["e"] for i in cal) and open_:
            out.append((d, "neutral"))
        elif open_:
            out.append((d, "fail" if now > deadline(d) else "neutral"))
        elif d < today or done:
            out.append((d, "ok"))
        else:
            out.append((d, "neutral"))
        d += timedelta(days=1)
    return out


# ======================================================================= 📉 Redukcja (tygodniowy)
REDUCE_LOW, REDUCE_HIGH = 300, 250     # widelki wokol celu bilansu: [cel-300, cel+250] kcal/dz
REDUCE_MIN_WEIGH, REDUCE_MIN_DAYS = 2, 5


def week_eval(c, ws: date, tgt: int) -> dict:
    we = ws + timedelta(days=6)
    away = sum(1 for i in range(7) if c.execute(
        "SELECT 1 FROM qbot_v2.calendar_entry WHERE kind='event' AND %s BETWEEN day AND COALESCE(end_day, day) "
        "AND (event_type IN ('delegacja','urlop') OR title ~* 'wyprawa') LIMIT 1", (ws + timedelta(days=i),)).fetchone())
    nw = c.execute("SELECT count(DISTINCT date) n FROM qbot_v2.body_measurements WHERE weight_kg IS NOT NULL AND date BETWEEN %s AND %s",
                   (ws, we)).fetchone()["n"]
    rows = c.execute(
        "SELECT f.day, (SELECT sum(i.kcal) FROM qbot_v2.intake_logs l JOIN qbot_v2.intake_items i ON i.intake_log_id=l.id WHERE l.date=f.day) k, "
        "(SELECT COALESCE(total_kcal_eff,total_kcal) FROM qbot_v2.energy_daily e WHERE e.date=f.day AND quality_status<>'partial') e "
        "FROM qbot_v2.food_day f WHERE f.closed_at IS NOT NULL AND f.day BETWEEN %s AND %s", (ws, we)).fetchall()
    bal = [float(r["k"]) - float(r["e"]) for r in rows if r["k"] and r["e"]]
    avg = round(st.mean(bal)) if bal else None
    if away >= 4:
        res = "neutral"
    elif nw >= REDUCE_MIN_WEIGH and len(bal) >= REDUCE_MIN_DAYS and tgt - REDUCE_LOW <= avg <= tgt + REDUCE_HIGH:
        res = "ok"
    else:
        res = "fail"
    return {"week": ws, "res": res, "weighings": nw, "days": len(bal), "avg_balance": avg, "target": tgt, "away": away}


def reduce_streak(now: datetime) -> dict:
    """Tygodnie (pn-nd) od STREAK_START (poniedzialek); tydzien oceniany po terminie (pn 12:00). Biezacy = w toku."""
    try:
        import qbot_food_plan as FP
        with _conn() as c:
            tgt = FP.target_balance(c)
            ws = STREAK_START - timedelta(days=STREAK_START.weekday())
            res, cur = [], None
            while ws <= now.date():
                ev = week_eval(c, ws, tgt)
                if now > deadline(ws + timedelta(days=6)):
                    res.append((ws, ev["res"]))
                else:
                    cur = ev
                ws += timedelta(days=7)
        out = _run(res)
        out["current"] = cur
        return out
    except Exception as e:
        return {"n": 0, "freezes": 0, "since": None, "used": 0, "current": None, "error": str(e)[:120]}


def milestone_lines(day: date) -> list[str]:
    import qbot_brokul as B
    st_ = B.state()
    return ["🎉 " + v for k, v in st_.items() if k.endswith("_txt") and str(st_.get(k[:-4], "")).startswith(day.isoformat())]


def check_milestones(s: dict | None = None) -> None:
    """Krotka wiadomosc przy 3/7/14/30/... dniach - raz na dany pas."""
    import qbot_brokul as B
    import qbot_food_log as F
    s = s or streaks()
    st_ = B.state()
    for kind, emo, txt in (("food", "🔥", "dni z rzędu z uczciwie zamkniętym jedzeniem"),
                           ("window", "🕗", "dni z rzędu w oknie żywieniowym"),
                           ("train", "💪", "dni z rzędu zgodnie z planem treningowym (passa 💪)"),
                           ("reduce", "📉", "tygodni z rzędu w celu redukcji")):
        x = s[kind]
        if x["n"] in MILESTONES and x["since"]:
            key = "ms_%s_%s_%d" % (kind, x["since"].isoformat(), x["n"])
            if not st_.get(key):
                # 2026-10-12: bez osobnej wiadomosci - linia w wiadomosci dnia (milestone_lines)
                B._state_update(**{key: time.strftime("%Y-%m-%d %H:%M:%S"), key + "_txt": "%s %d %s" % (emo, x["n"], txt)})


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


# ======================================================================= wazenie (etap 4)
WEIGH_EVERY_DAYS = 2          # ~3-4 wazenia w tygodniu
LONG_RIDE_SKIP_MIN = 180      # dzien po jezdzie >= 3 h: waga zawyzona woda - bez przypomnienia


def weigh_line(c, today: date) -> str | None:
    """Linia '⚖️ zważ się' na 7:00 albo None. Bez dramatu: raz dziennie, tylko gdy od ostatniego PRAWDZIWEGO wazenia
    (body_measurements) minely >= 2 dni; nie w delegacji/urlopie/wyprawie i nie dzien po dlugiej jezdzie."""
    r = c.execute("SELECT max(date) d FROM qbot_v2.body_measurements WHERE weight_kg IS NOT NULL").fetchone()
    last = r["d"] if r else None
    if last and (today - last).days < WEIGH_EVERY_DAYS:
        return None
    if c.execute("SELECT 1 FROM qbot_v2.calendar_entry WHERE kind='event' AND %s BETWEEN day AND COALESCE(end_day, day) "
                 "AND (event_type IN ('delegacja','urlop') OR title ~* 'wyprawa') LIMIT 1", (today,)).fetchone():
        return None
    y = c.execute("SELECT COALESCE(max(duration_s),0) m FROM qbot_v2.training_sessions WHERE date=%s",
                  (today - timedelta(days=1),)).fetchone()
    if y and y["m"] >= LONG_RIDE_SKIP_MIN * 60:
        return None
    lw = c.execute("SELECT weight_kg FROM qbot_v2.body_measurements WHERE date=%s AND weight_kg IS NOT NULL LIMIT 1", (last,)).fetchone() if last else None
    tail = (" (ostatnie %s · %s kg)" % (last.strftime("%d.%m"), ("%.1f" % lw["weight_kg"]).replace(".", ","))) if lw else ""
    return "⚖️ Ważenie rano, przed jedzeniem" + tail
