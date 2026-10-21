#!/usr/bin/env python3
"""Scenariusz trybu NAGRANIE QExt2 (sesja demo-2110, 21.10.2026) -- JEDNO zrodlo dla Karoo i symulatora w Garazu.

60 klatek (1 s), petla: plasko -> podjazd (moc rosnie, W' spada, BOMBA) -> szczyt (ODBUDOWA) -> zjazd -> plasko.
Jazda i trasa sa ZMYSLONE: brak wspolrzednych, nazw miejsc, prawdziwej wagi i progow Michala (CP 250 W, W' 16 kJ).
Czas jest przyspieszony (km i W' x10/x14), zeby w 60 s zmiescil sie caly podjazd; liczby na ekranie sa realistyczne.
Koniec petli ~ poczatek (W', tetno, km/h), zeby przejscie 59 -> 0 nie skakalo w kadrze.

Wynik (ten sam plik w dwoch miejscach):
  /opt/qbot/web/public/qext2-sim/demo-nagranie.json            -- symulator QExt2 w Garazu (scenariusz "Nagranie")
  /opt/qbot/qext2_deploy/app/src/main/assets/demo_nagranie.json -- QExt2 na Karoo (RecDemo.kt)

Uzycie: .venv/bin/python3 scripts/qext2_demo_scenario.py [--check | --podglad]
  --check:   tylko porownaj z zapisanymi plikami (kod 1 gdy rozjechane).
  --podglad: tabela klatek (nic nie zapisuje).
"""
from __future__ import annotations

import json
import math
import sys

OUT = (
    "/opt/qbot/web/public/qext2-sim/demo-nagranie.json",
    "/opt/qbot/qext2_deploy/app/src/main/assets/demo_nagranie.json",
)

CP = 250.0
CEIL = 225
W0 = 16000.0
LTHR = 165
KM_X = 10.0      # przyspieszenie drogi
W_X = 14.0       # przyspieszenie W'
TOTAL_KM = 84.0
KM0 = 42.0
W_START = 0.74   # W' na starcie petli (koniec petli wraca w okolice tej wartosci)
HR_START = 128.0
CASS = [10, 11, 12, 13, 15, 17, 19, 21, 24, 28, 32, 36, 40, 44, 52]
SEGS = [(0.0, 22.0, "PAVED"), (22.0, 40.0, "GRAVEL"), (40.0, 43.6, "PAVED"), (43.6, 46.8, "GRAVEL"),
        (46.8, 49.0, "LOOSE"), (49.0, 70.0, "PAVED"), (70.0, 84.0, "GRAVEL")]
SURF_N = {"PAVED": "asfalt", "GRAVEL": "szuter", "LOOSE": "trudny"}
WS = 4.5


def phase(t: int) -> str:
    if t < 14:
        return "flat"
    if t < 34:
        return "climb"
    if t < 39:
        return "top"
    if t < 54:
        return "descent"
    return "flat2"


def grade(t: int) -> float:
    p = phase(t)
    if p == "flat":
        return 0.6 + 0.4 * math.sin(t / 2.0)
    if p == "climb":
        return min(8.0, 3.0 + 1.6 * (t - 14)) + 0.7 * math.sin(t / 1.7)
    if p == "top":
        return 3.0 - 0.75 * (t - 34)
    if p == "descent":
        return -6.0 - min(3.0, 0.5 * (t - 39)) + 0.4 * math.sin(t)
    return 0.4 + 0.3 * math.sin(t / 2.0)


def power(t: int) -> int:
    p = phase(t)
    if p == "flat":
        return round(198 + 8 * math.sin(t / 1.3))
    if p == "climb":
        if t <= 30:
            return round(230 + (t - 14) * 6.6 + 6 * math.sin(t))
        return round(300 - (t - 30) * 6)
    if p == "top":
        return round(150 + (t - 34) * 5)
    if p == "descent":
        return 0 if t % 5 else 35
    return round(192 + 6 * math.sin(t / 1.3))


def wind_rel(t: int) -> int:
    p = phase(t)
    if p in ("flat", "flat2"):
        return 140          # skosem w twarz (czerwona strzalka)
    if p in ("climb", "top"):
        return 100          # z boku
    return 20               # w plecy na zjezdzie (zielona)


def speed_ms(P: float, g: float, head: float, surf: str, cap: float) -> float:
    m, gg, crr, cda, rho = 84.0, 9.81, {"PAVED": 0.0055, "GRAVEL": 0.011, "LOOSE": 0.018}[surf], 0.40, 1.2
    th = math.atan(g / 100.0)

    def f(v: float) -> float:
        air = v + head
        return v * m * gg * (crr * math.cos(th) + math.sin(th)) + 0.5 * rho * cda * air * abs(air) * v - P * 0.96

    lo, hi = 0.3, 22.0
    if f(hi) < 0:
        return min(hi, cap)
    if f(lo) > 0:
        return lo
    for _ in range(50):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return min(lo, cap)    # hamowanie na zjezdzie


