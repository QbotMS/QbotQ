"""qbot_notif.py - Centrum powiadomien (dzwonek w menu, 2026-10-08).

Jedno wspolne miejsce: tabela qbot_v2.notif (sql/notif_v1.sql). Dwa rodzaje pozycji:
- ZDARZENIA (klucz bez prefiksu live:) - dopisywane przez moduly przez push(), np. Trener
  (plan tygodnia, rozliczenie, zmiana planu z Kalendarza / po wykonaniu). Widoczne 14 dni.
- STAN NA ZYWO (klucz live:...) - liczony przy kazdym odczycie przez sync_live(): zadania przy
  rowerze (garage.db bike_task), trasy czekajace na potwierdzenie w Telegramie, brak swiezych danych
  (sen, waga > 3 dni). Gdy warunek znika, pozycja sama sie zamyka (resolved_at).
Telegram dziala jak dotad - dzwonek go nie zastepuje.
Zmiana tresci pozycji => znow nieprzeczytana. Daty w tekstach DD.MM.
"""
from __future__ import annotations

from datetime import date, datetime

EVENT_DAYS = 14
STALE_DAYS = 3

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.notif (
    id          BIGSERIAL PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT,
    url         TEXT,
    action      JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at     TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ
)"""

KIND_ICON = {"rower": "🔧", "trasa": "🗺️", "trener": "🏋️", "dane": "📡", "system": "⚙️"}


def _row(cur):
    r = cur.fetchone()
    if r is None:
        return None
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def _rows(cur):
    rs = cur.fetchall()
    if rs and not isinstance(rs[0], dict):
        cols = [d[0] for d in cur.description]
        rs = [dict(zip(cols, r)) for r in rs]
    return rs


def push(cur, key: str, kind: str, title: str, body: str | None = None, url: str | None = None,
         action: dict | None = None) -> None:
    """Dodaj albo odswiez pozycje. Nowa tresc albo ponowne otwarcie => nieprzeczytana."""
    import json
    aj = json.dumps(action, ensure_ascii=False) if action else None
    cur.execute("SELECT title, body, resolved_at FROM qbot_v2.notif WHERE key=%s", (key,))
    old = _row(cur)
    if old is None:
        cur.execute("INSERT INTO qbot_v2.notif (key, kind, title, body, url, action) VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                    (key, kind, title, body, url, aj))
    elif old["resolved_at"] is not None:
        cur.execute("UPDATE qbot_v2.notif SET kind=%s, title=%s, body=%s, url=%s, action=%s::jsonb, created_at=now(), "
                    "updated_at=now(), read_at=NULL, resolved_at=NULL WHERE key=%s", (kind, title, body, url, aj, key))
    elif (old["title"], old["body"]) != (title, body):
        cur.execute("UPDATE qbot_v2.notif SET kind=%s, title=%s, body=%s, url=%s, action=%s::jsonb, updated_at=now(), "
                    "read_at=NULL WHERE key=%s", (kind, title, body, url, aj, key))
    else:
        cur.execute("UPDATE qbot_v2.notif SET url=%s, action=%s::jsonb WHERE key=%s", (url, aj, key))


def resolve(cur, key: str) -> None:
    cur.execute("UPDATE qbot_v2.notif SET resolved_at=now() WHERE key=%s AND resolved_at IS NULL", (key,))


def _ddmm(d) -> str:
    if isinstance(d, (date, datetime)):
        return d.strftime("%d.%m")
    s = str(d or "")
    return f"{s[8:10]}.{s[5:7]}" if len(s) >= 10 else s


# ---------------- stan na zywo (czyste funkcje -> lista pozycji) ----------------

def live_bike(tasks: list[dict]) -> list[dict]:
    """Otwarte zadania przy rowerze -> jedna pozycja na rower."""
    by: dict = {}
    for t in tasks:
        by.setdefault(t.get("bike_id") or 0, []).append(t)
    out = []
    for bid, ts in by.items():
        labs = ", ".join(dict.fromkeys(t["label"] for t in ts))
        last = ts[-1]
        out.append({"key": f"live:rower:{bid}", "kind": "rower",
                    "title": f"{ts[0].get('bike') or 'Rower'}: do zrobienia ({len(ts)})",
                    "body": labs + f" — po jeździe {_ddmm(last.get('created_at'))}",
                    "url": "/raport-jazdy.html?ride=" + str(last.get("ride_key") or ""),
                    "action": {"label": "Zrobione", "post": "/api/bike-tasks/done", "body": {"ids": [t["id"] for t in ts]}}})
    return out


def live_routes(pending: list[dict]) -> list[dict]:
    out = []
    for p in pending:
        prev = (p.get("preview_text") or "").strip().splitlines()
        out.append({"key": f"live:trasa:{p['id']}", "kind": "trasa",
                    "title": "Trasa czeka na potwierdzenie",
                    "body": (prev[0][:160] if prev else f"akcja #{p['id']}") + " — odpowiedz w Telegramie",
                    "url": None, "action": None})
    return out


def live_stale(latest: dict, today: date) -> list[dict]:
    """latest = {'sen': date|None, 'waga': date|None}."""
    out = []
    for name, d in latest.items():
        age = (today - d).days if d else None
        if age is None or age > STALE_DAYS:
            out.append({"key": f"live:dane:{name}", "kind": "dane",
                        "title": f"Brak świeżych danych: {name}",
                        "body": f"ostatnie {_ddmm(d)} ({age} dni temu)" if d else "brak danych",
                        "url": "/forma.html", "action": None})
    return out


def sync_live(cur, garage_db: str | None = None, today: date | None = None) -> int:
    """Przelicz pozycje live:*. Kazde zrodlo osobno - blad jednego nie blokuje reszty."""
    today = today or date.today()
    items: list[dict] = []
    ok_prefixes: list[str] = []
    try:
        from qbot3.rides import bike_tasks as BT
        gc = BT.conn(garage_db)
        try:
            items += live_bike(BT.open_tasks(gc))
        finally:
            gc.close()
        ok_prefixes.append("live:rower:")
    except Exception:
        pass
    try:
        cur.execute("SELECT id, preview_text FROM public.telegram_pending_actions "
                    "WHERE status='pending' AND (expires_at IS NULL OR expires_at > now()) "
                    "AND action_type IN ('confirm_route_analysis','confirm_komoot_analysis') ORDER BY id")
        items += live_routes(_rows(cur))
        ok_prefixes.append("live:trasa:")
    except Exception:
        cur.connection.rollback()
    try:
        cur.execute("SELECT (SELECT max(date) FROM qbot_v2.qbot_wellness_daily WHERE sleep_score IS NOT NULL) AS sen, "
                    "(SELECT max(day) FROM qbot_v2.fitmodel_daily WHERE weight_kg IS NOT NULL) AS waga")
        items += live_stale(dict(_row(cur)), today)
        ok_prefixes.append("live:dane:")
    except Exception:
        cur.connection.rollback()
    keep = set()
    for it in items:
        push(cur, it["key"], it["kind"], it["title"], it["body"], it["url"], it["action"])
        keep.add(it["key"])
    cur.execute("SELECT key FROM qbot_v2.notif WHERE key LIKE 'live:%%' AND resolved_at IS NULL")
    for r in _rows(cur):
        if r["key"] not in keep and any(r["key"].startswith(p) for p in ok_prefixes):
            resolve(cur, r["key"])
    return len(items)


def listing(cur, limit: int = 60) -> dict:
    cur.execute("SELECT id, key, kind, title, body, url, action, created_at, updated_at, read_at FROM qbot_v2.notif "
                "WHERE resolved_at IS NULL AND (key LIKE 'live:%%' OR updated_at > now() - make_interval(days => %s)) "
                "ORDER BY (read_at IS NULL) DESC, updated_at DESC LIMIT %s", (EVENT_DAYS, limit))
    items = []
    for r in _rows(cur):
        items.append({"id": r["id"], "kind": r["kind"], "icon": KIND_ICON.get(r["kind"], "🔔"), "title": r["title"],
                      "body": r["body"], "url": r["url"], "action": r["action"], "unread": r["read_at"] is None,
                      "when": r["updated_at"].strftime("%d.%m %H:%M") if r["updated_at"] else "",
                      "live": r["key"].startswith("live:")})
    return {"unread": sum(1 for i in items if i["unread"]), "items": items}


def mark_read(cur, ids: list | None = None) -> int:
    if ids:
        cur.execute("UPDATE qbot_v2.notif SET read_at=now() WHERE read_at IS NULL AND id = ANY(%s)", ([int(i) for i in ids],))
    else:
        cur.execute("UPDATE qbot_v2.notif SET read_at=now() WHERE read_at IS NULL AND resolved_at IS NULL")
    return cur.rowcount


def dismiss(cur, nid: int) -> int:
    """Ukryj zdarzenie (stan na zywo wroci, jesli warunek dalej trwa)."""
    cur.execute("UPDATE qbot_v2.notif SET resolved_at=now(), read_at=coalesce(read_at, now()) WHERE id=%s", (int(nid),))
    return cur.rowcount
