"""VO2max QBota z krzywej mocy ModelQ ([GARMIN-DANE] Etap 2, decyzja 2026-10-14).

Dlaczego nie Garmin: VO2max rowerowy Garmina zamrozony od 2025-03-08 (46) -- jazdy
z Karoo trafiaja do Garmina jako plik "Tacx", a Garmin liczy VO2max tylko na urzadzeniu
w trakcie nagrania. Dlaczego nie regresja HR<->moc z jazd: test 2026-10-14 na 23 jazdach
dal wyniki od -100 do 400 (teren: podjazdy, wiatr, dryf tetna) -- odrzucona.

Metoda: moc 5-minutowa z krzywej ModelQ  P5 = CP + W'/300 s  (stabilna, nie wymaga
jazdy "na maksa"; surowe MMP 5 min bywa zaszumione), wzor ACSM dla roweru:
    VO2max [ml/kg/min] = 10.8 * P5 / waga + 7
Wartosc "na kg" -- decyzja uzytkownika 2026-10-14 (waga widoczna obok na wykresie).
Kalibracja: luty 2025 QBot 40.6 vs Garmin 46 -- Garmin systematycznie ~+5 (znane
zawyzanie); NIE skalujemy do Garmina.
Dok.: docs/GARMIN_DANE.md
"""
from __future__ import annotations

ACSM_SLOPE = 10.8      # ml O2 / W / min
ACSM_REST = 7.0        # ml/kg/min (spoczynek + koszt pedalowania bez obciazenia)
P5_SECONDS = 300.0

# Granice sensownosci wejsc (poza nimi -> None, zamiast bzdury na wykresie).
CP_RANGE = (80.0, 600.0)
WPRIME_KJ_RANGE = (2.0, 60.0)
WEIGHT_RANGE = (40.0, 180.0)


def _in(v, rng) -> bool:
    return v is not None and rng[0] <= float(v) <= rng[1]


def p5_from_modelq(cp_w, wprime_kj) -> float | None:
    """Moc 5-minutowa z modelu CP/W' [W]."""
    if not (_in(cp_w, CP_RANGE) and _in(wprime_kj, WPRIME_KJ_RANGE)):
        return None
    return float(cp_w) + float(wprime_kj) * 1000.0 / P5_SECONDS


def vo2max_ml_kg(cp_w, wprime_kj, weight_kg) -> float | None:
    """VO2max [ml/kg/min] z krzywej ModelQ i wagi; None gdy brak/nierealne dane."""
    p5 = p5_from_modelq(cp_w, wprime_kj)
    if p5 is None or not _in(weight_kg, WEIGHT_RANGE):
        return None
    return round(ACSM_SLOPE * p5 / float(weight_kg) + ACSM_REST, 1)


def add_vo2max(rows: list[dict]) -> list[dict]:
    """Dopisuje 'vo2max_ml_kg' do wierszy serii (posortowanych po dniu).

    Waga przenoszona z ostatniego dnia z waga (w fitmodel_daily bywaja dziury),
    tak samo CP/W' -- zeby linia nie miala przerw w dni bez nowych danych.
    """
    last = {"cp_modelq_w": None, "wprime_modelq_kj": None, "weight_kg": None}
    for r in rows:
        for k in last:
            if r.get(k) is not None:
                last[k] = r[k]
        r["vo2max_ml_kg"] = vo2max_ml_kg(last["cp_modelq_w"], last["wprime_modelq_kj"], last["weight_kg"])
    return rows
