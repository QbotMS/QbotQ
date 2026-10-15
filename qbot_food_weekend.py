#!/usr/bin/env python3
"""Weekend bez diety (15.10.2026): plan dzien po dniu (sb, nd) + LISTA ZAKUPOW.

Kazdy dzien ma tryb (przelacznik na stronie): "miasto" = sniadanie w domu, reszta na miescie (co zamawiac, szacunek kcal),
"dom" = wszystkie posilki z domu (proste przepisy). Posilki dnia sumuja sie do celu kcal (z qbot_food_plan.day_plan;
cel i paliwo na rower sa USTALONE, AI ich nie zmienia). Lista zakupow = skladniki wszystkich posilkow "dom" + jedzenie na rower,
ilosci na wybrana liczbe osob. Kontekst: docs/BROKUL.md (w tygodniu catering Brokul, w weekend bez diety).
Zapis: qbot_v2.food_weekend_plan (klucz = piatek; plan.modes = tryby dni), odhaczone zakupy w 'checked'.
Gdzie: Zdrowie > Weekend (zdrowie-weekend.js), piatkowa linijka porannej wiadomosci (link), Albert: food_weekend_plan.
API: GET /api/jedzenie/weekend, POST /api/jedzenie/weekend/build {portions, modes}, POST /api/jedzenie/weekend/mode {day, mode} (bez AI),
POST /api/jedzenie/weekend/check {key, on}. Plan ma obie wersje posilkow (dom + miasto); tryb dnia tylko zaweza widok i zakupy.
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
Dostajesz JEDEN dzień weekendu: cel kcal, białko, treningi, węgle na rower, wydarzenia oraz liczbę porcji.
Dla KAŻDEGO posiłku dnia podaj DWIE wersje: "dom" (prosty przepis, max 25 min) i "miasto" (co zamówić na mieście).
Wyjątki: "śniadanie" i "na rower" mają TYLKO wersję "dom" (śniadanie zawsze w domu).
Zwróć WYŁĄCZNIE JSON:
{"day": "sb", "unikaj": "...", "rower": "...",
  "posilki": [{"pora": "obiad",
               "dom": {"nazwa": "...", "kcal": 700, "bialko_g": 45, "czas_min": 20, "skladniki": ["200 g ..."], "kroki": ["..."],
                       "zakupy": [{"produkt": "Pierś z kurczaka", "ilosc": "200 g", "dzial": "mięso i ryby"}]},
               "miasto": {"nazwa": "...", "kcal": 750, "bialko_g": 45, "zamow": "co konkretnie zamówić"}}]}
Zasady:
- Pory: "śniadanie", "obiad", "przekąska", "kolacja"; w dzień z jazdą >= 75 min dodaj "na rower" (pokryj podane węgle).
- Wersje "dom" całego dnia SUMUJĄ się do celu kcal (+-10 %); wersje "miasto" mają podobne kcal jak "dom" tego posiłku. Białko blisko celu.
- Kcal i białko NA JEDNĄ PORCJĘ (szacunek). "skladniki" i "zakupy" z ilościami NA PODANĄ LICZBĘ PORCJI.
- "zakupy" posiłku = co trzeba kupić do TEGO posiłku (bez soli, pieprzu, oleju). "dzial": "warzywa i owoce", "mięso i ryby",
  "nabiał i jajka", "pieczywo", "suche i przyprawy", "na rower" albo "inne". Ten sam produkt nazywaj zawsze tak samo.
- "kroki" 3-6 krótkich. "unikaj": krótko, co rozwala cel. "rower": krótka wskazówka jedzenia na jeździe albo "".
Liczby: cel kcal dnia i węgle na rower są ustalone - nie zmieniaj ich."""


def _conn():
    import qbot_food_plan as FP
    return FP._conn()


