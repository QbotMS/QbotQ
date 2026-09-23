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


def details(sport: str, phase: str | None, dur_min: int, cut: bool = False, n: int = 0) -> dict:
    phase = phase if phase in DOSE else "bz"
    if sport == "sila":
        acc = ACCENTS[n % len(ACCENTS)]
        var = (n // len(ACCENTS)) % 4
        rounds, work, rest, note = DOSE[phase]
        if cut:
            rounds, note = 1, "wersja minimum: jedna runda całego obwodu"
        ex = [{"group": g, "name": opts[var % len(opts)]} for g, opts in BASE]
        extra = EXTRA[acc][var % 2]
        ex += [{"group": "➕ " + acc, "name": e} for e in extra]
        lines = [f"Obwód na całe ciało · akcent: {acc} · {rounds} × obwód · {work} · przerwa między rundami {rest}",
                 "Rozgrzewka 5′: krążenia ramion i bioder, 10 przysiadów bez obciążenia, 10 pompek na kolanach."]
        lines += [f"{i + 1}. {e['name']}" + (f" ({e['group']})" if not e["group"].startswith("➕") else " ➕") for i, e in enumerate(ex)]
        lines.append(f"Uwaga: {note}. Oddychaj, bez bólu stawów; gdy za łatwo — trudniejszy wariant lub cięższy hantel.")
        return {"title": f"Siła obwodowa — akcent {acc}", "accent": acc, "rounds": rounds, "exercises": ex, "text": "\n".join(lines)}
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
