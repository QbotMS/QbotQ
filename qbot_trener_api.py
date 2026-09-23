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
    if "acks" in b:
        ak = b.get("acks") or []
        if not isinstance(ak, list) or len(ak) > 20 or any(not isinstance(x, str) or len(x) > 80 for x in ak):
            raise BadInput("acks: lista kluczy")
        out["acks"] = ak
    if out.get("min_min") and out.get("dur_min") and out["min_min"] > out["dur_min"]:
        raise BadInput("min_min wieksze niz dur_min")
    return out


def clean_lab(b: dict, partial: bool = False) -> dict:
    if not isinstance(b, dict):
        raise BadInput("body: obiekt JSON")
    out: dict = {}
    if not partial or "day" in b:
        d = _date(b.get("day"), "day")
        if not d:
            raise BadInput("day: wymagane")
        out["day"] = d
    if not partial or "name" in b:
        out["name"] = _txt(b.get("name"), "name", required=True, max_len=80)
    if not partial or "value" in b:
        v = b.get("value")
        if v in (None, ""):
            out["value"] = None
        else:
            try:
                out["value"] = float(str(v).replace(",", "."))
            except ValueError:
                raise BadInput("value: liczba")
    for f, ml in (("unit", 20), ("ref_range", 60), ("note", 500)):
        if not partial or f in b:
            out[f] = _txt(b.get(f), f, max_len=ml)
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


