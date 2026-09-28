from __future__ import annotations

"""Straznik OBCIAZENIA (2026-09-28) - zastepuje alerty Telegram power_meter_guard.

Po co: power_meter_guard (P@HR wobec bazy miernika) dawal falszywe alarmy, szczegolnie
po zmianie miernika (koniec 08.2026). Ten straznik porownuje DWA niezalezne policzenia
obciazenia tej samej jazdy:
    XSS z mocy  (modelq2_ride.xss_total, xss_source='power')
    XSS z tetna (fitmodel.modelq2.hr_xss - kalibrowany na czystych jazdach)
Na czystej jezdzie stosunek ~1.0 (sezon 2026: mediany miesieczne 0.89-1.24).

Regula: jazda >= MIN_H godzin i stosunek poza [LO, HI] -> werdykt SPRAWDZ i pytanie
na Telegramie z przyciskami. NIC nie podmienia sam - decyduje uzytkownik:
    "Moc OK"        -> decision='moc' (bez zmian)
    "Licz z tetna"  -> kwarantanna miernika + XSS z tetna + przeliczenie ModelQ
Krotsze jazdy: zapis (werdykt KROTKA/OK), bez pytania - maly wplyw na obciazenie.
Znane ograniczenie: w chlodzie tetno bywa nizsze przy tych samych watach (stosunek w gore);
temperatura jest podawana w pytaniu jako podpowiedz.
Callback Telegram: prefiks 'lg:' (telegram_reply_processor.py -> handle_callback).
"""

import sys
import datetime as dt

sys.path.insert(0, "/opt/qbot/app")

