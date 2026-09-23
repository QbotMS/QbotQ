#!/usr/bin/env python3
"""TRENER - Etap 5: powiadomienia Telegram (plan tygodnia, przypomnienia w dniu treningu, rozliczenie tygodnia).

Uruchamiane z crona co 15 min:  QBOT3_ENABLED=1 .venv/bin/python3 qbot_trener_notify.py tick
Podglad bez wysylki:           .venv/bin/python3 qbot_trener_notify.py preview plan|day|review [RRRR-MM-DD]
Test (wysyla 1 wiadomosc):      .venv/bin/python3 qbot_trener_notify.py send-test

Ustawienia z Kalibracji (trainer_settings.overrides, domyslne jak w trener.js):
  notify.week_plan 0 wyl. / 1 pon 7:00 (biezacy tydzien) / 2 ndz 20:00 (nastepny tydzien)   dom. 2
  notify.day       0 wyl. / 1 rano 7:00 (lista na dzis) / 2 dwie godziny przed kazdym treningiem  dom. 1
  notify.review    0 wyl. / 1 ndz 19:00                                                         dom. 1
  notify.tone      0 lagodny / 1 rzeczowy / 2 wymagajacy                                          dom. 1
Deduplikacja: trainer_notify_log (klucz per typ i okres). Nic nie jest wysylane, gdy tydzien nie ma planu
ani celow (pusty uzytkownik). Plan na nowy tydzien generuje sie sam, jesli jeszcze go nie ma.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QBOT3_ENABLED", "1")

import qbot_trener_engine as E

TZ = ZoneInfo("Europe/Warsaw")
DEF = {"notify.week_plan": 2, "notify.day": 1, "notify.review": 1, "notify.tone": 1}
SIC = {"rower": "🚲", "sila": "🏋️", "wiosl": "🚣", "joga": "🧘"}
DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]
URL = "https://albert.cytr.us/trener.html"


def _conn():
    from fitmodel.api import _db_connect
    import psycopg.rows
    c = _db_connect()
    c.row_factory = psycopg.rows.dict_row
    return c


def pick_user(c) -> str | None:
    u = os.environ.get("TRENER_USER")
    if u:
        return u
    c.execute("""SELECT username, COUNT(*) n FROM (
                   SELECT username FROM qbot_v2.trainer_goal UNION ALL SELECT username FROM qbot_v2.trainer_rule
                   UNION ALL SELECT username FROM qbot_v2.trainer_session) x
                 WHERE username NOT LIKE '\\_%%' GROUP BY username ORDER BY n DESC LIMIT 1""")
    r = c.fetchone()
    return r["username"] if r else None


def settings(c, user: str) -> dict:
    c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username=%s", (user,))
    r = c.fetchone()
    ov = dict(r["overrides"]) if r else {}
    return {k: int(ov.get(k, v)) for k, v in DEF.items()}


def _sessions(c, user: str, d0: date, d1: date) -> list[dict]:
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s ORDER BY day, start_time NULLS LAST, id", (user, d0, d1))
    return [dict(r) for r in c.fetchall()]


def _line(s: dict, with_day: bool = True) -> str:
    st = s["start_time"].strftime("%H:%M") if s.get("start_time") else "—"
    mark = {"done": "✅ ", "skip": "✖️ "}.get(s["status"], "")
    day = f"{DN[s['day'].weekday()]} {s['day'].strftime('%d.%m')} " if with_day else ""
    return f"{mark}{day}{st} {SIC.get(s['sport'], '')} {s['name']} {s['dur_min']}′" + (" (minimum)" if s.get("cut") else "")


# ---------------- teksty (czyste, testowalne) ----------------

def text_plan(ws: date, sessions: list[dict], phase: str | None, target_h: float | None, notes: list[str] | None = None) -> str:
    act = sorted([s for s in sessions if s["status"] != "skip"], key=lambda s: (s["day"], s.get("start_time") or datetime.min.time()))
    h = sum(s["dur_min"] for s in act) / 60
    out = [f"🗓️ Plan tygodnia {ws.strftime('%d.%m')}–{(ws + timedelta(days=6)).strftime('%d.%m')}" + (f" · {phase}" if phase else ""),
           f"Razem {h:.1f} h" + (f" (cel {target_h} h)" if target_h else "") + f" · {len(act)} treningów", ""]
    cur = None
    for s in act:
        if s["day"] != cur:
            cur = s["day"]
        out.append(_line(s))
    if not act:
        out.append("Brak treningów w planie.")
    for n in (notes or [])[:4]:
        out.append("ℹ️ " + n)
    out += ["", f"Zmiany: {URL}"]
    return "\n".join(out)


def text_day(d: date, sessions: list[dict], details: dict | None = None) -> str | None:
    act = [s for s in sessions if s["status"] == "plan"]
    if not act:
        return None
    out = [f"💪 Dziś ({DN[d.weekday()]} {d.strftime('%d.%m')}):"]
    for s in act:
        out.append(_line(s, False))
        dt = (details or {}).get(s.get("id"))
        if dt and s["sport"] in ("sila", "wiosl"):
            out.append(dt)
    return "\n".join(out + ["", "Gorszy dzień? W Trenerze: ⋯ → brak czasu (wersje minimum) albo REST DAY.", URL])


def session_details(c, user: str, sessions: list[dict], phase: str | None) -> dict:
    import qbot_trener_workouts as TW
    out = {}
    for s in sessions:
        if s.get("id") and s["sport"] in ("sila", "wiosl"):
            n = TW.strength_index(c, user, s) if s["sport"] == "sila" else 0
            out[s["id"]] = TW.details(s["sport"], phase, s["dur_min"], bool(s.get("cut")), n)["text"]
    return out


def text_pre(s: dict) -> str:
    return f"⏰ Za 2 h: {_line(s, False)}\n" + (s.get("note") or "") + ("\n" if s.get("note") else "") + URL


def text_review(ws: date, sessions: list[dict], extra_h: float, tone: int, weight_slope: float | None) -> str:
    plan = [s for s in sessions if s["status"] != "skip" or True]
    planned = [s for s in plan]
    done = [s for s in planned if s["status"] == "done"]
    skipped = [s for s in planned if s["status"] == "skip"]
    missed = [s for s in planned if s["status"] == "plan" and s["day"] < date.today()]
    ph = sum(s["dur_min"] for s in planned if s["status"] != "skip") / 60
    dh = sum(s["dur_min"] for s in done) / 60 + extra_h
    pct = round(100 * dh / ph) if ph else None
    out = [f"📊 Rozliczenie tygodnia {ws.strftime('%d.%m')}–{(ws + timedelta(days=6)).strftime('%d.%m')}",
           f"Zrobione {dh:.1f} h z {ph:.1f} h planu" + (f" ({pct}%)" if pct is not None else "") + f" · treningi ✅ {len(done)} / {len(planned)}"]
    by = {}
    for s in planned:
        b = by.setdefault(s["sport"], [0, 0]); b[0] += 1
        if s["status"] == "done":
            b[1] += 1
    if by:
        out.append(" · ".join(f"{SIC.get(k, k)} {v[1]}/{v[0]}" for k, v in by.items()))
    if extra_h >= 0.2:
        out.append(f"Poza planem: {extra_h:.1f} h")
    if missed or skipped:
        out.append("Nie wyszło: " + "; ".join(_line(s) for s in (missed + skipped)[:5]))
    if weight_slope is not None:
        out.append(f"Waga (30 dni): {weight_slope:+.2f} kg/tydz.")
    if pct is None:
        verdict = "Brak planu w tym tygodniu."
    elif pct >= 90:
        verdict = ["Świetnie — tak trzymaj.", "Plan wykonany.", "Wykonane. Nie spoczywaj."][tone]
    elif pct >= 60:
        verdict = ["Dobrze, choć nie wszystko wyszło — w przyszłym tygodniu spokojnie dalej.",
                   "Większość zrobiona. Sprawdź, co przeszkodziło, i popraw okna w Dostępności.",
                   "Za mało. Następny tydzień bez wymówek — zaplanuj krótkie wersje zamiast pomijać."][tone]
    else:
        verdict = ["Trudny tydzień — to się zdarza. Zacznij od małego kroku.",
                   "Plan w dużej części nie wyszedł. Zmniejsz budżet albo przesuń okna, żeby był realny.",
                   "Tydzień przegrany. Ustal jeden trening, którego NIE odpuścisz, i zrób go."][tone]
    out += ["", verdict, URL]
    return "\n".join(out)


# ---------------- wysylka ----------------

def send(text: str) -> tuple[bool, str]:
    import qbot_config as cfg
    tok, chat = getattr(cfg, "TELEGRAM_TOKEN", None), getattr(cfg, "TELEGRAM_CHAT_ID", None)
    if not tok or not chat:
        return False, "brak TELEGRAM_TOKEN/CHAT_ID"
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",
                                     data=json.dumps({"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
        return bool(j.get("ok")), "ok" if j.get("ok") else str(j)[:200]
    except Exception as e:
        return False, str(e)[:200]


def _once(c, key: str, user: str, text: str | None, dry: bool) -> str:
    if not text:
        return f"{key}: pusto"
    c.execute("SELECT 1 FROM qbot_v2.trainer_notify_log WHERE key=%s", (key,))
    if c.fetchone():
        return f"{key}: już wysłane"
    if dry:
        return f"{key}: [DRY]\n{text}"
    ok, det = send(text)
    c.execute("INSERT INTO qbot_v2.trainer_notify_log (key, username, ok, detail) VALUES (%s,%s,%s,%s) ON CONFLICT (key) DO NOTHING", (key, user, ok, det))
    return f"{key}: {'wysłane' if ok else 'BŁĄD ' + det}"


def _ensure_plan(c, user: str, ws: date) -> dict:
    """Plan tygodnia: gdy brak sesji auto/recznych na przyszle dni - wygeneruj (jak przycisk 'przelicz')."""
    ctx = E.build_context(c, user, ws)
    res = E.plan_week(ctx)
    have = _sessions(c, user, ws, ws + timedelta(days=6))
    if not have and ws + timedelta(days=6) >= date.today():
        cols = ["day", "sport", "name", "start_time", "dur_min", "min_min", "zone", "xss", "is_long", "status", "cut", "source", "note"]
        for x in res["sessions"]:
            c.execute(f"INSERT INTO qbot_v2.trainer_session (username,{','.join(cols)}) VALUES (%s,{','.join(['%s'] * len(cols))})", [user] + [x.get(k) for k in cols])
        c.execute("INSERT INTO qbot_v2.trainer_change (username, week_start, action, payload, accepted) VALUES (%s,%s,'telegram_autoplan','{}'::jsonb,true)", (user, ws))
    return res


def tick(now: datetime | None = None, dry: bool = False) -> list[str]:
    now = (now or datetime.now(TZ)).astimezone(TZ)
    today, hm = now.date(), now.hour * 60 + now.minute
    log = []
    conn = _conn()
    try:
        c = conn.cursor()
        user = pick_user(c)
        if not user:
            return ["brak użytkownika Trenera — nic do wysłania"]
        st = settings(c, user)
        ws = E.monday(today)
        yr, wk, _ = today.isocalendar()
        c.execute("SELECT * FROM qbot_v2.trainer_goal WHERE username=%s", (user,))
        _goals = [dict(x) for x in c.fetchall()]
        c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username=%s", (user,))
        _r = c.fetchone(); _ov = dict(_r["overrides"]) if _r else {}
        if 5 * 60 <= hm < 5 * 60 + 15:  # co noc: biezacy tydzien + 2 kolejne maja plan (puste tygodnie planuja sie same)
            for k_ in range(3):
                w_ = ws + timedelta(weeks=k_)
                if not _sessions(c, user, w_, w_ + timedelta(days=6)):
                    _ensure_plan(c, user, w_)
                    log.append(f"horyzont: zaplanowano tydzień {w_.isoformat()}")
            conn.commit()
        if E.season_weeks(_goals, _ov, ws, 1)[0]["ph"] == "lz":
            return log + [f"{now.strftime('%a %H:%M')}: totalny luz — bez wiadomości"]
        # rozliczenie: ndz 19:00-19:59
        if st["notify.review"] == 1 and today.weekday() == 6 and 19 * 60 <= hm < 20 * 60:
            ses = _sessions(c, user, ws, ws + timedelta(days=6))
            linked = {s["training_session_id"] for s in ses if s.get("training_session_id")}
            c.execute("SELECT id, duration_s FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (ws, ws + timedelta(days=6)))
            extra = sum((r["duration_s"] or 0) for r in c.fetchall() if r["id"] not in linked) / 3600
            import qbot_trener_stats as ST
            slope = ST.balance(ST.load_days(c, 45), 30, 2)["weight_slope_kg_wk"]
            log.append(_once(c, f"review:{yr}-W{wk:02d}", user, text_review(ws, ses, extra, st["notify.tone"], slope) if ses else None, dry))
        # plan tygodnia
        send_plan = None
        if st["notify.week_plan"] == 1 and today.weekday() == 0 and 7 * 60 <= hm < 8 * 60:
            send_plan = ws
        if st["notify.week_plan"] == 2 and today.weekday() == 6 and 20 * 60 <= hm < 21 * 60:
            send_plan = ws + timedelta(days=7)
        if send_plan:
            res = _ensure_plan(c, user, send_plan) if not dry else E.plan_week(E.build_context(c, user, send_plan))
            ses = _sessions(c, user, send_plan, send_plan + timedelta(days=6)) or [dict(s, day=date.fromisoformat(s["day"]), start_time=datetime.strptime(s["start_time"], "%H:%M").time() if s.get("start_time") else None) for s in res["sessions"]]
            y2, w2, _ = send_plan.isocalendar()
            log.append(_once(c, f"plan:{y2}-W{w2:02d}", user, text_plan(send_plan, ses, res.get("phase_name"), res.get("target_h"), res.get("notes")) if ses else None, dry))
        # dzien
        if st["notify.day"] == 1 and 7 * 60 <= hm < 8 * 60:
            tses = _sessions(c, user, today, today)
            ph = E.plan_week(E.build_context(c, user, ws))["phase"] if tses else None
            log.append(_once(c, f"day:{today.isoformat()}", user, text_day(today, tses, session_details(c, user, tses, ph)), dry))
        if st["notify.day"] == 2:
            for s in _sessions(c, user, today, today):
                if s["status"] != "plan" or not s.get("start_time"):
                    continue
                t0 = s["start_time"].hour * 60 + s["start_time"].minute - 120
                if t0 <= hm < t0 + 15:
                    log.append(_once(c, f"pre:{s['id']}", user, text_pre(s), dry))
        conn.commit()
    finally:
        conn.close()
    return log or [f"{now.strftime('%a %H:%M')}: nic do wysłania"]


def albert_summary(week_start: str | None = None) -> dict:
    """Odczyt dla Alberta (tylko czyta): plan tygodnia z Trenera + statusy celow + bilans. Nic nie zapisuje."""
    d = date.fromisoformat(week_start) if week_start else date.today()
    ws = E.monday(d)
    conn = _conn()
    try:
        c = conn.cursor()
        user = pick_user(c)
        if not user:
            return {"status": "DATA_MISSING", "error": "Trener nie ma jeszcze danych (brak celów, wpisów i planu)"}
        res = E.plan_week(E.build_context(c, user, ws))
        ses = _sessions(c, user, ws, ws + timedelta(days=6))
        import qbot_trener_stats as ST
        c.execute("SELECT * FROM qbot_v2.trainer_goal WHERE username=%s AND status IN ('active','paused')", (user,))
        goals = [dict(x) for x in c.fetchall()]
        gst = ST.compute_goal_status(c, goals)
        c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username=%s", (user,))
        r = c.fetchone()
        bal = ST.compute_balance(c, dict(r["overrides"]) if r else {}, goals)["window"]
        conn.rollback()
    finally:
        conn.close()
    det = {}
    if ses:
        conn2 = _conn()
        try:
            det = session_details(conn2.cursor(), user, [s for s in ses if s["status"] == "plan" and s["day"] >= date.today()], res["phase"])
        finally:
            conn2.close()
    lines = [text_plan(ws, ses, res["phase_name"], res["target_h"], res["notes"]) if ses else
             f"Tydzień {ws.isoformat()}: brak zapisanego planu (faza {res['phase_name']}, cel {res['target_h']} h) — plan tworzy się przyciskiem „przelicz tydzień” w Trenerze."]
    if det:
        lines.append("\nZestawy ćwiczeń (nadchodzące sesje):")
        for s in ses:
            if s.get("id") in det:
                lines.append(f"\n{_line(s)}\n{det[s['id']]}")
    if goals:
        lines.append("\nCele:")
        for g in goals:
            v = gst.get(str(g["id"]), {})
            lines.append(f"- {g['name']} ({g['kind']}, {g['priority']}): {v.get('text', '')}")
    if bal.get("balance_kcal") is not None:
        lines.append(f"\nBilans {bal['days']} dni: {bal['balance_kcal']:+d} kcal/d (źródło: {'logi' if bal['source'] == 'logs' else 'waga'})")
    return {"status": "OK", "analysis": "\n".join(lines), "phase": res["phase_name"], "target_h": res["target_h"],
            "sessions": len(ses), "week_start": ws.isoformat()}


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "tick"
    if cmd == "tick":
        for l in tick():
            print(datetime.now(TZ).strftime("%Y-%m-%d %H:%M"), l)
        return 0
    if cmd == "preview":
        what = argv[2] if len(argv) > 2 else "plan"
        d = date.fromisoformat(argv[3]) if len(argv) > 3 else date.today()
        conn = _conn()
        try:
            c = conn.cursor(); user = pick_user(c)
            if not user:
                print("brak użytkownika Trenera"); return 0
            ws = E.monday(d)
            if what == "plan":
                res = E.plan_week(E.build_context(c, user, ws))
                ses = _sessions(c, user, ws, ws + timedelta(days=6)) or [dict(s, day=date.fromisoformat(s["day"]), start_time=datetime.strptime(s["start_time"], "%H:%M").time()) for s in res["sessions"]]
                print(text_plan(ws, ses, res["phase_name"], res["target_h"], res["notes"]))
            elif what == "day":
                print(text_day(d, _sessions(c, user, d, d)) or "(dziś brak treningów w planie)")
            else:
                print(text_review(ws, _sessions(c, user, ws, ws + timedelta(days=6)), 0.0, settings(c, user)["notify.tone"], None))
            conn.rollback()
        finally:
            conn.close()
        return 0
    if cmd == "send-test":
        print(send("✅ QBot Trener: test powiadomień. Plan tygodnia, przypomnienia i rozliczenie będą przychodzić tutaj.\n" + URL))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
