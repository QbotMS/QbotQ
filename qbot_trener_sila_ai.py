"""TRENER - planer silowni AI (2026-10-23, decyzja Michala; makieta /trening-sila-makieta.html zaakceptowana).

Co robi:
- USTAWIENIA uzytkownika (qbot_v2.trainer_sila_prefs, sql/trainer_v14.sql): moj sprzet (lista do edycji, wl/wyl),
  akcenty (np. biceps), wskazowki dla AI (twarde zasady, np. maly pokoj = tylko cwiczenia w miejscu).
- FILTR puli cwiczen (apply_filter, wolane z qbot_trener_sila.load_pool): cwiczenie znika z wyboru (tier X + powod),
  gdy wymaga wylaczonego sprzetu, gdy wskazowki je wykluczaja (skutek wskazowek liczy AI raz, cache w prefs.derived)
  albo gdy nie ma kodu Garmina (trening idzie na zegarek).
- WARIANT dnia (trainer_session.opts.sila_variant): ai (domyslnie) | gora | dol | cale | krotko. 'ai' = regula:
  jazda >= 2 h dzien przed albo dzien po -> gora ciala (bez ciezkich nog), inaczej cale cialo.
- WYBOR CWICZEN PRZEZ AI (ai_choose): model dostaje tydzien jazd (-3..+3 dni), bilans partii z 4 tygodni
  (biceps i triceps osobno), akcenty, wskazowki, sprzet, poprzedni trening i liste dozwolonych cwiczen; zwraca klucze
  + krotkie uzasadnienie. Wynik jest SPRAWDZANY (tylko dozwolone, jedno z rodziny, maks. 2 klasy ciezaru, akcent
  obecny, liczba ~ jak w ukladzie bazowym); blad / zly wynik -> uklad bazowy (choose) + wymuszony akcent.
Czesci czyste: allowed, variant_rule, validate_selection, ensure_accent (tests/test_trener_sila_ai.py).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, timedelta

KINDS = {"hantle": "hantle", "lawka": "ławka", "mata": "mata", "guma_mocna": "guma — mocny opór",
         "guma_lekka": "guma — lekki opór", "mini": "mini band", "sztanga": "sztanga / gryf", "talerz": "talerze",
         "kettlebell": "kettlebell", "drazek": "drążek", "inne": "inne"}
DEFAULT_EQUIPMENT = [
    {"id": "h1", "n": "Hantle — zestaw 1", "s": "regulowane, do 12 kg", "kind": "hantle", "on": True},
    {"id": "h2", "n": "Hantle — zestaw 2", "s": "", "kind": "hantle", "on": True},
    {"id": "lawka", "n": "Ławka", "s": "ze skosem", "kind": "lawka", "on": True},
    {"id": "mata", "n": "Mata", "s": "", "kind": "mata", "on": True},
    {"id": "gm", "n": "Guma — mocny opór", "s": "", "kind": "guma_mocna", "on": True},
    {"id": "gl", "n": "Guma — lekki opór", "s": "brak", "kind": "guma_lekka", "on": False},
    {"id": "mini", "n": "Mini band", "s": "brak", "kind": "mini", "on": False},
    {"id": "sztanga", "n": "Sztanga / gryf, talerze", "s": "planowany zakup", "kind": "sztanga", "on": False},
    {"id": "kb", "n": "Kettlebell", "s": "planowany zakup", "kind": "kettlebell", "on": False},
    {"id": "drazek", "n": "Drążek", "s": "planowany zakup", "kind": "drazek", "on": False},
]
DEFAULT_TIPS = ["Ćwiczę w małym pokoju, ok. 8 m², częściowo zajętym — tylko ćwiczenia w miejscu, bez przemieszczania się po pomieszczeniu."]
DEFAULT_ACCENTS = ["biceps"]

BICEPS = {"bicep_curl_db", "hammer_curl_db", "band_curl"}
TRICEPS = {"skull_crusher_db", "overhead_triceps_ext_db", "triceps_kickback_db", "bench_dips", "diamond_pushup"}
LIGHT_BAND = {"band_external_rotation", "band_dislocates", "band_pull_apart"}   # ruchy barku - mocna guma za ciezka
# akcent: (etykieta, klucze cwiczen albo partia)
ACCENTS = {
    "biceps": ("Biceps", BICEPS, None), "triceps": ("Triceps", TRICEPS, None),
    "tyl_barku": ("Tył barku", {"reverse_fly_db", "prone_t_raise_db", "band_pull_apart", "ytw_prone"}, None),
    "posladki": ("Pośladki", None, "tyl"), "brzuch": ("Brzuch", None, "core"), "plecy": ("Plecy", None, "plecy"),
    "klatka": ("Klatka", None, "klatka"), "nogi": ("Nogi", None, "nogi"), "barki": ("Barki", None, "barki"),
}
VARIANTS = {"ai": "AI poleca", "gora": "Góra ciała", "dol": "Dół ciała", "cale": "Całe ciało", "krotko": "Krótko 20′"}
VARIANT_SKIP = {"gora": ["nogi"], "dol": ["klatka", "plecy", "barki", "ramiona"], "cale": [], "krotko": []}
LONG_RIDE_MIN = 120


# ---------------- ustawienia ----------------
def _ensure(c) -> None:
    c.execute(open("/opt/qbot/app/sql/trainer_v14.sql", encoding="utf-8").read())


def load_prefs(c, user: str) -> dict:
    _ensure(c)
    c.execute("SELECT equipment, accents, tips, derived FROM qbot_v2.trainer_sila_prefs WHERE username=%s", (user,))
    r = c.fetchone()
    if not r:
        p = {"equipment": DEFAULT_EQUIPMENT, "accents": DEFAULT_ACCENTS, "tips": DEFAULT_TIPS, "derived": {}}
        c.execute("INSERT INTO qbot_v2.trainer_sila_prefs (username, equipment, accents, tips) VALUES (%s,%s::jsonb,%s::jsonb,%s::jsonb)",
                  (user, json.dumps(p["equipment"], ensure_ascii=False), json.dumps(p["accents"]), json.dumps(p["tips"], ensure_ascii=False)))
        return p
    g = lambda v: json.loads(v) if isinstance(v, str) else v
    return {"equipment": g(r["equipment"]) or [], "accents": g(r["accents"]) or [], "tips": g(r["tips"]) or [],
            "derived": g(r["derived"]) or {}}


def clean_prefs(body: dict) -> dict:
    """Walidacja tego, co przyslala strona. Bledy -> ValueError z czytelnym tekstem."""
    eq_in = body.get("equipment") or []
    if not isinstance(eq_in, list) or len(eq_in) > 40:
        raise ValueError("sprzęt: lista do 40 pozycji")
    eq, ids = [], set()
    for i, e in enumerate(eq_in):
        n = str((e or {}).get("n") or "").strip()[:60]
        if not n:
            raise ValueError("sprzęt: brak nazwy")
        kind = (e or {}).get("kind") or "inne"
        if kind not in KINDS:
            raise ValueError(f"sprzęt: nieznany rodzaj {kind}")
        eid = str((e or {}).get("id") or f"x{i}")[:20]
        while eid in ids:
            eid += "_"
        ids.add(eid)
        eq.append({"id": eid, "n": n, "s": str((e or {}).get("s") or "").strip()[:80], "kind": kind, "on": bool((e or {}).get("on"))})
    acc = [a for a in (body.get("accents") or []) if a in ACCENTS][:4]
    tips = [str(t).strip()[:300] for t in (body.get("tips") or []) if str(t).strip()][:12]
    return {"equipment": eq, "accents": list(dict.fromkeys(acc)), "tips": tips}


def save_prefs(c, user: str, body: dict, llm=None) -> dict:
    old = load_prefs(c, user)
    p = clean_prefs(body)
    derived = old.get("derived") or {}
    if tips_hash(p["tips"]) != derived.get("hash"):
        derived = derive_tips(c, p["tips"], llm=llm)
    c.execute("UPDATE qbot_v2.trainer_sila_prefs SET equipment=%s::jsonb, accents=%s::jsonb, tips=%s::jsonb, derived=%s::jsonb, "
              "updated_at=now() WHERE username=%s",
              (json.dumps(p["equipment"], ensure_ascii=False), json.dumps(p["accents"]), json.dumps(p["tips"], ensure_ascii=False),
               json.dumps(derived, ensure_ascii=False), user))
    return dict(p, derived=derived)


def tips_hash(tips: list) -> str:
    return hashlib.sha1(json.dumps(tips, ensure_ascii=False).encode()).hexdigest()[:12]


TIPS_SYSTEM = """Jesteś trenerem siłowym. Dostajesz WSKAZÓWKI użytkownika (twarde zasady) i listę ćwiczeń domowych.
Wskaż ćwiczenia, których przy tych wskazówkach NIE wolno planować (np. "mały pokój, tylko w miejscu" wyklucza ćwiczenia
z przemieszczaniem się: wykroki chodzone, spacery z ciężarem, chodzenie bokiem; ćwiczenia w miejscu zostają).
Wykluczaj tylko to, co naprawdę koliduje ze wskazówką — nie zgaduj. Odpowiedz WYŁĄCZNIE JSON:
{"exclude": [{"key": "klucz", "why": "krótko po polsku"}], "uwagi": "1 zdanie, czego wskazówki nie dotyczą wyboru ćwiczeń (albo pusty)"}"""


def derive_tips(c, tips: list, llm=None) -> dict:
    """Skutek wskazowek dla wyboru cwiczen - raz na zmiane wskazowek (cache w prefs.derived)."""
    out = {"hash": tips_hash(tips), "exclude": [], "why": {}, "uwagi": ""}
    if not tips:
        return out
    c.execute("SELECT key, name, grp FROM qbot_v2.trainer_exercise WHERE active ORDER BY key")
    rows = c.fetchall()
    keys = {r["key"] for r in rows}
    inp = {"wskazowki": tips, "cwiczenia": [{"key": r["key"], "nazwa": r["name"], "partia": r["grp"]} for r in rows]}
    if llm is None:
        from qgpt_client import qgpt_json as llm
    try:
        raw = llm(json.dumps(inp, ensure_ascii=False), system=TIPS_SYSTEM, max_tokens=900)
    except Exception as e:
        out["blad"] = f"AI niedostępne: {str(e)[:80]}"
        out["hash"] = ""   # sprobuj ponownie przy nastepnym zapisie / odczycie
        return out
    for it in (raw or {}).get("exclude") or []:
        k = str((it or {}).get("key") or "")
        if k in keys and k not in out["why"]:
            out["exclude"].append(k)
            out["why"][k] = str((it or {}).get("why") or "")[:120]
    out["uwagi"] = str((raw or {}).get("uwagi") or "")[:200]
    return out


def ensure_derived(c, user: str, prefs: dict) -> dict:
    """Wskazowki bez wyliczonego skutku (np. AI bylo niedostepne) -> policz teraz."""
    d = prefs.get("derived") or {}
    if prefs.get("tips") and d.get("hash") != tips_hash(prefs["tips"]):
        d = derive_tips(c, prefs["tips"])
        c.execute("UPDATE qbot_v2.trainer_sila_prefs SET derived=%s::jsonb WHERE username=%s", (json.dumps(d, ensure_ascii=False), user))
        prefs["derived"] = d
    return prefs


def prefs_hash(prefs: dict) -> str:
    on = sorted({e["kind"] for e in prefs.get("equipment") or [] if e.get("on")})
    det = sorted(f'{e["n"]}:{e.get("s", "")}' for e in prefs.get("equipment") or [] if e.get("on") and e["kind"] == "hantle")
    src = json.dumps([on, det, sorted(prefs.get("accents") or []), prefs.get("tips") or [],
                      sorted((prefs.get("derived") or {}).get("exclude") or [])], ensure_ascii=False)
    return hashlib.sha1(src.encode()).hexdigest()[:10]


# ---------------- filtr puli ----------------
def kinds_on(prefs: dict) -> set:
    return {e["kind"] for e in prefs.get("equipment") or [] if e.get("on")}


def allowed(x: dict, on: set, excl: set) -> str | None:
    """None = wolno; inaczej powod (krotko)."""
    if not x.get("garmin_kod") and x.get("grp") != "rozgrzewka":
        return "brak w Garmin"
    if x["key"] in excl:
        return "wskazówka"
    eq = set(x.get("equip") or [])
    if eq & {"h1", "h2"} and "hantle" not in on:
        return "brak hantli"
    if "lawka" in eq and "lawka" not in on:
        return "brak ławki"
    if "mata" in eq and "mata" not in on:
        return "brak maty"
    if "mini" in eq and "mini" not in on:
        return "brak mini bandu"
    if "guma" in eq:
        need = {"guma_lekka"} if x["key"] in LIGHT_BAND else {"guma_lekka", "guma_mocna"}
        if not need & on:
            return "brak gumy" + (" (lekkiej)" if x["key"] in LIGHT_BAND else "")
    return None


def apply_filter(c, user: str, pool: list) -> list:
    prefs = load_prefs(c, user)
    on, excl = kinds_on(prefs), set((prefs.get("derived") or {}).get("exclude") or [])
    for x in pool:
        why = allowed(x, on, excl)
        if why and x.get("tier") != "X":
            x["tier"], x["_why"] = "X", why
    return pool


# ---------------- kontekst ----------------
def bucket(key: str, grp: str) -> str:
    if key in BICEPS:
        return "biceps"
    if grp == "ramiona" or key in TRICEPS:
        return "triceps"
    return grp


BUCKET_LABEL = {"plecy": "Plecy", "core": "Brzuch", "nogi": "Nogi", "barki": "Barki", "klatka": "Klatka",
                "tyl": "Tył ciała", "triceps": "Triceps", "biceps": "Biceps"}


def balance(c, user: str, day: date, days: int = 28) -> dict:
    """Liczba cwiczen na partie w zestawach z ostatnich 'days' dni (bez dnia 'day'); biceps i triceps osobno."""
    cnt = Counter({b: 0 for b in BUCKET_LABEL})
    c.execute("SELECT key, grp FROM qbot_v2.trainer_exercise")
    grp = {r["key"]: r["grp"] for r in c.fetchall()}
    c.execute("SELECT data FROM qbot_v2.trainer_workout WHERE username=%s AND sport='sila' AND day BETWEEN %s AND %s",
              (user, day - timedelta(days=days), day - timedelta(days=1)))
    for r in c.fetchall():
        d = r["data"] if not isinstance(r["data"], str) else json.loads(r["data"])
        for e in (d or {}).get("exercises") or []:
            g = grp.get(e["key"])
            if g and g != "rozgrzewka":
                cnt[bucket(e["key"], g)] += 1
    return {"od": (day - timedelta(days=days)).isoformat(), "do": (day - timedelta(days=1)).isoformat(), "partie": dict(cnt)}


def week(c, user: str, day: date) -> list:
    c.execute("SELECT day, sport, name, dur_min, real_min, xss, real_xss, is_long, status FROM qbot_v2.trainer_session "
              "WHERE username=%s AND day BETWEEN %s AND %s ORDER BY day, start_time NULLS LAST",
              (user, day - timedelta(days=3), day + timedelta(days=3)))
    out = []
    for r in c.fetchall():
        m = r["real_min"] if r["status"] == "done" and r["real_min"] else r["dur_min"]
        out.append({"dzien": r["day"].isoformat(), "rel": (r["day"] - day).days, "sport": r["sport"], "nazwa": r["name"],
                    "min": int(m or 0), "xss": float(r["real_xss"] or r["xss"] or 0), "dluga": bool(r["is_long"]), "status": r["status"]})
    return out


def variant_rule(wk: list) -> tuple[str, str]:
    """Wariant 'AI poleca': dluga jazda dzien przed / dzien po -> gora ciala."""
    near = [w for w in wk if w["sport"] == "rower" and abs(w["rel"]) == 1 and (w["min"] >= LONG_RIDE_MIN or w["dluga"])]
    if near:
        w = near[0]
        kiedy = "jutro" if w["rel"] == 1 else "wczoraj"
        return "gora", f"{kiedy} {round(w['min'] / 60, 1):g} h jazdy — dziś bez ciężkich nóg"
    return "cale", "brak długiej jazdy dzień przed ani po — całe ciało"


def resolve_variant(s: dict, wk: list) -> tuple[str, str, str]:
    """(wybrany, faktyczny, powod). wybrany = co kliknal uzytkownik (ai domyslnie)."""
    opts = s.get("opts") if isinstance(s.get("opts"), dict) else {}
    chosen = (opts or {}).get("sila_variant") or "ai"
    if chosen not in VARIANTS:
        chosen = "ai"
    if chosen == "ai":
        v, why = variant_rule(wk)
        return chosen, v, why
    return chosen, chosen, f"wybrane: {VARIANTS[chosen]}"


def accent_keys(acc: str, pool: list) -> set:
    lab, keys, grp = ACCENTS[acc]
    return set(keys) if keys else {x["key"] for x in pool if x["grp"] == grp}


def short_text(t: str, limit: int) -> str:
    """Skrot po calym zdaniu (albo slowie) - bez ucinania w polowie wyrazu."""
    t = " ".join(t.split())
    if len(t) <= limit:
        return t
    cut = t[:limit]
    i = max(cut.rfind(". "), cut.rfind("; "))
    if i > limit // 3:   # pelne zdanie, jesli nie jest za krotkie
        return cut[: i + 1]
    return cut[: cut.rfind(" ")].rstrip(",;:") + "…"


# ---------------- AI: wybor cwiczen ----------------
PLAN_SYSTEM = """Jesteś trenerem siłowym kolarza amatora. Układasz JEDEN domowy trening siłowy w blokach ciężaru.
Wybierasz ćwiczenia WYŁĄCZNIE z listy "dostepne" (podajesz ich klucze "k"). Zasady twarde:
- liczba ćwiczeń: "liczba" (dopuszczalne ±1);
- z jednej "rodzina" najwyżej jedno ćwiczenie (wyjątek: ćwiczenia akcentu);
- akcenty: z każdego akcentu co najmniej "min_akcent" ćwiczeń z jego listy kluczy;
- najwyżej 2 klasy ciężaru z hantlami (C ciężkie, S średnie, L lekkie) + ćwiczenia bez hantli (klasa 0); w każdej użytej
  klasie co najmniej 2 ćwiczenia;