MIN_H = 2.0          # od tylu godzin jazda moze wywolac pytanie
LO, HI = 0.70, 1.40  # dozwolony stosunek XSS moc / XSS tetno
LOOKBACK_DAYS = 10
MIN_HR_XSS = 5.0     # ponizej: za malo tetna, brak porownania

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.load_guard (
    external_id  text PRIMARY KEY,
    ride_date    date,
    duration_s   integer,
    xss_power    real,
    xss_hr       real,
    ratio        real,
    temp_c       real,
    verdict      text,
    decision     text,
    decided_at   timestamptz,
    notified_at  timestamptz,
    checked_at   timestamptz DEFAULT now())"""


def ensure_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()


def classify(duration_s, xss_power, xss_hr, source) -> tuple:
    """Czysta funkcja: (werdykt, stosunek). Bez bazy - testowalna."""
    if source == "hr":
        return "KWARANTANNA", None
    if not xss_hr or xss_hr < MIN_HR_XSS or not xss_power:
        return "BRAK_TETNA", None
    ratio = float(xss_power) / float(xss_hr)
    if (duration_s or 0) < MIN_H * 3600:
        return "KROTKA", ratio
    return ("OK" if LO <= ratio <= HI else "SPRAWDZ"), ratio


def _hr_split(external_id):
    from fitmodel.modelq2.hr_xss import fetch_hr_rows, compute_hr_xss_split
    rows = fetch_hr_rows(external_id)
    lo, hi = compute_hr_xss_split(rows)
    return float(lo), float(hi)


def _fmt(x, d=0):
    if x is None:
        return "—"
    s = ("%." + str(d) + "f") % x
    return s.replace(".", ",")


def question_text(ride_date, duration_s, xss_power, xss_hr, ratio, temp_c) -> str:
    d = ride_date.strftime("%d.%m") if hasattr(ride_date, "strftime") else str(ride_date)
    kier = "więcej" if ratio > 1 else "mniej"
    t = ("Strażnik obciążenia · jazda %s (%s h)\n"
         "Obciążenie z mocy: %s, z tętna: %s (×%s).\n"
         "Moc daje wyraźnie %s niż tętno — możliwy problem z miernikiem."
         % (d, _fmt(duration_s / 3600.0, 1), _fmt(xss_power), _fmt(xss_hr), _fmt(ratio, 2), kier))
    if temp_c is not None and temp_c < 14 and ratio > 1:
        t += "\nUwaga: było chłodno (%s°C) — w chłodzie tętno bywa niższe przy tych samych watach." % _fmt(temp_c)
    t += "\n\nCzy miernik działał poprawnie?"
    return t


def _tg_ask(text: str, external_id: str) -> None:
    import httpx
    import qbot_config as cfg
    kb = {"inline_keyboard": [[{"text": "✅ Moc OK", "callback_data": "lg:ok:%s" % external_id},
                               {"text": "❤️ Licz z tętna", "callback_data": "lg:hr:%s" % external_id}]]}
    r = httpx.post("https://api.telegram.org/bot%s/sendMessage" % cfg.TELEGRAM_TOKEN,
                   json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": text, "reply_markup": kb}, timeout=10)
    r.raise_for_status()


def check_new_rides(conn, lookback_days: int = LOOKBACK_DAYS, send=None) -> dict:
    """Sprawdza jazdy z modelq2_ride z ostatnich N dni, ktorych jeszcze nie ma w load_guard.
    send(text, external_id): funkcja pytania (Telegram); None = tylko zapis."""
    ensure_table(conn)
    cur = conn.cursor()
    d_from = dt.date.today() - dt.timedelta(days=lookback_days)
    cur.execute("""SELECT m.external_id, m.ride_date, m.xss_total, m.xss_source, t.duration_s
                   FROM qbot_v2.modelq2_ride m JOIN qbot_v2.training_sessions t ON t.external_id = m.external_id
                   WHERE m.ride_date >= %s
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.load_guard g WHERE g.external_id = m.external_id)
                   ORDER BY m.ride_date""", (d_from,))
    rows = cur.fetchall()
    stats = {"checked": 0, "sprawdz": 0, "asked": 0}
    for eid, d, xss_p, src, dur in rows:
        try:
            lo, hi = _hr_split(eid) if src != "hr" else (None, None)
        except Exception:
            lo, hi = None, None
        xss_hr = (lo + hi) if lo is not None else None
        verdict, ratio = classify(dur, xss_p, xss_hr, src)
        cur.execute("SELECT avg(temperature_c) FROM qbot_v2.activity_record WHERE external_id=%s", (eid,))
        tr = cur.fetchone()
        temp = float(tr[0]) if tr and tr[0] is not None else None
        cur.execute("""INSERT INTO qbot_v2.load_guard (external_id, ride_date, duration_s, xss_power, xss_hr, ratio, temp_c, verdict)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (external_id) DO NOTHING""",
                    (eid, d, dur, xss_p, xss_hr, ratio, temp, verdict))
        stats["checked"] += 1
        if verdict == "SPRAWDZ":
            stats["sprawdz"] += 1
            if send is not None:
                try:
                    send(question_text(d, dur, float(xss_p), xss_hr, ratio, temp), eid)
                    cur.execute("UPDATE qbot_v2.load_guard SET notified_at=now() WHERE external_id=%s", (eid,))
                    stats["asked"] += 1
                except Exception as exc:
                    print("load_guard: telegram error: %s" % exc)
    conn.commit()
    return stats


def apply_decision(conn, external_id: str, decision: str) -> str:
    """decision: 'moc' | 'tetno'. Zwraca tekst potwierdzenia (prosty jezyk)."""
    ensure_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT decision, ride_date, xss_power FROM qbot_v2.load_guard WHERE external_id=%s", (external_id,))
    g = cur.fetchone()
    if not g:
        return "Nie znam tej jazdy w strażniku obciążenia."
    if g[0]:
        return "Ta jazda ma już decyzję: %s." % ("moc OK" if g[0] == "moc" else "liczona z tętna")
    ride_date = g[1]
    if decision == "moc":
        cur.execute("UPDATE qbot_v2.load_guard SET decision='moc', decided_at=now() WHERE external_id=%s", (external_id,))
        conn.commit()
        return "OK — jazda %s zostaje liczona z mocy." % ride_date.strftime("%d.%m")
    # 'tetno': ta sama sciezka co kwarantanna 08.2026 (publish.ingest_new_rides_xss, galaz hr)
    lo, hi = _hr_split(external_id)
    cur.execute("SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine WHERE external_id=%s AND released IS NULL", (external_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO qbot_v2.fitmodel_ride_quarantine (external_id, reason) VALUES (%s,%s)",
                    (external_id, "straznik obciazenia: decyzja uzytkownika (moc vs tetno poza %.2f-%.2f)" % (LO, HI)))
    cur.execute("SELECT xss_total FROM qbot_v2.modelq2_ride WHERE external_id=%s", (external_id,))
    old = cur.fetchone()
    cur.execute("UPDATE qbot_v2.modelq2_ride SET xss_low=%s, xss_high=%s, xss_peak=0.0, xss_total=%s, "
                "min_wbal_pct=NULL, xss_source='hr' WHERE external_id=%s",
                (round(lo, 1), round(hi, 2), round(lo + hi, 1), external_id))
    cur.execute("UPDATE qbot_v2.load_guard SET decision='tetno', decided_at=now() WHERE external_id=%s", (external_id,))
    conn.commit()
    from fitmodel.modelq2.publish import run_daily_v2
    run_daily_v2(conn)
    cur.execute("SELECT tsb_plus FROM qbot_v2.fitmodel_daily ORDER BY day DESC LIMIT 1")
    t = cur.fetchone()
    return ("Przeliczone z tętna: jazda %s — obciążenie %s → %s. Świeżość dziś: %s."
            % (ride_date.strftime("%d.%m"), _fmt(float(old[0]) if old and old[0] is not None else None),
               _fmt(lo + hi), _fmt(float(t[0]) if t and t[0] is not None else None)))


def handle_callback(cq, answer, send_plain, edit_markup, chat_id) -> None:
    """Callback 'lg:ok:<id>' / 'lg:hr:<id>' z telegram_reply_processor.py."""
    data = cq.get("data") or ""
    msg = cq.get("message") or {}
    if str((msg.get("chat") or {}).get("id", "")) != str(chat_id):
        answer(cq.get("id"), "Brak dostępu")
        return
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[1] not in ("ok", "hr"):
        answer(cq.get("id"), "Nieznana akcja")
        return
    answer(cq.get("id"), "Przyjęte")
    try:
        edit_markup(chat_id, msg.get("message_id"))
    except Exception:
        pass
    from fitmodel.ftp_resolver import _db_connect
    conn = _db_connect()
    try:
        send_plain(apply_decision(conn, parts[2], "moc" if parts[1] == "ok" else "tetno"))
    finally:
        conn.close()


def run(conn, lookback_days: int = LOOKBACK_DAYS) -> dict:
    """Wejscie dla daily_job / after_ride: sprawdz + zapytaj na Telegramie."""
    return check_new_rides(conn, lookback_days=lookback_days, send=_tg_ask)


if __name__ == "__main__":
    # reczne sprawdzenie BEZ Telegrama
    from fitmodel.ftp_resolver import _db_connect
    c = _db_connect()
    print(check_new_rides(c, send=None))
    c.close()
