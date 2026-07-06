#!/usr/bin/env python3
"""Watcher tras Komoot -> QBot (tryb: TYLKO POWIADAMIAJ).

Timer co 5 min:
- odswieza sesje Komoot,
- pobiera liste zaplanowanych tras,
- wykrywa NOWE (nieznany tour_id) i ZMIENIONE (nowszy changed_at),
- wysyla powiadomienie Telegram z przyciskami [Analizuj]/[Pomin] i sygnatura (nazwa + data utw. + #id),
- SAM NIE ingestuje i NIE pushuje.

Decyzje z przyciskow obsluguje telegram_reply_processor -> analyze_tour() / skip_tour().
Pierwszy przebieg (pusta tabela) = SEED: oznacza istniejace trasy jako widziane bez pytania.

Tabela stanu: qbot_v2.komoot_seen_tours.
"""
from __future__ import annotations
import os, sys, json, traceback
sys.path.insert(0, "/opt/qbot/app")
import komoot_auth
import komoot_ingest
from tools.komoot import client as kclient
import api_db

MIDDOT = "\u00b7"


def _load_env():
    import glob as _g
    for _ef in _g.glob("/etc/qbot/*.env"):
        try:
            for _line in open(_ef):
                if "=" in _line and not _line.startswith("#"):
                    _k, _, _v = _line.strip().partition("=")
                    os.environ.setdefault(_k, _v)
        except Exception:
            pass


