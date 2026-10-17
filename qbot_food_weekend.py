#!/usr/bin/env python3
"""Weekend bez diety (15.10.2026, wersja 4 -- przemyslany modul). Dok.: docs/BROKUL.md (sekcja Weekend).

IDEA: AI proponuje, Michal tylko wybiera i koryguje wyjatkami, QBot uczy sie z ocen. Nic nie trzeba przygotowywac z glowy.
1. PROFIL SMAKU -- interaktywna ankieta na stronie (kuchnie, bialko, ryby, gotowce, Thermomix, czas, ostrosc, sniadania,
   na miescie, czego unikac). Zapis: qbot_v2.food_taste_profile (jeden wiersz). AI zawsze bierze go pod uwage.
2. PROPOZYCJE -- po 3 na kazda pore dnia (dom; obiad/przekaska/kolacja tez 3 "na miescie"), ukladane w tle w czwartek
   rano (poranna wiadomosc) i w piatek, gdy brak. Zawsze NA 1 OSOBE; liczba osob tylko przelicza ilosci na stronie (bez AI).
   Zmiana pojedynczego posilku: "inne" (3 nowe propozycje tej pory, ~20 s) albo "moja wersja" (opis -> przepis). Calosc
   od nowa -- tylko na wyrazne zyczenie.
3. Przelacznik dnia Na miescie / W domu -- tylko zaweza (bez AI). Wybor po jednej propozycji, suma kcal vs cel na zywo.
4. ZATWIERDZENIE -> lista zakupow (z wybranych posilkow "dom") + wybrane posilki trafiaja do DNIA (Zdrowie > Dni) jako plan.
5. W DNIU: "Zjadlem" -> wpis do dziennika jedzenia (food_entries/intake, bilans i Trener go widza) + ocena 1-5.
   Oceny (qbot_v2.food_dish_ratings): >= 4 -> "sprawdzone" (AI czasem proponuje je ponownie), <= 2 -> AI unika podobnych.
   2026-10-17: ocena TYLKO posilkow domowych (decyzja Michala; Brokul i "na miescie" bez oceny) = gwiazdki + tagi "co poprawic"
   (np. za slone, za malo sosu, powtorz koniecznie) + komentarz -> kolumny tags/comment; _ctx przekazuje je AI jako "uwagi_do_dan",
   a AI poprawia przepis przy kolejnych planach. "Zjadlem" wskazujace na usuniety wpis = niezjedzone (nowy wpis przy kliknieciu).
Cel kcal dnia, bialko i paliwo na rower: qbot_food_plan.day_plan (USTALONE). Kcal/makro posilkow: szacunek AI na porcje.
Zapis planu: qbot_v2.food_weekend_plan (klucz = piatek): plan.modes, plan.choice {"sb|obiad|dom": idx}, plan.confirmed_at,
plan.eaten {"sb|obiad": entry_id}; checked = produkty "do kupienia".
API (prefiks /api/jedzenie/weekend): GET, /build, /mode, /choice, /regen {day,pora,kind}, /custom {day,pora,text}, /confirm,
/check {key,on}, /profile (GET/POST), /eat {day,pora}, /rate {day,pora,stars,tags,comment}. Dzien: day_meals(day) -> qbot_food_api.day_card.
Albert: food_weekend_plan (summary_text). Telegram: piatkowa linijka z linkiem (qbot_food_plan.weekend_lines).
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
CITY_PORY = ("obiad", "przekąska", "kolacja")
DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.food_weekend_plan (
    friday date PRIMARY KEY, portions integer NOT NULL DEFAULT 1, plan jsonb NOT NULL,
    checked jsonb NOT NULL DEFAULT '{}'::jsonb, built_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS qbot_v2.food_taste_profile (id integer PRIMARY KEY DEFAULT 1, answers jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS qbot_v2.food_dish_ratings (name text PRIMARY KEY, stars integer NOT NULL, dish jsonb,
    day date, rated_at timestamptz NOT NULL DEFAULT now())"""

