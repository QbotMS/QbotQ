#!/usr/bin/env python3
"""Weekend bez diety (15.10.2026): plan jedzenia na sobote i niedziele + LISTA ZAKUPOW + 2-3 proste posilki do zrobienia w domu.

Kontekst (docs/BROKUL.md): w tygodniu catering Brokul, w weekend bez diety -- glownie na miescie, czasem proste gotowanie w domu.
Dane dnia (cel kcal, trening, paliwo na rower) z qbot_food_plan.day_plan -- liczby ustalone, AI ich nie zmienia.
Zapis: qbot_v2.food_weekend_plan (jeden plan na weekend, klucz = piatek), odhaczone zakupy w 'checked'.
Gdzie: Zdrowie > Weekend (zdrowie-weekend.js), piatkowa linijka porannej wiadomosci (link), Albert: food_weekend_plan.
API: GET /api/jedzenie/weekend[?friday=RRRR-MM-DD], POST /api/jedzenie/weekend/build {portions, friday}, POST /api/jedzenie/weekend/check {key, on}.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request

TZ = ZoneInfo("Europe/Warsaw")
DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]
DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.food_weekend_plan (
    friday date PRIMARY KEY, portions integer NOT NULL DEFAULT 1, plan jsonb NOT NULL,
    checked jsonb NOT NULL DEFAULT '{}'::jsonb, built_at timestamptz NOT NULL DEFAULT now())"""

_PROMPT = """Jesteś dietetykiem sportowym. Użytkownik (mężczyzna ~104 kg, redukcja ~0,5 kg/tydz., kolarz gravel) w weekend NIE ma cateringu:
je głównie na mieście, czasem gotuje proste rzeczy w domu. Dostajesz plan dni (cel kcal, białko, trening, paliwo na rower, wydarzenia) i liczbę porcji.
Zwróć WYŁĄCZNIE JSON:
{"days": [{"day": "sb", "zamawiaj": "...", "unikaj": "...", "rower": "..."}],
 "posilki": [{"nazwa": "...", "kiedy": "sb śniadanie", "czas_min": 15, "kcal": 550, "bialko_g": 40,
              "skladniki": ["200 g piersi z kurczaka", "..."], "kroki": ["...", "..."]}],
 "zakupy": [{"produkt": "...", "ilosc": "...", "dzial": "warzywa i owoce"}]}
Zasady:
- "zamawiaj": 1-2 zdania, konkretne typy dań na mieście pod cel dnia (dużo białka, rozsądna porcja), prosto, po polsku.
- "unikaj": krótko, co rozwala cel. "rower": tylko gdy trening >= 75 min: co zabrać i zjeść (pokryj podaną ilość węgli), inaczej "".
- "posilki": 2-3 PROSTE posiłki do zrobienia w domu (max 25 min, mało naczyń), bogate w białko; kcal i białko NA JEDNĄ PORCJĘ
  (szacunek), składniki z ilościami NA PODANĄ LICZBĘ PORCJI; kroki krótkie (3-6). "kiedy" = dzień + pora (np. "nd obiad").
- "zakupy": wszystko do tych posiłków + przekąski na rower, ilości na podaną liczbę porcji, bez duplikatów, bez rzeczy zwykle w domu
  (sól, pieprz, olej). "dzial" jeden z: "warzywa i owoce", "mięso i ryby", "nabiał i jajka", "pieczywo", "suche i przyprawy", "na rower", "inne".
Liczby kcal dnia i węgli na rower są ustalone - nie zmieniaj ich."""


def _conn():
    import qbot_food_plan as FP
    return FP._conn()


def friday_for(d: date) -> date:
    """Pt-nd -> piatek tego tygodnia; pn-czw -> najblizszy piatek."""
    wd = d.weekday()
    return d - timedelta(days=wd - 4) if wd >= 4 else d + timedelta(days=4 - wd)


def _days_input(friday: date, c) -> list[dict]:
    import qbot_food_plan as FP
    out = []
    for d in (friday + timedelta(days=1), friday + timedelta(days=2)):
        p = FP.day_plan(d, c)
        ev = [r["title"] for r in c.execute(
            "SELECT title FROM qbot_v2.calendar_entry WHERE kind='event' AND %s BETWEEN day AND COALESCE(end_day, day)", (d,)).fetchall()
              if r["title"]]
        out.append({"day": DN[d.weekday()], "date": d.strftime("%d.%m"), "iso": d.isoformat(), "cel_kcal": p["target"],
                    "bialko_g": FP.PROTEIN_G, "brokul": bool(p["brokul"]), "wegle_na_rower_g": p["fuel_g"],
                    "treningi": ["%s %s %d min" % (s["sport"], s["name"], s["dur_min"] or 0) for s in p["sessions"]],
                    "wydarzenia": ev})
    return out


