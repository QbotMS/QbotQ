#!/usr/bin/env python3
"""Weekend bez diety (15.10.2026): plan dzien po dniu (sb, nd) + LISTA ZAKUPOW.

Kazdy dzien ma tryb (przelacznik na stronie): "miasto" = sniadanie w domu, reszta na miescie (co zamawiac, szacunek kcal),
"dom" = wszystkie posilki z domu (proste przepisy). Posilki dnia sumuja sie do celu kcal (z qbot_food_plan.day_plan;
cel i paliwo na rower sa USTALONE, AI ich nie zmienia). Lista zakupow = skladniki wszystkich posilkow "dom" + jedzenie na rower,
ilosci na wybrana liczbe osob. Kontekst: docs/BROKUL.md (w tygodniu catering Brokul, w weekend bez diety).
Zapis: qbot_v2.food_weekend_plan (klucz = piatek; plan.modes = tryby dni), odhaczone zakupy w 'checked'.
Gdzie: Zdrowie > Weekend (zdrowie-weekend.js), piatkowa linijka porannej wiadomosci (link), Albert: food_weekend_plan.
API: GET /api/jedzenie/weekend, POST /api/jedzenie/weekend/build {portions, modes:{sb,nd}}, POST /api/jedzenie/weekend/check {key, on}.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request

TZ = ZoneInfo("Europe/Warsaw")
DN = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]
MODES = ("miasto", "dom")
DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.food_weekend_plan (
    friday date PRIMARY KEY, portions integer NOT NULL DEFAULT 1, plan jsonb NOT NULL,
    checked jsonb NOT NULL DEFAULT '{}'::jsonb, built_at timestamptz NOT NULL DEFAULT now())"""

_PROMPT = """Jesteś dietetykiem sportowym. Użytkownik (mężczyzna ~104 kg, redukcja ~0,5 kg/tydz., kolarz gravel) w weekend NIE ma cateringu.
Dostajesz dni weekendu: cel kcal, białko, treningi, węgle na rower, wydarzenia oraz TRYB dnia i liczbę porcji.
TRYB "miasto": śniadanie w domu (prosty przepis), pozostałe posiłki na mieście (konkretne typy dań do zamówienia + szacunek kcal).
TRYB "dom": WSZYSTKIE posiłki w domu (proste przepisy, max 25 min, mało naczyń).
Zwróć WYŁĄCZNIE JSON:
{"days": [{"day": "sb", "unikaj": "...", "rower": "...",
           "posilki": [{"pora": "śniadanie", "gdzie": "dom", "nazwa": "...", "kcal": 500, "bialko_g": 40, "czas_min": 10,
                        "skladniki": ["..."], "kroki": ["..."]},
                       {"pora": "obiad", "gdzie": "miasto", "nazwa": "...", "kcal": 700, "bialko_g": 45, "zamow": "co konkretnie zamówić"}]}],
 "zakupy": [{"produkt": "...", "ilosc": "...", "dzial": "warzywa i owoce"}]}
Zasady:
- Posiłki dnia (śniadanie, obiad, przekąska, kolacja; w dzień z jazdą >= 75 min dodaj "na rower") SUMUJĄ się do celu kcal dnia (+-10 %).
  Białko łącznie blisko celu. Kcal i białko NA JEDNĄ PORCJĘ (szacunek).
- "dom": "skladniki" z ilościami NA PODANĄ LICZBĘ PORCJI, "kroki" 3-6 krótkich. "miasto": pole "zamow" (1 zdanie), bez skladnikow.
- "na rower": co zabrać, pokryj podane węgle (gdzie = "dom", skladniki = produkty).
- "unikaj": krótko, co rozwala cel. "rower": krótka wskazówka jedzenia na jeździe albo "".
- "zakupy": WSZYSTKIE składniki posiłków "dom" + jedzenie na rower, ilości na liczbę porcji, bez duplikatów, bez soli/pieprzu/oleju.
  "dzial": "warzywa i owoce", "mięso i ryby", "nabiał i jajka", "pieczywo", "suche i przyprawy", "na rower" albo "inne".
Liczby: cel kcal dnia i węgle na rower są ustalone - nie zmieniaj ich."""


def _conn():
    import qbot_food_plan as FP
    return FP._conn()


def friday_for(d: date) -> date:
    """Pt-nd -> piatek tego tygodnia; pn-czw -> najblizszy piatek."""
    wd = d.weekday()
    return d - timedelta(days=wd - 4) if wd >= 4 else d + timedelta(days=4 - wd)