# ANKIETA GUSTOW (2026-10-15, wersja 2 -- decyzja Michala: ma BADAC preferencje, nie wbijac sztywno skladnikow).
# Typy: "pairs" (to czy to: A / B / obojetne), "likert" (lubie / obojetne / nie lubie dla kazdej pozycji), "single", tekst "inne".
# AI dostaje odpowiedzi jako SYGNALY gustu (co lubi bardziej / czego nie lubi), nie jako liste obowiazkowych skladnikow.
SURVEY = [
    ("pary_obiad", "Który obiad wybierasz?", "pairs", [["Pad thai z krewetkami", "Schabowy z ziemniakami"],
        ["Łosoś z ryżem i warzywami", "Spaghetti bolognese"], ["Curry z kurczakiem", "Gulasz wołowy z kaszą"],
        ["Poke bowl", "Burger"], ["Sushi", "Pierogi"], ["Stir-fry z wołowiną", "Kotlet mielony z puree"],
        ["Dorsz pieczony z warzywami", "Pizza"], ["Zupa (np. ramen, tom yum)", "Danie z patelni / pieczone"]]),
    ("pary_sniadanie", "Które śniadanie?", "pairs", [["Jajecznica / omlet", "Owsianka"], ["Kanapki", "Skyr / jogurt z dodatkami"],
        ["Na słono", "Na słodko"]]),
    ("pary_kolacja", "Kolacja i przekąska — co bliżej Tobie?", "pairs", [["Serek wiejski z warzywami", "Kanapki z wędliną"],
        ["Skyr z owocami", "Jajka na twardo"], ["Wrap z kurczakiem", "Sałatka z tuńczykiem"], ["Ciepła kolacja", "Zimna kolacja"]]),
    ("smaki", "Smaki", "likert", ["słony / umami (sos sojowy)", "słodko-kwaśny", "ostry", "kremowe sosy", "świeży: cytryna, zioła",
                                  "wędzony", "pomidorowy", "czosnkowy"]),
    ("bazy", "Dodatki do obiadu", "likert", ["ryż", "makaron pszenny", "makaron ryżowy", "makaron konjac", "kasze", "ziemniaki",
                                             "pieczywo", "same warzywa"]),
    ("bialka", "Białko", "likert", ["kurczak", "indyk", "wołowina", "wieprzowina", "łosoś / tłuste ryby", "białe ryby (dorsz, mintaj)",
                                    "tuńczyk", "krewetki", "jajka", "nabiał (serek wiejski, twaróg, skyr)", "tofu"]),
    ("roznorodnosc", "Jedzenie w weekend", "single", ["lubię sprawdzone, powtarzalne", "trochę nowości", "dużo nowości"]),
    ("obiad_czas", "Ile czasu możesz dać obiadowi?", "single", ["do 20 min", "do 40 min", "do godziny"]),
    ("thermomix", "Thermomix przy obiedzie", "single", ["chętnie", "czasem", "nie"]),
    ("ostrosc", "Ostrość", "single", ["łagodnie", "średnio", "ostro"]),
]
DEFAULT_PROFILE = {"smaki": {"słony / umami (sos sojowy)": "lubię"},
                   "bialka": {"łosoś / tłuste ryby": "lubię", "białe ryby (dorsz, mintaj)": "lubię", "krewetki": "lubię"},
                   "bazy": {"makaron konjac": "lubię"}, "thermomix": "chętnie",
                   "inne": "lubię kuchnię azjatycką i ryby; makaron konjac kupuję gotowy (najchętniej po chińsku w sosie sojowym)"}

_COMMON = """Jesteś dietetykiem sportowym. Użytkownik: mężczyzna ~104 kg, redukcja ~0,5 kg/tydz., kolarz gravel; w weekend NIE ma cateringu.
Ma Thermomix, ale mało czasu. ZŁOŻONOŚĆ WG PORY (obowiązkowo):
- "przekąska" i "kolacja": TURBO PROSTE, 0-5 min, bez gotowania, tylko złożenie gotowych produktów (np. serek wiejski proteinowy
  z warzywami, kanapki, skyr z owocami, wrap z gotowym kurczakiem, sałatka z tuńczykiem z puszki, jajka na twardo, hummus).
- "śniadanie": proste, max ~10 min (jajecznica, owsianka, kanapki, skyr z dodatkami).
- "obiad": może być bardziej złożony (czas wg profilu), tu Thermomix (Varoma, sos, ryż w koszyczku), gdy pomaga.
- "na rower": gotowe produkty do kieszeni.
PROFIL SMAKU to SYGNAŁY gustu z ankiety (pary "to czy to", skale lubię / obojętne / nie lubię, pole "inne") -- nie lista obowiązkowych
składników. Idź w to, co lubi, omijaj "nie lubię", ale dbaj o RÓŻNORODNOŚĆ: ten sam główny składnik (np. makaron konjac, łosoś)
najwyżej raz w danej porze i najwyżej 2 razy na dzień; 3 propozycje jednej pory wyraźnie różne.
Dostajesz też SPRAWDZONE dania (oceny 4-5: możesz zaproponować jedno, nie wszystkie) i NIELUBIANE (oceny 1-2: unikaj podobnych).
Dostajesz też UWAGI_DO_DAN po zjedzeniu (ocena, tagi typu „za słone”, „za mało sosu”, komentarz): gdy proponujesz to samo lub podobne
danie, POPRAW przepis zgodnie z uwagami (np. więcej sosu, mniej soli, większa porcja, krócej); „powtórz koniecznie” = wolno je zaproponować ponownie.
Wszystko NA JEDNĄ OSOBĘ; kcal i makro na porcję (szacunek). Cel kcal dnia i węgle na rower są ustalone - nie zmieniaj ich."""

