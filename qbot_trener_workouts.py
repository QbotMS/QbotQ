"""TRENER - zestawy cwiczen: sila obwodowa na cale cialo (z rotujacym akcentem) i wioslarz, zalezne od okresu sezonu.

Sprzet: hantle, laweczka, masa ciala. Czysta funkcja details(sport, phase, dur_min, cut, n) -> dict (testy:
tests/test_trener_workouts.py). n = numer kolejnej sesji silowej uzytkownika (0,1,2,...) - wyznacza akcent
(klatka+ramiona -> plecy -> nogi -> brzuch -> ...) i wariant cwiczen (rotacja puli, zeby sie nie nudzilo).
"""
from __future__ import annotations

ACCENTS = ["klatka + ramiona", "plecy", "nogi", "brzuch"]

# obwod bazowy: 6 slotow (cale cialo); kazdy slot ma warianty rotowane co cykl akcentow
BASE = [
    ("nogi", ["Goblet squat z hantlem", "Wykroki w miejscu z hantlami", "Przysiad bułgarski (noga na ławce)", "Wejścia na ławkę z hantlami"]),
    ("klatka", ["Pompki (na kolanach → klasyczne → stopy na ławce)", "Wyciskanie hantli na ławce", "Pompki szerokie", "Wyciskanie hantli na ławce, chwyt neutralny"]),
    ("plecy", ["Wiosłowanie hantlem jednorącz (ręka i kolano na ławce)", "Wiosłowanie hantlami w opadzie", "Superman leżąc", "Wiosłowanie hantlem jednorącz, pauza 1 s w górze"]),
    ("barki", ["Wyciskanie hantli nad głowę siedząc", "Unoszenie hantli bokiem", "Wyciskanie hantli nad głowę stojąc", "Pike push-up (pompka w pozycji V)"]),
    ("brzuch", ["Deska (plank)", "Dead bug", "Deska boczna (na każdą stronę)", "Hollow hold"]),
    ("tył ciała", ["Hip thrust na ławce z hantlem", "Martwy ciąg rumuński z hantlami", "Most biodrowy na jednej nodze", "Good morning z hantlem"]),
]
EXTRA = {
    "klatka + ramiona": [["Wyciskanie hantli na ławce", "Dipy na ławce (triceps) + uginanie hantli (biceps)"],
                         ["Rozpiętki z hantlami na ławce", "Pompki diamentowe (triceps) + uginanie młotkowe (biceps)"]],
    "plecy": [["Wiosłowanie hantlami oburącz w opadzie", "Y-T-W leżąc na brzuchu (łopatki)"],
              ["Pullover z hantlem na ławce", "Odwrotne rozpiętki w opadzie (tył barków)"]],
    "nogi": [["Przysiad bułgarski (noga na ławce)", "Wspięcia na palce z hantlami (łydki)"],
             ["Wykroki chodzone z hantlami", "Martwy ciąg na jednej nodze z hantlem"]],
    "brzuch": [["Mountain climbers", "Unoszenie nóg leżąc na ławce"],
               ["Deska z dotykaniem barku", "Russian twist z hantlem"]],
}
# dawkowanie wg okresu (Sezon): rundy, praca, przerwa miedzy rundami, uwaga
DOSE = {
    "rt": (2, "40 s pracy / 20 s przerwy", "1 min", "lekko — wejście w siłę, bez zakwasów; technika przed ciężarem"),
    "bz": (3, "8–12 powtórzeń, ciężej (2 powtórzenia w zapasie)", "1–2 min", "główny czas na siłę; 4 rundy, gdy czujesz się dobrze"),
    "bd": (3, "8–10 powtórzeń; ćwiczenia na jedną nogę po 8/noga", "1,5 min", "pod podjazdy: nogi i tułów stabilne"),
    "tp": (2, "8 powtórzeń, umiarkowanie", "1 min", "podtrzymanie; nigdy dzień przed długą jazdą"),
    "rg": (1, "10 powtórzeń, lekko", "1 min", "regeneracja — ruch, nie trening"),
    "ev": (1, "10 powtórzeń, lekko", "1 min", "tylko podtrzymanie"),
}
ROW = {
    "rt": ("Spokojnie", ["Rozgrzewka 5′ luźno", "Główna część: równo, 18–22 pociągnięć/min, tempo rozmowy", "Schłodzenie 3′"]),
    "bz": ("Tempo umiarkowane", ["Rozgrzewka 5′", "3 × 8′ umiarkowanie (22–24 pociągnięć/min), między nimi 2′ luzu", "Schłodzenie 3′"]),
    "bd": ("Mocniejsze odcinki", ["Rozgrzewka 6′", "6 × 3′ mocniej (24–26 pociągnięć/min), między nimi 2′ luzu", "Schłodzenie 4′"]),
    "tp": ("Lekko", ["Rozgrzewka 5′", "Równo i lekko, 18–20 pociągnięć/min", "Schłodzenie 3′"]),
    "rg": ("Luźno", ["Cały czas luźno, 18 pociągnięć/min — rozruszanie"]),
    "ev": ("Luźno", ["Cały czas luźno"]),
}
ROW_TECH = "Technika: nogi → tułów → ręce przy pociągnięciu, w powrocie odwrotnie; plecy proste, nie szarp rękami."


BAD_AVG = 2.0  # srednia ocen cwiczenia <= 2 -> Trener go unika (qbot_trener_ratings.exercise_prefs)