def _days_input(friday: date, c, modes: dict) -> list[dict]:
    import qbot_food_plan as FP
    out = []
    for d in (friday + timedelta(days=1), friday + timedelta(days=2)):
        p = FP.day_plan(d, c)
        ev = [r["title"] for r in c.execute(
            "SELECT title FROM qbot_v2.calendar_entry WHERE kind='event' AND %s BETWEEN day AND COALESCE(end_day, day)", (d,)).fetchall()
              if r["title"]]
        dn = DN[d.weekday()]
        out.append({"day": dn, "date": d.strftime("%d.%m"), "iso": d.isoformat(), "tryb": modes.get(dn, "miasto"),
                    "cel_kcal": p["target"], "bialko_g": FP.PROTEIN_G, "wegle_na_rower_g": p["fuel_g"],
                    "treningi": ["%s %s %d min" % (s["sport"], s["name"], s["dur_min"] or 0) for s in p["sessions"]],
                    "wydarzenia": ev})
    return out


def build(friday: date, portions: int = 1, modes: dict | None = None) -> dict:
    import qbot_food_log as F
    portions = max(1, min(4, int(portions or 1)))
    modes = {k: (v if v in MODES else "miasto") for k, v in (modes or {}).items() if k in ("sb", "nd")}
    with _conn() as c:
        c.execute(DDL)
        days = _days_input(friday, c, modes)
        try:
            ai = F._ai_json(_PROMPT, [{"type": "text", "text": json.dumps({"porcje": portions, "dni": days}, ensure_ascii=False)}]) or {}
        except Exception as e:
            ai = {"_error": type(e).__name__}
        by = {x.get("day"): x for x in (ai.get("days") or []) if isinstance(x, dict)}
        pdays = []
        for d in days:
            a = by.get(d["day"]) or {}
            meals = [m for m in (a.get("posilki") or []) if isinstance(m, dict)][:7]
            tot = sum(float(m.get("kcal") or 0) for m in meals)
            pdays.append(dict(d, unikaj=a.get("unikaj", ""), rower=a.get("rower", ""), posilki=meals,
                              suma_kcal=round(tot), suma_bialko=round(sum(float(m.get("bialko_g") or 0) for m in meals))))
        plan = {"modes": {d["day"]: d["tryb"] for d in days}, "days": pdays,
                "zakupy": [z for z in (ai.get("zakupy") or []) if isinstance(z, dict) and z.get("produkt")][:40],
                "error": ai.get("_error")}
        c.execute("INSERT INTO qbot_v2.food_weekend_plan (friday, portions, plan, checked, built_at) VALUES (%s,%s,%s,'{}',now()) "
                  "ON CONFLICT (friday) DO UPDATE SET portions=EXCLUDED.portions, plan=EXCLUDED.plan, checked='{}', built_at=now()",
                  (friday, portions, json.dumps(plan, ensure_ascii=False)))
    return get(friday, build_if_missing=False)


def get(friday: date, build_if_missing: bool = True) -> dict | None:
    with _conn() as c:
        c.execute(DDL)
        r = c.execute("SELECT friday, portions, plan, checked, built_at FROM qbot_v2.food_weekend_plan WHERE friday=%s", (friday,)).fetchone()
    if r and "posilki" not in ((r["plan"] or {}).get("days") or [{}])[0]:
        r = None   # plan w starym formacie (sprzed widoku dzien po dniu) -> ulozyc od nowa
    if not r:
        if not build_if_missing:
            return None
        with _conn() as c:
            x = c.execute("SELECT portions FROM qbot_v2.food_weekend_plan ORDER BY friday DESC LIMIT 1").fetchone()
        return build(friday, x["portions"] if x else 1)
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
    L = ["Weekend %s (porcje: %d):" % (p["weekend"], p["portions"])]
    for d in p["plan"].get("days", []):
        L.append("%s %s (%s): cel ~%s kcal, plan ~%s kcal%s" % (d["day"], d["date"], d.get("tryb"), d["cel_kcal"], d.get("suma_kcal"),
                 (", na rower ~%d g węgli" % d["wegle_na_rower_g"]) if d.get("wegle_na_rower_g") else ""))
        for m in d.get("posilki", []):
            L.append("  %s (%s): %s ~%s kcal%s" % (m.get("pora"), m.get("gdzie"), m.get("nazwa"), m.get("kcal"),
                     (" — zamów: " + m["zamow"]) if m.get("zamow") else ""))
    if p["plan"].get("zakupy"):
        L.append("Zakupy: " + ", ".join("%s %s" % (z.get("produkt"), z.get("ilosc") or "") for z in p["plan"]["zakupy"]))
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
        return build(_fri(b.get("friday")), int(b.get("portions") or 1), b.get("modes") or {})

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
