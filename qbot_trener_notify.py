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
URL = "https://albert.cytr.us/trening.html"


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
    import qbot_trener_ratings as TR
    out, prefs = {}, None
    for s in sessions:
        if s.get("id") and s["sport"] in ("sila", "wiosl"):
            if prefs is None:
                prefs = TR.exercise_prefs(c, user)
            out[s["id"]] = TR.details_for(c, user, s, phase, prefs)["text"]
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
    dh = sum((s.get("real_min") or s["dur_min"]) for s in done) / 60 + extra_h   # zrobione = realny czas (2026-10-06)
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
    try:  # 2026-10-12: monitor rozbieznosci waga vs zalogowane jedzenie (qbot_food_streaks); bledy pomijane
        import qbot_food_streaks as _FS
        import qbot_food_plan as _FP
        out.append(_FP.week_food_line(ws))
        out.append(_FS.discrepancy_line())
    except Exception:
        pass
    out += ["", verdict, URL]
    return "\n".join(out)


# ---------------- wysylka ----------------

def day_buttons(d: date) -> list:
    """Przyciski pod wiadomoscia dnia (callback tr:<akcja>:<dzien>) - obsluga w telegram_reply_processor -> handle_callback."""
    ds = d.isoformat()
    return [[{"text": "😴 REST DAY", "callback_data": f"tr:rest:{ds}"}, {"text": "⏱️ Brak czasu", "callback_data": f"tr:short:{ds}"}],
            [{"text": "🤒 Choroba", "callback_data": f"tr:ill:{ds}"}]]


def send(text: str, buttons: list | None = None) -> tuple[bool, str]:
    import qbot_config as cfg
    tok, chat = getattr(cfg, "TELEGRAM_TOKEN", None), getattr(cfg, "TELEGRAM_CHAT_ID", None)
    if not tok or not chat:
        return False, "brak TELEGRAM_TOKEN/CHAT_ID"
    body = {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}
    if buttons:
        body["reply_markup"] = {"inline_keyboard": buttons}
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            j = json.loads(r.read().decode())
        return bool(j.get("ok")), "ok" if j.get("ok") else str(j)[:200]
    except Exception as e:
        return False, str(e)[:200]


def change_text(res: dict, head: str) -> str:
    """Krotkie podsumowanie przeliczenia (po przycisku / zmianie w Kalendarzu)."""
    L = [head]
    ch = res.get("lines") or []
    L += ["  " + x for x in ch[:8]] + (["  …"] if len(ch) > 8 else [])
    if not ch:
        L.append("  plan bez zmian w sesjach")
    for r in res.get("rolled") or []:
        L.append(f"Tydzień od {r['week_start'][8:10]}.{r['week_start'][5:7]} też zaktualizowany ({len(r['lines'])} zmian).")
    return "\n".join(L + [URL])


def _hm(m) -> str:
    m = int(round(float(m or 0)))
    return f"{m // 60}:{m % 60:02d}" if m >= 60 else f"{m}′"


def adapt_text(res: dict) -> str:
    """Wykonanie inne niz plan -> co Trener zmienil w reszcie tygodnia (czyste, testowalne)."""
    L = []
    for d in res.get("devs") or []:
        dd = date.fromisoformat(d["day"])
        more = (d.get("d_xss") or 0) > 0 or (d.get("d_xss") is None and (d.get("pct_min") or 0) > 0)
        L.append(f"{'📈' if more else '📉'} {DN[dd.weekday()]} {dd.strftime('%d.%m')} {SIC.get(d['sport'], '')} {d['name']}: "
                 f"plan {_hm(d['plan_min'])}" + (f" / obc. {round(d['plan_xss'])}" if d.get("plan_xss") is not None else "") +
                 f" → realnie {_hm(d['real_min'])}" + (f" / obc. {round(d['real_xss'])}" if d.get("real_xss") is not None else ""))
        if d.get("why"):
            L.append("   " + d["why"])
    txt = change_text(res, "\n".join(L) + "\n\nTrener przeliczył resztę tygodnia:")
    nts = [n for n in (res.get("notes") or []) if ("przerwa po ciężkiej" in n or "luz przed wyprawą" in n)][:3]
    if nts:
        txt = txt[: -len(URL)] + "\n".join("ℹ️ " + n for n in nts) + "\n" + URL
    return txt


