#!/usr/bin/env python3
"""QCal Telegram — send reminders, receive commands, basic poller."""

import json, os, sys
from datetime import date, datetime

sys.path.insert(0, "/opt/qbot/app")


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _allowed_chats() -> set:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    return set(raw.split(",")) if raw else set()


def status() -> dict:
    token = _token()
    allowed = _allowed_chats()
    configured = bool(token and allowed)
    try:
        import httpx
        me = {}
        if token:
            r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if r.status_code == 200:
                me = r.json().get("result", {})
    except Exception:
        me = {}
    return {
        "configured": configured,
        "bot_name": me.get("first_name", "?"),
        "bot_username": me.get("username", "?"),
        "allowed_chats": len(allowed),
    }


def send_message(text: str) -> bool:
    token = _token()
    allowed = _allowed_chats()
    if not token or not allowed:
        return False
    import httpx
    errors = []
    for chat_id in allowed:
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id.strip(), "text": text, "parse_mode": "Markdown"}, timeout=10)
        if r.status_code != 200:
            errors.append(f"chat={chat_id}: {r.status_code}")
    return not errors


def poll_once() -> list[dict]:
    token = _token()
    if not token: return []
    import httpx
    r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"limit": 10, "timeout": 5}, timeout=10)
    if r.status_code != 200: return []
    return r.json().get("result", [])


def handle_update(update: dict) -> str:
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    if chat_id not in _allowed_chats():
        return "unauthorized"
    text = msg.get("text", "")
    from_user = msg.get("from", {}).get("first_name", "?")

    if text.startswith("/"):
        cmd = text.split()[0].lower()
        if cmd == "/today":
            return _today_response()
        elif cmd == "/reminders":
            return _reminders_response()
        elif cmd == "/status":
            return "QBot status: OK"
        elif cmd in ("/help", "/start"):
            return "QCal Bot:\n/today /reminders /status"
        elif cmd == "/done":
            parts = text.split()
            if len(parts) > 1:
                try:
                    _mark_done(int(parts[1]))
                    return "✓ Done."
                except: pass
            return "Usage: /done ID"
    return ""


def _today_response() -> str:
    try:
        from qbot_calendar_core import get_snapshot
        d = date.today().isoformat()
        snap = get_snapshot(d)
        if snap:
            sd = snap.get("snapshot_json", {})
            if isinstance(sd, str):
                try: sd = json.loads(sd)
                except: sd = {}
            return f"Today {d}: completeness={snap.get('completeness_score',0)*100:.0f}%"
    except: pass
    return f"Today: {date.today().isoformat()}"


def _reminders_response() -> str:
    try:
        from psycopg import connect; from psycopg.rows import dict_row
        c = connect(host="127.0.0.1",port=5432,dbname="qbot",user="qbot",password=os.getenv("PGPASSWORD",""),row_factory=dict_row,connect_timeout=5)
        cur = c.cursor()
        cur.execute("SELECT id, title, reminder_type, time FROM reminders WHERE date=%s AND status='pending' ORDER BY time", (date.today().isoformat(),))
        rows = cur.fetchall(); c.close()
        if not rows: return "No pending reminders today."
        return "\n".join(f"[{r['id']}] {r.get('time','')} {r['title']}" for r in rows)
    except: return "Could not check reminders."


def _mark_done(rid: int):
    try:
        from psycopg import connect
        c = connect(host="127.0.0.1",port=5432,dbname="qbot",user="qbot",password=os.getenv("PGPASSWORD",""),connect_timeout=5)
        cur = c.cursor()
        cur.execute("UPDATE reminders SET status='done', sent_at=now(), updated_at=now() WHERE id=%s",(rid,))
        c.commit(); c.close()
    except: pass