_OPT_DOM = ('{"nazwa": "...", "kcal": 650, "bialko_g": 45, "wegle_g": 60, "tluszcz_g": 18, "czas_min": 15, "thermomix": true, '
            '"skladniki": ["200 g ..."], "kroki": ["..."], "zakupy": [{"produkt": "Pierś z kurczaka", "ilosc": "200 g", "dzial": "mięso i ryby"}]}')
_RULES_DOM = """- "kroki": 1-5 krótkich (przekąska/kolacja zwykle 1-2); gdy Thermomix pomaga przy obiedzie, kroki pod Thermomix i "thermomix": true.
- "zakupy" = co kupić do tej propozycji (bez soli, pieprzu, oleju); ten sam produkt nazywaj zawsze tak samo; ilości na 1 osobę.
- "dzial": "warzywa i owoce", "mięso i ryby", "nabiał i jajka", "pieczywo", "suche i przyprawy", "na rower" albo "inne"."""

_PROMPT_DOM = _COMMON + """
Podaj po 3 RÓŻNE propozycje DOMOWE dla KAŻDEJ pory z listy "pory" (tylko tych). Każda propozycja ma kcal blisko celu
tej pory z "cel_kcal_por" (+-10 %); "na rower" pokrywa podane węgle (proste, do kieszeni).
Zwróć WYŁĄCZNIE JSON: {"unikaj": "krótko, co rozwala cel", "slots": [{"pora": "obiad", "opcje": [""" + _OPT_DOM + """]}]}
""" + _RULES_DOM

_PROMPT_CITY = _COMMON + """
Podaj po 3 RÓŻNE propozycje DO ZAMÓWIENIA NA MIEŚCIE dla pór: "obiad", "przekąska", "kolacja" (wg profilu "na mieście",
dużo białka, rozsądna porcja; kcal blisko celu tej pory z "cel_kcal_por").
Zwróć WYŁĄCZNIE JSON: {"slots": [{"pora": "obiad", "opcje": [{"nazwa": "...", "kcal": 700, "bialko_g": 45, "wegle_g": 70,
"tluszcz_g": 25, "zamow": "co konkretnie zamówić i jak"}]}]}"""

_PROMPT_SLOT = _COMMON + """
Podaj 3 NOWE, RÓŻNE propozycje dla JEDNEJ pory (inne niż podane "dotychczasowe"). Rodzaj: "dom" (przepis) albo "miasto" (co zamówić).
Kcal blisko podanego celu posiłku. Zwróć WYŁĄCZNIE JSON: {"opcje": [...]} -- format opcji "dom": """ + _OPT_DOM + """;
format "miasto": {"nazwa", "kcal", "bialko_g", "wegle_g", "tluszcz_g", "zamow"}.
""" + _RULES_DOM

_PROMPT_CUSTOM = _COMMON + """
Użytkownik opisał SWOJĄ wersję posiłku. Ułóż z tego JEDEN prosty przepis domowy, trzymając się opisu (jeśli podał kilka wariantów,
np. "kurczak/krewetki/wołowina", wybierz jeden i wymień pozostałe w "uwagi"). Kcal blisko celu posiłku.
Zwróć WYŁĄCZNIE JSON: """ + _OPT_DOM[:-1] + """, "uwagi": "..."}
""" + _RULES_DOM


def _conn():
    import qbot_food_plan as FP
    return FP._conn()


