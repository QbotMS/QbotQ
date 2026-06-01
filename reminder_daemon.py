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
    if sent == 0:
        log("— brak przypomnień do wysłania")


if __name__ == "__main__":
    main()
