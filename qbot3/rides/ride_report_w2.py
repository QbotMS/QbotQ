# -*- coding: utf-8 -*-
"""W2 — analiza raportu z jazdy przez LLM (czyta TYLKO W1, cytuje pola, nic nie zmysla).

Nie rejestruje narzedzia Alberta (brak sprzezenia z _SYSTEM). Uzywa wspolnego klienta LLM
(qgpt_json) — tego samego, ktorym posluguje sie reszta QBota.
"""
import json
import re

W2_QUESTIONS = [
    "Jak ciezka byla ta jazda na tle Twoich mozliwosci (ModelQ)?",
    "Gdzie i dlaczego wyczerpales W' i jak z regeneracja miedzy wysilkami?",
    "Jak rozlozyles wysilek (pacing, splity, VI, decoupling)?",
    "Gdzie realnie szly waty (audyt energetyczny)?",
    "Co mowi naped i technika (biegi, kadencja wg nachylenia, hamowanie)?",
    "Czy wszedles na te jazde wypoczety (wellness poranny a decoupling)?",
    "Co ta jazda zmienila w ModelQ (forma) i jak wypada wobec benchmarku Xert?",
]

W2_SYSTEM = """Jestes analitykiem raportu z jazdy rowerowej (gravel) w systemie QBot.
Dostajesz dane W1 jako JSON — to fakty policzone deterministycznie z pliku FIT, z modelu formy ModelQ oraz z porannych danych Garmin.

TWARDE ZASADY:
- Analizuj WYLACZNIE na podstawie W1. Nie wymyslaj zadnych liczb ani faktow spoza W1.
- Kazde twierdzenie opieraj na konkretnych polach W1. W polu "tekst" pisz NATURALNA, zwiezla proza: wartosci podawaj po ludzku z jednostka (np. "praca 2695 kJ", "NP 191 W", "IF 0.81"), a NAZW POL / IDENTYFIKATOROW W1 (np. load.kj, modelq.current.cp_w) NIE wpisuj do tekstu. Pola-zrodla, na ktorych opierasz sekcje, podawaj WYLACZNIE w tablicy "cytaty".
- Blok terrain_impact ma rozklad wysilku: surface_by_type (moc/HR/kadencja/predkosc/nachylenie per typ nawierzchni) oraz wind_by_dir (moc/HR/kadencja/predkosc + koszt beztlenowy "W' ponad CP" dla: pod wiatr / z wiatrem / boczny) plus wind_note. WIAZ jazde z tym: jak rozkladala sie moc/HR/kadencja po nawierzchni oraz jak wydatkowana byla moc pod wiatr vs z wiatrem i jaki to mialo wplyw na zmeczenie (koszt beztlenowy). Tylko konkretne pole ze statusem "parked" (np. pelna pogoda) traktuj jako niedostepne.
- KONWENCJA WIATRU (wind/terrain_impact.wind): tail_*_ms > 0 = wiatr W PLECY (pomaga, podbija predkosc), < 0 = POD WIATR (przeszkadza). Nie odwracaj tego.
- Zrodlem formy ORAZ W' jest ModelQ/MQ2 (TP/LTP/W'=HIE/PP w bloku "modelq"; W'bal w bloku "wprime" liczony na kanonicznych danych activity_record). Xert to TYLKO benchmark — nigdy nie podawaj Xerta jako zrodla.
- Wartosci liczbowe podawaj tak jak w W1 (nie przeliczaj ich na nowo).
- Jezyk: polski, zwiezle, bezposrednio, rzeczowo. Bez motywacyjnych frazesow i lania wody.

Zwroc WYLACZNIE surowy JSON (bez ```), o dokladnie takiej strukturze:
{
 "verdict": "jedno zdanie podsumowujace jazde",
 "highlights": ["trzy krotkie kluczowe fakty"],
 "synteza": [{"tytul": "...", "tekst": "...", "cytaty": ["blok.pole", "..."], "km": [od_km, do_km]}],
 "next": ["2-4 konkretne wnioski na nastepny raz, wyprowadzone z danych (nie generyk)"]
}
Pole "km" w sekcji: zakres kilometrow jazdy, ktorego sekcja glownie dotyczy (liczby z trace.km albo z listy "momenty_km"); jesli sekcja dotyczy calej jazdy -> null. Nie wymyslaj km spoza trace.km.
W "synteza" daj 6-7 sekcji pokrywajacych: obciazenie vs ModelQ, W' i regeneracje, pacing/splity/VI/decoupling, teren i wiatr (terrain_impact) a koszt i tempo, audyt energii, naped i technike, wellness poranny a jazde. KAZDA sekcja to POLACZENIE danych z cytatami; NIE powtarzaj tej samej mysli w kilku sekcjach. NIE generuj listy 'pytania'.\n\nPRZYKLAD (tak NIE wolno / tak MA byc):\nZLE: \"Jazda weszla w obciazenie: \\\"load.if\\\" 0.77, \\\"load.kj\\\" 639.\"\nDOBRZE: \"Jazda weszla w obciazenie: IF 0.77, praca 639 kJ.\" (a w \"cytaty\": [\"load.if\",\"load.kj\"]).\nZamieniaj KAZDY identyfikator blok.pole na ludzka etykiete z jednostka. Dotyczy verdict, highlights, tekst ORAZ next. Zaden z tych czterech nie moze zawierac kropkowanych nazw pol."""


