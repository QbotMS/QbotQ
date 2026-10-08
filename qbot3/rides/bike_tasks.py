"""bike_tasks.py - "Rower po jezdzie - do zrobienia" (2026-10-08).

Zadania serwisowe zaznaczane w Raporcie z jazdy (okno "Ubior / rower") per jazda i rower.
Przechowywanie: garage.db (SQLite), tabela bike_task. Przypomnienie: qbot_trener_notify.tick
wysyla na Telegram 2 h przed najblizsza zaplanowana jazda rowerowa z Trenera (bez godziny startu:
o 7:00 w dniu jazdy); przycisk "Zrobione" (tr:bt:<max_id>) odhacza wszystkie pokazane zadania.
Niezrobione zadanie wraca przed kazda kolejna zaplanowana jazda.
"""
from __future__ import annotations

import sqlite3

GARAGE_DB = "/opt/qbot/app/data/garage.db"

# klucz -> etykieta (kolejnosc = kolejnosc na liscie)
TASKS = [
    ("naped", "regulacja napędu"),
    ("ustawienia", "regulacja ustawień"),
    ("lancuch", "wymień łańcuch"),
    ("hamulce", "sprawdź hamulce"),
    ("kola", "sprawdź koła"),
    ("swiatla", "naładuj światła"),
    ("smar", "nasmaruj"),
]
LABEL = dict(TASKS)

DDL = """CREATE TABLE IF NOT EXISTS bike_task (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ride_key   TEXT NOT NULL,
    bike_id    INTEGER,
    task       TEXT NOT NULL,
    note       TEXT,
    status     TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','done')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    done_at    TEXT,
    UNIQUE (ride_key, task)
)"""


def conn(path: str | None = None) -> sqlite3.Connection:
    c = sqlite3.connect(path or GARAGE_DB)
    c.row_factory = sqlite3.Row
    ensure(c)
    return c


def ensure(c: sqlite3.Connection) -> None:
    c.execute(DDL)


def _bike_names(c) -> dict:
    try:
        return {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM bikes").fetchall()}
    except sqlite3.Error:
        return {}


def for_ride(c, ride_key: str) -> dict:
    """Zadania tej jazdy + otwarte zadania z innych jazd (do wgladu w oknie)."""
    rows = c.execute("SELECT * FROM bike_task WHERE ride_key=? ORDER BY id", (ride_key,)).fetchall()
    mine = {r["task"]: {"id": r["id"], "status": r["status"], "bike_id": r["bike_id"]} for r in rows}
    note = next((r["note"] for r in rows if r["note"]), "")
    names = _bike_names(c)
    other = [{"id": r["id"], "task": r["task"], "label": LABEL.get(r["task"], r["task"]),
              "bike": names.get(r["bike_id"]), "ride_key": r["ride_key"], "created_at": r["created_at"]}
             for r in c.execute("SELECT * FROM bike_task WHERE status='todo' AND ride_key<>? ORDER BY id",
                                (ride_key,)).fetchall()]
    return {"tasks": [{"key": k, "label": v} for k, v in TASKS], "mine": mine, "note": note, "open_other": other}


def save(c, ride_key: str, bike_id, tasks: list, note: str | None) -> dict:
    """Ustaw liste zadan jazdy. Zaznaczone -> 'todo' (zrobione zostaja zrobione);
    odznaczone, jeszcze niezrobione -> usuniete."""
    ride_key = str(ride_key or "").strip()[:64]
    if not ride_key:
        raise ValueError("Brak ride")
    want = [t for t in dict.fromkeys(tasks or []) if t in LABEL]
    try:
        bike_id = int(bike_id) if bike_id not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        bike_id = None
    note = (str(note or "").strip()[:300]) or None
    for r in c.execute("SELECT id, task, status FROM bike_task WHERE ride_key=?", (ride_key,)).fetchall():
        if r["task"] not in want and r["status"] == "todo":
            c.execute("DELETE FROM bike_task WHERE id=?", (r["id"],))
    for t in want:
        c.execute("INSERT INTO bike_task (ride_key, bike_id, task, note) VALUES (?,?,?,?) "
                  "ON CONFLICT(ride_key, task) DO UPDATE SET bike_id=excluded.bike_id, note=excluded.note",
                  (ride_key, bike_id, t, note))
    c.execute("UPDATE bike_task SET note=? WHERE ride_key=?", (note, ride_key))
    c.commit()
    return {"ok": True, "ride": ride_key, "saved": len(want)}


def mark_done(c, ids=None, max_id: int | None = None) -> int:
    if ids:
        q = ",".join("?" * len(ids))
        n = c.execute(f"UPDATE bike_task SET status='done', done_at=datetime('now') "
                      f"WHERE status='todo' AND id IN ({q})", [int(i) for i in ids]).rowcount
    elif max_id is not None:
        n = c.execute("UPDATE bike_task SET status='done', done_at=datetime('now') "
                      "WHERE status='todo' AND id<=?", (int(max_id),)).rowcount
    else:
        n = 0
    c.commit()
    return n


def open_tasks(c) -> list[dict]:
    names = _bike_names(c)
    return [{"id": r["id"], "task": r["task"], "label": LABEL.get(r["task"], r["task"]),
             "bike_id": r["bike_id"], "bike": names.get(r["bike_id"]), "note": r["note"],
             "ride_key": r["ride_key"], "created_at": r["created_at"]}
            for r in c.execute("SELECT * FROM bike_task WHERE status='todo' ORDER BY bike_id, id").fetchall()]


def _ddmm(ts: str | None) -> str:
    s = str(ts or "")
    return f"{s[8:10]}.{s[5:7]}" if len(s) >= 10 else ""


def reminder_text(session_name: str, start: str | None, tasks: list[dict]) -> str | None:
    """Tekst powiadomienia przed jazda (czysty, testowalny). Brak zadan -> None."""
    if not tasks:
        return None
    when = f"o {start}" if start else "dziś"
    lines = [f"🔧 Przed jazdą {when} ({session_name}) — przy rowerze do zrobienia:"]
    groups: dict = {}
    for t in tasks:
        groups.setdefault(t.get("bike") or "rower", []).append(t)
    for bike, ts in groups.items():
        labs = ", ".join(dict.fromkeys(t["label"] for t in ts))
        dates = sorted({_ddmm(t.get("created_at")) for t in ts if t.get("created_at")})
        notes = [t["note"] for t in ts if t.get("note")]
        lines.append(f"• {bike}: {labs}" + (f" (po jeździe {', '.join(dates)})" if dates else ""))
        for n_ in dict.fromkeys(notes):
            lines.append(f"   ↳ {n_}")
    lines.append("Zrobione? Kliknij poniżej — inaczej przypomnę przed kolejną jazdą.")
    return "\n".join(lines)
