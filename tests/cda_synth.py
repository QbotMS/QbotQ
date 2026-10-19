# -*- coding: utf-8 -*-
"""Generator SZTUCZNYCH jazd do testow Centrum CdA (fitmodel/cda.py). 2026-10-19, audyt AERO (AERO_CDA_AUDIT_HANDOFF).

Jazda = fizyka krok 1 s: m*dv/dt = P*0,976/v - m*g*(nachylenie + Crr[nawierzchnia]) - 1/2*rho*CdA*v_pow*|v_pow|,
v_pow = v + wiatr*cos(kierunek_wiatru_skad - kurs)  (ta sama konwencja co cda.fit_ride).
Trasa = odcinki proste o zadanych kursach i nawierzchniach. Wynik w formacie, ktory przyjmuje cda.windows():
rows = (sec, moc, v, dystans, wysokosc, kadencja, temp, lat, lon, czas_epoch), trace = {"km": [...], "surface_cat": [...]}.
Bez bazy danych -- testy sa deterministyczne (stale ziarno). Gestosc powietrza domyslnie jak w cda (1013 hPa, 15 C)."""
from __future__ import annotations

import math
import random

G, ETA = 9.81, 0.976


def ride(legs, cda, crr, wind_ms=0.0, wind_from_deg=0.0, mass=117.0, power=180.0, noise=0.05, seed=1,
         rho=1013 * 100 / (287.05 * (15 + 273.15)), grade_true=0.0, grade_bias=0.0, power_wave=0.0, crr_scale=1.0):
    """legs: [(kurs_st, dlugosc_m, kategoria)]; crr: {kategoria: Crr}; grade_bias: blad wysokosci (nachylenie widziane
    przez QBota = grade_true + grade_bias); power_wave: amplituda zmian mocy co 60 s (0 = rowno); crr_scale: stan drogi
    (np. 1,2 = mokro, opor szutru i asfaltu x1,2)."""
    rnd = random.Random(seed)
    lat, lon, alt_seen, dist, v, t = 52.2, 21.0, 100.0, 0.0, 7.0, 0
    th = math.radians(wind_from_deg)
    rows, km, cats = [], [], []
    for heading, length, cat in legs:
        h = math.radians(heading)
        end = dist + length
        while dist < end:
            p = power * (1 + noise * rnd.gauss(0, 1)) * (1 + power_wave * math.sin(2 * math.pi * t / 60.0))
            p = max(1.0, p)
            va = v + wind_ms * math.cos(th - h)
            f = p * ETA / max(v, 0.5) - mass * G * (grade_true + crr[cat] * crr_scale) - 0.5 * rho * cda * va * abs(va)
            v = max(1.0, v + f / mass)
            dist += v
            alt_seen += v * (grade_true + grade_bias)
            lat += v * math.cos(h) / 111320.0
            lon += v * math.sin(h) / (111320.0 * math.cos(math.radians(lat)))
            rows.append((t, p, v, dist, alt_seen, 85.0, 15.0, lat, lon, 1.7e9 + t))
            if not km or dist / 1000.0 - km[-1] >= 0.05:
                km.append(dist / 1000.0)
                cats.append(cat)
            t += 1
    return rows, {"km": km, "surface_cat": cats}


def loop_legs(n_loops=4, leg_m=1500, cats=(1, 2, 1, 3)):
    """Prostokat: 4 kursy (0, 90, 180, 270 st.), nawierzchnie wg cats, powtorzony n_loops razy."""
    out = []
    for _ in range(n_loops):
        for hd, c in zip((0, 90, 180, 270), cats):
            out.append((hd, leg_m, c))
    return out