_JSON_COLS = {"target", "windows", "period", "overrides", "payload", "before", "after", "acks"}


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
                if table == "trainer_session":
                    d["source"] = "manual"
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
                if table == "trainer_session" and set(d) - {"acks"}:
                    d["source"] = "manual"
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

    @r.post("/goals/preview")
    async def goals_preview(request: Request):
        """Ocena realnosci celu PRZED zapisem (nic nie zapisuje)."""
        u = user_of(request)
        b = await body_of(request)
        import qbot_trener_stats as ST
        def go(c):
            g = clean_goal(dict(b or {}, name=(b or {}).get("name") or "podgląd"))
            g.update(id="preview", status="active", created_at=datetime.now().astimezone())
            st = ST.compute_goal_status(c, [g]).get("preview") or {}
            c.execute("SELECT AVG(weight_kg) AS w FROM qbot_v2.fitmodel_daily WHERE weight_kg IS NOT NULL AND day >= CURRENT_DATE - 7")
            w = c.fetchone()
            c.execute("SELECT ftp_est_w FROM qbot_v2.fitmodel_daily WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1")
            f = c.fetchone()
            st["now"] = {"weight_kg": round(float(w["w"]), 1) if w and w["w"] else None, "ftp_w": round(float(f["ftp_est_w"])) if f else None}
            return st
        return run(go)

    @r.get("/route_summary")
    def route_summary(request: Request, route_id: str = Query(...)):
        """Km, przewyzszenie (os 50 m) i przewazajaca nawierzchnia policzonej trasy QBota."""
        user_of(request)
        def go(c):
            c.execute("SELECT route_base_id, distance_m, source_meta_json FROM qbot_v2.route_base WHERE route_id=%s ORDER BY (status='disabled'), updated_at DESC LIMIT 1", (route_id,))
            rb = c.fetchone()
            if not rb:
                raise HTTPException(status_code=404, detail="brak trasy")
            c.execute("SELECT COALESCE(SUM(elevation_gain_m),0) AS up, COUNT(*) AS n FROM qbot_v2.route_axis_segments WHERE route_base_id=%s", (rb["route_base_id"],))
            ax = c.fetchone()
            up = float(ax["up"]) if ax and ax["n"] else float((rb["source_meta_json"] or {}).get("elevation_gain_m") or 0)
            c.execute("SELECT surface, COUNT(*) AS n FROM qbot_v2.route_surface_layer WHERE route_base_id=%s GROUP BY surface", (rb["route_base_id"],))
            cnt = {"asfalt": 0, "szuter": 0, "teren": 0, "nieznana": 0}
            PAVED = {"asphalt", "paved", "concrete", "paving_stones", "concrete:plates", "sett", "chipseal"}
            GRAV = {"gravel", "fine_gravel", "compacted", "pebblestone", "unpaved"}
            TER = {"ground", "dirt", "earth", "grass", "sand", "mud", "wood", "rock"}
            for x in c.fetchall():
                sname = (x["surface"] or "").lower()
                key = "asfalt" if sname in PAVED else ("szuter" if sname in GRAV else ("teren" if sname in TER else "nieznana"))
                cnt[key] += x["n"]
            known = cnt["asfalt"] + cnt["szuter"] + cnt["teren"]
            pct = {k: round(100 * v / known) for k, v in cnt.items() if k != "nieznana"} if known else {}
            if not pct:
                surf = None
            elif pct["asfalt"] >= 70:
                surf = "asfalt"
            elif pct["teren"] >= 40:
                surf = "teren"
            elif pct["szuter"] >= 50:
                surf = "szuter"
            else:
                surf = "mieszana"
            return {"route_id": route_id, "km": round(float(rb["distance_m"] or 0) / 1000, 1), "up_m": round(up), "surface": surf, "surface_pct": pct}
        return run(go)

    @r.post("/goals/{item_id}/calendar")
    def goal_calendar(item_id: int, request: Request):
        """Dopisz cel (wyprawa / dluga jazda) do Kalendarza jako wydarzenie; ponowne wywolanie aktualizuje wpis."""
        u = user_of(request)
        def go(c):
            c.execute("SELECT * FROM qbot_v2.trainer_goal WHERE id=%s AND username=%s", (item_id, u))
            g = c.fetchone()
            if not g or not g["date_from"]:
                raise HTTPException(status_code=400, detail="cel bez daty")
            end = g["date_to"] if g["date_to"] and g["date_to"] != g["date_from"] else None
            if g["calendar_entry_id"]:
                c.execute("UPDATE qbot_v2.calendar_entry SET day=%s, end_day=%s, title=%s WHERE id=%s RETURNING id", (g["date_from"], end, g["name"], g["calendar_entry_id"]))
                if c.fetchone():
                    return {"ok": True, "calendar_entry_id": g["calendar_entry_id"], "updated": True}
            c.execute("INSERT INTO qbot_v2.calendar_entry (day, end_day, kind, title, note) VALUES (%s,%s,'event',%s,'[trener-cel]') RETURNING id", (g["date_from"], end, g["name"]))
            cid = c.fetchone()["id"]
            c.execute("UPDATE qbot_v2.trainer_goal SET calendar_entry_id=%s WHERE id=%s", (cid, item_id))
            return {"ok": True, "calendar_entry_id": cid}
        return run(go)

    # /goals/status musi byc zarejestrowane PRZED /goals/{item_id}
    @r.get("/goals/status")
    def goals_status(request: Request):
        u = user_of(request)
        import qbot_trener_stats as ST
        def go(c):
            c.execute("SELECT * FROM qbot_v2.trainer_goal WHERE username=%s", (u,))
            return ST.compute_goal_status(c, [dict(x) for x in c.fetchall()])
        return run(go)

    for path, table, cleaner, order in (("goals", "trainer_goal", clean_goal, "date_from NULLS LAST, id"),
                                        ("rules", "trainer_rule", clean_rule, "sort, id"),
                                        ("labs", "trainer_lab", clean_lab, "day DESC, id DESC")):
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

    # ---------------- TYDZIEN (Etap 3: silnik planu) ----------------
    import qbot_trener_engine as E

    def _week_bounds(start: str | None) -> tuple[date, date]:
        try:
            d0 = date.fromisoformat(start) if start else date.today()
        except ValueError:
            raise BadInput("start: RRRR-MM-DD")
        d0 = d0 - timedelta(days=d0.weekday())
        return d0, d0 + timedelta(days=6)

    def _match_done(c, u: str, d0: date, d1: date) -> int:
        """Zrobione z Garmina -> status done w planie (ten sam dzien i sport, najblizsza godzina)."""
        c.execute("SELECT id, day, sport, start_time FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s "
                  "AND status='plan' AND training_session_id IS NULL AND day <= CURRENT_DATE", (u, d0, d1))
        plan = c.fetchall()
        if not plan:
            return 0
        c.execute("SELECT id, date, sport_type, started_at FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s", (d0, d1))
        acts = [a for a in c.fetchall()]
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

    def _sess_rows(c, u, d0, d1):
        c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s ORDER BY day, start_time NULLS LAST, id", (u, d0, d1))
        return [_jsonable(x) for x in c.fetchall()]

    _SIC = {"rower": "🚲", "sila": "🏋️", "wiosl": "🚣", "joga": "🧘"}

    def _desc(x: dict) -> str:
        return f"{str(x['day'])[5:]} {_SIC.get(x['sport'], '')} {x['name']} {str(x.get('start_time') or '')[:5]} {x['dur_min']}′"

    def _regenerate(c, u: str, d0: date, action: str, payload: dict) -> dict:
        _match_done(c, u, d0, d0 + timedelta(days=6))
        today = date.today()
        c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s AND source='auto' AND status='plan' AND day >= %s",
                  (u, d0, d0 + timedelta(days=6), today))
        before = [_jsonable(x) for x in c.fetchall()]
        c.execute("DELETE FROM qbot_v2.trainer_session WHERE id = ANY(%s)", ([x["id"] for x in before],))
        ctx = E.build_context(c, u, d0, today)
        res = E.plan_week(ctx)
        after_ids = []
        for x in res["sessions"]:
            cols = ["username", "day", "sport", "name", "start_time", "dur_min", "min_min", "zone", "xss", "is_long", "status", "cut", "source", "note"]
            c.execute(f"INSERT INTO qbot_v2.trainer_session ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))}) RETURNING id",
                      [u] + [x.get(k) for k in cols[1:]])
            after_ids.append(c.fetchone()["id"])
        bset = {(_desc(x)) for x in before}
        aset = {(_desc(x)) for x in res["sessions"]}
        lines = ["− " + t for t in sorted(bset - aset)] + ["+ " + t for t in sorted(aset - bset)]
        payload = dict(payload, after_ids=after_ids, notes=res["notes"])
        c.execute("INSERT INTO qbot_v2.trainer_change (username, week_start, action, payload, before, after) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb) RETURNING id",
                  (u, d0, action, json.dumps(payload, ensure_ascii=False), json.dumps(before, ensure_ascii=False, default=str),
                   json.dumps(res["sessions"], ensure_ascii=False, default=str)))
        cid = c.fetchone()["id"]
        return {"change_id": cid, "lines": lines, "notes": res["notes"], "added": len(after_ids), "removed": len(before)}

    def _ensure_horizon(c, u: str, d0: date) -> bool:
        """Biezacy tydzien + 2 kolejne planuja sie SAME, gdy nie maja zadnej sesji (zmiany uzytkownika zostaja)."""
        m0 = date.today() - timedelta(days=date.today().weekday())
        if not (m0 <= d0 <= m0 + timedelta(weeks=2)):
            return False
        c.execute("SELECT 1 FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s LIMIT 1", (u, d0, d0 + timedelta(days=6)))
        if c.fetchone():
            return False
        c.execute("SELECT 1 FROM qbot_v2.trainer_goal WHERE username=%s UNION ALL SELECT 1 FROM qbot_v2.trainer_rule WHERE username=%s LIMIT 1", (u, u))
        if not c.fetchone():
            return False  # pusty Trener - nic nie planujemy
        res = _regenerate(c, u, d0, "auto_horizon", {})
        c.execute("UPDATE qbot_v2.trainer_change SET accepted=true WHERE id=%s", (res["change_id"],))
        return True

    @r.get("/week")
    def week_get(request: Request, start: str = Query(None)):
        u = user_of(request)
        def go(c):
            d0, d1 = _week_bounds(start)
            auto_planned = _ensure_horizon(c, u, d0)
            matched = _match_done(c, u, d0, d1)
            sessions = _sess_rows(c, u, d0, d1)
            c.execute("SELECT id, day, end_day, kind, event_type, title, at_time, note FROM qbot_v2.calendar_entry "
                      "WHERE day <= %s AND COALESCE(end_day, day) >= %s ORDER BY day, id", (d1, d0))
            cal = [_jsonable(x) for x in c.fetchall()]
            c.execute("SELECT id, date, started_at, sport_type, activity_name, distance_m, duration_s, elevation_m, tss "
                      "FROM qbot_v2.training_sessions WHERE date BETWEEN %s AND %s ORDER BY started_at NULLS LAST", (d0, d1))
            done = [_jsonable(x) for x in c.fetchall()]
            meta = {}
            try:
                ctx = E.build_context(c, u, d0)
                pw = E.plan_week(ctx)
                meta = {"phase": pw["phase"], "phase_name": pw["phase_name"], "light": pw["light"], "target_h": pw["target_h"],
                        "days": pw["days"], "readiness_today": ctx["readiness_today"], "readiness_threshold": ctx["readiness_threshold"],
                        "has_weather": bool(ctx["weather"])}
                c.execute("SELECT ftp_est_w FROM qbot_v2.fitmodel_daily WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1")
                fr = c.fetchone()
                meta["ftp_w"] = float(fr["ftp_est_w"]) if fr else None
                import os as _os
                lt = _os.environ.get("RIDER_LTHR_BPM")
                if not lt:
                    for _ef in ("/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env", "/opt/qbot/app/.env"):
                        try:
                            for _ln in open(_ef, encoding="utf-8"):
                                _ln = _ln.strip()
                                if _ln.startswith("export "):
                                    _ln = _ln[7:].strip()
                                if _ln.startswith("RIDER_LTHR_BPM="):
                                    lt = _ln.split("=", 1)[1].strip().strip('"').strip("'")
                        except OSError:
                            pass
                        if lt:
                            break
                meta["lthr_bpm"] = int(lt) if lt and lt.isdigit() else None
                meta["ov"] = {k: v for k, v in ctx["ov"].items() if k.startswith("wx.")}
            except Exception as e:  # meta pomocnicze - tydzien ma sie pokazac nawet bez niego
                meta = {"error": str(e)[:200]}
            import qbot_trener_workouts as TW
            for x in sessions:
                if x["sport"] in ("sila", "wiosl", "joga"):
                    n = TW.strength_index(c, u, x) if x["sport"] == "sila" else 0
                    x["details"] = TW.details(x["sport"], meta.get("phase"), x["dur_min"], bool(x.get("cut")), n)
            c.execute("SELECT id, action, payload, created_at FROM qbot_v2.trainer_change WHERE username=%s AND week_start=%s AND accepted IS NULL "
                      "ORDER BY id DESC LIMIT 1", (u, d0))
            last = c.fetchone()
            return {"start": d0.isoformat(), "end": d1.isoformat(), "sessions": sessions, "calendar": cal, "activities": done,
                    "matched_now": matched, "meta": meta, "auto_planned": auto_planned,
                    "warnings": E.check_rules_detailed(sessions, meta.get("ov") or {}, meta.get("days")),
                    "pending_change": (_jsonable(last) if last else None)}
        return run(go)

    @r.post("/week/generate")
    async def week_generate(request: Request):
        u = user_of(request)
        b = await body_of(request) if (await request.body()) else {}
        def go(c):
            d0, _ = _week_bounds((b or {}).get("start"))
            if d0 + timedelta(days=6) < date.today():
                raise BadInput("nie przeliczam minionych tygodni")
            return _regenerate(c, u, d0, "generate", {})
        return run(go)

    DAY_ACTIONS = ("rest", "ill", "del", "short", "clear")

    @r.post("/week/action")
    async def week_action(request: Request):
        u = user_of(request)
        b = await body_of(request)
        def go(c):
            act = _choice((b or {}).get("action"), "action", DAY_ACTIONS)
            d = _date((b or {}).get("day"), "day")
            if not d:
                raise BadInput("day: wymagane")
            dd = date.fromisoformat(d)
            if dd < date.today():
                raise BadInput("dzień już minął")
            payload = {"day": d, "cal_ids": [], "day_state": None, "cleared": []}
            if act in ("rest", "ill", "del"):
                kind, et, title = {"rest": ("event", "rest", "REST DAY"), "ill": ("illness", None, "Choroba"), "del": ("event", "delegacja", "Delegacja")}[act]
                c.execute("INSERT INTO qbot_v2.calendar_entry (day, kind, event_type, title, note) VALUES (%s,%s,%s,%s,'[trener]') RETURNING id", (dd, kind, et, title))
                payload["cal_ids"].append(c.fetchone()["id"])
            elif act == "short":
                c.execute("INSERT INTO qbot_v2.trainer_day (username, day, state) VALUES (%s,%s,'short') ON CONFLICT (username, day) DO NOTHING RETURNING day", (u, dd))
                if c.fetchone():
                    payload["day_state"] = d
            else:
                c.execute("DELETE FROM qbot_v2.calendar_entry WHERE day=%s AND note='[trener]' RETURNING id, day, kind, event_type, title", (dd,))
                payload["cleared"] = [_jsonable(x) for x in c.fetchall()]
                c.execute("DELETE FROM qbot_v2.trainer_day WHERE username=%s AND day=%s", (u, dd))
            return _regenerate(c, u, dd - timedelta(days=dd.weekday()), "day_" + act, payload)
        return run(go)

    @r.post("/week/undo")
    async def week_undo(request: Request):
        u = user_of(request)
        b = await body_of(request)
        def go(c):
            cid = _int((b or {}).get("id"), "id", 1, 10 ** 12, required=True)
            c.execute("SELECT * FROM qbot_v2.trainer_change WHERE id=%s AND username=%s AND accepted IS NULL", (cid, u))
            ch = c.fetchone()
            if not ch:
                raise HTTPException(status_code=404, detail="brak zmiany do cofnięcia")
            p = ch["payload"] or {}
            if p.get("after_ids"):
                c.execute("DELETE FROM qbot_v2.trainer_session WHERE username=%s AND id = ANY(%s) AND source='auto'", (u, p["after_ids"]))
            cols = ["day", "sport", "name", "start_time", "dur_min", "min_min", "zone", "xss", "is_long", "status", "cut", "source", "note"]
            for x in (ch["before"] or []):
                c.execute(f"INSERT INTO qbot_v2.trainer_session (username,{','.join(cols)}) VALUES (%s,{','.join(['%s'] * len(cols))})", [u] + [x.get(k) for k in cols])
            if p.get("cal_ids"):
                c.execute("DELETE FROM qbot_v2.calendar_entry WHERE id = ANY(%s) AND note='[trener]'", (p["cal_ids"],))
            if p.get("day_state"):
                c.execute("DELETE FROM qbot_v2.trainer_day WHERE username=%s AND day=%s", (u, p["day_state"]))
            for x in p.get("cleared") or []:
                c.execute("INSERT INTO qbot_v2.calendar_entry (day, kind, event_type, title, note) VALUES (%s,%s,%s,%s,'[trener]')", (x["day"], x["kind"], x["event_type"], x["title"]))
            c.execute("UPDATE qbot_v2.trainer_change SET accepted=false WHERE id=%s", (cid,))
            return {"ok": True, "undone": cid}
        return run(go)

    @r.post("/week/accept")
    async def week_accept(request: Request):
        u = user_of(request)
        b = await body_of(request)
        def go(c):
            cid = _int((b or {}).get("id"), "id", 1, 10 ** 12, required=True)
            c.execute("UPDATE qbot_v2.trainer_change SET accepted=true WHERE id=%s AND username=%s AND accepted IS NULL RETURNING id", (cid, u))
            if not c.fetchone():
                raise HTTPException(status_code=404, detail="brak zmiany")
            return {"ok": True}
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
        import qbot_trener_stats as ST
        def go(c):
            out = compute_auto(c)
            wx = ST.weather_auto_cached(c, db_conn)
            for k, v in wx.items():
                if k.startswith("wx."):
                    out[k] = v
            out["_weather"] = {"computed_at": wx.get("_computed_at"), "computing": wx.get("_computing"), "n": wx.get("_n")}
            return out
        return run(go)

    @r.get("/notify/preview")
    def notify_preview(request: Request, kind: str = Query("plan"), start: str = Query(None)):
        u = user_of(request)
        import qbot_trener_notify as N
        def go(c):
            d0, _ = _week_bounds(start)
            if kind == "plan":
                res = E.plan_week(E.build_context(c, u, d0))
                c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s ORDER BY day, start_time NULLS LAST", (u, d0, d0 + timedelta(days=6)))
                ses = [dict(x) for x in c.fetchall()]
                if not ses:
                    ses = [dict(x, day=date.fromisoformat(x["day"]), start_time=datetime.strptime(x["start_time"], "%H:%M").time() if x.get("start_time") else None) for x in res["sessions"]]
                return {"text": N.text_plan(d0, ses, res["phase_name"], res["target_h"], res["notes"])}
            if kind == "review":
                c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day BETWEEN %s AND %s ORDER BY day, start_time NULLS LAST", (u, d0, d0 + timedelta(days=6)))
                rows = [dict(x) for x in c.fetchall()]
                st = N.settings(c, u)
                return {"text": N.text_review(d0, rows, 0.0, st["notify.tone"], None)}
            d = date.today()
            c.execute("SELECT * FROM qbot_v2.trainer_session WHERE username=%s AND day=%s ORDER BY start_time NULLS LAST", (u, d))
            return {"text": N.text_day(d, [dict(x) for x in c.fetchall()]) or "(dziś brak treningów w planie)"}
        return run(go)

    @r.get("/season")
    def season_get(request: Request):
        """Model sezonu: tygodnie (okres, h, wyprawy) od biezacego tygodnia, granice sezonow (auto/nadpisane), plan km."""
        u = user_of(request)
        import qbot_trener_stats as ST
        def go(c):
            c.execute("SELECT * FROM qbot_v2.trainer_goal WHERE username=%s", (u,))
            goals = [dict(x) for x in c.fetchall()]
            c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username=%s", (u,))
            row = c.fetchone(); ov = dict(row["overrides"]) if row else {}
            today = date.today(); s0 = today - timedelta(days=today.weekday())
            W = E.season_weeks(goals, ov, s0, 66)
            weeks = [{"s": w["s"].isoformat(), "ph": w["ph"], "name": E.PH_NAME.get(w["ph"], w["ph"]), "h": round(w["h"], 1), "lt": w["lt"],
                      "pre": w["pre"], "season": w["season"], "ev": [{"name": x["g"]["name"], "kind": x["g"]["kind"], "pr": x["pr"],
                      "a": x["a"].isoformat(), "b": x["b"].isoformat()} for x in w["ev"]]} for w in W]
            vol = []
            for g in goals:
                t = g.get("target") or {}
                if g["kind"] == "volume" and g["status"] == "active" and g.get("date_from") and g.get("date_to"):
                    key = "km" if t.get("km") else ("h" if t.get("h") else ("sessions" if t.get("sessions") else None))
                    if key:
                        prof = ST.month_profile(c, "rower" if key == "km" else t.get("sport", "rower"))
                        vol.append({"id": g["id"], "name": g["name"], "unit": key, "plan": ST.volume_plan(g["date_from"], g["date_to"], float(t[key]), prof)})
            params = {k: E.P(ov, k) for k in ("season.taper_w", "season.regen_w", "season.light_every_w", "season.volume")}
            return {"weeks": weeks, "seasons": E.seasons_summary(goals, ov, today, 3), "volume": vol, "params": params,
                    "overridden": {k: v for k, v in ov.items() if k.startswith("season.")}}
        return run(go)

    @r.post("/week/review")
    async def week_review(request: Request):
        """Weryfikacja tygodnia przez AI (drugi pilot). Nic nie zmienia - zwraca uwagi do decyzji uzytkownika."""
        u = user_of(request)
        b = await body_of(request) if (await request.body()) else {}
        import qbot_trener_review as RV
        def go(c):
            d0, _ = _week_bounds((b or {}).get("start"))
            return RV.review_week(c, u, d0, force=bool((b or {}).get("force")))
        return run(go)

    @r.get("/balance")
    def balance_get(request: Request):
        u = user_of(request)
        import qbot_trener_stats as ST
        def go(c):
            c.execute("SELECT overrides FROM qbot_v2.trainer_settings WHERE username=%s", (u,))
            row = c.fetchone()
            c.execute("SELECT * FROM qbot_v2.trainer_goal WHERE username=%s", (u,))
            goals = [dict(x) for x in c.fetchall()]
            return ST.compute_balance(c, dict(row["overrides"]) if row else {}, goals)
        return run(go)

    @r.get("/time")
    def time_get(request: Request):
        u = user_of(request)
        import qbot_trener_stats as ST
        return run(lambda c: ST.compute_time(c, u))

    return r