def _ai(system: str, payload: dict) -> dict:
    """Anthropic (ten sam model co dziennik jedzenia), max_tokens 8000. Bez JSON-a jedna prosba o poprawke."""
    import httpx
    import qbot_config as cfg
    from qgpt_client import parse_json_text
    msgs = [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    for _ in range(2):
        r = httpx.post("https://api.anthropic.com/v1/messages",
                       headers={"content-type": "application/json", "x-api-key": cfg.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
                       json={"model": cfg.ANTHROPIC_MODEL, "max_tokens": 8000, "temperature": 0.4, "system": system, "messages": msgs},
                       timeout=170)
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


# ------------------------------------------------------------------ profil smaku i oceny
def profile() -> dict:
    with _conn() as c:
        c.execute(DDL)
        r = c.execute("SELECT answers, updated_at FROM qbot_v2.food_taste_profile WHERE id=1").fetchone()
    return {"answers": (r["answers"] if r else DEFAULT_PROFILE), "saved": bool(r),
            "updated_at": r["updated_at"].astimezone(TZ).strftime("%d.%m %H:%M") if r else None,
            "survey": [{"key": k, "q": q, "type": t, "options": o} for k, q, t, o in SURVEY]}


def save_profile(answers: dict) -> dict:
    keys = {k for k, *_ in SURVEY} | {"inne"}
    a = {k: v for k, v in (answers or {}).items() if k in keys}
    with _conn() as c:
        c.execute(DDL)
        c.execute("INSERT INTO qbot_v2.food_taste_profile (id, answers) VALUES (1, %s) ON CONFLICT (id) "
                  "DO UPDATE SET answers=EXCLUDED.answers, updated_at=now()", (json.dumps(a, ensure_ascii=False),))
    return profile()


_COLS_OK = False


def _ensure_cols(c) -> None:
    """2026-10-17: kolumny uwag do ocen (tags jsonb, comment text) - raz na proces (ALTER bierze blokade, wiec nie przy kazdym zapytaniu)."""
    global _COLS_OK
    if _COLS_OK:
        return
    c.execute(DDL)
    have = {r["column_name"] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='qbot_v2' "
                                                  "AND table_name='food_dish_ratings'").fetchall()}
    if not {"tags", "comment"} <= have:
        c.execute("ALTER TABLE qbot_v2.food_dish_ratings ADD COLUMN IF NOT EXISTS tags jsonb, ADD COLUMN IF NOT EXISTS comment text")
        c.commit()
    _COLS_OK = True


def _ctx() -> dict:
    """Profil + sprawdzone + nielubiane + uwagi do zjedzonych dan -- do kazdego zapytania AI."""
    with _conn() as c:
        _ensure_cols(c)
        good = [r["name"] for r in c.execute("SELECT name FROM qbot_v2.food_dish_ratings WHERE stars>=4 ORDER BY rated_at DESC LIMIT 15").fetchall()]
        bad = [r["name"] for r in c.execute("SELECT name FROM qbot_v2.food_dish_ratings WHERE stars<=2 ORDER BY rated_at DESC LIMIT 15").fetchall()]
        notes = [{"danie": r["name"], "ocena": r["stars"], "uwagi": [t for t in (r["tags"] or []) if t], "komentarz": r["comment"] or None}
                 for r in c.execute("SELECT name, stars, tags, comment FROM qbot_v2.food_dish_ratings WHERE (tags IS NOT NULL AND tags <> '[]'::jsonb) "
                                    "OR coalesce(comment, '') <> '' ORDER BY rated_at DESC LIMIT 20").fetchall()]
    return {"profil_smaku": profile()["answers"], "sprawdzone": good, "nielubiane": bad, "uwagi_do_dan": notes}


# ------------------------------------------------------------------ plan
def _days_input(friday: date, c) -> list[dict]:
    import qbot_food_plan as FP
    out = []
    for d in (friday + timedelta(days=1), friday + timedelta(days=2)):
        p = FP.day_plan(d, c)
        out.append({"day": DN[d.weekday()], "date": d.strftime("%d.%m"), "iso": d.isoformat(), "cel_kcal": p["target"],
                    "bialko_g": FP.PROTEIN_G, "wegle_na_rower_g": p["fuel_g"],
                    "treningi": ["%s %s %d min" % (s["sport"], s["name"], s["dur_min"] or 0) for s in p["sessions"]]})
    return out


SHARE = {"śniadanie": 0.25, "obiad": 0.35, "przekąska": 0.12, "kolacja": 0.28}


def _por_kcal(d: dict) -> dict:
    """Cel kcal kazdej pory liczony przez QBota (nie AI): rower = paliwo (wegle x 4), reszta wg udzialow."""
    out = {}
    rest = float(d["cel_kcal"] or 0)
    if d.get("wegle_na_rower_g"):
        out["na rower"] = round(d["wegle_na_rower_g"] * 4)
        rest -= out["na rower"]
    for k, v in SHARE.items():
        out[k] = int(round(rest * v / 10.0) * 10)
    return out


def _clean(opts) -> list[dict]:
    return [o for o in (opts or []) if isinstance(o, dict) and o.get("nazwa")][:3]


def build(friday: date, modes: dict | None = None) -> dict:
    ctx = _ctx()
    old = get(friday, build_if_missing=False)
    modes = modes or ((old or {}).get("plan") or {}).get("modes") or {}
    with _conn() as c:
        c.execute(DDL)
        days = _days_input(friday, c)
    res, errs = {}, []

    def _call(key, system, d):
        try:
            res[key] = _ai(system, dict(ctx, dzien=d))
        except Exception as e:
            errs.append("%s: %s" % (key, type(e).__name__))
    th = []
    for d in days:
        d["cel_kcal_por"] = _por_kcal(d)
        groups = [["śniadanie", "obiad"], ["przekąska", "kolacja"] + (["na rower"] if d.get("wegle_na_rower_g") else [])]
        for gi, g in enumerate(groups):
            th.append(threading.Thread(target=_call, args=("%s|dom%d" % (d["day"], gi), _PROMPT_DOM, dict(d, pory=g))))
        th.append(threading.Thread(target=_call, args=(d["day"] + "|miasto", _PROMPT_CITY, d)))
    [t.start() for t in th]
    [t.join(200) for t in th]
    order = ["śniadanie", "na rower", "obiad", "przekąska", "kolacja"]
    pdays = []
    for d in days:
        d2 = {k: v for k, v in d.items() if k != "pory"}
        dom = {"unikaj": (res.get(d["day"] + "|dom0") or {}).get("unikaj") or (res.get(d["day"] + "|dom1") or {}).get("unikaj", ""),
               "slots": sorted([s for gi in (0, 1) for s in (res.get("%s|dom%d" % (d["day"], gi)) or {}).get("slots") or [] if isinstance(s, dict)],
                               key=lambda s: order.index(s.get("pora")) if s.get("pora") in order else 9)}
        city = {s.get("pora"): s.get("opcje") for s in (res.get(d["day"] + "|miasto") or {}).get("slots") or [] if isinstance(s, dict)}
        slots = []
        for s in dom.get("slots") or []:
            if not isinstance(s, dict) or not _clean(s.get("opcje")):
                continue
            slot = {"pora": s.get("pora", ""), "dom": _clean(s["opcje"])}
            if slot["pora"] in CITY_PORY and _clean(city.get(slot["pora"])):
                slot["miasto"] = _clean(city[slot["pora"]])
            slots.append(slot)
        pdays.append(dict(d2, unikaj=dom.get("unikaj", ""), slots=slots))
    plan = {"version": 4, "modes": {d["day"]: modes.get(d["day"], "dom") for d in days}, "choice": {}, "confirmed_at": None,
            "eaten": {}, "days": pdays, "error": "; ".join(errs) or None}
    with _conn() as c:
        c.execute("INSERT INTO qbot_v2.food_weekend_plan (friday, portions, plan, checked, built_at) VALUES (%s,1,%s,'{}',now()) "
                  "ON CONFLICT (friday) DO UPDATE SET plan=EXCLUDED.plan, checked='{}', built_at=now()",
                  (friday, json.dumps(plan, ensure_ascii=False)))
    return get(friday, build_if_missing=False)


def get(friday: date, build_if_missing: bool = True) -> dict | None:
    with _conn() as c:
        c.execute(DDL)
        r = c.execute("SELECT friday, portions, plan, checked, built_at FROM qbot_v2.food_weekend_plan WHERE friday=%s", (friday,)).fetchone()
    if r and (r["plan"] or {}).get("version") != 4:
        r = None if build_if_missing else r
    if not r:
        return build(friday) if build_if_missing else None
    return {"friday": r["friday"].isoformat(), "weekend": "%s–%s" % ((friday + timedelta(days=1)).strftime("%d.%m"),
                                                                    (friday + timedelta(days=2)).strftime("%d.%m")),
            "portions": r["portions"], "plan": r["plan"], "checked": r["checked"] or {},
            "built_at": r["built_at"].astimezone(TZ).strftime("%d.%m %H:%M")}


def _upd(friday: date, fn) -> dict:
    """Zmiana planu w bazie bez AI (tryb, wybor, zatwierdzenie, liczba osob, zjedzone)."""
    with _conn() as c:
        r = c.execute("SELECT plan FROM qbot_v2.food_weekend_plan WHERE friday=%s FOR UPDATE", (friday,)).fetchone()
        if not r:
            raise ValueError("brak planu")
        plan = r["plan"]
        fn(plan, c)
        c.execute("UPDATE qbot_v2.food_weekend_plan SET plan=%s WHERE friday=%s", (json.dumps(plan, ensure_ascii=False), friday))
    return get(friday, build_if_missing=False)


def _slot(plan, day, pora):
    d = next((x for x in plan["days"] if x["day"] == day), None)
    s = next((x for x in (d or {}).get("slots", []) if x["pora"] == pora), None)
    if not s:
        raise ValueError("brak takiego posilku")
    return d, s


def set_mode(friday, day, mode):
    if day not in ("sb", "nd") or mode not in MODES:
        raise ValueError("zly dzien/tryb")
    return _upd(friday, lambda p, c: (p.setdefault("modes", {}).__setitem__(day, mode), p.__setitem__("confirmed_at", None)))


def set_choice(friday, day, pora, kind, idx):
    if kind not in MODES or not (0 <= int(idx) <= 3):
        raise ValueError("zly wybor")
    def f(p, c):
        p.setdefault("choice", {})["%s|%s|%s" % (day, pora, kind)] = int(idx)
        p["confirmed_at"] = None
    return _upd(friday, f)


def set_portions(friday, n):
    n = max(1, min(4, int(n or 1)))
    with _conn() as c:
        c.execute("UPDATE qbot_v2.food_weekend_plan SET portions=%s WHERE friday=%s", (n, friday))
    return get(friday, build_if_missing=False)


def confirm(friday):
    return _upd(friday, lambda p, c: p.__setitem__("confirmed_at", datetime.now(TZ).strftime("%d.%m %H:%M")))


def regen_slot(friday, day, pora, kind):
    """'Inne': 3 nowe propozycje JEDNEJ pory (AI ~20 s); wlasna wersja zostaje."""
    p = get(friday, build_if_missing=False)
    if not p:
        raise ValueError("brak planu")
    d, s = _slot(p["plan"], day, pora)
    cur = [o for o in s.get(kind) or [] if not o.get("wlasna")]
    target = round(sum(float(o.get("kcal") or 0) for o in cur) / max(1, len(cur))) if cur else None
    new = _clean(_ai(_PROMPT_SLOT, dict(_ctx(), dzien={k: d[k] for k in ("day", "cel_kcal", "bialko_g", "wegle_na_rower_g", "treningi")},
                                        pora=pora, rodzaj=kind, cel_kcal_posilku=target,
                                        dotychczasowe=[o.get("nazwa") for o in cur])).get("opcje"))
    if not new:
        raise ValueError("AI nie zaproponowało nic nowego")

    def f(plan, c):
        _, ss = _slot(plan, day, pora)
        ss[kind] = new + [o for o in ss.get(kind) or [] if o.get("wlasna")]
        plan.setdefault("choice", {})["%s|%s|%s" % (day, pora, kind)] = 0
        plan["confirmed_at"] = None
    return _upd(friday, f)


def custom_meal(friday, day, pora, text):
    """'Moja wersja': opis uzytkownika -> przepis (AI ~20 s), dodany jako propozycja 'dom' i od razu wybrany."""
    text = " ".join(str(text or "").split())[:300]
    if not text:
        raise ValueError("pusty opis")
    p = get(friday, build_if_missing=False)
    if not p:
        raise ValueError("brak planu")
    d, s = _slot(p["plan"], day, pora)
    base = [o for o in s["dom"] if not o.get("wlasna")]
    target = round(sum(float(o.get("kcal") or 0) for o in base) / max(1, len(base)))
    o = _ai(_PROMPT_CUSTOM, dict(_ctx(), pora=pora, cel_kcal_posilku=target, opis_uzytkownika=text))
    o = dict(o, wlasna=True, opis=text)

    def f(plan, c):
        _, ss = _slot(plan, day, pora)
        ss["dom"] = [x for x in ss["dom"] if not x.get("wlasna")] + [o]
        plan.setdefault("choice", {})["%s|%s|dom" % (day, pora)] = len(ss["dom"]) - 1
        plan.setdefault("modes", {})[day] = plan["modes"].get(day, "dom")
        plan["confirmed_at"] = None
    return _upd(friday, f)


def view(plan: dict) -> dict:
    """Wybrane posilki wg trybow i wyborow (to samo liczy strona) + lista zakupow z wybranych posilkow 'dom' (na 1 osobe)."""
    modes, ch = plan.get("modes") or {}, plan.get("choice") or {}
    days, shop = [], {}
    for d in plan.get("days", []):
        md = modes.get(d["day"], "dom")
        ms = []
        for s in d.get("slots", []):
            kind = "miasto" if (md == "miasto" and s.get("miasto")) else "dom"
            opts = s.get(kind) or []
            if not opts:
                continue
            i = min(int(ch.get("%s|%s|%s" % (d["day"], s["pora"], kind), 0)), len(opts) - 1)
            o = opts[i]
            ms.append(dict(o, pora=s["pora"], gdzie=kind, idx=i))
            if kind == "dom":
                for z in o.get("zakupy") or []:
                    k = (z.get("produkt") or "").strip()
                    if k:
                        e = shop.setdefault(k.lower(), {"produkt": k, "dzial": z.get("dzial") or "inne", "ilosci": []})
                        if z.get("ilosc"):
                            e["ilosci"].append(z["ilosc"])
        days.append(dict(d, tryb=md, widok=ms, suma_kcal=round(sum(float(x.get("kcal") or 0) for x in ms)),
                         suma_bialko=round(sum(float(x.get("bialko_g") or 0) for x in ms))))
    return {"days": days, "zakupy": [dict(e, ilosc=" + ".join(e["ilosci"])) for e in shop.values()]}


# ------------------------------------------------------------------ DZIEN: plan, zjadlem, ocena
def day_meals(day: date) -> list[dict] | None:
    """Zatwierdzone posilki weekendu dla dnia (karta Dnia). None = dzien nie jest w zatwierdzonym planie."""
    if day.weekday() not in (5, 6):
        return None
    p = get(friday_for(day), build_if_missing=False)
    if not p or not p["plan"].get("confirmed_at") or p["plan"].get("version") != 4:
        return None
    dn = DN[day.weekday()]
    v = next((x for x in view(p["plan"])["days"] if x["day"] == dn), None)
    if not v:
        return None
    eaten = p["plan"].get("eaten") or {}
    with _conn() as c:
        _ensure_cols(c)
        rt = {r["name"]: r for r in c.execute("SELECT name, stars, tags, comment FROM qbot_v2.food_dish_ratings").fetchall()}
        ids = [int(x) for x in eaten.values() if x]
        alive = {r["id"] for r in c.execute("SELECT id FROM qbot_v2.food_entries WHERE id = ANY(%s) AND status <> 'deleted'", (ids,)).fetchall()} if ids else set()
    out = []
    for m in v["widok"]:
        r = rt.get(m.get("nazwa")) or {}
        out.append({"pora": m["pora"], "gdzie": m["gdzie"], "nazwa": m.get("nazwa"), "kcal": m.get("kcal"), "bialko_g": m.get("bialko_g"),
                    "zamow": m.get("zamow"), "eaten": eaten.get("%s|%s" % (dn, m["pora"])) in alive,   # 17.10: tylko zywy wpis = zjedzone
                    "stars": r.get("stars"), "tags": r.get("tags") or [], "comment": r.get("comment") or ""})
    return out


def eat(day: date, pora: str, undo: bool = False) -> dict:
    """'Zjadlem' -> wpis do dziennika jedzenia (food_entries + intake), jak szybkie przyciski. undo -> usuniecie wpisu."""
    import qbot_food_log as F
    fr, dn = friday_for(day), DN[day.weekday()]
    p = get(fr, build_if_missing=False)
    if not p:
        raise ValueError("brak planu")
    key = "%s|%s" % (dn, pora)
    eid = (p["plan"].get("eaten") or {}).get(key)
    if eid and not undo:   # 17.10: znacznik wskazuje na usuniety wpis (np. "Usun" w Dzienniku) -> traktuj jak niezjedzone, utworz nowy wpis
        with F._conn() as c:
            r = c.execute("SELECT status FROM qbot_v2.food_entries WHERE id=%s", (eid,)).fetchone()
        if not r or r["status"] == "deleted":
            eid = None
    if undo:
        if eid:
            from qbot_brokul_meals import remove_intake
            with F._conn() as c:
                r = c.execute("SELECT intake_log_id FROM qbot_v2.food_entries WHERE id=%s", (eid,)).fetchone()
                remove_intake(c, r["intake_log_id"] if r else None)
                c.execute("UPDATE qbot_v2.food_entries SET status='deleted', intake_log_id=NULL, updated_at=now() WHERE id=%s", (eid,))
                c.commit()
        _upd(fr, lambda pl, c: pl.setdefault("eaten", {}).pop(key, None))
    elif not eid:
        m = next((x for x in view(p["plan"])["days"] if x["day"] == dn), {"widok": []})
        m = next((x for x in m["widok"] if x["pora"] == pora), None)
        if not m:
            raise ValueError("brak posilku")
        items = [{"name": m.get("nazwa"), "portion": "1 porcja (plan weekendu)", "kcal": m.get("kcal") or 0,
                  "protein_g": m.get("bialko_g") or 0, "carbs_g": m.get("wegle_g") or 0, "fat_g": m.get("tluszcz_g") or 0}]
        new = F.create_entry("quick", day, raw_text="🏠 " + str(m.get("nazwa")), items=items)
        with F._conn() as c:
            e = F._get(c, new)
            F._write_intake(c, e)
            c.commit()
        _upd(fr, lambda pl, c: pl.setdefault("eaten", {}).__setitem__(key, new))
    try:
        F.refresh_day(day)
    except Exception:
        pass
    return {"ok": True}


def rate(day: date, pora: str, stars: int, tags=None, comment=None) -> dict:
    """Ocena posilku DOMOWEGO: gwiazdki 1-5 + tagi "co poprawic" + komentarz (2026-10-17). Posilki "na miescie" bez oceny."""
    stars = max(1, min(5, int(stars)))
    tags = [str(t).strip()[:40] for t in (tags or []) if str(t).strip()][:12]
    comment = str(comment or "").strip()[:500]
    p = get(friday_for(day), build_if_missing=False)
    dn = DN[day.weekday()]
    v = next((x for x in view(p["plan"])["days"] if x["day"] == dn), {"widok": []})
    m = next((x for x in v["widok"] if x["pora"] == pora), None)
    if not m or not m.get("nazwa"):
        raise ValueError("brak posilku")
    if m.get("gdzie") != "dom":
        raise ValueError("ocena tylko dla posiłków przygotowanych samodzielnie")
    with _conn() as c:
        _ensure_cols(c)
        c.execute("INSERT INTO qbot_v2.food_dish_ratings (name, stars, dish, day, tags, comment) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (name) "
                  "DO UPDATE SET stars=EXCLUDED.stars, dish=EXCLUDED.dish, day=EXCLUDED.day, tags=EXCLUDED.tags, comment=EXCLUDED.comment, rated_at=now()",
                  (m["nazwa"], stars, json.dumps(m, ensure_ascii=False), day, json.dumps(tags, ensure_ascii=False), comment or None))
    return {"ok": True, "stars": stars, "tags": tags, "comment": comment}


def prebuild_async(friday: date) -> None:
    """Czwartek/piatek rano (poranna wiadomosc): uloz propozycje w tle, zeby strona otwierala sie od razu."""
    def _go():
        try:
            get(friday, build_if_missing=True)
        except Exception as e:
            print("weekend prebuild blad:", type(e).__name__)
    threading.Thread(target=_go, daemon=True).start()


def summary_text(friday: date) -> str:
    """Krotko dla Alberta (wybrane posilki wg trybow dni)."""
    p = get(friday)
    if not p:
        return "Brak planu weekendu."
    v = view(p["plan"])
    st = "zatwierdzony %s" % p["plan"]["confirmed_at"] if p["plan"].get("confirmed_at") else "propozycje do wyboru (niezatwierdzone)"
    L = ["Weekend %s (%s, osób: %d):" % (p["weekend"], st, p["portions"])]
    for d in v["days"]:
        L.append("%s %s (%s): cel ~%s kcal, wybrane ~%s kcal" % (d["day"], d["date"], "na mieście" if d["tryb"] == "miasto" else "w domu",
                 d["cel_kcal"], d["suma_kcal"]))
        for m in d["widok"]:
            L.append("  %s (%s): %s ~%s kcal" % (m.get("pora"), m.get("gdzie"), m.get("nazwa"), m.get("kcal")))
    if v["zakupy"]:
        L.append("Zakupy (na 1 osobę, z wybranych): " + ", ".join("%s %s" % (z["produkt"], z["ilosc"]) for z in v["zakupy"]))
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

    def _owner(request):
        if not owner_user(request):
            raise HTTPException(status_code=403, detail="tylko odczyt (sesja demo)")

    async def _do(request, fn):
        _owner(request)
        b = await request.json()
        try:
            return fn(b)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    def _day(b):
        return date.fromisoformat(str(b.get("date"))[:10])

    @r.get("")
    def weekend_get(request: Request, friday: str | None = None):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        fr = _fri(friday)
        p = get(fr, build_if_missing=bool(owner_user(request)))   # demo nie odpala AI
        return p or {"friday": fr.isoformat(), "plan": None}

    @r.post("/build")
    async def weekend_build(request: Request):
        return await _do(request, lambda b: build(_fri(b.get("friday"))))

    @r.post("/mode")
    async def weekend_mode(request: Request):
        return await _do(request, lambda b: set_mode(_fri(b.get("friday")), str(b.get("day")), str(b.get("mode"))))

    @r.post("/choice")
    async def weekend_choice(request: Request):
        return await _do(request, lambda b: set_choice(_fri(b.get("friday")), str(b.get("day")), str(b.get("pora")), str(b.get("kind")), int(b.get("idx") or 0)))

    @r.post("/portions")
    async def weekend_portions(request: Request):
        return await _do(request, lambda b: set_portions(_fri(b.get("friday")), b.get("n")))

    @r.post("/regen")
    async def weekend_regen(request: Request):
        return await _do(request, lambda b: regen_slot(_fri(b.get("friday")), str(b.get("day")), str(b.get("pora")), str(b.get("kind") or "dom")))

    @r.post("/custom")
    async def weekend_custom(request: Request):
        return await _do(request, lambda b: custom_meal(_fri(b.get("friday")), str(b.get("day")), str(b.get("pora")), b.get("text")))

    @r.post("/confirm")
    async def weekend_confirm(request: Request):
        return await _do(request, lambda b: confirm(_fri(b.get("friday"))))

    @r.post("/check")
    async def weekend_check(request: Request):
        _owner(request)
        b = await request.json()
        fr, key, on = _fri(b.get("friday")), str(b.get("key") or "")[:120], bool(b.get("on"))
        with _conn() as c:
            c.execute("UPDATE qbot_v2.food_weekend_plan SET checked = CASE WHEN %s THEN checked || jsonb_build_object(%s, true) "
                      "ELSE checked - %s END WHERE friday=%s", (on, key, key, fr))
        return {"ok": True}

    @r.get("/profile")
    def weekend_profile(request: Request):
        if not current_user(request):
            raise HTTPException(status_code=401, detail="unauthorized")
        return profile()

    @r.post("/profile")
    async def weekend_profile_save(request: Request):
        return await _do(request, lambda b: save_profile(b.get("answers") or {}))

    @r.post("/eat")
    async def weekend_eat(request: Request):
        return await _do(request, lambda b: eat(_day(b), str(b.get("pora")), bool(b.get("undo"))))

    @r.post("/rate")
    async def weekend_rate(request: Request):
        return await _do(request, lambda b: rate(_day(b), str(b.get("pora")), int(b.get("stars") or 0), b.get("tags"), b.get("comment")))

    return r