def surf_at(km: float) -> str:
    for a, b, s in SEGS:
        if a <= km < b:
            return s
    return SEGS[-1][2]


def next_surface(km: float):
    """(km do zmiany, nazwa, dlugosc) najblizszej innej nawierzchni przed toba."""
    cur = surf_at(km)
    for a, b, s in SEGS:
        if a > km and s != cur:
            return a - km, SURF_N[s], b - a
    return None


def mmss(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return "%d:%02d" % (sec // 60, sec % 60)


def km_txt(km: float) -> str:
    return ("%.1f" % km).replace(".", ",") if km < 10 else str(int(round(km)))


def np_of(a: list[float]) -> int:
    if len(a) < 5:
        return round(sum(a) / max(1, len(a)))
    return round((sum(x ** 4 for x in a) / len(a)) ** 0.25)


def cap_at(t: int) -> float:
    return 13.6 + 0.6 * math.sin(t / 1.6)     # ~47-51 km/h na zjezdzie


def build() -> dict:
    frames = []
    km, w, hr = KM0, W0 * W_START, HR_START
    hist = [196.0] * 30          # historia mocy do NP 5 (wczesniejsza jazda)
    asc_done = 612.0
    np_ride, xss, kcal, rsrv = 198.0, 118.0, 1640.0, 64.0
    # pozycja startu podjazdu i jego dlugosc: najpierw przebieg "na sucho"
    climb_km = []
    k = KM0
    for t in range(60):
        head = -WS * math.cos(math.radians(wind_rel(t)))
        v = speed_ms(power(t), grade(t), head, surf_at(k), cap_at(t))
        if phase(t) == "climb":
            climb_km.append(k)
        k += v * KM_X / 1000.0
    c0, c1 = climb_km[0], climb_km[-1] + 0.05
    climb_gain = 0.0
    for t in range(60):
        g, P, rel = grade(t), power(t), wind_rel(t)
        head = -WS * math.cos(math.radians(rel))
        v = speed_ms(P, g, head, surf_at(km), cap_at(t))
        hist.append(float(P))
        hist = hist[-30:]
        # tetno z opoznieniem (na zjezdzie spada powoli, nie ponizej ~118)
        hr_t = max(118.0, min(176.0, 72 + 0.36 * P + (8 if phase(t) == "climb" else 0)))
        hr += (hr_t - hr) / (5.0 if hr_t > hr else 9.0)
        # W' bal (Skiba), przyspieszony
        if P > CP:
            w -= (P - CP) * W_X
        else:
            tau = 546 * math.exp(-0.01 * (CP - P)) + 316
            w += (W0 - w) * (1 - math.exp(-W_X / tau))
        w = max(0.0, min(W0, w))
        wp = round(w / W0 * 100)
        dkm = v * KM_X / 1000.0
        if g > 0:
            gain = g / 100.0 * dkm * 1000.0
            asc_done += gain
            if phase(t) == "climb":
                climb_gain += gain
        km += dkm
        np5 = np_of(hist)
        np_ride += (np5 - np_ride) * 0.01
        xss += max(0.0, (P / CP) ** 2 * 0.09)
        kcal += P * KM_X / 1000.0 / 0.23 / 4.184 / 3.0
        rsrv -= 0.03 + (0.1 if P > CP else 0.0)
        cad = 0 if P < 40 else round(max(68, min(98, 88 - max(0.0, g - 3) * 2.2 + 3 * math.sin(t / 1.9))))
        rear = CASS[0]
        if cad > 0:
            ideal = 40 * (cad / 60.0) * 2.15 / max(1.0, v)
            rear = min(CASS, key=lambda c: abs(c - ideal))
        # komunikat (kolejnosc jak w QExt2: W' < 55% ma pierwszenstwo)
        p = phase(t)
        if wp < 55:
            if P > CP + 10:
                msg = ("WPRIME", "W′ %d%%:" % wp, "BOMBA " + mmss(w / (P - CP)), "#FF8C8C")
            else:
                msg = ("WPRIME", "W′ %d%%:" % wp, "ODBUDOWA " + mmss((55 - wp) / 4.0 * 60), "#FF8C8C")
        elif p == "flat":
            msg = ("CLIMB", "za %s km: podjazd" % km_txt(max(0.1, c0 - km)), "%s km · 8%%" % km_txt(c1 - c0), "#FB923C")
        elif p == "climb":
            msg = ("CLIMB", "podjazd:", "zostało %s km · 8%%" % km_txt(max(0.1, c1 - km)), "#FB923C")
        elif p == "top":
            msg = ("CLIMB", "szczyt:", "↑ %d m" % round(climb_gain), "#4ADE80")
        elif p == "descent" and t < 47:
            msg = ("DESCENT", "zjazd:", "−9% " + SURF_N[surf_at(km)], "#FF8C8C")
        elif p == "descent":
            msg = ("RAIN", "deszcz za 35′:", "60%", "#60A5FA")
        else:
            ns = next_surface(km)
            msg = ("SURFACE", "za %s km:" % km_txt(ns[0]), "%s %s km" % (ns[1], km_txt(ns[2])), "#D9A04E") if ns \
                else ("SURFACE", "do mety:", "%s km" % km_txt(TOTAL_KM - km), "#D9A04E")
        dyn_k = ["ATD", "WIND", "water", "shop"][(t // 4) % 4]
        dyn = {
            "ATD": ("ATD", str(round(1150 - asc_done)), "m"),
            "WIND": ("WIND", "11", "km"),
            "water": ("water", km_txt(max(0.1, 49.5 - km)), "km"),
            "shop": ("shop", km_txt(max(0.1, 57.8 - km)), "km"),
        }[dyn_k]
        frames.append({
            "t": t, "phase": p, "km": round(km, 3), "grade": round(g, 1), "power": int(P), "speedKmh": round(v * 3.6, 1),
            "hr": round(hr), "cadence": cad, "rearCog": rear, "wbalPct": wp,
            "wbalTrend": "plummeting" if P > CP + 40 else ("falling" if P > CP else ("rising" if wp < 97 else "stable")),
            "np5": np5, "np": round(np_ride), "rsrv": round(rsrv), "xss": round(xss, 1), "kcal": round(kcal),
            "ascDone": round(asc_done), "ascLeft": max(0, round(1150 - asc_done)),
            "windRelDeg": rel, "windSignedMps": round(head, 1), "alarm": bool(p == "climb" and 24 <= t <= 31),
            "msg": {"kind": msg[0], "lead": msg[1], "accent": msg[2], "color": msg[3]},
            "dyn": {"kind": dyn[0], "value": dyn[1], "unit": dyn[2]},
        })
    return {
        "version": 1,
        "name": "Nagranie (trailer)",
        "opis": "Plasko -> podjazd 8% (W' spada, BOMBA) -> szczyt -> zjazd -> plasko. Dane zmyslone, czas przyspieszony.",
        "static": {
            "cpW": CP, "ceilingW": CEIL, "lthr": LTHR, "totalKm": TOTAL_KM, "tempC": 14, "windMps": WS, "sky": "PARTLY",
            "cogs": CASS, "gearFront": 40, "optCadLow": 80, "optCadHigh": 95, "hrAvg": 141, "cadAvg": 84, "avgKmh": 24.6,
            "segments": [{"from": a, "to": b, "surface": s} for a, b, s in SEGS], "stopsKm": [18.5, 61.0],
            "typEf": 1.42, "xssPlan": 160, "carbRate": 70, "fluidRate": 0.6, "batDrain": 6.5,
            "winNp": [176, 184, 191, 188, 205, 182, 179, 194, 199, 187, 183, 201], "winEf": [1.45, 1.44, 1.43, 1.44, 1.40, 1.43, 1.44, 1.42, 1.41, 1.42, 1.43, 1.39],
            "tempo": [[192, 25.1], [188, 24.2]], "movingSecAtStart": 6120, "stopsSec": 840,
        },
        "frames": frames,
    }


def main() -> int:
    d = build()
    if "--podglad" in sys.argv:
        print(" t faza     km    gr%   W   km/h  HR  kad  W'%  NP5 komunikat")
        for f in d["frames"]:
            m = f["msg"]
            print("%2d %-7s %6.2f %5.1f %4d %5.1f %3d %4d %4d %4d %s %s%s" % (
                f["t"], f["phase"], f["km"], f["grade"], f["power"], f["speedKmh"], f["hr"], f["cadence"],
                f["wbalPct"], f["np5"], m["lead"], m["accent"], "  [ALARM]" if f["alarm"] else ""))
        return 0
    data = json.dumps(d, ensure_ascii=False, indent=1)
    if "--check" in sys.argv:
        bad = 0
        for p in OUT:
            try:
                same = open(p, encoding="utf-8").read() == data
            except OSError:
                same = False
            print(("OK  " if same else "ROZNI SIE ") + p)
            bad += 0 if same else 1
        return 1 if bad else 0
    for p in OUT:
        with open(p, "w", encoding="utf-8") as f:
            f.write(data)
        print("zapisano", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