def _for_prompt(w1: dict) -> dict:
    """Lekka kopia W1 do promptu: bez ciezkich serii i redundancji."""
    d = dict(w1)
    try:
        if "wprime" in d and isinstance(d["wprime"], dict):
            wp = dict(d["wprime"]); wp.pop("wbal_series", None); d["wprime"] = wp
    except Exception:
        pass
    d.pop("form_context", None)
    return d


_ID_RE = re.compile(r'["\u201e\u201d\u201c\u2019\u2018]?\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+\b["\u201e\u201d\u201c\u2019\u2018]?')

def _iter_texts(out):
    yield ("verdict", out.get("verdict", "") or "")
    for i, h in enumerate(out.get("highlights", []) or []):
        yield ("highlights[%d]" % i, h if isinstance(h, str) else "")
    for i, sec in enumerate(out.get("synteza", []) or []):
        if isinstance(sec, dict):
            yield ("synteza[%d].tytul" % i, sec.get("tytul", "") or "")
            yield ("synteza[%d].tekst" % i, sec.get("tekst", "") or "")
    for i, nx in enumerate(out.get("next", []) or []):
        yield ("next[%d]" % i, nx if isinstance(nx, str) else "")

def _has_ids(out):
    for _, t in _iter_texts(out):
        if t and _ID_RE.search(t):
            return True
    return False

def _scrub(t):
    if not t:
        return t
    t = _ID_RE.sub("", t)
    t = re.sub(r'["\u201e\u201d\u201c]{1,2}', "", t)
    t = re.sub(r'\s+([,.;:])', r'\1', t)
    t = re.sub(r'([,:])\s*(?=[,.;:])', "", t)
    t = re.sub(r'\(\s*\)', "", t)
    t = re.sub(r'\s{2,}', " ", t).strip()
    t = re.sub(r'\s+([,.;:])', r'\1', t)
    return t

def _scrub_out(out):
    if isinstance(out.get("verdict"), str):
        out["verdict"] = _scrub(out["verdict"])
    out["highlights"] = [_scrub(h) if isinstance(h, str) else h for h in (out.get("highlights") or [])]
    for sec in (out.get("synteza") or []):
        if isinstance(sec, dict):
            if isinstance(sec.get("tytul"), str):
                sec["tytul"] = _scrub(sec["tytul"])
            if isinstance(sec.get("tekst"), str):
                sec["tekst"] = _scrub(sec["tekst"])
    out["next"] = [_scrub(n) if isinstance(n, str) else n for n in (out.get("next") or [])]
    return out


