from __future__ import annotations

"""Odczucie przy niskim zapasie W'bal -> bieza kontrola HIE ModelQ (MODELQ-PRZEGLAD, decyzja Michala 2026-10-14).

Po co: ModelQ nie ma jak zmierzyc HIE bez wysilkow maksymalnych (Michal ich nie robi). Jedynym realnym sprawdzianem
jest odczucie w momencie, gdy model mowi "zapas prawie zero". Kalibracja 14.10 (HIE 20 kJ) stala na takim odczuciu.
Regula: jazda z min W'bal (ModelQ) <= MAX_WBAL_PCT % -> pytanie na Telegramie z 3 przyciskami:
    wf:cut:<id>   "Odcielo"        -> model mowi 0 i bylo 0       (zgodne przy min ~0 %)
    wf:close:<id> "Blisko"         -> trudno, nie odcielo         (zgodne przy kilku %)
    wf:ok:<id>    "Mialem zapas"   -> model zbyt pesymistyczny    (HIE/TP za nisko)
NIC nie zmienia w ModelQ. Po >= SERIES zgodnych sygnalach tego samego rodzaju (ok -> za nisko) w ostatnich 90 dniach
wysyla notke "propozycja korekty HIE" -- decyzja zawsze Michala.
Callback Telegram: prefiks 'wf:' (telegram_reply_processor.py -> handle_callback).
"""

import sys
import datetime as dt

sys.path.insert(0, "/opt/qbot/app")

MAX_WBAL_PCT = 5.0
LOOKBACK_DAYS = 3
START_DATE = dt.date(2026, 10, 15)   # nie pytamy o jazdy sprzed wdrozenia
SERIES = 3
ANSWERS = {"cut": "odcięło", "close": "blisko", "ok": "miałem zapas"}

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.wbal_feel (
    external_id  text PRIMARY KEY,
    ride_date    date,
    min_wbal_pct real,
    hie_kj       real,
    tp_w         real,
    answer       text,
    answered_at  timestamptz,
    notified_at  timestamptz,
    created_at   timestamptz DEFAULT now())"""


def ensure_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()


def _fmt(x, d=0):
    return ("%." + str(d) + "f") % x if x is not None else "—"


def question_text(ride_date, min_wbal, hie_kj, tp_w) -> str:
    d = ride_date.strftime("%d.%m") if hasattr(ride_date, "strftime") else str(ride_date)
    return ("Zapas na mocne wysiłki · jazda %s\n"
            "Model pokazał najniższy zapas %s%% (próg %s W, zapas %s kJ).\n"
            "Jak to było naprawdę w najcięższym momencie?"
            % (d, _fmt(min_wbal), _fmt(tp_w), _fmt(hie_kj, 1).replace(".", ",")))


def series_signal(answers: list[str]) -> str | None:
    """answers: od najnowszej. Zwraca 'za_nisko' gdy SERIES ostatnich = 'ok' (zapas mimo ~0 %), inaczej None.
    'cut'/'close' przy niskim W'bal = model zgodny z odczuciem."""
    last = answers[:SERIES]
    if len(last) == SERIES and all(a == "ok" for a in last):
        return "za_nisko"
    return None


def _tg_ask(text: str, external_id: str) -> None:
    import httpx
    import qbot_config as cfg
    kb = {"inline_keyboard": [[{"text": "🟥 Odcięło", "callback_data": "wf:cut:%s" % external_id},
                               {"text": "🟧 Blisko", "callback_data": "wf:close:%s" % external_id},
                               {"text": "🟩 Miałem zapas", "callback_data": "wf:ok:%s" % external_id}]]}
    r = httpx.post("https://api.telegram.org/bot%s/sendMessage" % cfg.TELEGRAM_TOKEN,
                   json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": text, "reply_markup": kb}, timeout=10)
    r.raise_for_status()


def check_new_rides(conn, send=None, today: dt.date | None = None) -> dict:
    ensure_table(conn)
    cur = conn.cursor()
    today = today or dt.date.today()
    d_from = max(START_DATE, today - dt.timedelta(days=LOOKBACK_DAYS))
    cur.execute("""SELECT external_id, ride_date, min_wbal_pct, sig_hie_kj, sig_tp_w FROM qbot_v2.modelq2_ride
                   WHERE ride_date >= %s AND COALESCE(xss_source,'power') <> 'hr' AND min_wbal_pct IS NOT NULL
                     AND min_wbal_pct <= %s
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.wbal_feel f WHERE f.external_id = modelq2_ride.external_id)
                   ORDER BY ride_date""", (d_from, MAX_WBAL_PCT))
    stats = {"nowe": 0, "zapytane": 0}
    for eid, d, w, hie, tp in cur.fetchall():
        cur.execute("INSERT INTO qbot_v2.wbal_feel (external_id, ride_date, min_wbal_pct, hie_kj, tp_w) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (eid, d, w, hie, tp))
        stats["nowe"] += 1
        if send is not None:
            try:
                send(question_text(d, float(w), float(hie or 0), float(tp or 0)), eid)
                cur.execute("UPDATE qbot_v2.wbal_feel SET notified_at=now() WHERE external_id=%s", (eid,))
                stats["zapytane"] += 1
            except Exception as exc:
                print("wbal_feel: telegram error: %s" % exc)
    conn.commit()
    return stats


def apply_answer(conn, external_id: str, answer: str) -> str:
    ensure_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT answer, ride_date FROM qbot_v2.wbal_feel WHERE external_id=%s", (external_id,))
    r = cur.fetchone()
    if not r:
        return "Nie znam tej jazdy."
    if r[0]:
        return "Ta jazda ma już odpowiedź: %s." % ANSWERS.get(r[0], r[0])
    cur.execute("UPDATE qbot_v2.wbal_feel SET answer=%s, answered_at=now() WHERE external_id=%s", (answer, external_id))
    cur.execute("SELECT answer FROM qbot_v2.wbal_feel WHERE answer IS NOT NULL AND ride_date >= %s ORDER BY ride_date DESC",
                (dt.date.today() - dt.timedelta(days=90),))
    hist = [x[0] for x in cur.fetchall()]
    conn.commit()
    msg = "Zapisane: %s — %s. Dzięki, to jedyny realny sprawdzian zapasu w ModelQ." % (r[1].strftime("%d.%m"), ANSWERS[answer])
    if series_signal(hist) == "za_nisko":
        msg += ("\n⚠️ %d razy z rzędu „miałem zapas” przy zapasie bliskim zera — ModelQ może zaniżać zapas (HIE). "
                "Przygotuję propozycję korekty do Twojej decyzji." % SERIES)
    return msg


def handle_callback(cq, answer, send_plain, edit_markup, chat_id) -> None:
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    if str((msg.get("chat") or {}).get("id", "")) != str(chat_id):
        answer(cq.get("id"), "Brak dostępu")
        return
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[1] not in ANSWERS:
        answer(cq.get("id"), "Nieznana akcja")
        return
    answer(cq.get("id"), "Zapisane")
    try:
        edit_markup(chat_id, msg.get("message_id"))
    except Exception:
        pass
    from fitmodel.ftp_resolver import _db_connect
    conn = _db_connect()
    try:
        send_plain(apply_answer(conn, parts[2], parts[1]))
    finally:
        conn.close()


def run(conn) -> dict:
    """Wejscie dla daily_job."""
    return check_new_rides(conn, send=_tg_ask)


if __name__ == "__main__":
    from fitmodel.ftp_resolver import _db_connect
    c = _db_connect()
    print(check_new_rides(c, send=None))
    c.close()
