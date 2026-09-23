"""TRENER (sekcja Formy) - API Etap 1: cele, wpisy tygodnia, nadpisania kalibracji, sesje planu.

Montowane w qbot_web.py przez build_router(_db_conn, _current_user) PRZED app.mount("/").
Wszystko per uzytkownik (username z ciasteczka sesji). Tabele: sql/trainer_v1.sql.
Walidacja w czystych funkcjach clean_* (testy: tests/test_trener_api.py, bez bazy).
Wartosci "auto" kalibracji NIE sa zapisywane - trainer_settings trzyma tylko reczne nadpisania.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request

GOAL_KINDS = ("trip", "long_ride", "volume", "weight", "power", "habit", "other")
GOAL_STATUS = ("active", "paused", "done", "dropped")
RULE_KINDS = ("busy", "flex", "pref")
SPORTS = ("rower", "sila", "wiosl", "joga")
SESSION_STATUS = ("plan", "done", "skip")
WIN_KINDS = ("h", "all", "var")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DDMM = re.compile(r"^(0[1-9]|[12]\d|3[01])\.(0[1-9]|1[0-2])$")
MAX_TEXT = 200
MAX_JSON = 20000


class BadInput(ValueError):
    pass


def _txt(v: Any, field: str, required: bool = False, max_len: int = MAX_TEXT) -> str | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise BadInput(f"{field}: wymagane")
        return None
    if not isinstance(v, str):
        raise BadInput(f"{field}: ma byc tekstem")
    v = v.strip()
    if len(v) > max_len:
        raise BadInput(f"{field}: za dlugie (max {max_len})")
    return v


def _date(v: Any, field: str) -> str | None:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)).isoformat()
    except ValueError:
        raise BadInput(f"{field}: zla data (RRRR-MM-DD)")


def _choice(v: Any, field: str, allowed: tuple, default: str | None = None) -> str:
    if v in (None, "") and default is not None:
        return default
    if v not in allowed:
        raise BadInput(f"{field}: dozwolone {', '.join(allowed)}")
    return v


def _int(v: Any, field: str, lo: int, hi: int, required: bool = False) -> int | None:
    if v in (None, ""):
        if required:
            raise BadInput(f"{field}: wymagane")
        return None
    try:
        i = int(v)
    except (TypeError, ValueError):
        raise BadInput(f"{field}: ma byc liczba")
    if not lo <= i <= hi:
        raise BadInput(f"{field}: zakres {lo}-{hi}")
    return i


def _json_small(v: Any, field: str) -> Any:
    if len(json.dumps(v, ensure_ascii=False)) > MAX_JSON:
        raise BadInput(f"{field}: za duze")
    return v


def clean_goal(b: dict, partial: bool = False) -> dict:
    if not isinstance(b, dict):
        raise BadInput("body: obiekt JSON")
    out: dict = {}
    if not partial or "kind" in b:
        out["kind"] = _choice(b.get("kind"), "kind", GOAL_KINDS)
    if not partial or "name" in b:
        out["name"] = _txt(b.get("name"), "name", required=True)
    if not partial or "priority" in b:
        out["priority"] = _choice(b.get("priority"), "priority", ("A", "B", "C"), default="B")
    for f in ("date_from", "date_to"):
        if not partial or f in b:
            out[f] = _date(b.get(f), f)
    if out.get("date_from") and out.get("date_to") and out["date_to"] < out["date_from"]:
        raise BadInput("date_to przed date_from")
    if not partial or "target" in b:
        t = b.get("target") or {}
        if not isinstance(t, dict):
            raise BadInput("target: obiekt")
        out["target"] = _json_small(t, "target")
    if not partial or "status" in b:
        out["status"] = _choice(b.get("status"), "status", GOAL_STATUS, default="active")
    if not partial or "note" in b:
        out["note"] = _txt(b.get("note"), "note", max_len=1000)
    return out


def clean_window(w: Any, rule_kind: str) -> dict:
    if not isinstance(w, dict):
        raise BadInput("okno: obiekt")
    d = w.get("d")
    if not (isinstance(d, list) and len(d) == 7 and all(x in (0, 1, 2) for x in d)):
        raise BadInput("okno.d: 7 wartosci 0/1/2")
    k = _choice(w.get("k"), "okno.k", WIN_KINDS, default="h")
    o = {"d": d, "k": k}
    if k == "h":
        a, bb = w.get("a"), w.get("b")
        if not (isinstance(a, str) and _HHMM.match(a) and isinstance(bb, str) and _HHMM.match(bb)):
            raise BadInput("okno: godziny HH:MM")
        if bb <= a:
            raise BadInput("okno: koniec musi byc po poczatku")
        o["a"], o["b"] = a, bb
    ac = w.get("ac") or []
    if not isinstance(ac, list) or any(x not in SPORTS for x in ac):
        raise BadInput("okno.ac: " + ", ".join(SPORTS))
    o["ac"] = [] if rule_kind == "busy" else sorted(set(ac), key=SPORTS.index)
    return o


def clean_period(p: Any) -> dict:
    if p in (None, {}):
        return {"m": "all"}
    if not isinstance(p, dict):
        raise BadInput("period: obiekt")
    m = _choice(p.get("m"), "period.m", ("all", "yearly", "once"), default="all")
    if m == "all":
        return {"m": "all"}
    f, t = p.get("f"), p.get("t")
    if m == "yearly":
        if not (isinstance(f, str) and _DDMM.match(f) and isinstance(t, str) and _DDMM.match(t)):
            raise BadInput("period: daty DD.MM")
        return {"m": m, "f": f, "t": t}
    f2, t2 = _date(f, "period.f"), _date(t, "period.t")
    if not f2 or not t2 or t2 < f2:
        raise BadInput("period: zakres dat")
    return {"m": m, "f": f2, "t": t2}


def clean_rule(b: dict, partial: bool = False) -> dict:
    if not isinstance(b, dict):
        raise BadInput("body: obiekt JSON")
    out: dict = {}
    kind = b.get("kind")
    if not partial or "kind" in b:
        out["kind"] = kind = _choice(kind, "kind", RULE_KINDS)
    if not partial or "name" in b:
        out["name"] = _txt(b.get("name"), "name", required=True)
    if not partial or "icon" in b:
        out["icon"] = _txt(b.get("icon"), "icon", max_len=16) or "📌"
    if not partial or "windows" in b:
        ws = b.get("windows") or []
        if not isinstance(ws, list) or len(ws) > 20:
            raise BadInput("windows: lista (max 20)")
        out["windows"] = [clean_window(w, kind or "busy") for w in ws]
    if not partial or "period" in b:
        out["period"] = clean_period(b.get("period"))
    if not partial or "max_min" in b:
        out["max_min"] = _int(b.get("max_min"), "max_min", 5, 1440)
    if not partial or "note" in b:
        out["note"] = _txt(b.get("note"), "note", max_len=500)
    if "active" in b:
        out["active"] = bool(b.get("active"))
    if "sort" in b:
        out["sort"] = _int(b.get("sort"), "sort", -10000, 10000) or 0
    return out


def clean_session(b: dict, partial: bool = False) -> dict:
    if not isinstance(b, dict):
        raise BadInput("body: obiekt JSON")
    out: dict = {}
    if not partial or "day" in b:
        d = _date(b.get("day"), "day")
        if not d:
            raise BadInput("day: wymagane")
        out["day"] = d
    if not partial or "sport" in b:
        out["sport"] = _choice(b.get("sport"), "sport", SPORTS)
    if not partial or "name" in b:
        out["name"] = _txt(b.get("name"), "name", required=True)
    if not partial or "start_time" in b:
        st = b.get("start_time")
        if st in (None, ""):
            out["start_time"] = None
        elif isinstance(st, str) and _HHMM.match(st[:5]):
            out["start_time"] = st[:5]
        else:
            raise BadInput("start_time: HH:MM")
    if not partial or "dur_min" in b:
        out["dur_min"] = _int(b.get("dur_min"), "dur_min", 1, 1440, required=True)
    if not partial or "min_min" in b:
        out["min_min"] = _int(b.get("min_min"), "min_min", 1, 1440)
    if not partial or "zone" in b:
        out["zone"] = _int(b.get("zone"), "zone", 1, 7)
    if "xss" in b:
        x = b.get("xss")
        if x in (None, ""):
            out["xss"] = None
        else:
            try:
                out["xss"] = float(x)
            except (TypeError, ValueError):
                raise BadInput("xss: liczba")
    for f in ("is_long", "cut"):
        if f in b:
            out[f] = bool(b.get(f))
    if not partial or "status" in b:
        out["status"] = _choice(b.get("status"), "status", SESSION_STATUS, default="plan")
    if "note" in b:
        out["note"] = _txt(b.get("note"), "note", max_len=1000)
    if out.get("min_min") and out.get("dur_min") and out["min_min"] > out["dur_min"]:
        raise BadInput("min_min wieksze niz dur_min")
    return out


def clean_overrides(b: Any) -> dict:
    """{klucz: wartosc|None}; None usuwa nadpisanie (powrot do auto). Klucze: [a-z0-9_.]."""
    if not isinstance(b, dict):
        raise BadInput("overrides: obiekt")
    for k in b:
        if not re.match(r"^[a-z0-9_.]{1,64}$", k):
            raise BadInput(f"klucz '{k}': dozwolone a-z 0-9 _ .")
    _json_small(b, "overrides")
    return b


def _jsonable(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        elif hasattr(v, "isoformat") and not isinstance(v, str):
            out[k] = v.isoformat()[:5] if k == "start_time" else v.isoformat()
        elif v.__class__.__name__ == "Decimal":
            out[k] = float(v)
        else:
            out[k] = v
    return out


_JSON_COLS = {"target", "windows", "period", "overrides", "payload", "before", "after"}


def _vals(d: dict) -> list:
    return [json.dumps(v, ensure_ascii=False) if k in _JSON_COLS else v for k, v in d.items()]



# ---------------- AUTO (liczone na zywo z bazy, nie zapisywane) ----------------

def _rank(v: list) -> list:
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0] * len(v)
    for k, i in enumerate(o):
        r[i] = k
    return r


def _pearson(x: list, y: list) -> float | None:
    n = len(x)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sx = sum((a - mx) ** 2 for a in x) ** .5
    sy = sum((b - my) ** 2 for b in y) ** .5
    if not sx or not sy:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def auto_sensitivity(pairs: list) -> dict:
    """pairs: (gotowosc rano, EF jazdy / norma 28 d). Slaby zwiazek -> niska czulosc."""
    if len(pairs) < 20:
        return {"value": 5, "n": len(pairs), "r": None, "note": "za mało jazd z gotowością — wartość domyślna"}
    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]
    r = _pearson(_rank(x), _rank(y))
    v = 5 if r is None else max(1, min(10, round(2 + abs(r) * 16)))
    return {"value": v, "n": len(pairs), "r": None if r is None else round(r, 3),
            "note": f"związek gotowości z jazdą: {'brak danych' if r is None else round(r, 2)} ({len(pairs)} jazd)"}


def auto_min_threshold(values: list, pct: int = 15) -> dict:
    v = sorted(values)
    if len(v) < 30:
        return {"value": pct, "threshold": None, "n": len(v), "note": "za mało dni z gotowością"}
    th = v[min(len(v) - 1, int(len(v) * pct / 100))]
    return {"value": pct, "threshold": round(th, 3), "n": len(v),
            "note": f"{pct}% najsłabszych dni = gotowość poniżej {round(th, 2)} ({len(v)} dni)"}


def auto_heavy_gap(recover_days: list, share: float = 0.75) -> dict:
    n = len(recover_days)
    if n < 10:
        return {"value": 48, "n": n, "note": "za mało ciężkich jazd z HRV — wartość domyślna"}
    for k in (1, 2, 3, 4):
        got = sum(1 for d in recover_days if d <= k) / n
        if got >= share:
            return {"value": k * 24, "n": n, "note": f"po ciężkiej jeździe HRV i tętno wracają do normy w {round(got*100)}% do {k} dni ({n} jazd)"}
    return {"value": 96, "n": n, "note": f"powrót dłuższy niż 3 dni ({n} jazd)"}


def compute_auto(c) -> dict:
    c.execute("SELECT day, readiness_effective AS re, hrv_night AS hrv, rhr, xss_daily AS xss, ef_med_28d AS ef "
              "FROM qbot_v2.fitmodel_daily ORDER BY day")
    D = {}
    for r in c.fetchall():
        D[r["day"]] = {k: (float(r[k]) if r[k] is not None else None) for k in ("re", "hrv", "rhr", "xss", "ef")}
    c.execute("SELECT date, normalized_power_w AS np, avg_hr_bpm AS hr FROM qbot_v2.training_sessions "
              "WHERE sport_type IN ('cycling','gravel_cycling') AND duration_s >= 2700 AND normalized_power_w > 0 AND avg_hr_bpm > 80")
    pairs = []
    for r in c.fetchall():
        d, p = D.get(r["date"]), D.get(r["date"] - timedelta(days=1))
        if d and d["re"] is not None and p and p["ef"]:
            pairs.append((d["re"], (float(r["np"]) / float(r["hr"])) / p["ef"]))
    days = sorted(D)
    last = days[-1] if days else date.today()
    rv = [D[d]["re"] for d in days if d > last - timedelta(days=365) and D[d]["re"] is not None]
    rec = []
    for d0 in days:
        x = D[d0]["xss"] or 0
        nxt = D.get(d0 + timedelta(days=1))
        if x < 120 or not nxt or (nxt["xss"] or 0) > 40:
            continue
        base = [D.get(d0 - timedelta(days=k)) for k in range(1, 8)]
        bh = [b["hrv"] for b in base if b and b["hrv"]]
        br = [b["rhr"] for b in base if b and b["rhr"]]
        if len(bh) < 4 or len(br) < 4:
            continue
        bh.sort(); br.sort()
        mh, mr = bh[len(bh) // 2], br[len(br) // 2]
        res = None
        for k in range(1, 6):
            dd = D.get(d0 + timedelta(days=k))
            if not dd or dd["hrv"] is None or dd["rhr"] is None:
                break
            if dd["hrv"] >= 0.97 * mh and dd["rhr"] <= mr + 1:
                res = k
                break
        else:
            res = 6
        if res is not None:
            rec.append(res)
    return {"regen.sensitivity": auto_sensitivity(pairs),
            "regen.min_pct": auto_min_threshold(rv),
            "regen.heavy_gap_h": auto_heavy_gap(rec),
            "_computed_at": datetime.now().isoformat(timespec="seconds")}


def build_router(db_conn: Callable, current_user: Callable) -> APIRouter:
    r = APIRouter(prefix="/api/trener")

    def user_of(request: Request) -> str:
        u = current_user(request)
        if not u:
            raise HTTPException(status_code=401, detail="unauthorized")
        return u

    async def body_of(request: Request) -> Any:
        try:
            return await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="body: niepoprawny JSON")

    def run(fn):
        conn = db_conn()
        try:
            res = fn(conn.cursor())
            conn.commit()
            return res
        except BadInput as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except HTTPException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def crud(table: str, cleaner: Callable, order: str):
        def list_(request: Request):
            u = user_of(request)
            return run(lambda c: (c.execute(f"SELECT * FROM qbot_v2.{table} WHERE username=%s ORDER BY {order}", (u,)),
                                  {"items": [_jsonable(x) for x in c.fetchall()]})[1])

        async def create(request: Request):
            u = user_of(request)
            b = await body_of(request)
            def go(c):
                d = cleaner(b)
                cols = ["username"] + list(d.keys())
                c.execute(f"INSERT INTO qbot_v2.{table} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING *",
                          [u] + _vals(d))
                return _jsonable(c.fetchone())
            return run(go)

        async def update(item_id: int, request: Request):
            u = user_of(request)
            b = await body_of(request)
            def go(c):
                d = cleaner(b, partial=True)
                if not d:
                    raise BadInput("brak pol do zmiany")
                sets = ",".join(f"{k}=%s" for k in d) + ",updated_at=now()"
                c.execute(f"UPDATE qbot_v2.{table} SET {sets} WHERE id=%s AND username=%s RETURNING *", _vals(d) + [item_id, u])
                row = c.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="nie znaleziono")
                return _jsonable(row)
            return run(go)

        def delete(item_id: int, request: Request):
            u = user_of(request)
            def go(c):
                c.execute(f"DELETE FROM qbot_v2.{table} WHERE id=%s AND username=%s RETURNING id", (item_id, u))
                if not c.fetchone():
                    raise HTTPException(status_code=404, detail="nie znaleziono")
                return {"ok": True, "id": item_id}
            return run(go)

        return list_, create, update, delete

    for path, table, cleaner, order in (("goals", "trainer_goal", clean_goal, "date_from NULLS LAST, id"),
                                        ("rules", "trainer_rule", clean_rule, "sort, id")):
        l_, c_, u_, d_ = crud(table, cleaner, order)
        r.add_api_route(f"/{path}", l_, methods=["GET"])
        r.add_api_route(f"/{path}", c_, methods=["POST"])
        r.add_api_route(f"/{path}/{{item_id}}", u_, methods=["PUT"])
        r.add_api_route(f"/{path}/{{item_id}}", d_, methods=["DELETE"])

    _, s_create, s_update, s_delete = crud("trainer_session", clean_session, "day, start_time NULLS LAST, id")
    r.add_api_route("/sessions", s_create, methods=["POST"])
    r.add_api_route("/sessions/{item_id}", s_update, methods=["PUT"])
    r.add_api_route("/sessions/{item_id}", s_delete, methods=["DELETE"])

    @r.get("/settings")
    def settings_get(request: Request):
        u = user_of(request)
        def go(c):
            c.execute("SELECT overrides, updated_at FROM qbot_v2.trainer_settings WHERE username=%s", (u,))
            row = c.fetchone()
            return {"overrides": (row["overrides"] if row else {}), "updated_at": (row["updated_at"].isoformat() if row else None)}
        return run(go)

    @r.post("/settings")
    async def settings_set(request: Request):
        u = user_of(request)
        b = await body_of(request)
        def go(c):
            patch = clean_overrides((b or {}).get("overrides", b))
            c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username=%s FOR UPDATE", (u,))
            row = c.fetchone()
            cur = dict(row["overrides"]) if row else {}
            for k, v in patch.items():
                if v is None:
                    cur.pop(k, None)
                else:
                    cur[k] = v
            c.execute("INSERT INTO qbot_v2.trainer_settings(username, overrides, updated_at) VALUES (%s,%s::jsonb,now()) "
                      "ON CONFLICT (username) DO UPDATE SET overrides=EXCLUDED.overrides, updated_at=now()",
                      (u, json.dumps(cur, ensure_ascii=False)))
            return {"overrides": cur}
        return run(go)

    @r.get("/week")
    def week_get(request: Request, start: str = Query(None)):
        u = user_of(request)
        try:
            d0 = date.fromisoformat(start) if start else date.today()
        except ValueError:
            raise HTTPException(status_code=400, detail="start: RRRR-MM-DD")
        d0 = d0 - timedelta(days=d0.weekday())
        d1 = d0 + timedelta(days=6)
        def go(c):
            c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s "
                      "ORDER BY day, start_time NULLS LAST, id", (u, d0, d1))
            sessions = [_jsonable(x) for x in c.fetchall()]
            c.execute("SELECT id, day, end_day, kind, event_type, title, at_time FROM qbot_v2.calendar_entry "
                      "WHERE day <= %s AND COALESCE(end_day, day) >= %s ORDER BY day, id", (d1, d0))
            cal = [_jsonable(x) for x in c.fetchall()]
            c.execute("SELECT id, date, started_at, sport_type, activity_name, distance_m, duration_s, elevation_m "
                      "FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s ORDER BY started_at NULLS LAST", (d0, d1))
            done = [_jsonable(x) for x in c.fetchall()]
            return {"start": d0.isoformat(), "end": d1.isoformat(), "sessions": sessions, "calendar": cal, "activities": done}
        return run(go)

    @r.get("/health")
    def health(request: Request):
        user_of(request)
        def go(c):
            out = {}
            for t in ("trainer_goal", "trainer_rule", "trainer_settings", "trainer_session", "trainer_change"):
                c.execute(f"SELECT to_regclass('qbot_v2.{t}') IS NOT NULL AS ok")
                out[t] = bool(c.fetchone()["ok"])
            return {"ok": all(out.values()), "tables": out}
        return run(go)

    @r.get("/auto")
    def auto_get(request: Request):
        user_of(request)
        return run(compute_auto)

    return r
