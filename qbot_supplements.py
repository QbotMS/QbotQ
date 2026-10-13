"""Suplementy i leki (2026-10-13): lista z wersjami dawek, dziennik przyjec, potwierdzenie rano za wczoraj,
regularnosc (bez passy), lista do raportu dla lekarza.

Decyzje Michala (13.10.2026): potwierdzanie RANO za dzien poprzedni, jednym przyciskiem "Wszystkie" w porannej wiadomosci 7:00
(wyjatki poprawia recznie w Zdrowie > Suplementy), bez passy - tylko statystyka regularnosci. Dzien liczy sie po kliknieciu
(nic nie jest zaliczane automatycznie). Zmiana dawki = nowa wersja od dnia (historia zostaje poprawna).
Tabele: sql/supl_v1.sql. API: /api/supl (build_router). Dokumentacja: docs/SUPLEMENTY.md. Testy: tests/test_supplements.py.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request   # na poziomie modulu: adnotacje (from __future__) musza sie rozwiazac

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

SLOTS = {"rano": "rano", "wieczor": "wieczorem", "przed_snem": "przed snem", "dowolnie": "w ciągu dnia"}
KINDS = ("suplement", "lek")
DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]


def _conn():
    from fitmodel.api import _db_connect
    return _db_connect()


def fmt_dose(dose, unit) -> str:
    if dose is None:
        return ""
    d = ("%g" % float(dose)).replace(".", ",")
    return f"{d} {unit or ''}".strip()


def is_scheduled(days: list[int] | None, day: date) -> bool:
    return not days or day.weekday() in days


# ---------------- odczyt ----------------

def items(cur, include_inactive: bool = False) -> list[dict]:
    cur.execute("""SELECT id, name, kind, slot, days, active, note, sort FROM qbot_v2.supplement
                   WHERE NOT deleted """ + ("" if include_inactive else "AND active ") + "ORDER BY sort, id")
    out = []
    for i, n, k, sl, dy, ac, nt, so in cur.fetchall():
        cur.execute("SELECT valid_from, dose, unit FROM qbot_v2.supplement_dose WHERE supplement_id=%s ORDER BY valid_from", (i,))
        vers = [{"from": vf.isoformat(), "dose": float(d) if d is not None else None, "unit": u} for vf, d, u in cur.fetchall()]
        out.append({"id": i, "name": n, "kind": k, "slot": sl, "days": list(dy) if dy else None, "active": ac, "note": nt,
                    "versions": vers, "dose": vers[-1]["dose"] if vers else None, "unit": vers[-1]["unit"] if vers else None})
    return out


def dose_on(versions: list[dict], day: date) -> dict | None:
    v = [x for x in versions if x["from"] <= day.isoformat()]
    return v[-1] if v else None


def scheduled(cur, day: date) -> list[dict]:
    """Pozycje do przyjecia w dniu (aktywne, z dawka obowiazujaca tego dnia, wg dni tygodnia)."""
    out = []
    for it in items(cur):
        v = dose_on(it["versions"], day)
        if v and is_scheduled(it["days"], day):
            out.append(dict(it, dose=v["dose"], unit=v["unit"]))
    return out


def day_status(cur, day: date) -> list[dict]:
    cur.execute("SELECT supplement_id, status, dose, unit FROM qbot_v2.supplement_log WHERE day=%s", (day,))
    log = {r[0]: {"status": r[1], "dose": r[2], "unit": r[3]} for r in cur.fetchall()}
    return [dict(it, log=log.get(it["id"])) for it in scheduled(cur, day)]


# ---------------- zapis ----------------

def confirm_all(cur, day: date, source: str = "telegram") -> int:
    """'Wszystkie' za dzien: zapisuje wziete dla pozycji bez wpisu (recznie oznaczonych nie nadpisuje)."""
    n = 0
    for it in scheduled(cur, day):
        cur.execute("""INSERT INTO qbot_v2.supplement_log (day, supplement_id, status, dose, unit, source)
                       VALUES (%s,%s,'taken',%s,%s,%s) ON CONFLICT (day, supplement_id) DO NOTHING""",
                    (day, it["id"], it["dose"], it["unit"], source))
        n += cur.rowcount or 0
    return n


def set_log(cur, day: date, sid: int, status: str | None, dose: float | None = None, source: str = "web") -> None:
    if status is None:
        cur.execute("DELETE FROM qbot_v2.supplement_log WHERE day=%s AND supplement_id=%s", (day, sid))
        return
    if status not in ("taken", "skipped"):
        raise ValueError("status: taken / skipped")
    v = None
    for it in items(cur, include_inactive=True):
        if it["id"] == sid:
            v = dose_on(it["versions"], day)
    cur.execute("""INSERT INTO qbot_v2.supplement_log (day, supplement_id, status, dose, unit, source) VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (day, supplement_id) DO UPDATE SET status=EXCLUDED.status, dose=EXCLUDED.dose, unit=EXCLUDED.unit,
                   source=EXCLUDED.source, at=now()""",
                (day, sid, status, dose if dose is not None else (v or {}).get("dose"), (v or {}).get("unit"), source))


def create(cur, name: str, kind: str, slot: str, dose: float | None, unit: str, days: list[int] | None = None,
           valid_from: date | None = None, note: str | None = None) -> int:
    if kind not in KINDS or slot not in SLOTS or not name.strip():
        raise ValueError("nazwa, rodzaj (suplement/lek) i pora sa wymagane")
    cur.execute("SELECT coalesce(max(sort), 0) + 1 FROM qbot_v2.supplement")
    so = cur.fetchone()[0]
    cur.execute("INSERT INTO qbot_v2.supplement (name, kind, slot, days, note, sort) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (name.strip(), kind, slot, days or None, note, so))
    sid = cur.fetchone()[0]
    cur.execute("INSERT INTO qbot_v2.supplement_dose (supplement_id, valid_from, dose, unit) VALUES (%s,%s,%s,%s)",
                (sid, valid_from or date.today(), dose, unit))
    return sid


def update(cur, sid: int, **f) -> None:
    allowed = {k: v for k, v in f.items() if k in ("name", "kind", "slot", "days", "active", "note")}
    if "kind" in allowed and allowed["kind"] not in KINDS:
        raise ValueError("rodzaj: suplement / lek")
    if "slot" in allowed and allowed["slot"] not in SLOTS:
        raise ValueError("pora: " + ", ".join(SLOTS))
    for k, v in allowed.items():
        cur.execute(f"UPDATE qbot_v2.supplement SET {k}=%s WHERE id=%s", (v or None if k == "days" else v, sid))


def set_dose(cur, sid: int, dose: float | None, unit: str, valid_from: date) -> None:
    """Nowa dawka od dnia (historia dawek zostaje)."""
    cur.execute("""INSERT INTO qbot_v2.supplement_dose (supplement_id, valid_from, dose, unit) VALUES (%s,%s,%s,%s)
                   ON CONFLICT (supplement_id, valid_from) DO UPDATE SET dose=EXCLUDED.dose, unit=EXCLUDED.unit""",
                (sid, valid_from, dose, unit))


def delete(cur, sid: int) -> None:
    cur.execute("UPDATE qbot_v2.supplement SET deleted=true, active=false WHERE id=%s", (sid,))


# ---------------- regularnosc ----------------

def regularity(sched: dict[date, list[int]], log: dict[tuple[date, int], str]) -> dict[str, Any]:
    """Czyste: sched = {dzien: [id]}, log = {(dzien, id): status}. Procent = wziete / zaplanowane."""
    per: dict[int, dict] = {}
    for d, ids in sched.items():
        for i in ids:
            p = per.setdefault(i, {"plan": 0, "taken": 0, "skipped": 0, "none": 0})
            p["plan"] += 1
            st = log.get((d, i))
            p["taken" if st == "taken" else "skipped" if st == "skipped" else "none"] += 1
    for p in per.values():
        p["pct"] = round(100 * p["taken"] / p["plan"]) if p["plan"] else None
    tot = sum(p["plan"] for p in per.values())
    return {"items": per, "pct": round(100 * sum(p["taken"] for p in per.values()) / tot) if tot else None,
            "unconfirmed_days": sorted({d.isoformat() for d, ids in sched.items() for i in ids if (d, i) not in log})}


def overview(days: int = 35, today: date | None = None) -> dict:
    today = today or date.today()
    c = _conn()
    try:
        cur = c.cursor()
        its = items(cur, include_inactive=True)
        d0 = today - timedelta(days=days - 1)
        cur.execute("SELECT day, supplement_id, status, dose, unit FROM qbot_v2.supplement_log WHERE day BETWEEN %s AND %s", (d0, today))
        rows = cur.fetchall()
    finally:
        c.close()
    log = {(d, i): s for d, i, s, _, _ in rows}
    logd = {f"{d.isoformat()}:{i}": {"status": s, "dose": float(x) if x is not None else None, "unit": u} for d, i, s, x, u in rows}
    sched: dict[date, list[int]] = {}
    for k in range(days):
        d = d0 + timedelta(days=k)
        if d >= today:      # dzisiejszy dzien potwierdza sie jutro rano
            continue
        sched[d] = [it["id"] for it in its if it["active"] and dose_on(it["versions"], d) and is_scheduled(it["days"], d)]
    reg = regularity(sched, log)
    return {"today": today.isoformat(), "from": d0.isoformat(), "items": its, "log": logd,
            "scheduled": {d.isoformat(): ids for d, ids in sched.items()}, "regularity": reg,
            "slots": SLOTS, "kinds": list(KINDS), "min_n": MIN_N}


# ---------------- Telegram (poranna wiadomosc 7:00) i raport ----------------

def morning(today: date | None = None) -> tuple[str | None, list]:
    """Linia + przycisk za WCZORAJ (tylko gdy cos zaplanowane i niepotwierdzone)."""
    y = (today or date.today()) - timedelta(days=1)
    c = _conn()
    try:
        st = day_status(c.cursor(), y)
    finally:
        c.close()
    if not st:
        return None, []
    todo = [s for s in st if not s["log"]]
    if not todo:
        return None, []
    names = " · ".join(f"{s['name']} {fmt_dose(s['dose'], s['unit'])}".strip() for s in st)
    return (f"💊 Wczoraj ({y.strftime('%d.%m')}): {names}",
            [[{"text": "💊 Wczoraj wszystkie wzięte", "callback_data": f"tr:supl:{y.strftime('%Y%m%d')}"}]])


def tg_confirm(day_str: str) -> str:
    d = datetime.strptime(day_str, "%Y%m%d").date()
    c = _conn()
    try:
        cur = c.cursor()
        n = confirm_all(cur, d, "telegram")
        c.commit()
        st = day_status(cur, d)
    finally:
        c.close()
    ok = sum(1 for s in st if (s["log"] or {}).get("status") == "taken")
    return (f"💊 {d.strftime('%d.%m')}: zapisane – wzięte {ok} z {len(st)}." if n else
            f"💊 {d.strftime('%d.%m')}: już było zapisane ({ok} z {len(st)}).") + " Wyjątki popraw w Zdrowie → Suplementy."


def report_lines() -> list[str]:
    """Aktualne leki i suplementy (dla raportu dla lekarza)."""
    c = _conn()
    try:
        its = items(c.cursor())
    finally:
        c.close()
    out = []
    for it in its:
        dn = "" if not it["days"] else " (" + ", ".join(DN[d] for d in it["days"]) + ")"
        out.append(f"{it['name']} {fmt_dose(it['dose'], it['unit'])} {SLOTS.get(it['slot'], '')}{dn}"
                   f" – {it['kind']}, od {datetime.fromisoformat(it['versions'][0]['from']).strftime('%d.%m.%Y')}")
    return out


# ---------------- API ----------------

def build_router(current_user, owner_user):
    r = APIRouter(prefix="/api/supl")

    def _auth(request, write=False):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        if write and not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko odczyt (sesja demo)")

    def _write(fn):
        c = _conn()
        try:
            cur = c.cursor()
            res = fn(cur)
            c.commit()
            return res
        except ValueError as e:
            c.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            c.close()

    def _d(s):
        return datetime.strptime(s, "%Y-%m-%d").date() if s else None

    @r.get("")
    def get_all(request: Request, days: int = 35):
        _auth(request)
        o = overview(max(7, min(180, days)))
        o["night"] = night_effects()
        return o

    @r.post("")
    async def post_item(request: Request):
        _auth(request, True)
        b = await request.json()
        sid = _write(lambda cur: create(cur, str(b.get("name") or ""), b.get("kind") or "suplement", b.get("slot") or "dowolnie",
                                        float(b["dose"]) if b.get("dose") not in (None, "") else None, b.get("unit") or "",
                                        b.get("days") or None, _d(b.get("from")), b.get("note")))
        return {"ok": True, "id": sid}

    @r.put("/{sid}")
    async def put_item(sid: int, request: Request):
        _auth(request, True)
        b = await request.json()

        def fn(cur):
            update(cur, sid, **{k: b[k] for k in ("name", "kind", "slot", "days", "active", "note") if k in b})
            if "dose" in b:
                set_dose(cur, sid, float(b["dose"]) if b["dose"] not in (None, "") else None, b.get("unit") or "", _d(b.get("from")) or date.today())
        _write(fn)
        return {"ok": True}

    @r.delete("/{sid}")
    def del_item(sid: int, request: Request):
        _auth(request, True)
        _write(lambda cur: delete(cur, sid))
        return {"ok": True}

    @r.post("/log")
    async def post_log(request: Request):
        _auth(request, True)
        b = await request.json()
        d = _d(b.get("day"))
        if b.get("all"):
            n = _write(lambda cur: confirm_all(cur, d, "web"))
            return {"ok": True, "saved": n}
        _write(lambda cur: set_log(cur, d, int(b["id"]), b.get("status"), float(b["dose"]) if b.get("dose") not in (None, "") else None))
        return {"ok": True}

    return r


# ---------------- wplyw na noc (2026-10-13) ----------------
# Noc po dniu D = rekord wellness z dnia D+1 (Garmin zapisuje sen pod dniem obudzenia).
# Porownanie nocy po dniach "wziete" vs "pominiete" (tylko potwierdzone wpisy; niepotwierdzone pomijane).

MIN_N = 7
METRICS = [("sen_min", "sen", "min", +1), ("sen_score", "jakość snu", "pkt", +1), ("hrv", "HRV nocne", "ms", +1),
           ("rhr", "tętno spoczynkowe", "ud./min", -1), ("spo2_low", "najniższa SpO2", "%", +1)]


def effect(taken: list[float], skipped: list[float]) -> dict:
    """Czyste: srednie, roznica i sila efektu (d Cohena). Bez wniosku przy < MIN_N nocy w ktorejkolwiek grupie."""
    t = [x for x in taken if x is not None]
    k = [x for x in skipped if x is not None]
    out = {"n_taken": len(t), "n_skipped": len(k)}
    if len(t) < MIN_N or len(k) < MIN_N:
        out["enough"] = False
        return out
    mt, mk = sum(t) / len(t), sum(k) / len(k)
    vt = sum((x - mt) ** 2 for x in t) / (len(t) - 1)
    vk = sum((x - mk) ** 2 for x in k) / (len(k) - 1)
    sd = ((vt + vk) / 2) ** 0.5
    d = (mt - mk) / sd if sd else 0.0
    out.update(enough=True, mean_taken=round(mt, 1), mean_skipped=round(mk, 1), diff=round(mt - mk, 1), d=round(d, 2),
               size="wyraźny" if abs(d) >= 0.8 else "umiarkowany" if abs(d) >= 0.5 else "mały" if abs(d) >= 0.2 else "brak")
    return out


def night_effects(today: date | None = None, days: int = 180) -> list[dict]:
    """Dla kazdej pozycji: porownanie nocy po dniach wziete vs pominiete."""
    today = today or date.today()
    d0 = today - timedelta(days=days)
    c = _conn()
    try:
        cur = c.cursor()
        its = items(cur, include_inactive=True)
        cur.execute("SELECT day, supplement_id, status FROM qbot_v2.supplement_log WHERE day >= %s", (d0,))
        log = cur.fetchall()
        cur.execute("""SELECT date, max(sleep_duration_min), max(sleep_score), max(hrv_ms),
                              coalesce(max(resting_hr_bpm) FILTER (WHERE source='garmin'), max(resting_hr_bpm))
                       FROM qbot_v2.qbot_wellness_daily WHERE date >= %s GROUP BY date""", (d0,))
        well = {r[0]: {"sen_min": r[1], "sen_score": r[2], "hrv": r[3], "rhr": r[4]} for r in cur.fetchall()}
        cur.execute("SELECT day, lowest_spo2 FROM qbot_v2.spo2_daily WHERE day >= %s", (d0,))
        for dd_, lo in cur.fetchall():
            well.setdefault(dd_, {})["spo2_low"] = lo
    finally:
        c.close()
    out = []
    for it in its:
        rows = [(d, st) for d, sid, st in log if sid == it["id"]]
        res = {"id": it["id"], "name": it["name"], "metrics": []}
        for key, label, unit, better in METRICS:
            tk = [float(well.get(d + timedelta(days=1), {}).get(key)) for d, st in rows if st == "taken" and well.get(d + timedelta(days=1), {}).get(key) is not None]
            sk = [float(well.get(d + timedelta(days=1), {}).get(key)) for d, st in rows if st == "skipped" and well.get(d + timedelta(days=1), {}).get(key) is not None]
            e = effect(tk, sk)
            e.update(key=key, label=label, unit=unit, better=better)
            res["metrics"].append(e)
        res["n_taken"] = sum(1 for _, st in rows if st == "taken")
        res["n_skipped"] = sum(1 for _, st in rows if st == "skipped")
        res["enough"] = any(m.get("enough") for m in res["metrics"])
        out.append(res)
    return out


def summary_for_albert(today: date | None = None) -> dict:
    """Narzedzie Alberta 'supplements': lista, wczoraj, regularnosc 35 dni, wplyw na noc (gdy sa dane)."""
    today = today or date.today()
    ov = overview(35, today)
    y = (today - timedelta(days=1)).isoformat()
    per = (ov["regularity"] or {}).get("items") or {}
    lst = []
    for it in ov["items"]:
        if not it["active"]:
            continue
        lg = ov["log"].get(f"{y}:{it['id']}")
        lst.append({"nazwa": it["name"], "rodzaj": it["kind"], "dawka": fmt_dose(it["dose"], it["unit"]), "pora": SLOTS.get(it["slot"]),
                    "dni": "codziennie" if not it["days"] else ", ".join(DN[d] for d in it["days"]),
                    "wczoraj": ((lg or {}).get("status") or "niepotwierdzone") if it["id"] in (ov["scheduled"].get(y) or []) else "nie było w planie (lista od " + it["versions"][0]["from"] + ")",
                    "regularnosc_35d_pct": (per.get(it["id"]) or {}).get("pct"),
                    "historia_dawek": [f"{fmt_dose(v['dose'], v['unit'])} od {v['from']}" for v in it["versions"]]})
    eff = []
    for e in night_effects(today):
        good = [m for m in e["metrics"] if m.get("enough")]
        eff.append({"nazwa": e["name"], "nocy_wziete": e["n_taken"], "nocy_pominiete": e["n_skipped"],
                    "wnioski": [f"{m['label']}: {m['mean_taken']} vs {m['mean_skipped']} {m['unit']} (efekt {m['size']})" for m in good]
                    or [f"za mało danych (potrzeba po {MIN_N} nocy z i bez)"]})
    return {"lista": lst, "regularnosc_35d_pct": (ov["regularity"] or {}).get("pct"),
            "niepotwierdzone_dni": len((ov["regularity"] or {}).get("unconfirmed_days") or []), "wplyw_na_noc": eff,
            "gdzie": "Zdrowie → Suplementy; potwierdzenie rano za wczoraj przyciskiem w Telegramie"}
