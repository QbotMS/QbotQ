"""TRENER - operacje na planie wspolne dla strony, Telegrama i crona.

* regenerate(week)      - przelicza SESJE TRENERA (auto, plan, od dzis) jednego tygodnia; Twoje reczne zostaja; zapis zmiany
                          w trainer_change (Akceptuj / Cofnij).
* cascade(from_week)    - ROLOWANIE: po zmianie w tygodniu N przelicza N+1..koniec horyzontu (biezacy + 2), tylko tygodnie,
                          ktore maja juz plan; zmiany "dzieci" sa od razu zaakceptowane i cofaja sie razem z rodzicem.
* day_action            - REST / brak czasu / choroba / delegacja / wyczysc (strona i przyciski Telegrama).
* after_session_edit    - po Twojej zmianie sesji (dodanie / przeniesienie / usuniecie) przelicza tydzien + rolowanie.
* replan_horizon        - po zmianie celow / dostepnosci / Kalibracji / Kalendarza: przelicza caly horyzont.
* calendar_changed      - wykrywa zmiany w Kalendarzu (podpis wpisow w horyzoncie, cache calsig:<user>).
* undo(change)          - cofa zmiane (i jej rolowanie).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

import qbot_trener_engine as E

_SIC = {"rower": "🚲", "sila": "🏋️", "wiosl": "🚣", "joga": "🧘"}
COLS = ["day", "sport", "name", "start_time", "dur_min", "min_min", "zone", "xss", "is_long", "status", "cut", "source", "note"]


def _j(x: dict) -> dict:
    from qbot_trener_api import _jsonable
    return _jsonable(x)


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def horizon(today: date | None = None) -> list[date]:
    m0 = monday(today or date.today())
    return [m0 + timedelta(weeks=k) for k in range(3)]


def desc(x: dict) -> str:
    return f"{str(x['day'])[5:]} {_SIC.get(x['sport'], '')} {x['name']} {str(x.get('start_time') or '')[:5]} {x['dur_min']}′"


def match_done(c, u: str, d0: date, d1: date) -> int:
    """Zrobione z Garmina -> status done w planie (ten sam dzien i sport, najblizsza godzina)."""
    c.execute("SELECT id, day, sport, start_time FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s "
              "AND status='plan' AND training_session_id IS NULL AND day <= CURRENT_DATE", (u, d0, d1))
    plan = c.fetchall()
    if not plan:
        return 0
    c.execute("SELECT id, date, sport_type, started_at FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (d0, d1))
    acts = list(c.fetchall())
    c.execute("SELECT training_session_id FROM qbot_v2.trainer_session WHERE username=%s AND training_session_id IS NOT NULL", (u,))
    used = {r["training_session_id"] for r in c.fetchall()}
    n = 0
    for p in plan:
        best = None
        for a in acts:
            if a["id"] in used or a["date"] != p["day"] or E.SPORT_OF.get(a["sport_type"]) != p["sport"]:
                continue
            dist = abs((a["started_at"].hour * 60 + a["started_at"].minute) - (p["start_time"].hour * 60 + p["start_time"].minute)) if a["started_at"] and p["start_time"] else 0
            if best is None or dist < best[0]:
                best = (dist, a["id"])
        if best:
            used.add(best[1]); n += 1
            c.execute("UPDATE qbot_v2.trainer_session SET status='done', training_session_id=%s, updated_at=now() WHERE id=%s", (best[1], p["id"]))
    return n


def regenerate(c, u: str, d0: date, action: str, payload: dict, accepted: bool | None = None) -> dict:
    match_done(c, u, d0, d0 + timedelta(days=6))
    today = date.today()
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s AND source='auto' AND status='plan' AND day >= %s",
              (u, d0, d0 + timedelta(days=6), today))
    before = [_j(x) for x in c.fetchall()]
    c.execute("DELETE FROM qbot_v2.trainer_session WHERE id = ANY(%s)", ([x["id"] for x in before],))
    ctx = E.build_context(c, u, d0, today)
    res = E.plan_week(ctx)
    after_ids = []
    for x in res["sessions"]:
        cols = ["username"] + COLS
        c.execute(f"INSERT INTO qbot_v2.trainer_session ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id",
                  [u] + [x.get(k) for k in COLS])
        after_ids.append(c.fetchone()["id"])
    bset = {desc(x) for x in before}
    aset = {desc(x) for x in res["sessions"]}
    lines = ["− " + t for t in sorted(bset - aset)] + ["+ " + t for t in sorted(aset - bset)]
    payload = dict(payload, after_ids=after_ids, notes=res["notes"])
    c.execute("INSERT INTO qbot_v2.trainer_change (username, week_start, action, payload, before, after, accepted) "
              "VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s) RETURNING id",
              (u, d0, action, json.dumps(payload, ensure_ascii=False, default=str), json.dumps(before, ensure_ascii=False, default=str),
               json.dumps(res["sessions"], ensure_ascii=False, default=str), accepted))
    cid = c.fetchone()["id"]
    return {"change_id": cid, "week_start": d0.isoformat(), "lines": lines, "notes": res["notes"], "added": len(after_ids), "removed": len(before)}


def _has_plan(c, u: str, ws: date) -> bool:
    c.execute("SELECT 1 FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s LIMIT 1", (u, ws, ws + timedelta(days=6)))
    return bool(c.fetchone())


def cascade(c, u: str, from_ws: date, parent_id: int | None, reason: str) -> list[dict]:
    """Rolowanie: kolejne tygodnie horyzontu (majace plan) przeliczone po zmianie w tygodniu from_ws."""
    out = []
    for ws in horizon():
        if ws <= from_ws or not _has_plan(c, u, ws):
            continue
        r = regenerate(c, u, ws, "rolowanie", {"parent": parent_id, "reason": reason}, accepted=True)
        if r["lines"]:
            out.append(r)
    return out


def _supersede_pending(c, u: str, ws: date) -> None:
    """Nowa automatyczna zmiana tygodnia zastepuje poprzednia oczekujaca (ta sama zostaje w historii jako zaakceptowana)."""
    c.execute("UPDATE qbot_v2.trainer_change SET accepted=true WHERE username=%s AND week_start=%s AND accepted IS NULL", (u, ws))


def day_action(c, u: str, dd: date, act: str) -> dict:
    payload = {"day": dd.isoformat(), "cal_ids": [], "day_state": None, "cleared": []}
    if act in ("rest", "ill", "del"):
        kind, et, title = {"rest": ("event", "rest", "REST DAY"), "ill": ("illness", None, "Choroba"), "del": ("event", "delegacja", "Delegacja")}[act]
        c.execute("INSERT INTO qbot_v2.calendar_entry (day, kind, event_type, title, note) VALUES (%s,%s,%s,%s,'[trener]') RETURNING id", (dd, kind, et, title))
        payload["cal_ids"].append(c.fetchone()["id"])
    elif act == "short":
        c.execute("INSERT INTO qbot_v2.trainer_day (username, day, state) VALUES (%s,%s,'short') ON CONFLICT (username, day) DO NOTHING RETURNING day", (u, dd))
        if c.fetchone():
            payload["day_state"] = dd.isoformat()
    else:
        c.execute("DELETE FROM qbot_v2.calendar_entry WHERE day=%s AND note='[trener]' RETURNING id, day, kind, event_type, title", (dd,))
        payload["cleared"] = [_j(x) for x in c.fetchall()]
        c.execute("DELETE FROM qbot_v2.trainer_day WHERE username=%s AND day=%s", (u, dd))
    ws = monday(dd)
    _supersede_pending(c, u, ws)
    res = regenerate(c, u, ws, "day_" + act, payload)
    res["rolled"] = cascade(c, u, ws, res["change_id"], "day_" + act)
    remember_calendar(c, u)   # nasze wpisy [trener] nie sa "zmiana w Kalendarzu" do ponownego przeliczenia
    return res


def after_session_edit(c, u: str, days: list) -> dict | None:
    """Po Twojej zmianie sesji: przelicz tydzien(e) tej zmiany (sesje trenera) + rolowanie dalej."""
    weeks = sorted({monday(E._d(d)) for d in days if d})
    weeks = [w for w in weeks if w + timedelta(days=6) >= date.today()]
    if not weeks:
        return None
    first = None
    for ws in weeks:
        _supersede_pending(c, u, ws)
        r = regenerate(c, u, ws, "po_zmianie", {"reason": "Twoja zmiana"})
        first = first or r
    first["rolled"] = cascade(c, u, weeks[-1], first["change_id"], "po_zmianie")
    return first


def replan_horizon(c, u: str, reason: str) -> dict | None:
    """Zmiana celow / dostepnosci / Kalibracji / Kalendarza: przelicz biezacy tydzien (do akceptacji) i rolowanie."""
    hz = [w for w in horizon() if _has_plan(c, u, w)]
    if not hz:
        return None
    _supersede_pending(c, u, hz[0])
    r = regenerate(c, u, hz[0], "aktualizacja", {"reason": reason})
    r["rolled"] = cascade(c, u, hz[0], r["change_id"], reason)
    r["reason"] = reason
    return r


def undo(c, u: str, cid: int) -> dict:
    c.execute("SELECT * FROM qbot_v2.trainer_change WHERE id=%s AND username=%s AND accepted IS NOT FALSE", (cid, u))
    ch = c.fetchone()
    if not ch:
        return {"ok": False, "error": "brak zmiany do cofnięcia"}
    c.execute("SELECT id FROM qbot_v2.trainer_change WHERE username=%s AND payload->>'parent' = %s AND accepted IS NOT FALSE ORDER BY id DESC", (u, str(cid)))
    kids = [r["id"] for r in c.fetchall()]
    for k in kids + [cid]:
        c.execute("SELECT * FROM qbot_v2.trainer_change WHERE id=%s", (k,))
        x = c.fetchone()
        p = x["payload"] or {}
        if p.get("after_ids"):
            c.execute("DELETE FROM qbot_v2.trainer_session WHERE username=%s AND id = ANY(%s) AND source='auto'", (u, p["after_ids"]))
        for s in (x["before"] or []):
            c.execute(f"INSERT INTO qbot_v2.trainer_session (username,{','.join(COLS)}) VALUES (%s,{','.join(['%s'] * len(COLS))})", [u] + [s.get(k2) for k2 in COLS])
        if p.get("cal_ids"):
            c.execute("DELETE FROM qbot_v2.calendar_entry WHERE id = ANY(%s) AND note='[trener]'", (p["cal_ids"],))
        if p.get("day_state"):
            c.execute("DELETE FROM qbot_v2.trainer_day WHERE username=%s AND day=%s", (u, p["day_state"]))
        for s in p.get("cleared") or []:
            c.execute("INSERT INTO qbot_v2.calendar_entry (day, kind, event_type, title, note) VALUES (%s,%s,%s,%s,'[trener]')", (s["day"], s["kind"], s["event_type"], s["title"]))
        c.execute("UPDATE qbot_v2.trainer_change SET accepted=false WHERE id=%s", (k,))
    remember_calendar(c, u)
    return {"ok": True, "undone": cid, "rolled_back": kids}


# ---------------- zmiany w Kalendarzu ----------------
def calendar_signature(c) -> str:
    hz = horizon()
    a, b = hz[0] - timedelta(days=3), hz[-1] + timedelta(days=7)
    c.execute("""SELECT e.id, e.day, e.end_day, e.kind, e.event_type, e.title, e.at_time, e.note,
                        (SELECT string_agg(r.route_id || '@' || r.day::text, ',' ORDER BY r.day) FROM qbot_v2.calendar_day_route r WHERE r.entry_id = e.id) AS routes
                 FROM qbot_v2.calendar_entry e WHERE e.day <= %s AND COALESCE(e.end_day, e.day) >= %s ORDER BY e.id""", (b, a))
    return hashlib.sha1(json.dumps([list(dict(r).values()) for r in c.fetchall()], default=str).encode()).hexdigest()


def remember_calendar(c, u: str) -> None:
    sig = calendar_signature(c)
    c.execute("INSERT INTO qbot_v2.trainer_auto_cache (key, value, computed_at) VALUES (%s, %s::jsonb, now()) "
              "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, computed_at=now()", (f"calsig:{u}", json.dumps({"sig": sig})))


def calendar_changed(c, u: str) -> dict | None:
    """Jesli Kalendarz w horyzoncie zmienil sie od ostatniego razu -> przelicz horyzont. Pierwsze wywolanie tylko zapamietuje."""
    sig = calendar_signature(c)
    c.execute("SELECT value FROM qbot_v2.trainer_auto_cache WHERE key=%s", (f"calsig:{u}",))
    r = c.fetchone()
    old = (r["value"] or {}).get("sig") if r else None
    if old == sig:
        return None
    res = replan_horizon(c, u, "zmiana w Kalendarzu") if old else None
    remember_calendar(c, u)
    return res
