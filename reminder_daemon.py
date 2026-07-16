#!/usr/bin/env python3
"""reminder_daemon.py — sprawdza przypomnienia i wysyła Telegram. Cron: * * * * *"""
import json, os, sys
from datetime import datetime

try:
    from dotenv import load_dotenv; load_dotenv("/opt/qbot/app/.env")
except Exception:
    pass

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
LOG_PATH = "/opt/qbot/app/logs/reminders.log"

from qbot_reminder_tools import _db, DAY_MAP, DB_PATH


def log(m: str):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a") as f:
        f.write(f"[{ts}] {m}\n")


def _fire_calendar_reminders(TOKEN, CHAT_ID, log):
    """Przypomnienia z kalendarza (qbot_v2.calendar_entry kind=reminder). Odpala co minute."""
    import os as _os, sys as _sys
    from datetime import datetime, timedelta
    _os.environ.setdefault("QBOT3_ENABLED", "1")
    if "/opt/qbot/app" not in _sys.path:
        _sys.path.insert(0, "/opt/qbot/app")
    from fitmodel.api import _db_connect
    import requests
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    curmin = now.strftime("%Y-%m-%d %H:%M")
    conn = _db_connect(); cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS qbot_v2.calendar_reminder_fired("
        "entry_id bigint NOT NULL, target_key text NOT NULL, "
        "sent_at timestamptz NOT NULL DEFAULT now(), UNIQUE(entry_id, target_key))")
    conn.commit()
    cur.execute(
        "SELECT id, title, at_time::text, remind_offsets, note "
        "FROM qbot_v2.calendar_entry WHERE kind='reminder' AND day=%s", (today,))
    rows = cur.fetchall()
    sent = 0
    for r in rows:
        eid, title, at_time, offs, note = r[0], r[1], r[2], r[3], r[4]
        if not at_time:
            tgt = now.replace(hour=8, minute=0, second=0, microsecond=0); off = None
        else:
            hh, mm = int(at_time[0:2]), int(at_time[3:5])
            try:
                off = int((offs or "0").strip() or "0")
            except Exception:
                off = 0
            tgt = now.replace(hour=hh, minute=mm, second=0, microsecond=0) - timedelta(minutes=off)
        tkey = tgt.strftime("%Y-%m-%d %H:%M")
        if tkey != curmin:
            continue
        cur.execute("SELECT 1 FROM qbot_v2.calendar_reminder_fired WHERE entry_id=%s AND target_key=%s", (eid, tkey))
        if cur.fetchone():
            continue
        when = "całodzienne (08:00)" if not at_time else at_time[0:5]
        lead = ""
        if at_time and off:
            lead = {60: " · 1 h przed", 240: " · 4 h przed", 480: " · 8 h przed"}.get(off, "")
        desc = ("\n" + note) if note else ""
        text = "🔔 <b>Przypomnienie</b>\n\n📅 " + (title or "") + "\n🕒 " + when + lead + desc
        try:
            resp = requests.post(
                "https://api.telegram.org/bot%s/sendMessage" % TOKEN,
                json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
            if resp.ok:
                cur.execute("INSERT INTO qbot_v2.calendar_reminder_fired (entry_id, target_key) VALUES (%s, %s) ON CONFLICT DO NOTHING", (eid, tkey))
                conn.commit(); sent += 1; log("CAL OK [%s] %s" % (eid, title))
            else:
                log("CAL TELEGRAM_ERR [%s]: HTTP %s" % (eid, resp.status_code))
        except Exception as e:
            log("CAL EXC [%s]: %s" % (eid, e))
    conn.close()
    return sent


def main():
    if not TOKEN or not CHAT_ID:
        log("BLOCKED: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set")
        return

    import requests
    now = datetime.now()
    conn = _db()  # creates tables if missing
    # dezaktywuj przeterminowane
    conn.execute(
        "UPDATE reminders SET active=0 WHERE active=1 AND deadline IS NOT NULL "
        "AND datetime(deadline) < datetime('now')"
    )
    conn.commit()
    rows = conn.execute("SELECT * FROM reminders WHERE active=1").fetchall()
    hhmm = now.strftime("%H:%M")
    fired_key = now.strftime("%Y-%m-%d %H:%M")
    sent = 0
    for r in rows:
        times = json.loads(r["remind_times"])
        if hhmm not in times:
            continue
        days = json.loads(r["repeat_days"])
        if "daily" not in days:
            nums = [DAY_MAP.get(d.lower(), -1) for d in days]
            if now.weekday() not in nums:
                continue
        already = conn.execute(
            "SELECT id FROM reminders_fired WHERE reminder_id=? AND fired_at=?",
            (r["id"], fired_key),
        ).fetchone()
        if already:
            continue
        dl = ""
        if r["deadline"]:
            try:
                dt = datetime.fromisoformat(r["deadline"])
                left = (dt.date() - now.date()).days
                if left == 0:
                    dl = "\n⏰ <b>Dziś ostatni dzień!</b>"
                elif left > 0:
                    dl = f"\n⏰ Zostało {left} dni (do {dt.strftime('%d.%m')})"
            except Exception:
                pass
        desc = f"\n{r['description']}" if r.get("description") else ""
        text = f"🔔 <b>Przypomnienie</b>\n\n📌 {r['title']}{desc}{dl}"
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
            if resp.ok:
                conn.execute(
                    "INSERT INTO reminders_fired (reminder_id,fired_at) VALUES (?,?)",
                    (r["id"], fired_key),
                )
                conn.commit()
                sent += 1
                log(f"OK [{r['id']}] {r['title']}")
            else:
                log(f"TELEGRAM_ERR [{r['id']}] {r['title']}: HTTP {resp.status_code}")
        except Exception as e:
            log(f"TELEGRAM_EXC [{r['id']}] {r['title']}: {e}")
    conn.execute(
        "DELETE FROM reminders_fired WHERE fired_at < datetime('now','-7 days')"
    )
    conn.commit()
    conn.close()
    try:
        sent += _fire_calendar_reminders(TOKEN, CHAT_ID, log)
    except Exception as e:
        log("CAL_STEP_EXC: %s" % e)
    if sent == 0:
        log("— brak przypomnień do wysłania")


if __name__ == "__main__":
    main()
