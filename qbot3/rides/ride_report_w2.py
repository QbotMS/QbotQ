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
 "synteza": [{"tytul": "...", "tekst": "...", "cytaty": ["blok.pole", "..."]}],
 "next": ["2-4 konkretne wnioski na nastepny raz, wyprowadzone z danych (nie generyk)"]
}
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


def build_w2(w1: dict, *, max_tokens: int = 4096) -> dict:
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