def _chat_id():
    return os.getenv("TELEGRAM_CHAT_ID") or (os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")[0].strip() or None)


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _alert(msg):
    print("[KOMOOT-WATCH ALERT]", msg)
    try:
        _load_env()
        from qbot_telegram_client import send_message
        chat = _chat_id()
        if chat:
            send_message(chat, "Komoot-watch: " + msg)
    except Exception as _e:
        print("[KOMOOT-WATCH] Telegram alarm nieudany:", _e)


def _notify(t):
    """Powiadomienie z przyciskami. Zwraca True jesli wyslano."""
    _load_env()
    chat = _chat_id()
    if not chat:
        print("[KOMOOT-WATCH] brak TELEGRAM_CHAT_ID - nie moge powiadomic")
        return False
    tid = str(t["id"])
    name = t.get("name") or ("Komoot " + tid)
    d = (t.get("date") or "")[:10]
    km = t.get("distance_m")
    km_s = ("%.1f km" % (km / 1000.0)) if km else ""
    line2 = "#" + tid
    if d:
        line2 += " " + MIDDOT + " utworzona " + d
    if km_s:
        line2 += " " + MIDDOT + " " + km_s
    text = ("\U0001F195 <b>Nowa trasa z Komoot</b>\n" + _esc(name) + "\n" + line2 + "\nAnalizowac w QBot?")
    kb = {"inline_keyboard": [[
        {"text": "\u2705 Analizuj", "callback_data": "kmt:y:" + tid},
        {"text": "\u274C Pomin", "callback_data": "kmt:n:" + tid},
    ]]}
    from qbot_telegram_client import _api
    r = _api("sendMessage", {"chat_id": str(chat), "text": text, "parse_mode": "HTML", "reply_markup": kb})
    return bool(r and r.get("ok"))


# -- tabela stanu ---------------------------------------------------------------

def _ensure_table():
    with api_db._conn() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS qbot_v2.komoot_seen_tours ("
            " tour_id text PRIMARY KEY, changed_at text, geometry_hash text,"
            " route_id text, name text, created_date text, last_status text,"
            " updated_at timestamptz DEFAULT now())"
        )
        c.execute("ALTER TABLE qbot_v2.komoot_seen_tours ADD COLUMN IF NOT EXISTS created_date text")
        c.commit()


def _seen_map(c):
    rows = c.execute("SELECT tour_id, changed_at, geometry_hash, route_id, name, created_date, last_status FROM qbot_v2.komoot_seen_tours").fetchall()
    return {r["tour_id"]: dict(r) for r in rows}


def _mark(c, tour_id, changed_at, geometry_hash, route_id, name, created_date, status):
    c.execute(
        "INSERT INTO qbot_v2.komoot_seen_tours"
        " (tour_id, changed_at, geometry_hash, route_id, name, created_date, last_status, updated_at)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s, now())"
        " ON CONFLICT (tour_id) DO UPDATE SET"
        " changed_at=EXCLUDED.changed_at, geometry_hash=EXCLUDED.geometry_hash,"
        " route_id=EXCLUDED.route_id, name=EXCLUDED.name, created_date=EXCLUDED.created_date,"
        " last_status=EXCLUDED.last_status, updated_at=now()",
        (tour_id, changed_at, geometry_hash, route_id, name, created_date, status),
    )


def _list_all_planned(session, cap=1200):
    out = []
    page = 0
    while True:
        r = kclient.list_planned_tours(session, limit=50, page=page)
        ts = r["tours"]
        out.extend(ts)
        if len(ts) < 50 or len(out) >= cap:
            break
        page += 1
    return out


def seed(session):
    _ensure_table()
    tours = _list_all_planned(session)
    with api_db._conn() as c:
        for t in tours:
            _mark(c, str(t["id"]), t.get("changed_at"), None, None, t.get("name"), (t.get("date") or "")[:10], "seeded")
        c.commit()
    return len(tours)


def check_once(session=None, seed_if_empty=True):
    _load_env()
    _ensure_table()
    session = session or komoot_auth.KomootSession()
    try:
        if not session.is_fresh():
            session.refresh()
    except komoot_auth.KomootAuthError as e:
        _alert("Sesja Komoot padla - przeloguj (ciasteczka). %s" % e)
        return {"error": "auth", "detail": str(e)}
    with api_db._conn() as c:
        seen = _seen_map(c)
    if not seen and seed_if_empty:
        n = seed(session)
        return {"seeded": n, "notified": []}
    tours = _list_all_planned(session)
    notified = []
    for t in tours:
        tid = str(t["id"])
        ca = t.get("changed_at")
        prev = seen.get(tid)
        if prev and prev.get("changed_at") == ca:
            continue  # bez zmian od ostatniego razu
        ok = _notify(t)
        with api_db._conn() as c:
            _mark(c, tid, ca,
                  prev.get("geometry_hash") if prev else None,
                  prev.get("route_id") if prev else None,
                  t.get("name"), (t.get("date") or "")[:10],
                  "asked" if ok else "notify_failed")
            c.commit()
        notified.append({"tour_id": tid, "name": t.get("name"), "notified": ok})
    return {"notified": notified, "count": len(notified)}


# -- akcje z przyciskow (wolane przez telegram_reply_processor) ------------------

def analyze_tour(tour_id, session=None):
    """Po klikni. [Analizuj]: pelny ingest (material do web). Zwraca {route_id, name}."""
    _load_env()
    _ensure_table()
    tour_id = str(tour_id)
    session = session or komoot_auth.KomootSession()
    res = komoot_ingest.ingest_komoot_tour(tour_id, session, precompute=True)
    art = res.get("artifact", {})
    gh = None
    try:
        gh = res["route_base"]["route_base"]["geometry_hash"]
    except Exception:
        pass
    with api_db._conn() as c:
        row = c.execute("SELECT changed_at, created_date FROM qbot_v2.komoot_seen_tours WHERE tour_id=%s", (tour_id,)).fetchone()
        ca = row["changed_at"] if row else None
        cd = row["created_date"] if row else None
        _mark(c, tour_id, ca, gh, art.get("route_id"), art.get("name"), cd, "analyzed")
        c.commit()
    return {"route_id": art.get("route_id"), "name": art.get("route_name") or art.get("name"), "geometry_hash": gh}


def skip_tour(tour_id):
    _ensure_table()
    tour_id = str(tour_id)
    with api_db._conn() as c:
        row = c.execute("SELECT changed_at, geometry_hash, route_id, name, created_date FROM qbot_v2.komoot_seen_tours WHERE tour_id=%s", (tour_id,)).fetchone()
        _mark(c, tour_id,
              row["changed_at"] if row else None,
              row["geometry_hash"] if row else None,
              row["route_id"] if row else None,
              row["name"] if row else None,
              row["created_date"] if row else None,
              "skipped")
        c.commit()
    return {"tour_id": tour_id, "status": "skipped"}


if __name__ == "__main__":
    s = komoot_auth.KomootSession()
    if "--seed" in sys.argv:
        print(json.dumps({"seeded": seed(s)}, ensure_ascii=False))
    elif "--notify-test" in sys.argv:
        # jednorazowy test powiadomienia dla podanego tour_id
        tid = sys.argv[sys.argv.index("--notify-test") + 1]
        from tools.komoot import client as _k
        meta = _k.get_tour_meta(tid, s)
        t = {"id": tid, "name": meta.get("name"), "date": meta.get("date"), "distance_m": meta.get("distance_m")}
        print(json.dumps({"notified": _notify(t)}, ensure_ascii=False))
    else:
        print(json.dumps(check_once(s), ensure_ascii=False, indent=2))