def handle_callback(cq: dict, answer, send_plain, clear_buttons, chat_ok: str) -> None:
    """Przycisk z Telegrama: tr:rest|short|ill:<RRRR-MM-DD>, tr:undo:<id zmiany>, tr:wxok|wxno:<id sesji> (pogoda)."""
    import qbot_trener_ops as OPS
    data = cq.get("data") or ""
    m = cq.get("message") or {}
    chat_id = str((m.get("chat") or {}).get("id", ""))
    if chat_id != str(chat_ok):
        answer(cq.get("id"), "Brak dostępu"); return
    parts = data.split(":")
    act, arg = (parts[1] if len(parts) > 1 else ""), (parts[2] if len(parts) > 2 else "")
    conn = _conn()
    try:
        c = conn.cursor(); user = pick_user(c)
        if not user:
            answer(cq.get("id"), "Brak planu"); return
        if act == "undo":
            r = OPS.undo(c, user, int(arg))
            conn.commit()
            answer(cq.get("id"), "Cofnięte" if r.get("ok") else "Nie ma czego cofnąć")
            send_plain("↩️ Cofnięte — plan wrócił do poprzedniej wersji." if r.get("ok") else "Tej zmiany nie da się już cofnąć.")
        elif act == "bt":  # 2026-10-08: zadania przy rowerze odhaczone
            from qbot3.rides import bike_tasks as BT
            gc = BT.conn()
            try:
                n_ = BT.mark_done(gc, max_id=int(arg))
            finally:
                gc.close()
            answer(cq.get("id"), "Odhaczone")
            send_plain(f"✅ Rower gotowy — odhaczono {n_} zadań." if n_ else "Te zadania były już odhaczone.")
        elif act == "supl":  # 2026-10-13: suplementy za wczoraj - "wszystkie"; pozostale przyciski wiadomosci zostaja
            import qbot_supplements as SP
            answer(cq.get("id"), "Zapisane")
            send_plain(SP.tg_confirm(arg))
            return
        elif act == "wake":  # [GARMIN-DANE] Etap 5: pobudka przed budzikiem (oznaczenie uzytkownika)
            from fitmodel.sleep_target import mark_early_wake
            _msg = mark_early_wake(c, arg); conn.commit()
            answer(cq.get("id"), "Zapisane")
            send_plain(_msg)
            return
        elif act in ("wxok", "wxno"):  # 2026-10-12: propozycja korekty z uwagi na pogode (qbot_trener_weather)
            import qbot_trener_weather as W
            if act == "wxno":
                W.dismiss(c, int(arg)); conn.commit()
                answer(cq.get("id"), "Zostaje bez zmian")
                send_plain("👌 Jazda zostaje zgodnie z planem.")
            else:
                r = W.apply(c, user, int(arg))
                conn.commit()
                if r.get("ok"):
                    answer(cq.get("id"), "Zmienione")
                    send(f"🌦️ Plan zmieniony z uwagi na pogodę: {r['text']}.\n{URL}",
                         [[{"text": "↩️ Cofnij", "callback_data": f"tr:undo:{r['change_id']}"}]])
                else:
                    answer(cq.get("id"), "Nie da się zmienić")
                    send_plain(f"Nie zmieniłem planu: {r.get('error')}.")
        elif act in ("rest", "short", "ill"):
            d = date.fromisoformat(arg)
            if d < date.today():
                answer(cq.get("id"), "Ten dzień już minął"); return
            answer(cq.get("id"), "Przeliczam…")
            res = OPS.day_action(c, user, d, act)
            conn.commit()
            head = {"rest": "😴 REST DAY", "short": "⏱️ Brak czasu — wersje minimum", "ill": "🤒 Choroba — dziś wolne, potem lżej"}[act]
            txt = change_text(res, f"{head} ({d.strftime('%d.%m')}). Zmiany w planie:")
            send(txt, [[{"text": "↩️ Cofnij", "callback_data": f"tr:undo:{res['change_id']}"}]])
        else:
            answer(cq.get("id"))
            return
    finally:
        conn.close()
    if m.get("message_id"):
        clear_buttons(chat_id, m["message_id"])


def _nc(c, key: str, text: str) -> None:
    """2026-10-08: kopia wiadomosci Trenera do Centrum powiadomien (dzwonek, qbot_notif.py). Bledy pomijane."""
    try:
        import qbot_notif as NF
        lines = [x for x in str(text or "").strip().splitlines() if x.strip()]
        if lines:
            c.execute("SAVEPOINT nc")
            NF.push(c, "trener:" + key, "trener", lines[0][:140], "\n".join(lines[1:])[:400] or None, "/trener.html")
            c.execute("RELEASE SAVEPOINT nc")
    except Exception:
        try:
            c.execute("ROLLBACK TO SAVEPOINT nc")
        except Exception:
            pass