def _ai_day(payload: str) -> dict:
    """Jeden dzien planu (Anthropic, ten sam model co dziennik jedzenia). Bez JSON-a jedna prosba o poprawke."""
    import httpx
    import qbot_config as cfg
    from qgpt_client import parse_json_text
    msgs = [{"role": "user", "content": payload}]
    for _ in range(2):
        r = httpx.post("https://api.anthropic.com/v1/messages",
                       headers={"content-type": "application/json", "x-api-key": cfg.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
                       json={"model": cfg.ANTHROPIC_MODEL, "max_tokens": 8000, "temperature": 0, "system": _PROMPT, "messages": msgs},
                       timeout=150)
        r.raise_for_status()
        txt = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        a, b = txt.find("{"), txt.rfind("}")
        try:
            j = parse_json_text(txt[a:b + 1]) if 0 <= a < b else None
        except ValueError:
            j = None
        if isinstance(j, dict):
            return j
        msgs += [{"role": "assistant", "content": txt or "?"}, {"role": "user", "content": "To nie jest kompletny JSON. Odpowiedz WYŁĄCZNIE JSON-em."}]
    raise ValueError("AI: brak JSON")


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
    portions = max(1, min(4, int(portions or 1)))
    modes = {k: (v if v in MODES else "miasto") for k, v in (modes or {}).items() if k in ("sb", "nd")}
    with _conn() as c:
        c.execute(DDL)
        days = _days_input(friday, c, modes)
        res, errs = {}, []

        def _one(d):
            try:
                res[d["day"]] = _ai_day(json.dumps({"porcje": portions, "dzien": d}, ensure_ascii=False))
            except Exception as e:
                errs.append("%s: %s" % (d["day"], type(e).__name__))
        th = [threading.Thread(target=_one, args=(d,)) for d in days]
        [t.start() for t in th]
        [t.join(170) for t in th]
        ai = {"days": [dict(res[d["day"]], day=d["day"]) for d in days if d["day"] in res], "_error": "; ".join(errs) or None}
        by = {x.get("day"): x for x in (ai.get("days") or []) if isinstance(x, dict)}
        pdays = []
        for d in days:
            a = by.get(d["day"]) or {}
            meals = []
            for m in (a.get("posilki") or [])[:7]:
                if not isinstance(m, dict) or not isinstance(m.get("dom"), dict):
                    continue
                mm = {"pora": m.get("pora", ""), "dom": m["dom"]}
                if isinstance(m.get("miasto"), dict) and m.get("pora") not in ("śniadanie", "na rower"):
                    mm["miasto"] = m["miasto"]
                meals.append(mm)
            pdays.append(dict(d, unikaj=a.get("unikaj", ""), rower=a.get("rower", ""), posilki=meals))
        plan = {"version": 2, "modes": {d["day"]: d["tryb"] for d in days}, "days": pdays, "error": ai.get("_error")}
        c.execute("INSERT INTO qbot_v2.food_weekend_plan (friday, portions, plan, checked, built_at) VALUES (%s,%s,%s,'{}',now()) "
                  "ON CONFLICT (friday) DO UPDATE SET portions=EXCLUDED.portions, plan=EXCLUDED.plan, checked='{}', built_at=now()",
                  (friday, portions, json.dumps(plan, ensure_ascii=False)))
    return get(friday, build_if_missing=False)


def get(friday: date, build_if_missing: bool = True) -> dict | None:
    with _conn() as c:
        c.execute(DDL)
        r = c.execute("SELECT friday, portions, plan, checked, built_at FROM qbot_v2.food_weekend_plan WHERE friday=%s", (friday,)).fetchone()
    if r and (r["plan"] or {}).get("version") != 2:
        r = None   # plan w starym formacie -> ulozyc od nowa
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


def view(plan: dict) -> dict:
    """Widok wg trybow dni (to samo liczy strona): posilki wybranej wersji, sumy, lista zakupow z posilkow 'dom'."""
    modes = plan.get("modes") or {}
    days, shop = [], {}
    for d in plan.get("days", []):
        md = modes.get(d["day"], "miasto")
        ms = []
        for m in d.get("posilki", []):
            v = m["miasto"] if (md == "miasto" and m.get("miasto")) else m["dom"]
            ms.append(dict(v, pora=m["pora"], gdzie="miasto" if v is m.get("miasto") else "dom"))
            if v is m["dom"]:
                for z in m["dom"].get("zakupy") or []:
                    k = (z.get("produkt") or "").strip()
                    if k:
                        e = shop.setdefault(k.lower(), {"produkt": k, "dzial": z.get("dzial") or "inne", "ilosci": []})
                        if z.get("ilosc"):
                            e["ilosci"].append(z["ilosc"])
        days.append(dict(d, tryb=md, widok=ms, suma_kcal=round(sum(float(x.get("kcal") or 0) for x in ms)),
                         suma_bialko=round(sum(float(x.get("bialko_g") or 0) for x in ms))))
    return {"days": days, "zakupy": [dict(e, ilosc=" + ".join(e["ilosci"])) for e in shop.values()]}


def set_mode(friday: date, day: str, mode: str) -> dict:
    if day not in ("sb", "nd") or mode not in MODES:
        raise ValueError("zly dzien/tryb")
    with _conn() as c:
        c.execute("UPDATE qbot_v2.food_weekend_plan SET plan = jsonb_set(plan, '{modes,%s}' , to_jsonb(%%s::text)) WHERE friday=%%s" % day,
                  (mode, friday))
    return get(friday, build_if_missing=False)


def summary_text(friday: date) -> str:
    """Krotko dla Alberta (wg aktualnych trybow dni)."""
    p = get(friday)
    if not p:
        return "Brak planu weekendu."
    v = view(p["plan"])
    L = ["Weekend %s (porcje: %d):" % (p["weekend"], p["portions"])]
    for d in v["days"]:
        L.append("%s %s (%s): cel ~%s kcal, plan ~%s kcal%s" % (d["day"], d["date"], "na mieście" if d["tryb"] == "miasto" else "w domu",
                 d["cel_kcal"], d["suma_kcal"], (", na rower ~%d g węgli" % d["wegle_na_rower_g"]) if d.get("wegle_na_rower_g") else ""))
        for m in d["widok"]:
            L.append("  %s (%s): %s ~%s kcal%s" % (m.get("pora"), m.get("gdzie"), m.get("nazwa"), m.get("kcal"),
                     (" — zamów: " + m["zamow"]) if m.get("zamow") else ""))
    if v["zakupy"]:
        L.append("Zakupy: " + ", ".join("%s %s" % (z["produkt"], z["ilosc"]) for z in v["zakupy"]))
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

    @r.post("/mode")
    async def weekend_mode(request: Request):
        """Przelacznik Na miescie / W domu: tylko zapis trybu, bez ukladania od nowa."""
        if not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko odczyt (sesja demo)")
        b = await request.json()
        try:
            return set_mode(_fri(b.get("friday")), str(b.get("day")), str(b.get("mode")))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

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
