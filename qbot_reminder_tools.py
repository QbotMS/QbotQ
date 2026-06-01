"""qbot_reminder_tools.py — przypomnienia cykliczne z deadline, przez Telegram."""
from __future__ import annotations
import sqlite3, json, re, os
from datetime import datetime
from typing import Any

DB_PATH = "/opt/qbot/app/data/garage.db"

DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
    "monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6,
    "pn": 0, "wt": 1, "sr": 2, "sr": 2, "czw": 3, "pt": 4, "sb": 5, "nd": 6,
    "poniedziałek":0,"wtorek":1,"środa":2,"czwartek":3,"piątek":4,"sobota":5,"niedziela":6,
}
DAY_SHORT = ["Pon","Wt","Śr","Czw","Pt","Sob","Nd"]


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        remind_times TEXT NOT NULL DEFAULT '["09:00"]',
        repeat_days TEXT NOT NULL DEFAULT '["daily"]',
        deadline TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS reminders_fired (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reminder_id INTEGER NOT NULL,
        fired_at TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def _parse_deadline(s: str) -> str | None:
    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"]:
        try:
            dt = datetime.strptime(s, fmt)
            if "%H" not in fmt: dt = dt.replace(hour=23, minute=59)
            return dt.isoformat()
        except ValueError:
            continue
    return None


def _fmt(r: dict) -> str:
    times = ", ".join(json.loads(r["remind_times"]))
    days = json.loads(r["repeat_days"])
    if "daily" in days:
        days_str = "codziennie"
    else:
        nums = sorted(DAY_MAP.get(d.lower(), -1) for d in days)
        days_str = ", ".join(DAY_SHORT[n] for n in nums if 0 <= n <= 6)
    dl = ""
    if r.get("deadline"):
        try:
            dt = datetime.fromisoformat(r["deadline"])
            left = (dt.date() - datetime.now().date()).days
            if left < 0: dl = f" | ⚠️ po terminie"
            elif left == 0: dl = f" | ⏰ dziś ostatni dzień!"
            else: dl = f" | do {dt.strftime('%d.%m')} ({left}d)"
        except: dl = f" | {r['deadline']}"
    icon = "✅" if r["active"] else "⏸️"
    desc = f"\n   📝 {r['description']}" if r.get("description") else ""
    return f"{icon} [{r['id']}] <b>{r['title']}</b>\n   🕐 {times} | {days_str}{dl}{desc}"


def _tool_qbot_reminder_add(args: dict) -> dict:
    """Dodaj przypomnienie cykliczne. Pola: title, remind_times (lista HH:MM),
    repeat_days (['daily'] lub ['mon','tue',...] / ['pn','wt',...]),
    deadline (YYYY-MM-DD lub DD.MM.YYYY), description."""
    title = args.get("title", "").strip()
    if not title:
        return {"status": "ERROR", "error": "Brak tytułu"}
    times = args.get("remind_times", ["09:00"])
    if isinstance(times, str): times = [times]
    for t in times:
        if not re.match(r"^\d{2}:\d{2}$", t):
            return {"status": "ERROR", "error": f"Zły format godziny: {t} (użyj HH:MM)"}
    days = args.get("repeat_days", ["daily"])
    deadline_iso = None
    if args.get("deadline"):
        deadline_iso = _parse_deadline(args["deadline"])
        if not deadline_iso:
            return {"status": "ERROR", "error": f"Zły format deadline: {args['deadline']}"}
    desc = args.get("description", "")
    conn = _db()
    cur = conn.execute(
        "INSERT INTO reminders (title,description,remind_times,repeat_days,deadline,active) VALUES (?,?,?,?,?,1)",
        (title, desc, json.dumps(times), json.dumps(days), deadline_iso)
    )
    rid = cur.lastrowid
    conn.commit()
    row = dict(conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone())
    conn.close()
    return {"status": "OK", "message": f"✅ Dodano przypomnienie!\n\n{_fmt(row)}", "id": rid}


def _tool_qbot_reminder_list(args: dict) -> dict:
    """Lista przypomnień. Opcjonalnie include_inactive=true żeby zobaczyć wstrzymane."""
    conn = _db()
    include_all = args.get("include_inactive", False)
    q = "SELECT * FROM reminders ORDER BY active DESC, id"
    if not include_all:
        q = "SELECT * FROM reminders WHERE active=1 ORDER BY id"
    rows = [dict(r) for r in conn.execute(q).fetchall()]
    conn.close()
    if not rows:
        return {"status": "OK", "message": "📭 Brak przypomnień.", "count": 0}
    lines = [f"🔔 <b>Przypomnienia</b> ({len(rows)}):\n"] + [_fmt(r) for r in rows]
    return {"status": "OK", "message": "\n\n".join(lines), "count": len(rows)}


def _tool_qbot_reminder_edit(args: dict) -> dict:
    """Edytuj przypomnienie. Wymagane: id. Opcjonalne: title, remind_times,
    repeat_days, deadline ('' = usuń), description, active (true/false)."""
    rid = args.get("id") or args.get("reminder_id")
    if not rid:
        return {"status": "ERROR", "error": "Brak id przypomnienia"}
    conn = _db()
    row = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
    if not row:
        conn.close()
        return {"status": "ERROR", "error": f"Nie znaleziono przypomnienia ID {rid}"}
    updates, params = [], []
    if "title" in args:
        updates.append("title=?"); params.append(args["title"])
    if "remind_times" in args:
        t = args["remind_times"]
        if isinstance(t, str): t = [t]
        updates.append("remind_times=?"); params.append(json.dumps(t))
    if "repeat_days" in args:
        updates.append("repeat_days=?"); params.append(json.dumps(args["repeat_days"]))
    if "deadline" in args:
        if args["deadline"] == "":
            updates.append("deadline=NULL")
        else:
            dl = _parse_deadline(args["deadline"])
            if not dl:
                conn.close()
                return {"status": "ERROR", "error": f"Zły format deadline: {args['deadline']}"}
            updates.append("deadline=?"); params.append(dl)
    if "description" in args:
        updates.append("description=?"); params.append(args["description"])
    if "active" in args:
        updates.append("active=?"); params.append(1 if args["active"] else 0)
    if not updates:
        conn.close()
        return {"status": "ERROR", "error": "Nie podano żadnych zmian"}
    params.append(rid)
    conn.execute(f"UPDATE reminders SET {', '.join(updates)} WHERE id=?", params)
    conn.commit()
    updated = dict(conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone())
    conn.close()
    return {"status": "OK", "message": f"✏️ Zaktualizowano!\n\n{_fmt(updated)}"}


def _tool_qbot_reminder_delete(args: dict) -> dict:
    """Usuń lub dezaktywuj przypomnienie. Wymagane: id.
    permanent=true = trwałe usunięcie, domyślnie tylko dezaktywacja."""
    rid = args.get("id") or args.get("reminder_id")
    if not rid:
        return {"status": "ERROR", "error": "Brak id"}
    conn = _db()
    row = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
    if not row:
        conn.close()
        return {"status": "ERROR", "error": f"Nie znaleziono ID {rid}"}
    title = row["title"]
    if args.get("permanent"):
        conn.execute("DELETE FROM reminders WHERE id=?", (rid,))
        conn.execute("DELETE FROM reminders_fired WHERE reminder_id=?", (rid,))
        msg = f"🗑️ Usunięto trwale: <b>{title}</b>"
    else:
        conn.execute("UPDATE reminders SET active=0 WHERE id=?", (rid,))
        msg = f"⏸️ Dezaktywowano: <b>{title}</b> [ID {rid}] (użyj edit z active=true żeby przywrócić)"
    conn.commit()
    conn.close()
    return {"status": "OK", "message": msg}