def _once(c, key: str, user: str, text: str | None, dry: bool, buttons: list | None = None) -> str:
    if not text:
        return f"{key}: pusto"
    c.execute("SELECT 1 FROM qbot_v2.trainer_notify_log WHERE key=%s", (key,))
    if c.fetchone():
        return f"{key}: już wysłane"
    if dry:
        return f"{key}: [DRY]\n{text}"
    ok, det = send(text, buttons)
    if key.startswith(("plan:", "review:")):
        _nc(c, key, text)
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
        if 5 * 60 <= hm < 5 * 60 + 15 and not dry:  # 2026-10-14: przelicznik obciazenia planu z Twoich jazd (ModelQ)
            try:
                cal = E.calibrate_xss(c)
                if cal.get("changed"):
                    n_ = E.rescale_plan_xss(c, user, ws)
                    log.append(f"kalibracja obciążenia: mnożnik {cal.get('k')} (jazd {cal['n']}), przeliczono {n_} sesji")
                conn.commit()
            except Exception as e:
                conn.rollback(); log.append(f"kalibracja: błąd {str(e)[:120]}")
        if 5 * 60 <= hm < 5 * 60 + 15:  # co noc: biezacy tydzien + 2 kolejne maja plan (puste tygodnie planuja sie same)
            for k_ in range(3):
                w_ = ws + timedelta(weeks=k_)
                if not _sessions(c, user, w_, w_ + timedelta(days=6)):
                    _ensure_plan(c, user, w_)
                    log.append(f"horyzont: zaplanowano tydzień {w_.isoformat()}")
            conn.commit()
        try:
            import qbot_trener_ops as OPS
            upd = OPS.calendar_changed(c, user)
            conn.commit()
            if upd:
                log.append(f"kalendarz: przeliczono ({len(upd['lines'])} zmian)")
                if (upd["lines"] or upd.get("rolled")) and not dry:
                    _nc(c, f"chg:{upd['change_id']}", change_text(upd, "🗓️ Zmiana w Kalendarzu — plan zaktualizowany:")); conn.commit()
                    send(change_text(upd, "🗓️ Zmiana w Kalendarzu — plan zaktualizowany:"),
                         [[{"text": "↩️ Cofnij", "callback_data": f"tr:undo:{upd['change_id']}"}]])
        except Exception as e:
            conn.rollback(); log.append(f"kalendarz: błąd {str(e)[:120]}")
        if not dry:  # 2026-10-06: wykonanie vs plan - duza odchylka przelicza reszte tygodnia (+ Cofnij)
            try:
                import qbot_trener_ops as OPS
                ad = OPS.adapt_check(c, user, today)
                conn.commit()
                if ad:
                    log.append(f"wykonanie: odchyłka od planu — przeliczono ({len(ad['lines'])} zmian)")
                    _nc(c, f"adapt:{ad['change_id']}", adapt_text(ad)); conn.commit()
                    send(adapt_text(ad), [[{"text": "↩️ Cofnij", "callback_data": f"tr:undo:{ad['change_id']}"}]])
            except Exception as e:
                conn.rollback(); log.append(f"wykonanie: błąd {str(e)[:120]}")
        # 2026-10-08: "Rower po jezdzie - do zrobienia" (Raport z jazdy) -> Telegram 2 h przed zaplanowana
        # jazda rowerowa (bez godziny startu: 7:00 w dniu jazdy). Niezrobione wraca przed kolejna jazda.
        try:
            from qbot3.rides import bike_tasks as BT
            for s in _sessions(c, user, today, today):
                if s["sport"] != "rower" or s["status"] != "plan":
                    continue
                st_ = s.get("start_time")
                t0 = (st_.hour * 60 + st_.minute - 120) if st_ else 7 * 60
                if not (t0 <= hm < t0 + 15):
                    continue
                gc = BT.conn()
                try:
                    ot = BT.open_tasks(gc)
                finally:
                    gc.close()
                txt = BT.reminder_text(s["name"], st_.strftime("%H:%M") if st_ else None, ot)
                btn = [[{"text": "✅ Zrobione", "callback_data": f"tr:bt:{max(t['id'] for t in ot)}"}]] if ot else None
                log.append(_once(c, f"bt:{s['id']}", user, txt, dry, btn))
        except Exception as e:
            log.append(f"rower-zadania: błąd {str(e)[:120]}")
        if E.season_weeks(_goals, _ov, ws, 1)[0]["ph"] == "lz":
            return log + [f"{now.strftime('%a %H:%M')}: totalny luz — bez wiadomości"]
        # rozliczenie: ndz 19:00-19:59
        _rev = None  # 2026-10-12: gdy plan tygodnia idzie w ndz 20:00, rozliczenie dolacza do niego (jedna wiadomosc)
        _merge = st["notify.week_plan"] == 2
        if st["notify.review"] == 1 and today.weekday() == 6 and ((20 * 60 <= hm < 21 * 60) if _merge else (19 * 60 <= hm < 20 * 60)):
            ses = _sessions(c, user, ws, ws + timedelta(days=6))
            linked = {s["training_session_id"] for s in ses if s.get("training_session_id")}
            c.execute("SELECT id, duration_s FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (ws, ws + timedelta(days=6)))
            extra = sum((r["duration_s"] or 0) for r in c.fetchall() if r["id"] not in linked) / 3600
            import qbot_trener_stats as ST
            slope = ST.balance(ST.load_days(c, 45), 30, 2)["weight_slope_kg_wk"]
            _rt = text_review(ws, ses, extra, st["notify.tone"], slope) if ses else None
            if _rt:
                try:   # [GARMIN-DANE] Etap 6: ModelQ vs Garmin w rozliczanym tygodniu (fitmodel/garmin_load_check.py)
                    from fitmodel.garmin_load_check import week_line as _gwl
                    _gl = _gwl(c, ws, ws + timedelta(days=6))
                    if _gl:
                        _rt += "\n" + _gl
                except Exception as e:
                    conn.rollback(); log.append(f"garmin-check: błąd {str(e)[:120]}")
                try:   # 15.10.2026: dlugi trend tetna spoczynkowego (fitmodel/day_status.py rhr_trend_note), tylko gdy jest
                    with conn.cursor() as _cc:
                        _cc.execute("SELECT rhr_trend_note FROM qbot_v2.fitmodel_daily WHERE day <= %s ORDER BY day DESC LIMIT 1",
                                    (ws + timedelta(days=6),))
                        _tr = _cc.fetchone()
                    _tr = (list(_tr.values())[0] if isinstance(_tr, dict) else _tr[0]) if _tr else None
                    if _tr:
                        _rt += "\n🫀 " + _tr + "."
                except Exception as e:
                    conn.rollback(); log.append(f"tetno-trend: błąd {str(e)[:120]}")
                try:   # [GARMIN-DANE] Etap 5: sen tygodnia; miesieczna analiza pobudek gdy tydzien obejmuje koniec miesiaca
                    from fitmodel import sleep_target as _ST
                    _swl = _ST.week_line(c, ws, ws + timedelta(days=6))
                    if _swl:
                        _rt += "\n" + _swl
                    if ws.month != (ws + timedelta(days=7)).month:
                        _ml = _ST.month_line(c, ws.replace(day=1))
                        if _ml:
                            _rt += "\n" + _ml
                except Exception as e:
                    conn.rollback(); log.append(f"garmin-check: błąd {str(e)[:120]}")
            if _merge and _rt:
                _rev = (f"review:{yr}-W{wk:02d}", _rt)
            else:
                log.append(_once(c, f"review:{yr}-W{wk:02d}", user, _rt, dry))
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
            _pt = text_plan(send_plan, ses, res.get("phase_name"), res.get("target_h"), res.get("notes")) if ses else None
            if _rev:
                c.execute("SELECT 1 FROM qbot_v2.trainer_notify_log WHERE key=%s", (_rev[0],))
                if not c.fetchone():
                    _pt = _rev[1] + ("\n\n" + _pt if _pt else "")
                    if not dry:
                        c.execute("INSERT INTO qbot_v2.trainer_notify_log (key, username, ok, detail) VALUES (%s,%s,true,'scalone z planem tygodnia') "
                                  "ON CONFLICT (key) DO NOTHING", (_rev[0], user))
                _rev = None
            log.append(_once(c, f"plan:{y2}-W{w2:02d}", user, _pt, dry))
        # dzien
        if 7 * 60 <= hm < 8 * 60:  # 2026-10-12: JEDNA poranna wiadomosc: trening + wazenie + jedzenie + przypomnienia (zwiezle)
            tses = _sessions(c, user, today, today) if st["notify.day"] == 1 else []
            act = [s for s in tses if s["status"] == "plan"]
            tl = []
            if act:
                ph = E.plan_week(E.build_context(c, user, ws))["phase"]
                det = session_details(c, user, act, ph)
                for s in act:
                    tl.append(_line(s, False))
                    if det.get(s.get("id")) and s["sport"] in ("sila", "wiosl"):  # zwiezle: 1. linia, cwiczenia na stronie Trening
                        tl.append(det[s["id"]].split("\n")[0][:110] + " · ćwiczenia: strona Trening")
            _wxb = []  # 2026-10-12: pogoda w oknie dzisiejszych jazd -> propozycja (Zmien / Zostaw), reczne: ostrzezenie
            if act:
                try:
                    import qbot_trener_weather as W
                    c.execute("SELECT 1 FROM qbot_v2.trainer_notify_log WHERE key=%s", (f"day:{today.isoformat()}",))
                    if not c.fetchone():
                        _wx = W.morning_check(c, user, today, hm)
                        tl += _wx["lines"]
                        _wxb = W.buttons(_wx["proposal"])
                        conn.rollback() if dry else conn.commit()
                except Exception as e:
                    conn.rollback(); log.append(f"pogoda: błąd {str(e)[:120]}")
            try:   # [GARMIN-DANE] Etap 4: temp. skory + HRV/tetno -> jedno zdanie, TYLKO gdy sygnal (fitmodel/body_signal.py)
                from fitmodel.body_signal import today_signal as _bsig
                _bs = _bsig(c, today)
                if _bs and _bs["signal"]:
                    tl.append("🌡️ " + _bs["text"])
            except Exception as e:
                conn.rollback(); log.append(f"temp. skory: błąd {str(e)[:120]}")
            try:
                import qbot_food_plan as _FP
                _txt = _FP.morning_digest(today, tl)
            except Exception as e:
                log.append(f"poranek: błąd {str(e)[:120]}")
                _txt = text_day(today, tses, None)
            _kb = (_wxb + day_buttons(today)) if act else []
            try:  # 2026-10-13: przyciski potwierdzenia wczorajszego okna 10-20 (Zdrowie)
                import qbot_food_plan as _FPb
                _kb = _kb + _FPb.morning_buttons(today)
            except Exception as e:
                log.append(f"okno: błąd {str(e)[:80]}")
            try:  # 2026-10-13: suplementy/leki - potwierdzenie RANO za wczoraj jednym przyciskiem (qbot_supplements)
                import qbot_supplements as SP
                _spl, _spb = SP.morning(today)
                if _spl:
                    _txt = (_txt or "").rstrip() + "\n" + _spl
                _kb = _kb + _spb
            except Exception as e:
                log.append(f"suplementy: błąd {str(e)[:120]}")
            try:  # [GARMIN-DANE] Etap 5: przycisk 'Pobudka przed budzikiem' (zawsze; klikam tylko gdy sam sie obudzilem)
                from fitmodel.sleep_target import wake_button as _wkb
                _kb = _kb + _wkb(today)
            except Exception as e:
                log.append(f"pobudka: błąd {str(e)[:80]}")
            try:  # 2026-10-13: Garaz > Zakupy - konczy sie zapas (linia + Kup ponownie / +7 dni)
                import qbot_zakupy_api as ZK
                _zkl, _zkb = ZK.morning(today)
                if _zkl:
                    _txt = (_txt or "").rstrip() + "\n" + _zkl
                _kb = _kb + _zkb
            except Exception as e:
                log.append(f"zakupy: błąd {str(e)[:120]}")
            log.append(_once(c, f"day:{today.isoformat()}", user, _txt, dry, _kb or None))
        if st["notify.day"] == 2:
            for s in _sessions(c, user, today, today):
                if s["status"] != "plan" or not s.get("start_time"):
                    continue
                t0 = s["start_time"].hour * 60 + s["start_time"].minute - 120
                if t0 <= hm < t0 + 15:
                    log.append(_once(c, f"pre:{s['id']}", user, text_pre(s), dry, day_buttons(today)))
        if _rev:  # plan nie poszedl (brak sesji) - samo rozliczenie
            log.append(_once(c, _rev[0], user, _rev[1], dry))
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
    det, rated = {}, ""
    conn2 = _conn()
    try:
        c2 = conn2.cursor()
        if ses:
            det = session_details(c2, user, [s for s in ses if s["status"] == "plan" and s["day"] >= date.today()], res["phase"])
        try:
            import qbot_trener_ratings as TR
            rated = TR.text_recent(TR.recent_for_ai(c2, user, ws))
        except Exception as e:
            print("trener albert: oceny:", e)
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
    if rated:
        lines.append("\n" + rated)
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