- ćwiczenia bez hantli (klasa 0, w tym brzuch) to NAJWYŻEJ połowa treningu; duże partie (nogi, tył ciała, plecy, klatka)
  rób przede wszystkim z hantlami, w klasie C (ciężkie) albo S;
- każda partia z "partie_obowiazkowe" co najmniej raz; jedna partia najwyżej 2 ćwiczenia (nie licząc akcentu);
- nie powtarzaj ćwiczeń z "poprzedni_trening", jeśli jest zamiennik;
- wskazówki użytkownika są twarde.
Cele: równowaga ciała (pchanie/ciągnięcie, przód/tył) w ramach wariantu, nadrabianie partii, które w "bilans_4tyg" mają
najmniej ćwiczeń, dopasowanie do jazd w "tydzien" (przy długiej jeździe dzień przed/po nogi lżej), preferuj "podstawowe".
Odpowiedz WYŁĄCZNIE JSON: {"cwiczenia": ["k", ...], "uzasadnienie": "maks. 2 krótkie zdania (do 220 znaków) po polsku:
dlaczego taki trening (konkretnie: jazdy, zaniedbane partie, akcent) — bez ogólników"}"""


def validate_selection(keys: list, by: dict, *, n: int, acc_sets: dict, min_acc: int, fam, must: set | None = None) -> tuple[list, list]:
    """Sprawdza wybor AI. Zwraca (lista kluczy, uwagi). Pusta lista = odrzucone."""
    notes, out, fams = [], [], set()
    acc_all = set().union(*acc_sets.values()) if acc_sets else set()
    for k in keys:
        if k not in by:
            notes.append(f"spoza listy: {k}")
            continue
        if k in out or (fam(k) in fams and k not in acc_all):   # akcent moze miec 2 odmiany tego samego ruchu
            notes.append(f"dubel: {k}")
            continue
        out.append(k); fams.add(fam(k))
    cls = Counter(by[k]["wclass"] for k in out if by[k]["wclass"] != "0")
    if len(cls) > 2:
        keep = {c for c, _ in cls.most_common(2)}
        drop = [k for k in out if by[k]["wclass"] not in keep and by[k]["wclass"] != "0"]
        out = [k for k in out if k not in drop]
        notes.append(f"3. klasa ciężaru usunięta: {', '.join(drop)}")
    for a, ks in acc_sets.items():
        if sum(1 for k in out if k in ks) < min_acc:
            notes.append(f"za mało akcentu {a}")
    if len(out) < max(4, n - 2):
        notes.append(f"za mało ćwiczeń ({len(out)} z {n})")
        return [], notes
    zero = sum(1 for k in out if by[k]["wclass"] == "0")
    if zero > (len(out) + 1) // 2:
        notes.append(f"za dużo ćwiczeń bez hantli ({zero} z {len(out)}) — maks. połowa")
        return [], notes
    per = Counter(by[k]["grp"] for k in out if k not in acc_all)
    za_duzo = sorted(g for g, v in per.items() if v > 2)
    if za_duzo:
        notes.append("ponad 2 ćwiczenia na partię: " + ", ".join(za_duzo))
        return [], notes
    if must:
        brak = sorted(g for g in must if not any(by[k]["grp"] == g for k in out))
        if brak:
            notes.append("brak partii: " + ", ".join(brak))
            return [], notes
    return out[: n + 1], notes


def ensure_accent(chosen: list, pool: list, acc_sets: dict, min_acc: int, fam, last: set) -> list:
    """Dopisuje / podmienia cwiczenia akcentu, gdy ich brakuje (zapas, gdy AI zawiodlo)."""
    chosen = [dict(x) for x in chosen]
    for a, ks in acc_sets.items():
        have = [x for x in chosen if x["key"] in ks]
        for x in have:
            x["accent"] = True
        need = min_acc - len(have)
        while need > 0:
            used, fams = {x["key"] for x in chosen}, {fam(x["key"]) for x in chosen}
            present = {x["wclass"] for x in chosen if x["wclass"] != "0"}
            cs = [p for p in pool if p["key"] in ks and p["tier"] != "X" and p.get("img") and p["key"] not in used]
            cs.sort(key=lambda p: (p["wclass"] not in present | {"0"}, fam(p["key"]) in fams, p["key"] in last, -(p.get("prio") or 0)))
            if not cs:
                break
            y = dict(cs[0], accent=True)
            rep = [i for i, x in enumerate(chosen) if not x.get("accent") and x["wclass"] == y["wclass"] and x["grp"] not in ("core",)]
            if rep and len(chosen) >= 8:
                chosen[rep[-1]] = y
            else:
                chosen.append(y)
            need -= 1
    return chosen


def ai_choose(c, user: str, s: dict, phase, pool: list, hist: list, base: dict, prefs: dict, variant: tuple,
              skipped: set, bad: set, fam, maxlvl: int, llm=None) -> dict:
    """Zwraca {chosen, uzasadnienie, ai: bool, uwagi}. base = uklad bazowy (choose) - liczba cwiczen i zapas."""
    day = s["day"] if isinstance(s["day"], date) else date.fromisoformat(str(s["day"])[:10])
    n = max(5, len(base["chosen"]))
    min_acc = 1 if (s.get("cut") or s["dur_min"] < 30) else 2
    acc_sets = {a: accent_keys(a, pool) for a in prefs.get("accents") or [] if a in ACCENTS}
    acc_sets = {a: ks for a, ks in acc_sets.items() if not ({x["grp"] for x in pool if x["key"] in ks} <= skipped)}
    last = set(hist[0]) if hist else set()
    ok = [x for x in pool if x["grp"] != "rozgrzewka" and x.get("img") and x["tier"] != "X" and x["key"] not in bad
          and x["level"] <= maxlvl and x["grp"] not in skipped and (x["grp"] != "core" or x["wclass"] == "0")]
    by = {x["key"]: x for x in ok}
    must = {g for g in ("nogi", "tyl", "plecy", "klatka", "core") if g not in skipped and any(x["grp"] == g for x in ok)}
    wk = week(c, user, day)
    bal = balance(c, user, day)
    names = {x["key"]: x["name"] for x in pool}
    inp = {
        "dzien": day.isoformat(), "czas_min": s["dur_min"], "okres": phase, "liczba": n,
        "wariant": VARIANTS.get(variant[1], variant[1]), "wariant_powod": variant[2],
        "pominiete_partie": sorted(skipped), "min_akcent": min_acc,
        "partie_obowiazkowe": sorted(must),
        "akcenty": [{"akcent": ACCENTS[a][0], "klucze": sorted(k for k in ks if k in by)} for a, ks in acc_sets.items()],
        "wskazowki": prefs.get("tips") or [],
        "sprzet": [f'{e["n"]}' + (f' ({e["s"]})' if e.get("s") else "") for e in prefs.get("equipment") or [] if e.get("on")],
        "tydzien": wk, "bilans_4tyg": {BUCKET_LABEL.get(k, k): v for k, v in bal["partie"].items()},
        "poprzedni_trening": [names.get(k, k) for k in (hist[0] if hist else [])],
        "dostepne": [{"k": x["key"], "nazwa": x["name"], "partia": BUCKET_LABEL.get(bucket(x["key"], x["grp"]), x["grp"]),
                      "klasa": x["wclass"], "poziom": x["level"], "rodzina": fam(x["key"]), "podstawowe": x["tier"] == "P"}
                     for x in ok],
    }
    res = {"chosen": None, "uzasadnienie": "", "ai": False, "uwagi": []}
    if llm is None:
        from qgpt_client import qgpt_json as llm
    for proba in range(2):   # 2. proba dostaje liste bledow 1. proby
        try:
            raw = llm(json.dumps(inp, ensure_ascii=False), system=PLAN_SYSTEM, max_tokens=700)
        except Exception as e:
            res["uwagi"].append(f"AI niedostępne: {str(e)[:80]}")
            break
        keys = [str(k) for k in ((raw or {}).get("cwiczenia") or [])]
        sel, notes = validate_selection(keys, by, n=n, acc_sets=acc_sets, min_acc=min_acc, fam=fam, must=must)
        res["uwagi"] += [f"próba {proba + 1}: {x}" for x in notes]
        if sel:
            res["chosen"] = [dict(by[k], accent=any(k in ks for ks in acc_sets.values())) for k in sel]
            res["uzasadnienie"] = short_text(str((raw or {}).get("uzasadnienie") or ""), 260)
            res["ai"] = True
            break
        inp["popraw"] = notes
    if not res["chosen"]:
        res["chosen"] = [dict(x, accent=False) for x in base["chosen"]]
        res["uzasadnienie"] = "Układ zapasowy (AI niedostępne) — " + variant[2] + "."
    res["chosen"] = ensure_accent(res["chosen"], ok, acc_sets, min_acc, fam, last)
    res["akcent"] = " + ".join(ACCENTS[a][0] for a in acc_sets) or None
    return res
