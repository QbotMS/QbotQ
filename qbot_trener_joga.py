"""TRENER - joga w Down Dog (2026-10-23, decyzja Michala; makieta /trening-joga-makieta.html zaakceptowana).

1. OPCJE DOWN DOG pobierane automatycznie (refresh): manifest aplikacji
   https://www.downdogapp.com/json/manifest?version=<wersja>&language=pl  (bez logowania, PL przez Accept-Language).
   Z manifestu bierzemy tylko typy z filtra "Joga" (bez medytacji, HIIT, pilatesu, prenatalnych - decyzja 23.10):
   id, nazwa, opis, Boosty, ustawienia "Czas trzymania pozycji" / "Szybkosc przejsc" / "Savasana".
   Raz na 7 dni (watek w qbot_web). Nowy typ / Boost -> dzwonek. Serwer odpowiada "zaktualizuj aplikacje"
   (tylko requiredUpdateAnnouncement) -> probujemy kolejnych numerow wersji; nie pomaga -> dzwonek, zostaje
   ostatnia dzialajaca lista. Stan: qbot_v2.downdog_options (sql/trainer_v15.sql).
2. PRZEPIS przy sesji jogi (recipe): AI dostaje tydzien (-3..+3 dni, jazdy / sila / joga), sesje (nazwa, notatka
   planu, minuty), uwagi uzytkownika do jogi (oceny + komentarze z trainer_rating, uwagi zapisane przy przepisach)
   i liste opcji; zwraca typ + Boost 1 + Boost 2 + ustawienia + 2 alternatywy + krotkie "dlaczego". Wynik sprawdzany
   (tylko istniejace opcje, Boosty z danego typu, rozne); zle / AI niedostepne -> regula zapasowa.
   Zapis: trainer_workout sport='joga' (podpis: opcje + sesja + tydzien + uwagi + "inna propozycja").
Czesci czyste: extract, next_versions, validate_recipe, rule_recipe (tests/test_trener_joga.py).
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

URL = "https://www.downdogapp.com/json/manifest"
BASE_VERSION = "8.2.2"
REFRESH_DAYS = 7
SETTINGS = ("Czas trzymania pozycji", "Szybkość przejść", "Savasana")
SPORT = "joga"
NOTE_DAYS = 90


# ---------------- opcje Down Dog ----------------
def _ensure(c) -> None:
    c.execute(open("/opt/qbot/app/sql/trainer_v15.sql", encoding="utf-8").read())


def _get(version: str) -> dict:
    q = urllib.parse.urlencode({"language": "pl", "platform": "web", "timeZone": "Europe/Warsaw", "version": version})
    req = urllib.request.Request(f"{URL}?{q}", headers={"User-Agent": "Mozilla/5.0 (QBot; prywatny planer)",
                                                         "Accept-Language": "pl-PL,pl;q=0.9"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def next_versions(v: str) -> list:
    """Kandydaci, gdy serwer chce nowszej wersji: kolejne poprawki, potem nastepne mniejsze i wieksze wydanie."""
    try:
        a, b, c = (int(x) for x in v.split("."))
    except Exception:
        return [BASE_VERSION]
    out = [f"{a}.{b}.{c + i}" for i in range(1, 6)] + [f"{a}.{b + i}.0" for i in range(1, 4)]
    out += [f"{a}.{b + i}.{k}" for i in range(1, 3) for k in range(1, 4)] + [f"{a + 1}.0.0", f"{a + 1}.0.1", f"{a + 1}.1.0"]
    return out


def extract(root: dict) -> dict:
    """sequenceSettingsRoot manifestu -> typy jogi z Boostami i ustawieniami (tylko filtr 'Joga')."""
    ids = None
    for f in root.get("categoryFilters") or []:
        if str(f.get("label", "")).lower().startswith("joga"):
            ids = [str(x) for x in f.get("categoryIds") or []]
    byid = {str(c.get("id")): c for c in root.get("categoryOptions") or []}
    types = []
    for i in ids or []:
        c = byid.get(i)
        if not c:
            continue
        b = c.get("boostSetting") or {}
        boosts = [o.get("label") for o in b.get("options") or [] if o.get("label") and o.get("label") != "Brak"]
        st = {}
        for s in c.get("otherSettings") or []:
            if s.get("label") in SETTINGS:
                st[s["label"]] = [o.get("label") for o in s.get("options") or [] if o.get("label")]
        types.append({"id": i, "label": c.get("label"), "help": c.get("helpText") or "", "boosts": boosts, "settings": st})
    return {"types": types}


def opts_hash(data: dict) -> str:
    return hashlib.sha1(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def diff(old: dict, new: dict) -> list:
    """Nowosci w new wzgledem old: ['typ: X', 'Boost Y w Z', ...]."""
    if not (old or {}).get("types"):
        return []
    ot = {t["label"]: set(t["boosts"]) for t in old["types"]}
    out = []
    for t in new.get("types") or []:
        if t["label"] not in ot:
            out.append(f"nowy typ: {t['label']}")
        else:
            for b in sorted(set(t["boosts"]) - ot[t["label"]]):
                out.append(f"nowy Boost „{b}” w {t['label']}")
    return out


def load(c) -> dict | None:
    _ensure(c)
    c.execute("SELECT version, fetched_at, checked_at, hash, data, error FROM qbot_v2.downdog_options WHERE id=1")
    r = c.fetchone()
    if not r:
        return None
    r = dict(r) if isinstance(r, dict) else dict(zip(("version", "fetched_at", "checked_at", "hash", "data", "error"), r))
    if isinstance(r.get("data"), str):
        r["data"] = json.loads(r["data"])
    return r


def refresh(c, force: bool = False, getter=None) -> dict:
    """Pobierz opcje, gdy ostatnie udane pobranie starsze niz REFRESH_DAYS (albo force). Zwraca stan."""
    getter = getter or _get
    cur = load(c)
    now = datetime.now(timezone.utc)
    if cur and not force and cur.get("fetched_at") and now - cur["fetched_at"] < timedelta(days=REFRESH_DAYS):
        return {"status": "aktualne", "version": cur["version"]}
    tried, root, ver = [], None, None
    for v in [x for x in dict.fromkeys([(cur or {}).get("version") or BASE_VERSION, BASE_VERSION] +
                                     next_versions((cur or {}).get("version") or BASE_VERSION)) if x]:
        tried.append(v)
        try:
            o = _get(v) if getter is _get else getter(v)
        except Exception as e:
            err = f"Down Dog niedostępny: {str(e)[:120]}"
            c.execute("INSERT INTO qbot_v2.downdog_options (id, checked_at, error) VALUES (1, now(), %s) "
                      "ON CONFLICT (id) DO UPDATE SET checked_at=now(), error=EXCLUDED.error", (err,))
            return {"status": "blad", "error": err}
        if (o or {}).get("sequenceSettingsRoot"):
            root, ver = o["sequenceSettingsRoot"], v
            break
    if not root:
        err = f"Down Dog wymaga nowszej wersji aplikacji (sprawdzone: {', '.join(tried[:6])}…)"
        c.execute("INSERT INTO qbot_v2.downdog_options (id, checked_at, error) VALUES (1, now(), %s) "
                  "ON CONFLICT (id) DO UPDATE SET checked_at=now(), error=EXCLUDED.error", (err,))
        _bell(c, "downdog:blad", "Down Dog: nie udało się pobrać opcji", err + ". Joga używa ostatniej listy.")
        return {"status": "blad", "error": err}
    data = extract(root)
    h = opts_hash(data)
    nowe = diff((cur or {}).get("data") or {}, data)
    c.execute("""INSERT INTO qbot_v2.downdog_options (id, version, fetched_at, checked_at, hash, data, error)
                 VALUES (1, %s, now(), now(), %s, %s::jsonb, NULL)
                 ON CONFLICT (id) DO UPDATE SET version=EXCLUDED.version, fetched_at=now(), checked_at=now(),
                   hash=EXCLUDED.hash, data=EXCLUDED.data, error=NULL""", (ver, h, json.dumps(data, ensure_ascii=False)))
    try:
        import qbot_notif as N
        N.resolve(c, "downdog:blad")
    except Exception:
        pass
    if nowe:
        _bell(c, f"downdog:nowe:{h}", "Nowe w Down Dog", "; ".join(nowe[:6]) + ". Trener już je uwzględnia.")
    return {"status": "ok", "version": ver, "nowe": nowe, "typy": len(data["types"])}


def _bell(c, key: str, title: str, body: str) -> None:
    try:
        import qbot_notif as N
        N.push(c, key, "trener", title, body, url="/trening.html#miesiac")
    except Exception as e:
        print("downdog: dzwonek:", repr(e)[:200])


def options(c) -> dict:
    cur = load(c)
    if not cur or not (cur.get("data") or {}).get("types"):
        refresh(c, force=True)
        cur = load(c)
    return cur or {}


# ---------------- przepis ----------------
def validate_recipe(r: dict, types: list) -> tuple[dict | None, list]:
    """Sprawdza przepis AI wzgledem opcji. Zwraca (przepis znormalizowany albo None, uwagi)."""
    notes = []
    by = {t["label"]: t for t in types}
    t = by.get(str((r or {}).get("typ") or ""))
    if not t:
        return None, [f"nieznany typ: {(r or {}).get('typ')}"]
    b1, b2 = str(r.get("boost1") or ""), str(r.get("boost2") or "")
    if t["boosts"]:
        if b1 not in t["boosts"]:
            return None, [f"Boost spoza typu {t['label']}: {b1}"]
        if b2 and (b2 not in t["boosts"] or b2 == b1):
            notes.append(f"Boost 2 odrzucony: {b2}")
            b2 = ""
    else:
        b1 = b2 = ""
    st = {}
    for k, vals in t["settings"].items():
        v = str(((r.get("ustawienia") or {}).get(k)) or "")
        if v in vals:
            st[k] = v
    return {"typ": t["label"], "typ_id": t["id"], "opis": t["help"], "boost1": b1, "boost2": b2, "ustawienia": st}, notes


def rule_recipe(session: dict, wk: list, types: list) -> dict:
    """Zapas bez AI: po dlugiej jezdzie Yin (biodra + tyl uda), dzien przed dluga jazda lagodnie, inaczej Vinyasa."""
    by = {t["label"]: t for t in types}
    long_before = any(w for w in wk if w["sport"] == "rower" and w["rel"] == -1 and (w["min"] >= 120 or w.get("dluga")))
    long_after = any(w for w in wk if w["sport"] == "rower" and w["rel"] == 1 and (w["min"] >= 120 or w.get("dluga")))
    if long_before:
        typ, b1, b2 = "Yin", "Zginacze bioder", "Tył uda"
    elif long_after:
        typ, b1, b2 = "Łagodna", "Biodra", "Dolna część pleców"
    else:
        typ, b1, b2 = "Vinyasa", "Biodra", "Klatka piersiowa i barki"
    if typ not in by and types:
        typ = types[0]["label"]
    t = by.get(typ) or (types[0] if types else {"label": typ, "id": "", "help": "", "boosts": [], "settings": {}})
    b1 = b1 if b1 in t["boosts"] else (t["boosts"][0] if t["boosts"] else "")
    b2 = b2 if b2 in t["boosts"] and b2 != b1 else ""
    st = {k: ("Długi" if typ == "Yin" and "Długi" in v else ("Domyślne" if "Domyślne" in v else (v[0] if v else "")))
          for k, v in t["settings"].items() if k != "Savasana"}
    if "Savasana" in t["settings"] and "3 min" in t["settings"]["Savasana"]:
        st["Savasana"] = "3 min"
    return {"typ": t["label"], "typ_id": t["id"], "opis": t["help"], "boost1": b1, "boost2": b2, "ustawienia": st}


SYSTEM = """Jesteś trenerem przygotowania motorycznego kolarza amatora. Ustalasz, co ustawić w aplikacji Down Dog na JEDNĄ
sesję jogi. Wybierasz WYŁĄCZNIE z listy "opcje" (typ, Boosty tego typu, wartości ustawień tego typu).
Zasady: dzień po długiej jeździe — regeneracja bioder, zginaczy bioder, tyłu uda, dolnych pleców, bez wysiłku nóg;
dzień przed długą jazdą albo siłą nóg — bez mocnego obciążania nóg; dzień wolny od innych treningów (sesja "mobilność") — AKTYWNIEJ: Vinyasa, Hatha, Joga + Pilates, Rozciąganie w staniu albo
Joga na pobudkę (nie Regeneracyjna/Yin); uwzględnij "uwagi" użytkownika (np. "wycisk" = ta opcja jest mocna — nie w dzień przed/po
długiej jeździe); nie powtarzaj typu + Boostów z "inne_jogi" (pozostałe sesje jogi w tych tygodniach) — urozmaicaj;
jeśli jest "poprzedni_przepis", użytkownik prosi o INNĄ propozycję: inny typ albo oba Boosty inne.
Odpowiedz WYŁĄCZNIE JSON:
{"typ": "...", "boost1": "...", "boost2": "...", "ustawienia": {"nazwa ustawienia": "wartość"},
 "uzasadnienie": "1–2 krótkie zdania po polsku, konkretnie (jazdy, dzień, uwagi), maks. 220 znaków",
 "alternatywy": [{"typ": "...", "boost1": "...", "boost2": "..."}, {"typ": "...", "boost1": "...", "boost2": "..."}]}"""


def notes(c, user: str, day: date) -> list:
    """Uwagi do jogi: oceny/komentarze z trainer_rating + uwagi zapisane przy przepisach (data.uwaga)."""
    out = []
    try:
        c.execute("SELECT day, rating, note, title FROM qbot_v2.trainer_rating WHERE username=%s AND sport=%s AND day BETWEEN %s AND %s "
                  "ORDER BY day DESC LIMIT 12", (user, SPORT, day - timedelta(days=NOTE_DAYS), day))
        for r in c.fetchall():
            r = dict(r) if isinstance(r, dict) else dict(zip(("day", "rating", "note", "title"), r))
            if r.get("note") or r.get("rating"):
                out.append({"dzien": str(r["day"]), "ocena": r.get("rating"), "uwaga": r.get("note") or "", "co": r.get("title") or ""})
    except Exception:
        pass
    c.execute("SELECT day, data FROM qbot_v2.trainer_workout WHERE username=%s AND sport=%s AND day BETWEEN %s AND %s ORDER BY day DESC",
              (user, SPORT, day - timedelta(days=NOTE_DAYS), day - timedelta(days=1)))
    for r in c.fetchall():
        r = dict(r) if isinstance(r, dict) else dict(zip(("day", "data"), r))
        d = r["data"] if not isinstance(r["data"], str) else json.loads(r["data"])
        rc = (d or {}).get("recipe") or {}
        if (d or {}).get("uwaga"):
            out.append({"dzien": str(r["day"]), "uwaga": d["uwaga"], "co": f"{rc.get('typ', '')}" + (f" · {rc['boost1']}" if rc.get("boost1") else "")})
    out.sort(key=lambda x: x["dzien"], reverse=True)
    return out[:12]


def _sig(o: dict, s: dict, wk: list, nt: list, rr: int) -> str:
    src = json.dumps([o.get("hash"), s.get("name"), s.get("dur_min"), s.get("note"),
                      [(w["rel"], w["sport"], w["min"]) for w in wk], [(n["dzien"], n.get("uwaga")) for n in nt], rr],
                     ensure_ascii=False, default=str)
    return "dd1|" + hashlib.sha1(src.encode()).hexdigest()[:12]


def _saved(c, user: str, day) -> dict | None:
    c.execute("SELECT sig, data FROM qbot_v2.trainer_workout WHERE username=%s AND day=%s AND sport=%s", (user, day, SPORT))
    r = c.fetchone()
    if not r:
        return None
    r = dict(r) if isinstance(r, dict) else dict(zip(("sig", "data"), r))
    if isinstance(r["data"], str):
        r["data"] = json.loads(r["data"])
    return r


def _save(c, user: str, day, sig: str, data: dict) -> None:
    c.execute("""INSERT INTO qbot_v2.trainer_workout (username, day, sport, sig, data, updated_at) VALUES (%s,%s,%s,%s,%s::jsonb, now())
                 ON CONFLICT (username, day, sport) DO UPDATE SET sig=EXCLUDED.sig, data=EXCLUDED.data, updated_at=now()""",
              (user, day, SPORT, sig, json.dumps(data, ensure_ascii=False, default=str)))


def recipe(c, user: str, s: dict, llm=None, force: bool = False) -> dict:
    """Przepis Down Dog dla sesji jogi (z pamieci, gdy aktualny). s = wiersz trainer_session."""
    import qbot_trener_sila_ai as SA
    day = s["day"] if isinstance(s["day"], date) else date.fromisoformat(str(s["day"])[:10])
    o = options(c)
    types = (o.get("data") or {}).get("types") or []
    wk = SA.week(c, user, day)
    nt = notes(c, user, day)
    sv = _saved(c, user, day)
    old = (sv or {}).get("data") or {}
    rr = int(old.get("reroll") or 0)
    sig = _sig(o, s, wk, nt, rr)
    if sv and sv["sig"] == sig and old.get("recipe") and not force:
        return old
    if s.get("status") == "done" and old.get("recipe") and not force:
        return old   # zrobiona sesja: przepis zostaje taki, jak byl
    out = {"reroll": rr, "uwaga": old.get("uwaga")}
    if not types:
        out.update(recipe=None, alts=[], uzasadnienie="Brak listy opcji Down Dog — sprawdzę ją ponownie.", ai=False)
        return out
    prev = old.get("recipe") if rr and old.get("recipe") else None
    inne = others(c, user, day)
    inp = {"dzien": day.isoformat(), "sesja": s.get("name"), "plan": s.get("note"), "minuty": s.get("dur_min"),
           "tydzien": wk, "uwagi": nt, "inne_jogi": inne,
           "poprzedni_przepis": ({k: prev.get(k) for k in ("typ", "boost1", "boost2")} if prev else None),
           "opcje": [{"typ": t["label"], "opis": t["help"], "boosty": t["boosts"], "ustawienia": t["settings"]} for t in types]}
    rec, alts, why, ai, uw = None, [], "", False, []
    if llm is None:
        from qgpt_client import qgpt_json as llm
    try:
        raw = llm(json.dumps(inp, ensure_ascii=False, default=str), system=SYSTEM, max_tokens=700, temperature=0.4 if rr else 0)
        rec, uw = validate_recipe(raw or {}, types)
        if rec and prev and same(rec, prev):
            uw.append("AI dało ten sam przepis co poprzednio")
            alt0 = next((v for v in (validate_recipe(dict(a, ustawienia={}), types)[0] for a in (raw or {}).get("alternatywy") or [])
                         if v and not same(v, prev)), None)
            rec = alt0
        if rec:
            ai = True
            why = SA.short_text(str((raw or {}).get("uzasadnienie") or ""), 260)
            for a in (raw or {}).get("alternatywy") or []:
                v, _n = validate_recipe(dict(a, ustawienia={}), types)
                if v and (v["typ"], v["boost1"]) != (rec["typ"], rec["boost1"]):
                    alts.append(v)
    except Exception as e:
        uw.append(f"AI niedostępne: {str(e)[:80]}")
    if not rec:
        rec = rule_recipe(s, wk, types)
        why = "Układ zapasowy (AI niedostępne): " + ("po długiej jeździe — regeneracja bioder i tyłu uda." if rec["typ"] == "Yin"
                                                    else "spokojna mobilność.")
    out.update(recipe=dict(rec, minuty=s.get("dur_min")), alts=alts[:2], uzasadnienie=why, ai=ai, uwagi_ai=uw)
    _save(c, user, day, sig, out)
    return out


def same(a: dict, b: dict) -> bool:
    return a.get("typ") == b.get("typ") and {a.get("boost1"), a.get("boost2")} == {b.get("boost1"), b.get("boost2")}


def others(c, user: str, day: date) -> list:
    """Przepisy pozostalych sesji jogi (+-14 dni) - zeby AI nie powtarzalo jednego przepisu."""
    c.execute("SELECT day, data FROM qbot_v2.trainer_workout WHERE username=%s AND sport=%s AND day BETWEEN %s AND %s AND day <> %s ORDER BY day",
              (user, SPORT, day - timedelta(days=14), day + timedelta(days=14), day))
    out = []
    for r in c.fetchall():
        r = dict(r) if isinstance(r, dict) else dict(zip(("day", "data"), r))
        d = r["data"] if not isinstance(r["data"], str) else json.loads(r["data"])
        rc = (d or {}).get("recipe")
        if rc:
            out.append({"dzien": str(r["day"]), "typ": rc.get("typ"), "boost1": rc.get("boost1"), "boost2": rc.get("boost2")})
    return out


def reroll(c, user: str, s: dict) -> dict:
    day = s["day"]
    sv = _saved(c, user, day)
    data = (sv or {}).get("data") or {}
    data["reroll"] = int(data.get("reroll") or 0) + 1
    _save(c, user, day, (sv or {}).get("sig") or "", data)
    return recipe(c, user, s)


def pick(c, user: str, s: dict, idx: int) -> dict:
    """Alternatywa nr idx staje sie przepisem (stary przepis idzie na liste alternatyw)."""
    day = s["day"]
    sv = _saved(c, user, day)
    data = (sv or {}).get("data") or {}
    alts = data.get("alts") or []
    if not (0 <= idx < len(alts)):
        raise ValueError("nie ma takiej propozycji")
    o = options(c)
    types = (o.get("data") or {}).get("types") or []
    new = dict(alts[idx])
    t = next((x for x in types if x["label"] == new["typ"]), None)
    if t:   # ustawienia dla nowego typu: domyslne
        new["ustawienia"] = {k: ("Domyślne" if "Domyślne" in v else (v[0] if v else "")) for k, v in t["settings"].items() if k != "Savasana"}
        if "Savasana" in t["settings"] and "3 min" in t["settings"]["Savasana"]:
            new["ustawienia"]["Savasana"] = "3 min"
    old = data.get("recipe")
    data["recipe"] = dict(new, minuty=(old or {}).get("minuty"))
    data["alts"] = [a for i, a in enumerate(alts) if i != idx] + ([{k: old[k] for k in ("typ", "typ_id", "opis", "boost1", "boost2", "ustawienia") if k in old}] if old else [])
    data["uzasadnienie"] = "Twój wybór z propozycji AI."
    _save(c, user, day, (sv or {}).get("sig") or "", data)
    return data


def set_note(c, user: str, s: dict, text: str) -> dict:
    day = s["day"]
    sv = _saved(c, user, day)
    data = (sv or {}).get("data") or {}
    data["uwaga"] = (text or "").strip()[:300] or None
    _save(c, user, day, (sv or {}).get("sig") or "", data)
    return data
