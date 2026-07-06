#!/usr/bin/env python3
"""Watcher tras Komoot -> QBot.

Cyklicznie (timer co 5 min) lub na zadanie:
- odswieza sesje Komoot,
- pobiera liste zaplanowanych tras,
- wykrywa NOWE (nieznany tour_id) i ZMIENIONE (nowszy changed_at),
- dla kazdej: pelny ingest (nawierzchnia+wysokosci+POI); opcjonalnie push na Karoo,
- push tylko gdy geometria faktycznie sie zmienila (nie sama nazwa),
- pierwszy przebieg (pusta tabela) = SEED: oznacza istniejace trasy jako widziane BEZ analizy.

Tabela stanu: qbot_v2.komoot_seen_tours.
"""
from __future__ import annotations
import os, sys, json, traceback
sys.path.insert(0, "/opt/qbot/app")
import komoot_auth
import komoot_ingest
from tools.komoot import client as kclient
import api_db


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


def _alert(msg):
    """Alarm: stdout + Telegram (jesli skonfigurowany)."""
    print("[KOMOOT-WATCH ALERT]", msg)
    try:
        _load_env()
        from qbot_telegram_client import send_message
        chat = os.getenv("TELEGRAM_CHAT_ID") or (os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")[0].strip() or None)
        if chat:
            send_message(chat, "Komoot-watch: " + msg)
    except Exception as _e:
        print("[KOMOOT-WATCH] Telegram alarm nieudany:", _e)


def _ensure_table():
    with api_db._conn() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS qbot_v2.komoot_seen_tours ("
            " tour_id text PRIMARY KEY,"
            " changed_at text,"
            " geometry_hash text,"
            " route_id text,"
            " name text,"
            " last_status text,"
            " updated_at timestamptz DEFAULT now())"
        )
        c.commit()


def _seen_map(c):
    rows = c.execute("SELECT tour_id, changed_at, geometry_hash FROM qbot_v2.komoot_seen_tours").fetchall()
    return {r["tour_id"]: dict(r) for r in rows}


def _mark(c, tour_id, changed_at, geometry_hash, route_id, name, status):
    c.execute(
        "INSERT INTO qbot_v2.komoot_seen_tours"
        " (tour_id, changed_at, geometry_hash, route_id, name, last_status, updated_at)"
        " VALUES (%s,%s,%s,%s,%s,%s, now())"
        " ON CONFLICT (tour_id) DO UPDATE SET"
        " changed_at=EXCLUDED.changed_at, geometry_hash=EXCLUDED.geometry_hash,"
        " route_id=EXCLUDED.route_id, name=EXCLUDED.name,"
        " last_status=EXCLUDED.last_status, updated_at=now()",
        (tour_id, changed_at, geometry_hash, route_id, name, status),
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


def _geometry_hash(res):
    try:
        return res["route_base"]["route_base"]["geometry_hash"]
    except Exception:
        return None


def seed(session):
    """Oznacz wszystkie istniejace zaplanowane trasy jako widziane BEZ analizy."""
    _ensure_table()
    tours = _list_all_planned(session)
    with api_db._conn() as c:
        for t in tours:
            _mark(c, t["id"], t.get("changed_at"), None, None, t.get("name"), "seeded")
        c.commit()
    return len(tours)


def check_once(session=None, do_push=False, seed_if_empty=True):
    _load_env()
    _ensure_table()
    session = session or komoot_auth.KomootSession()
    # odswiez sesje z gory, zeby wychwycic wygasniecie i zaalarmowac
    try:
        if not session.is_fresh():
            session.refresh()
    except komoot_auth.KomootAuthError as e:
        _alert("Sesja Komoot padla - przeloguj (skopiuj ciasteczka). %s" % e)
        return {"error": "auth", "detail": str(e)}

    with api_db._conn() as c:
        seen = _seen_map(c)
    if not seen and seed_if_empty:
        n = seed(session)
        return {"seeded": n, "processed": []}

    tours = _list_all_planned(session)
    processed = []
    for t in tours:
        tid = t["id"]
        ca = t.get("changed_at")
        prev = seen.get(tid)
        if prev and prev.get("changed_at") == ca:
            continue  # bez zmian
        try:
            res = komoot_ingest.ingest_komoot_tour(tid, session, precompute=True)
        except Exception:
            _alert("Ingest trasy %s (%s) nie powiodl sie:\n%s" % (tid, t.get("name"), traceback.format_exc()[-600:]))
            with api_db._conn() as c:
                _mark(c, tid, ca, prev.get("geometry_hash") if prev else None,
                      prev.get("route_id") if prev else None, t.get("name"), "error")
                c.commit()
            continue
        gh = _geometry_hash(res)
        route_id = res["artifact"]["route_id"]
        pushed = False
        geom_changed = (not prev) or (prev.get("geometry_hash") != gh)
        if do_push and geom_changed:
            try:
                import qbot_web
                qbot_web.push_karoo(route_id)
                pushed = True
            except Exception:
                _alert("Push na Karoo trasy %s nie powiodl sie:\n%s" % (tid, traceback.format_exc()[-600:]))
        with api_db._conn() as c:
            _mark(c, tid, ca, gh, route_id, t.get("name"),
                  "pushed" if pushed else ("analyzed" if geom_changed else "name_only"))
            c.commit()
        processed.append({"tour_id": tid, "name": t.get("name"),
                          "geom_changed": geom_changed, "pushed": pushed})
    return {"processed": processed, "count": len(processed)}


if __name__ == "__main__":
    _load_env()
    do_push = "--push" in sys.argv
    do_seed = "--seed" in sys.argv
    s = komoot_auth.KomootSession()
    if do_seed:
        n = seed(s)
        print(json.dumps({"seeded": n}, ensure_ascii=False))
    else:
        out = check_once(s, do_push=do_push)
        print(json.dumps(out, ensure_ascii=False, indent=2))
