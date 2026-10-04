"""TRENER - prosba do AI o zmiane planu tygodnia ("napisz, co chcesz zmienic").

propose(c, user, ws, text) -> {summary, changes[], rejected[]}  - AI (QGPT) dostaje tydzien (sesje Z ID, dni, zajetosci,
    pogoda, gotowosc) + tresc prosby i zwraca liste konkretnych operacji. NIC nie zapisuje.
apply(c, user, ws, text, changes) -> {change_id, lines, notes} - ponowna walidacja po stronie serwera, wykonanie jako
    TWOJE zmiany (source=manual, silnik ich nie rusza), zapis w trainer_change (action 'prosba_ai', Akceptuj / Cofnij),
    potem przeliczenie sesji trenera w tygodniu + rolowanie (dzieci z payload.parent - cofaja sie razem).
Operacje: add (nowa sesja), edit (godzina / czas / dzien / nazwa / notatka / pominiete partie sily), remove (status skip
    + "usunięte przez Ciebie", jak w UI). Bezpieczniki: maks. 6 operacji, tylko dni tego tygodnia od dzis, sesje z tego
    tygodnia i nie zrobione, sporty i partie z listy, kolizje z zajetosciami jako ostrzezenie.
Cofanie: payload.ai = {created: [id], restore: [wiersze sprzed zmiany]} - obsluga w qbot_trener_ops.undo.
Testy: tests/test_trener_ask.py (walidacja, bez LLM).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

import qbot_trener_engine as E
import qbot_trener_workouts as TW

SPORTS = ("rower", "sila", "wiosl", "joga")
SNAME = {"rower": "Rower spokojnie", "sila": "Siła obwodowa", "wiosl": "Wioślarz spokojnie", "joga": "Joga"}
SIC = {"rower": "🚲", "sila": "🏋️", "wiosl": "🚣", "joga": "🧘"}
MIN_MIN = {"rower": 30, "sila": 15, "wiosl": 15, "joga": 10}
MAX_OPS = 6
REST_COLS = ["day", "sport", "name", "start_time", "dur_min", "min_min", "zone", "xss", "is_long", "status", "cut", "source", "note", "opts"]
DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]

SYSTEM = """Jesteś asystentem trenera (kolarstwo gravel/bikepacking + siła obwodowa + wioślarz + joga). Użytkownik pisze PROŚBĘ
o zmianę planu tygodnia. Zamień ją na listę KONKRETNYCH operacji na planie. Dostajesz: prośbę, dziś, tydzień (dni: typ,
zajętości, pogoda, sesje z \"id\"), gotowość i dozwolone wartości.
OPERACJE:
- {\"op\":\"add\",\"day\":\"RRRR-MM-DD\",\"sport\":\"rower|sila|wiosl|joga\",\"start\":\"HH:MM\",\"dur_min\":N,\"name\":\"krótko\",\"note\":\"krótko\",\"skip_groups\":[...]}
- {\"op\":\"edit\",\"id\":ID,\"start\":\"HH:MM\",\"dur_min\":N,\"day\":\"RRRR-MM-DD\",\"name\":\"...\",\"note\":\"...\",\"skip_groups\":[...]} (podaj tylko pola do zmiany)
- {\"op\":\"remove\",\"id\":ID}
skip_groups (tylko siła) = partie do POMINIĘCIA, z listy: nogi, klatka, ramiona, plecy, barki, brzuch. \"bez nóg\" = [\"nogi\"]
(wypadają też ćwiczenia na tył ciała). Pusta lista [] = przywróć pełny obwód.
ZASADY: rób DOKŁADNIE to, o co prosi użytkownik — nic ponad to (nie przestawiaj innych sesji, chyba że prosi albo jest
twarda kolizja). Istniejącą sesję zmieniaj przez edit z jej id (nie usuwaj i nie dodawaj od nowa). Nową sesję wstaw w
wolnym miejscu dnia: nie w zajętości, nie nakładając się na inną sesję (zostaw ≥30 min przerwy), rozsądna pora (07:00–20:00);
DZIŚ tylko po "teraz" (godzina w danych) — nigdy na porę, która już minęła; dotyczy też przesuwania dzisiejszych sesji.
Nazwy własne z prośby (np. rower "Grail", miejsce, osoba) przepisuj DOKŁADNIE, litera w literę — nie poprawiaj ich.
gdy prośba podaje zakres czasu (np. 30–45 min) — wybierz środek i zapisz zakres w note. Dni tylko z tego tygodnia, od dziś.
Gdy prośba jest niejasna albo niemożliwa — pusta lista operacji i w summary jedno pytanie / wyjaśnienie.
W summary (1–2 zdania, prosto, po polsku) napisz, co zmieniasz; dodaj krótką uwagę TYLKO gdy coś grozi zdrowiu
(np. ciężka jazda dzień przed długą, choroba) — opieraj się na danych.
Odpowiedz WYŁĄCZNIE JSON: {\"summary\":\"...\",\"changes\":[...]}"""


def _hm(v) -> str | None:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*", str(v or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _mins(hm: str | None) -> int | None:
    return None if not hm else int(hm[:2]) * 60 + int(hm[3:5])


def _txt(v, n: int) -> str | None:
    t = re.sub(r"\s+", " ", str(v or "")).strip()
    return t[:n] or None


def _skip(v):
    """None = brak zmiany; lista = nowe pominiete partie (pusta = pelny obwod)."""
    if v is None:
        return None
    if not isinstance(v, list):
        v = [v]
    return TW.clean_skip([str(x).strip().lower() for x in v])


def _desc(day, sport, name, start, dur) -> str:
    d = E._d(day)
    return f"{DN[d.weekday()]} {d.strftime('%d.%m')} {SIC.get(sport, '')} {name} {start or ''} {dur}′".replace("  ", " ")


def validate(resp, ws: date, today: date, sessions: list, busy: dict | None = None) -> dict:
    """Sprawdza operacje AI (albo odeslane z przegladarki). Zwraca {summary, changes (z 'line' i 'warn'), rejected}."""
    if not isinstance(resp, dict):
        return {"summary": "Nie udało się odczytać odpowiedzi AI.", "changes": [], "rejected": []}
    busy = busy or {}
    days = {(ws + timedelta(days=i)).isoformat() for i in range(7) if ws + timedelta(days=i) >= today}
    by_id = {int(s["id"]): s for s in sessions}
    out, rej, used = [], [], set()
    for it in (resp.get("changes") or [])[: MAX_OPS * 2]:
        if len(out) >= MAX_OPS:
            rej.append(f"pominięto — maks. {MAX_OPS} zmian naraz")
            break
        if not isinstance(it, dict):
            continue
        op = str(it.get("op") or "").lower()
        if op == "add":
            day = str(it.get("day") or "")[:10]
            sport = str(it.get("sport") or "")
            start = _hm(it.get("start"))
            try:
                dur = int(round(float(it.get("dur_min"))))
            except (TypeError, ValueError):
                dur = 0
            if day not in days:
                rej.append(f"dodanie: dzień {day or '?'} spoza tygodnia albo z przeszłości"); continue
            if sport not in SPORTS:
                rej.append(f"dodanie: nieznany sport {sport or '?'}"); continue
            if not (5 <= dur <= 600):
                rej.append(f"dodanie: czas {dur}′ poza zakresem 5–600"); continue
            skip = _skip(it.get("skip_groups")) if sport == "sila" else None
            name = _txt(it.get("name"), 60) or SNAME[sport]
            if skip:
                name = SNAME["sila"] + " (bez: " + ", ".join(skip) + ")"
            ch = {"op": "add", "day": day, "sport": sport, "start": start, "dur_min": dur, "name": name,
                  "note": _txt(it.get("note"), 120), "skip_groups": skip or None}
            ch["line"] = "+ " + _desc(day, sport, name, start, dur) + (f" · {ch['note']}" if ch["note"] else "")
        elif op in ("edit", "remove"):
            try:
                sid = int(it.get("id"))
            except (TypeError, ValueError):
                rej.append(f"{op}: brak id sesji"); continue
            s = by_id.get(sid)
            if not s:
                rej.append(f"{op}: sesji {sid} nie ma w tym tygodniu"); continue
            if sid in used:
                rej.append(f"{op}: sesja {sid} zmieniana dwa razy"); continue
            if s["status"] == "done" or E._d(s["day"]) < today:
                rej.append(f"{op}: {s['name']} — zrobiona albo z przeszłości"); continue
            old = _desc(s["day"], s["sport"], s["name"], str(s.get("start_time") or "")[:5] or None, s["dur_min"])
            if op == "remove":
                ch = {"op": "remove", "id": sid, "line": "− " + old}
            else:
                ch = {"op": "edit", "id": sid}
                if it.get("day") is not None:
                    d = str(it.get("day"))[:10]
                    if d not in days:
                        rej.append(f"zmiana: dzień {d} spoza tygodnia albo z przeszłości"); continue
                    ch["day"] = d
                if it.get("start") is not None:
                    st = _hm(it.get("start"))
                    if not st:
                        rej.append(f"zmiana: zła godzina {it.get('start')}"); continue
                    ch["start"] = st
                if it.get("dur_min") is not None:
                    try:
                        dur = int(round(float(it.get("dur_min"))))
                    except (TypeError, ValueError):
                        dur = 0
                    if not (5 <= dur <= 600):
                        rej.append(f"zmiana: czas {dur}′ poza zakresem 5–600"); continue
                    ch["dur_min"] = dur
                if it.get("name") is not None and _txt(it.get("name"), 60):
                    ch["name"] = _txt(it.get("name"), 60)
                if it.get("note") is not None:
                    ch["note"] = _txt(it.get("note"), 120)
                if it.get("skip_groups") is not None:
                    if s["sport"] != "sila":
                        rej.append(f"zmiana: pomijanie partii tylko dla siły ({s['name']})"); continue
                    ch["skip_groups"] = _skip(it.get("skip_groups"))
                    if "name" not in ch:
                        ch["name"] = SNAME["sila"] + ((" (bez: " + ", ".join(ch["skip_groups"]) + ")") if ch["skip_groups"] else "")
                if len(ch) <= 2:
                    rej.append(f"zmiana: nic do zmiany w {s['name']}"); continue
                new = _desc(ch.get("day", s["day"]), s["sport"], ch.get("name", s["name"]),
                            ch.get("start", str(s.get("start_time") or "")[:5] or None), ch.get("dur_min", s["dur_min"]))
                ch["line"] = "~ " + old + " → " + new + (f" · {ch['note']}" if ch.get("note") else "")
            used.add(sid)
        else:
            rej.append(f"nieznana operacja: {op or '?'}"); continue
        # kolizje z zajetosciami dnia (ostrzezenie, nie blokada)
        if ch["op"] != "remove":
            s0 = by_id.get(ch.get("id")) or {}
            day = ch.get("day") or str(s0.get("day") or "")[:10]
            st = _mins(ch.get("start") or (str(s0.get("start_time") or "")[:5] or None))
            dur = ch.get("dur_min") or s0.get("dur_min") or 0
            warn = []
            if st is not None:
                for a, b, lab in busy.get(day, []):
                    if a is not None and st < b and st + dur > a:
                        warn.append(f"koliduje z zajętością {E.t2(a)}–{E.t2(b)} {str(lab).strip()}")
            ns = _mins(ch.get("start"))   # tylko nowa godzina: dzis nie w przeszlosci
            if ns is not None and day == date.today().isoformat() and ns < datetime.now().hour * 60 + datetime.now().minute:
                warn.append("ta godzina dziś już minęła")
            if warn:
                ch["warn"] = "; ".join(warn)[:200]
        out.append(ch)
    return {"summary": str(resp.get("summary") or "")[:400], "changes": out, "rejected": rej[:8]}


def _load(c, user: str, ws: date):
    today = date.today()
    ctx = E.build_context(c, user, ws, today)
    res = E.plan_week(ctx)
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s ORDER BY day, start_time NULLS LAST, id",
              (user, ws, ws + timedelta(days=6)))
    sessions = [dict(x) for x in c.fetchall()]
    for s in sessions:
        if s.get("start_time"):
            s["start_time"] = s["start_time"].strftime("%H:%M")
    busy = {}
    for i in range(7):
        d = ws + timedelta(days=i)
        busy[d.isoformat()] = [(a, b, l) for a, b, l in E.day_info(ctx, d)["busy"]]
    return ctx, res, sessions, busy, today


def build_input(ctx: dict, res: dict, sessions: list, text: str) -> dict:
    import qbot_trener_review as RV
    inp = RV.build_input(ctx, sessions, [], [], res)
    for day in inp["dni"]:
        day["plan"] = [{"id": s["id"], "godz": s.get("start_time"), "sport": s["sport"], "nazwa": s["name"], "min": s["dur_min"],
                        "status": s["status"], "reczna": s.get("source") == "manual", "dluga": bool(s.get("is_long")),
                        "pominiete_partie": ((s.get("opts") or {}).get("skip_groups") if isinstance(s.get("opts"), dict) else None),
                        "uwaga": (s.get("note") or "")[:120] or None}
                       for s in sessions if str(s["day"])[:10] == day["data"]]
        day.pop("zrobione_z_garmina", None)
    for k in ("reguly", "oceny_uzytkownika", "suma_godzin", "widelki_godzin", "progi"):
        inp.pop(k, None)
    inp["prosba"] = text
    inp["teraz"] = datetime.now().strftime("%H:%M")
    inp["dozwolone"] = {"sporty": list(SPORTS), "skip_groups": list(TW.SKIP_GROUPS)}
    return inp


def propose(c, user: str, ws: date, text: str, llm=None) -> dict:
    text = _txt(text, 600)
    if not text:
        return {"summary": "Napisz, co chcesz zmienić.", "changes": [], "rejected": []}
    ctx, res, sessions, busy, today = _load(c, user, ws)
    if ws + timedelta(days=6) < today:
        return {"summary": "To miniony tydzień — nie zmieniam przeszłości.", "changes": [], "rejected": []}
    inp = build_input(ctx, res, sessions, text)
    if llm is None:
        from qgpt_client import qgpt_json as llm
    try:
        raw = llm(json.dumps(inp, ensure_ascii=False, default=str), system=SYSTEM, max_tokens=1200)
    except Exception as e:
        return {"summary": f"AI niedostępne ({str(e)[:120]}).", "changes": [], "rejected": []}
    return validate(raw, ws, today, sessions, busy)


def _snap(s: dict) -> dict:
    from qbot_trener_api import _jsonable
    r = _jsonable(dict(s))
    return {k: r.get(k) for k in ["id"] + REST_COLS}


def apply(c, user: str, ws: date, text: str, changes: list) -> dict:
    import qbot_trener_ops as OPS
    ctx, res, sessions, busy, today = _load(c, user, ws)
    v = validate({"summary": "", "changes": changes}, ws, today, sessions, busy)
    if not v["changes"]:
        return {"ok": False, "error": "brak poprawnych zmian" + (": " + "; ".join(v["rejected"]) if v["rejected"] else ""), "rejected": v["rejected"]}
    c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s", (user, ws, ws + timedelta(days=6)))
    raw = {int(r["id"]): dict(r) for r in c.fetchall()}
    OPS._supersede_pending(c, user, ws)
    created, restore = [], []
    for ch in v["changes"]:
        if ch["op"] == "add":
            sp = ch["sport"]
            note = "dodane przez Ciebie" + (" · " + ch["note"] if ch.get("note") else "") + " (prośba do AI)"
            opts = json.dumps({"skip_groups": ch["skip_groups"]}) if ch.get("skip_groups") else None
            c.execute("INSERT INTO qbot_v2.trainer_session (username, day, sport, name, start_time, dur_min, min_min, zone, is_long, status, cut, source, note, opts) "
                      "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,false,'plan',false,'manual',%s,%s::jsonb) RETURNING id",
                      (user, ch["day"], sp, ch["name"], ch.get("start"), ch["dur_min"], min(MIN_MIN[sp], ch["dur_min"]),
                       2 if sp == "rower" else None, note[:200], opts))
            created.append(c.fetchone()["id"])
            continue
        s = raw[ch["id"]]
        restore.append(_snap(s))
        if ch["op"] == "remove":
            c.execute("UPDATE qbot_v2.trainer_session SET status='skip', note=%s, updated_at=now() WHERE id=%s AND username=%s",
                      (("usunięte przez Ciebie (prośba do AI)" + (" · " + s["note"] if s.get("note") else ""))[:200], ch["id"], user))
            continue
        sets, vals = ["source='manual'"], []
        for k, col in (("day", "day"), ("start", "start_time"), ("dur_min", "dur_min"), ("name", "name")):
            if k in ch:
                sets.append(f"{col}=%s"); vals.append(ch[k])
        if "dur_min" in ch:
            sets.append("min_min=LEAST(COALESCE(min_min, %s), %s)"); vals += [ch["dur_min"], ch["dur_min"]]
        if "skip_groups" in ch:
            sets.append("opts=%s::jsonb"); vals.append(json.dumps({"skip_groups": ch["skip_groups"]}) if ch["skip_groups"] else None)
        note = ch.get("note") if "note" in ch else None
        sets.append("note=%s"); vals.append((("zmienione na Twoją prośbę (AI)" + (" · " + note if note else "")) if note or not s.get("note")
                                             else (s["note"] + " · zmienione na Twoją prośbę (AI)"))[:200])
        c.execute(f"UPDATE qbot_v2.trainer_session SET {', '.join(sets)}, updated_at=now() WHERE id=%s AND username=%s", vals + [ch["id"], user])
    lines = [ch["line"] for ch in v["changes"]]
    payload = {"ai": {"created": created, "restore": restore}, "request": _txt(text, 600), "lines": lines,
               "notes": ["Prośba: " + (_txt(text, 200) or "")]}
    c.execute("INSERT INTO qbot_v2.trainer_change (username, week_start, action, payload, before, after, accepted) "
              "VALUES (%s,%s,'prosba_ai',%s::jsonb,'[]'::jsonb,%s::jsonb,NULL) RETURNING id",
              (user, ws, json.dumps(payload, ensure_ascii=False, default=str), json.dumps(v["changes"], ensure_ascii=False, default=str)))
    cid = c.fetchone()["id"]
    # silnik dopasowuje swoje sesje do Twoich zmian (dzieci zmiany: cofaja sie razem z nia)
    r = OPS.regenerate(c, user, ws, "rolowanie", {"parent": cid, "reason": "prośba do AI"}, accepted=True)
    rolled = OPS.cascade(c, user, ws, cid, "prośba do AI")
    notes = list(payload["notes"])
    if r["lines"]:
        notes.append("Trener dopasował resztę tygodnia: " + "; ".join(r["lines"])[:300])
    if rolled:
        notes.append(f"Przeliczone też kolejne tygodnie: {len(rolled)}.")
    return {"ok": True, "change_id": cid, "week_start": ws.isoformat(), "lines": lines, "notes": notes, "rejected": v["rejected"]}
