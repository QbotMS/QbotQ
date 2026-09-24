"""Garaz: edycja wynikow audytu garderoby (pola a_* w garage.db gear), czytanych przez doradce ubioru.

GET  /api/garage/audit?id=N      -> {id, audit:{...}|null, options:{...}}
POST /api/garage/audit/save      <- {id, audit:{st, fit, use, t_min, t_max, eff, rain, wind, wet, pad, carry,
                                            role, pairs, note, out, src}}  (pusty audit albo clear=true = usun ocene)
Slowniki wartosci = te same co scripts/garage_audit_import.py (jedno zrodlo prawdy: import stamtad).
"""
from __future__ import annotations

import datetime as _dt
import sqlite3
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request

GARAGE_DB = "/opt/qbot/app/data/garage.db"
OPTIONS = {
    "st": ["CORE", "ROTATION", "SPECIAL", "BACKUP", "RETIRE_CANDIDATE", "FIT_BLOCKED", "OFF_BIKE", "NEW"],
    "fit": ["OK", "LEKKO_CIASNA", "ZA_LUZNA", "BLOKUJE"],
    "use": ["CZESTO", "SPORADYCZNIE", "RZADKO", "NIGDY"],
    "eff": ["spokojnie", "Z2", "Z2-Z3"],
    "rain": ["brak_oczekiwan", "nietestowany", "mzawka_przemaka", "mzawka_sucho", "umiarkowany_przemaka_po_czasie",
             "umiarkowany_sucho", "ulewa_sucho"],
    "wind": ["mocna", "umiarkowana", "czesciowa", "mala"],
    "pad": ["0", "<1", "1-2", "2-4", "4-6", ">6"],
    "carry": ["czesto", "sporadycznie", "rzadko"],
}
MAP = {"st": "a_status", "fit": "a_fit", "use": "a_use", "t_min": "a_temp_min", "t_max": "a_temp_max",
       "eff": "a_effort", "rain": "a_rain", "wind": "a_wind", "wet": "a_wet_cold", "pad": "a_pad_h",
       "carry": "a_carry", "role": "a_role", "pairs": "a_pairs", "note": "a_note", "out": "a_out", "src": "a_src"}
TEXT_MAX = {"role": 160, "pairs": 300, "note": 600, "src": 120}


def _conn():
    c = sqlite3.connect(GARAGE_DB)
    c.row_factory = sqlite3.Row
    return c


def _read(c, gid):
    r = c.execute("SELECT id, " + ", ".join(sorted(set(MAP.values()) | {"a_date"})) + " FROM gear WHERE id=?", (gid,)).fetchone()
    if not r:
        return None
    if not r["a_date"]:
        return {"id": gid, "audit": None}
    a = {k: r[col] for k, col in MAP.items()}
    a["wet"] = bool(a["wet"]); a["out"] = bool(a["out"]); a["date"] = r["a_date"]
    return {"id": gid, "audit": a}


def _clean(a: dict) -> dict:
    v = {}
    for k in ("st", "fit", "use", "eff", "rain", "wind", "pad", "carry"):
        x = (a.get(k) or "").strip() if isinstance(a.get(k), str) else a.get(k)
        if x in (None, ""):
            v[k] = None
        elif x in OPTIONS[k]:
            v[k] = x
        else:
            raise HTTPException(status_code=400, detail="zla wartosc %s=%s" % (k, x))
    for k in ("t_min", "t_max"):
        x = a.get(k)
        if x in (None, ""):
            v[k] = None
        else:
            try:
                v[k] = max(-20, min(40, int(round(float(str(x).replace(",", "."))))))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="zla temperatura %s" % k)
    if v["t_min"] is not None and v["t_max"] is not None and v["t_min"] > v["t_max"]:
        raise HTTPException(status_code=400, detail="temperatura od > do")
    for k, n in TEXT_MAX.items():
        x = a.get(k)
        v[k] = (str(x).strip()[:n] or None) if x not in (None, "") else None
    v["wet"] = 1 if a.get("wet") in (1, "1", True, "true", "on") else 0
    v["out"] = 1 if a.get("out") in (1, "1", True, "true", "on") else 0
    if v["st"] in ("FIT_BLOCKED",):
        v["out"] = 1
    if not v["src"]:
        v["src"] = "edycja w Garazu"
    return v


def build_router(current_user: Callable) -> APIRouter:
    r = APIRouter(prefix="/api/garage/audit")

    def need_user(request: Request):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")

    @r.get("")
    def audit_get(request: Request, id: int = Query(...)) -> Any:
        need_user(request)
        c = _conn()
        try:
            d = _read(c, int(id))
        finally:
            c.close()
        if d is None:
            raise HTTPException(status_code=404, detail="brak rzeczy")
        d["options"] = OPTIONS
        return d

    @r.post("/save")
    async def audit_save(request: Request) -> Any:
        need_user(request)
        try:
            b = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Bledny JSON")
        try:
            gid = int(b.get("id"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Brak id")
        a = b.get("audit")
        c = _conn()
        try:
            if not c.execute("SELECT 1 FROM gear WHERE id=?", (gid,)).fetchone():
                raise HTTPException(status_code=404, detail="brak rzeczy")
            if b.get("clear") or not a:
                c.execute("UPDATE gear SET " + ", ".join("%s=NULL" % col for col in list(MAP.values()) + ["a_date"]) + " WHERE id=?", (gid,))
            else:
                if not isinstance(a, dict):
                    raise HTTPException(status_code=400, detail="audit musi byc obiektem")
                v = _clean(a)
                cols = list(MAP.items())
                c.execute("UPDATE gear SET " + ", ".join("%s=?" % col for _, col in cols) + ", a_date=? WHERE id=?",
                          [v[k] for k, _ in cols] + [_dt.date.today().isoformat(), gid])
            c.commit()
            out = _read(c, gid)
        finally:
            c.close()
        out["ok"] = True
        return out

    return r