def build_w2_v1(w1: dict, *, max_tokens: int = 4096) -> dict:
    from qgpt_client import qgpt_json
    base = (
        "Zanalizuj ta jazde na podstawie danych W1. Zwroc verdict, highlights, synteza, next.\n\n"
        "Dane W1 (JSON):\n"
        + json.dumps(_for_prompt(w1), ensure_ascii=False, default=str)
    )
    out = qgpt_json(base, system=W2_SYSTEM, max_tokens=max_tokens, temperature=0)
    if not isinstance(out, dict):
        raise ValueError("W2: model nie zwrocil obiektu JSON")
    # walidacja: pola tekstowe nie moga zawierac identyfikatorow blok.pole -> jedna korekta
    if _has_ids(out):
        bad = [f"{p}: {t}" for p, t in _iter_texts(out) if t and _ID_RE.search(t)][:8]
        corr = (
            base
            + "\n\nUWAGA: poprzednia odpowiedz miala BLAD - w polach tekstowych byly nazwy pol W1 (np. load.if). "
            "Przepisz CALOSC tak, by verdict/highlights/tekst/next NIE zawieraly ZADNYCH identyfikatorow typu "
            "blok.pole - zamien je na ludzkie etykiety z jednostka (IF 0.77, praca 639 kJ, XSS 98.1). "
            "Identyfikatory wylacznie w \"cytaty\". Bledne fragmenty:\n- "
            + "\n- ".join(bad)
        )
        try:
            out2 = qgpt_json(corr, system=W2_SYSTEM, max_tokens=max_tokens, temperature=0)
            if isinstance(out2, dict):
                out = out2
        except Exception:
            pass
    if _has_ids(out):
        out = _scrub_out(out)  # ostatnia deska ratunku (deterministycznie)
    out.setdefault("verdict", "")
    out.setdefault("highlights", [])
    out.setdefault("synteza", [])
    out.setdefault("pytania", [])
    out.setdefault("next", [])
    out["_meta"] = {"generator": "w2_llm", "source": "qgpt", "reads": "W1 only"}
    return out



# =====================================================================================
# W2 v2 (2026-09-28): analiza wg 4 pytan uzytkownika. Liczby licza sie w ride_report_facts
# (plan, wykonanie, konsekwencje, jedzenie); LLM dostaje GOTOWE porownania i ma wyciagnac
# wnioski, a NIE opisywac dane zdaniami. Klucze verdict/highlights/synteza/next zostaja
# (Telegram + mail w ride_report_notify ich uzywaja).
# =====================================================================================
W2V2_SYSTEM = """Jestes trenerem kolarskim (gravel, turystyka, bikepacking) w systemie QBot. Uzytkownik jest hobbysta.
Dostajesz: FAKTY (plan, wykonanie, konsekwencje, jedzenie) policzone deterministycznie przez program oraz W1 (szczegoly jazdy).
Uzytkownik chce z analizy dowiedziec sie TYLKO czterech rzeczy:
 1) co zaplanowal,
 2) jak to pojechal w ramach swoich mozliwosci (wobec planu, wobec formy z ktora wszedl w jazde, wobec podobnych jazd),
 3) jakie sa konsekwencje tej jazdy (zmeczenie, forma, ile odpoczynku, co z najblizszymi treningami),
 4) na co powinien zwrocic uwage.

ZASADY:
- NIE przepisuj danych na zdania. Kazde zdanie ma byc WNIOSKIEM (co z tego wynika), liczba tylko jako dowod.
- Liczby wylacznie z FAKTOW/W1, nie przeliczaj i nie wymyslaj. Nie wpisuj nazw pol (np. load.if) - pisz po ludzku.
- Forme, zmeczenie i gotowosc bierz WYLACZNIE z FAKTY.wykonanie.wejscie i FAKTY.konsekwencje (W1.modelq.current bywa sprzed nocnego przeliczenia).
- Obciazenie = skala planera i modelu formy (FAKTY.wykonanie.realnie.obciazenie). Nie uzywaj W1 load.xss.
- Slownik dla uzytkownika: swiezosc (TSB) ujemna = zmeczony; gotowosc ujemna = organizm zmeczony rano; EF = moc na uderzenie serca (wyzej = lepiej).
- Porownanie z podobnymi jazdami jest orientacyjne - wyciagaj wniosek tylko gdy roznica jest duza, i zaznacz ostroznosc.
- Brak planu -> napisz to wprost i ocen jazde wobec mozliwosci.
- PREDKOSC (OBOWIAZKOWO, w "wykonanie.tekst"): podaj srednia NETTO (w ruchu) i BRUTTO (z postojami) w km/h
  z FAKTY.wykonanie.predkosc i porownaj netto z TWOJA tabela predkosci (model_kmh: normalny/sport/wyscig,
  pole poziom, vs_model_pct). Dodaj postoje: realne (postoje_min) vs typowe z modelu (postoje_model_min).
  Gdy by_surface ma wiecej niz jedna klase - jedno zdanie, gdzie odstawales od tabeli. Tabela nie zna wiatru:
  jesli odchylka jest duza, sprawdz wiatr (W1.wind / terrain_impact) zanim wyciagniesz wniosek o formie.
  Gdy predkosc to null - napisz, ze brak danych o predkosci.
- Jezyk: polski, prosty (hobbysta, nie sportowiec zawodowy), konkretny, bez frazesow i motywowania.

Zwroc WYLACZNIE surowy JSON:
{
 "verdict": "jedno zdanie: ocena calej jazdy + najwazniejsza konsekwencja",
 "plan": "1-2 zdania: co bylo zaplanowane (dystans, czas, obciazenie, sposob jazdy)",
 "wykonanie": {"ocena": "w planie | za mocno | za slabo | nierowno | brak planu",
               "tekst": "3-6 zdan: predkosc netto/brutto wobec Twojej tabeli predkosci, jak pojechal wobec planu, wobec formy z ktora wszedl i wobec podobnych jazd",
               "odcinki": [{"km": [od, do], "ocena": "krotko", "tekst": "1 zdanie wniosku o tym odcinku"}]},
 "konsekwencje": "2-4 zdania: co jazda zrobila ze zmeczeniem i forma, kiedy wroci swiezosc, czy najblizsze treningi z TRENERA pasuja",
 "uwagi": [{"co": "krotki naglowek", "dlaczego": "przyczyna z danych", "zalecenie": "co konkretnie zrobic nastepnym razem"}],
 "dobrze": "jedna rzecz, ktora wyszla dobrze (z danych)",
 "jedzenie": "1 zdanie: plan jedzenia/picia vs wpisy (albo ze brak wpisow i czego to dotyczy)"
}
"uwagi": 2-3 pozycje, od najwazniejszej. "odcinki": tylko odcinki z FAKTY.wykonanie.odcinki (te same km)."""


