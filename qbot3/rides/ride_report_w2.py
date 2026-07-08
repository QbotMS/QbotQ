# -*- coding: utf-8 -*-
"""W2 — analiza raportu z jazdy przez LLM (czyta TYLKO W1, cytuje pola, nic nie zmysla).

Nie rejestruje narzedzia Alberta (brak sprzezenia z _SYSTEM). Uzywa wspolnego klienta LLM
(qgpt_json) — tego samego, ktorym posluguje sie reszta QBota.
"""
import json

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
- Kazde twierdzenie opieraj na konkretnych polach W1 i wypisuj te pola w "cytaty" (np. "load.xss", "wprime.cutoff", "modelq.ride_impact").
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
W "synteza" daj 6-7 sekcji pokrywajacych: obciazenie vs ModelQ, W' i regeneracje, pacing/splity/VI/decoupling, teren i wiatr (terrain_impact) a koszt i tempo, audyt energii, naped i technike, wellness poranny a jazde. KAZDA sekcja to POLACZENIE danych z cytatami; NIE powtarzaj tej samej mysli w kilku sekcjach. NIE generuj listy 'pytania'."""


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


def build_w2(w1: dict, *, max_tokens: int = 4096) -> dict:
    from qgpt_client import qgpt_json
    prompt = (
        "Zanalizuj ta jazde na podstawie danych W1. Zwroc verdict, highlights, synteza, next.\n\n"
        "Dane W1 (JSON):\n"
        + json.dumps(_for_prompt(w1), ensure_ascii=False, default=str)
    )
    out = qgpt_json(prompt, system=W2_SYSTEM, max_tokens=max_tokens, temperature=0)
    if not isinstance(out, dict):
        raise ValueError("W2: model nie zwrocil obiektu JSON")
    out.setdefault("verdict", "")
    out.setdefault("highlights", [])
    out.setdefault("synteza", [])
    out.setdefault("pytania", [])
    out.setdefault("next", [])
    out["_meta"] = {"generator": "w2_llm", "source": "qgpt", "reads": "W1 only"}
    return out