def build(friday: date, portions: int = 1) -> dict:
    import qbot_food_log as F
    portions = max(1, min(4, int(portions or 1)))
    with _conn() as c:
        c.execute(DDL)
        days = _days_input(friday, c)
        try:
            ai = F._ai_json(_PROMPT, [{"type": "text", "text": json.dumps({"porcje": portions, "dni": days}, ensure_ascii=False)}]) or {}
        except Exception as e:
            ai = {"_error": type(e).__name__}
        by = {x.get("day"): x for x in (ai.get("days") or []) if isinstance(x, dict)}
        plan = {"days": [dict(d, **{k: (by.get(d["day"]) or {}).get(k, "") for k in ("zamawiaj", "unikaj", "rower")}) for d in days],
                "posilki": [m for m in (ai.get("posilki") or []) if isinstance(m, dict)][:3],
                "zakupy": [z for z in (ai.get("zakupy") or []) if isinstance(z, dict) and z.get("produkt")][:30],
                "error": ai.get("_error")}
        c.execute("INSERT INTO qbot_v2.food_weekend_plan (friday, portions, plan, checked, built_at) VALUES (%s,%s,%s,'{}',now()) "
                  "ON CONFLICT (friday) DO UPDATE SET portions=EXCLUDED.portions, plan=EXCLUDED.plan, checked='{}', built_at=now()",
                  (friday, portions, json.dumps(plan, ensure_ascii=False)))
    return get(friday, build_if_missing=False)


def get(friday: date, build_if_missing: bool = True) -> dict | None:
    with _conn() as c:
        c.execute(DDL)
        r = c.execute("SELECT friday, portions, plan, checked, built_at FROM qbot_v2.food_weekend_plan WHERE friday=%s", (friday,)).fetchone()
    if not r:
        if not build_if_missing:
            return None
        last = None
        with _conn() as c:
            x = c.execute("SELECT portions FROM qbot_v2.food_weekend_plan ORDER BY friday DESC LIMIT 1").fetchone()
            last = x["portions"] if x else 1
        return build(friday, last)
    return {"friday": r["friday"].isoformat(), "weekend": "%s–%s" % ((friday + timedelta(days=1)).strftime("%d.%m"),
                                                                    (friday + timedelta(days=2)).strftime("%d.%m")),
            "portions": r["portions"], "plan": r["plan"], "checked": r["checked"] or {},
            "built_at": r["built_at"].astimezone(TZ).strftime("%d.%m %H:%M")}


def prebuild_async(friday: date) -> None:
    """Piatek rano (poranna wiadomosc): przygotuj plan w tle, zeby strona otwierala sie od razu."""
    def _go():
        try:
            get(friday, build_if_missing=True)
        except Exception as e:
            print("weekend prebuild blad:", type(e).__name__)
    threading.Thread(target=_go, daemon=True).start()


def summary_text(friday: date) -> str:
    """Krotko dla Alberta."""
    p = get(friday)
    if not p:
        return "Brak planu weekendu."
    pl = p["plan"]
    L = ["Weekend %s (porcje: %d):" % (p["weekend"], p["portions"])]
    for d in pl.get("days", []):
        L.append("%s %s: cel ~%s kcal%s. Na mieście: %s" % (d["day"], d["date"], d["cel_kcal"],
                 (", na rower ~%d g węgli" % d["wegle_na_rower_g"]) if d.get("wegle_na_rower_g") else "", d.get("zamawiaj") or "-"))
    for m in pl.get("posilki", []):
        L.append("Do zrobienia: %s (%s, ~%s kcal, %s g białka/porcję)" % (m.get("nazwa"), m.get("kiedy"), m.get("kcal"), m.get("bialko_g")))
    if pl.get("zakupy"):
        L.append("Zakupy: " + ", ".join("%s %s" % (z.get("produkt"), z.get("ilosc") or "") for z in pl["zakupy"]))
    return "\n".join(L)


def build_router(current_user, owner_user) -> APIRouter:
    r = APIRouter(prefix="/api/jedzenie/weekend")

    def _fri(s):
        if s:
            try:
                return friday_for(date.fromisoformat(s))
            except ValueError:
                raise HTTPException(status_code=400, detail="zła data")
        return friday_for(datetime.now(TZ).date())

    @r.get("")
    def weekend_get(request: Request, friday: str | None = None):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        fr = _fri(friday)
        p = get(fr, build_if_missing=bool(owner_user(request)))   # demo nie odpala AI
        return p or {"friday": fr.isoformat(), "plan": None}

    @r.post("/build")
    async def weekend_build(request: Request):
        if not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko odczyt (sesja demo)")
        b = await request.json()
        return build(_fri(b.get("friday")), int(b.get("portions") or 1))

    @r.post("/check")
    async def weekend_check(request: Request):
        if not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko odczyt (sesja demo)")
        b = await request.json()
        fr, key, on = _fri(b.get("friday")), str(b.get("key") or "")[:120], bool(b.get("on"))
        with _conn() as c:
            c.execute("UPDATE qbot_v2.food_weekend_plan SET checked = CASE WHEN %s THEN checked || jsonb_build_object(%s, true) "
                      "ELSE checked - %s END WHERE friday=%s", (on, key, key, fr))
        return {"ok": True}

    return r
