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
- Kazde twierdzenie opieraj na konkretnych polach W1 i wypisuj te pola w "cytaty" (np. "load.tss", "wprime.cutoff", "modelq.ride_impact").
- Pola ze statusem "parked" (wind, surface) oznaczaja BRAK DANYCH — nie twierdz niczego o wietrze ani nawierzchni jako fakt; mozesz najwyzej zaznaczyc, ze dane niedostepne.
- Zrodlem formy jest ModelQ (FTP/CP/W' z bloku "modelq"). Xert to TYLKO benchmark — nigdy nie podawaj Xerta jako zrodla formy.
- W' w bloku "wprime" jest oznaczone jako zewnetrzne (Xert) — jesli o nim mowisz, zaznacz ze to wartosc tymczasowa z Xerta.
- Wartosci liczbowe podawaj tak jak w W1 (nie przeliczaj ich na nowo).
- Jezyk: polski, zwiezle, bezposrednio, rzeczowo. Bez motywacyjnych frazesow i lania wody.

Zwroc WYLACZNIE surowy JSON (bez ```), o dokladnie takiej strukturze:
{
 "verdict": "jedno zdanie podsumowujace jazde",
 "highlights": ["trzy krotkie kluczowe fakty"],
 "synteza": [{"tytul": "...", "tekst": "...", "cytaty": ["blok.pole", "..."]}],
 "pytania": [{"q": "tresc pytania", "a": "odpowiedz", "cytaty": ["blok.pole", "..."]}],
 "next": ["2-4 konkretne wnioski na nastepny raz, wyprowadzone z danych (nie generyk)"]
}
W "synteza" daj 3-5 polaczen MIEDZY roznymi blokami (np. pacing x wiatr x W'), a nie powtorzenia pojedynczych blokow.
W "pytania" odpowiedz na KAZDE z zadanych pytan, w tej samej kolejnosci."""


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
    questions = "\n".join(f"{i+1}. {q}" for i, q in enumerate(W2_QUESTIONS))
    prompt = (
        "Pytania do odpowiedzenia (odpowiedz na kazde, w kolejnosci):\n"
        + questions
        + "\n\nDane W1 (JSON):\n"
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