# Pomijanie partii (opts.skip_groups sesji, np. z prosby do AI): partia -> sloty obwodu i akcenty, ktore wypadaja
SKIP_GROUPS = {
    "nogi": ({"nogi", "tył ciała"}, {"nogi"}),
    "klatka": ({"klatka"}, {"klatka + ramiona"}),
    "ramiona": (set(), {"klatka + ramiona"}),
    "plecy": ({"plecy"}, {"plecy"}),
    "barki": ({"barki"}, set()),
    "brzuch": ({"brzuch"}, {"brzuch"}),
}


def clean_skip(skip) -> list:
    return [g for g in SKIP_GROUPS if g in (skip or [])]


def _ok(prefs: dict, name: str) -> bool:
    v = prefs.get(name)
    return v is None or v > BAD_AVG


def _pick(opts: list, var: int, prefs: dict | None) -> tuple[str, bool]:
    """Wariant z rotacji; gdy nisko oceniony - najlepiej oceniony inny wariant tej grupy (nieoceniony = 3)."""
    first = opts[var % len(opts)]
    if not prefs or _ok(prefs, first):
        return first, False
    cands = [opts[(var + k) % len(opts)] for k in range(1, len(opts))]
    good = [o for o in cands if _ok(prefs, o)]
    if not good:
        return first, False
    return max(good, key=lambda o: prefs.get(o, 3.0)), True


def details(sport: str, phase: str | None, dur_min: int, cut: bool = False, n: int = 0, prefs: dict | None = None,
            skip: list | None = None) -> dict:
    phase = phase if phase in DOSE else "bz"
    if sport == "sila":
        skip = clean_skip(skip)
        no_slot = set().union(*[SKIP_GROUPS[g][0] for g in skip]) if skip else set()
        no_acc = set().union(*[SKIP_GROUPS[g][1] for g in skip]) if skip else set()
        acc = None
        for k in range(len(ACCENTS)):   # akcent z rotacji; pominieta partia -> nastepny dozwolony
            a = ACCENTS[(n + k) % len(ACCENTS)]
            if a not in no_acc:
                acc = a
                break
        var = (n // len(ACCENTS)) % 4
        rounds, work, rest, note = DOSE[phase]
        if cut:
            rounds, note = 1, "wersja minimum: jedna runda całego obwodu"
        ex = []
        for g, opts in BASE:
            if g in no_slot:
                continue
            nm, sw = _pick(opts, var, prefs)
            ex.append({"group": g, "name": nm, "swapped": sw})
        if acc:
            extra, esw = EXTRA[acc][var % 2], False
            if prefs and not all(_ok(prefs, e) for e in extra):
                alt = EXTRA[acc][(var + 1) % 2]
                if all(_ok(prefs, e) for e in alt):
                    extra, esw = alt, True
            ex += [{"group": "➕ " + acc, "name": e, "swapped": esw} for e in extra]
        bez = (" (bez: " + ", ".join(skip) + ")") if skip else ""
        warm = ("Rozgrzewka 5′: krążenia ramion i bioder, 10 pompek na kolanach, 10 krążeń tułowia." if "nogi" in skip
                else "Rozgrzewka 5′: krążenia ramion i bioder, 10 przysiadów bez obciążenia, 10 pompek na kolanach.")
        lines = [f"Obwód{bez} · akcent: {acc or '—'} · {rounds} × obwód · {work} · przerwa między rundami {rest}", warm]
        lines += [f"{i + 1}. {e['name']}" + (f" ({e['group']})" if not e["group"].startswith("➕") else " ➕")
                  + (" · zamiana wg Twoich ocen" if e.get("swapped") else "") for i, e in enumerate(ex)]
        if skip:
            lines.append("Pominięte na Twoją prośbę: " + ", ".join(skip) + ".")
        lines.append(f"Uwaga: {note}. Oddychaj, bez bólu stawów; gdy za łatwo — trudniejszy wariant lub cięższy hantel.")
        return {"title": f"Siła obwodowa{bez} — akcent {acc or 'brak'}", "accent": acc, "rounds": rounds, "exercises": ex,
                "skip": skip, "text": "\n".join(lines)}
    if sport == "wiosl":
        name, steps = ROW[phase]
        if cut:
            steps = [f"Wersja minimum: {dur_min}′ równo i spokojnie"]
        return {"title": f"Wioślarz — {name.lower()} {dur_min}′", "steps": steps, "text": "\n".join([f"Wioślarz {dur_min}′ · {name}"] + steps + [ROW_TECH])}
    if sport == "joga":
        return {"title": f"Joga {dur_min}′", "text": f"Joga {dur_min}′: biodra, tył uda, odcinek piersiowy — spokojnie, bez rozciągania na siłę."}
    return {"title": "", "text": ""}


def strength_index(c, username: str, session: dict) -> int:
    """Numer kolejnej sesji silowej (do rotacji akcentu): ile silowych (nie pominietych) bylo przed ta sesja."""
    c.execute("SELECT COUNT(*) AS n FROM qbot_v2.trainer_session WHERE username=%s AND sport='sila' AND status<>'skip' "
              "AND (day < %s OR (day = %s AND id < %s))", (username, session["day"], session["day"], session["id"]))
    r = c.fetchone()
    return int(r["n"] if isinstance(r, dict) else r[0])