def _trim_w1(w1):
    d = _for_prompt(w1)
    d.pop("trace", None)
    d.pop("plan_vs_actual", None)
    try:
        mq = dict(d.get("modelq") or {})
        cur = dict(mq.get("current") or {})
        for k in ("atl", "ctl", "tsb", "readiness"):
            cur.pop(k, None)
        mq["current"] = cur
        d["modelq"] = mq
        ld = dict(d.get("load") or {})
        ld.pop("xss", None)
        d["load"] = ld
    except Exception:
        pass
    return d


def _scrub_any(x):
    if isinstance(x, str):
        return _scrub(x)
    if isinstance(x, list):
        return [_scrub_any(v) for v in x]
    if isinstance(x, dict):
        return {k: (_scrub_any(v) if k != "km" else v) for k, v in x.items()}
    return x


def build_w2(w1: dict, *, max_tokens: int = 4096) -> dict:
    from qgpt_client import qgpt_json
    from qbot3.rides import ride_report_facts as _F
    ride_key = str((w1 or {}).get("ride_key") or "")
    facts = _F.build_facts(ride_key, w1)
    prompt = ("FAKTY (JSON):\n" + json.dumps(facts, ensure_ascii=False, default=str)
              + "\n\nW1 - szczegoly jazdy (JSON):\n" + json.dumps(_trim_w1(w1), ensure_ascii=False, default=str))
    out = qgpt_json(prompt, system=W2V2_SYSTEM, max_tokens=max_tokens, temperature=0)
    if not isinstance(out, dict):
        raise ValueError("W2: model nie zwrocil obiektu JSON")
    out = _scrub_any(out)
    wyk = out.get("wykonanie") if isinstance(out.get("wykonanie"), dict) else {"tekst": str(out.get("wykonanie") or "")}
    out["wykonanie"] = wyk
    uw = [u for u in (out.get("uwagi") or []) if isinstance(u, dict)][:3]
    out["uwagi"] = uw
    # zgodnosc wstecz (Telegram / mail / stary widok)
    out.setdefault("verdict", "")
    out["highlights"] = [u.get("co") for u in uw if u.get("co")][:3]
    out["synteza"] = [s for s in [
        {"tytul": "Co zaplanowałeś", "tekst": out.get("plan") or ""},
        {"tytul": "Jak pojechałeś", "tekst": wyk.get("tekst") or ""},
        {"tytul": "Konsekwencje", "tekst": out.get("konsekwencje") or ""},
        {"tytul": "Jedzenie i picie", "tekst": out.get("jedzenie") or ""},
        {"tytul": "Co wyszło dobrze", "tekst": out.get("dobrze") or ""},
    ] if s["tekst"]]
    out["next"] = [("%s: %s" % (u.get("co"), u.get("zalecenie"))) if u.get("co") else (u.get("zalecenie") or "")
                   for u in uw if u.get("zalecenie")]
    out["fakty"] = facts
    out["_meta"] = {"generator": "w2_llm_v2", "source": "qgpt", "reads": "FAKTY (ride_report_facts) + W1"}
    return out
