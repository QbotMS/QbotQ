"""[PODJAZDY-SKALA etap A] Symulator calej jazdy po trasie - ramka 50 m (kanon QBot).

ZERO NOWYCH MIAR - wszystko z istniejacych kanonow:
- ramki 50 m: qbot_v2.route_elevation_samples (FRAME_M z route_elevation_engine),
  wygladzanie 200 m jak w raporcie;
- predkosc bazowa: empiryczna tabela nawierzchnia x nachylenie
  (qbot_route_time_tools.segment_speed_kmh, tryb 'normalny');
- przerwy: kanon stops_minutes (mikro 0.22 min/km rozproszone, krotkie co 9 km
  po 4.5 min) + DLUGIE wg deklaracji uzytkownika, pozycje _long_stop_positions;
- fizjologia: W' jak w kanonie wbal_replay (tau odbudowy, czynnik ciepla
  heat = clamp(1-0.007*(T-20), 0.85, 1.0), cf = clamp(heat, 0.88, 1.06));
- temperatura: per km z silnika meteo (per_segment, temp_c przy ETA);
- fizyka mocy i Crr nawierzchni: qbot3.routes.climb_score.

Wyjscie zastepuje chain_verdict (ten sam ksztalt + rozszerzenia): tryb
atak/tempo per podjazd wynika teraz z symulacji CALEGO przebiegu, nie tylko
sekwencji podjazdow.
"""
from __future__ import annotations

import math

from qbot_route_time_tools import (SHORT_BREAK_EVERY_KM, SHORT_BREAK_MIN,
                                   MICRO_MIN_PER_KM, _long_stop_positions,
                                   segment_speed_kmh)
from qbot3.routes.climb_score import (CRR, CRR_DEFAULT, BIKE_GEAR_KG,
                                      V_FLOOR_HARD_KMH, TEMPO_FRAC,
                                      WBAL_SAFE_PCT, power_req, _tau_s)

SMOOTH_WIN_M = 200.0      # okno wygladzania profilu (sweet-spot QBot)
WALK_KMH = 3.5            # tempo pchania
WALK_P_W = 40.0           # wysilek przy pchaniu (umowny, ponizej CP -> odbudowa wolna)
SERIES_STEP_KM = 0.5      # gestosc serii W' w wyniku


def _heat_cf(temp_c) -> float:
    if temp_c is None:
        return 1.0
    heat = max(1.0 - 0.007 * max(float(temp_c) - 20.0, 0.0), 0.85)
    return min(max(heat, 0.88), 1.06)


def _smooth(prof, win_m=SMOOTH_WIN_M):
    n = len(prof)
    if n < 3:
        return [p[1] for p in prof]
    ds = [p[0] for p in prof]
    es = [p[1] for p in prof]
    half = win_m / 2.0
    j0 = j1 = 0
    out = []
    for i in range(n):
        lo, hi = ds[i] - half, ds[i] + half
        while j0 < n and ds[j0] < lo:
            j0 += 1
        while j1 < n and ds[j1] <= hi:
            j1 += 1
        seg = es[j0:j1] if j1 > j0 else [es[i]]
        out.append(sum(seg) / len(seg))
    return out


def _cat_lookup(ribbon, km):
    """kategoria nawierzchni (1-5) dla km; ribbon = [{a,b,k}] posortowany."""
    for r in ribbon or []:
        if r["a"] <= km <= r["b"]:
            return r["k"]
    return None


def _temp_lookup(per, km):
    """temp_c z meteo per_segment dla km (najblizszy punkt <= km, fallback pierwszy)."""
    if not per:
        return None
    best = None
    for p in per:
        pk = float(p.get("km") or 0.0)
        if pk <= km:
            best = p
        else:
            break
    return (best or per[0]).get("temp_c")


def simulate_ride(frames, ribbon, weather_per, cp_w, wprime_kj, mass_rider_kg,
                  long_stops=0, long_stop_min_total=0.0, mode="normalny",
                  climbs=None):
    """frames: [(dist_m, elev_m)] z route_elevation_samples (50 m).
    Zwraca dict zgodny z chain_verdict + rozszerzenia (series, heat, walk...)."""
    if not frames or len(frames) < 3 or not cp_w:
        return None
    cp = float(cp_w)
    wp_j = float(wprime_kj or 20.0) * 1000.0
    mass = float(mass_rider_kg) + BIKE_GEAR_KG
    total_km = frames[-1][0] / 1000.0

    smoothed = _smooth(frames)
    # przerwy kanonu: progi km
    micro_rest_s_per_km = MICRO_MIN_PER_KM * 60.0
    short_every_km = SHORT_BREAK_EVERY_KM
    short_rest_s = SHORT_BREAK_MIN * 60.0
    n_long = int(long_stops or 0)
    long_positions = [f * total_km for f in _long_stop_positions(n_long)]
    long_each_s = (float(long_stop_min_total or 0.0) * 60.0 / n_long) if n_long else 0.0

    wbal = wp_j
    t_s = 0.0
    move_s = 0.0
    rest_s_total = 0.0
    next_short_km = short_every_km
    next_micro_km = 1.0
    li = 0  # indeks nastepnego dlugiego postoju
    series = [(0.0, 100.0)]
    next_series_km = SERIES_STEP_KM
    min_wbal, min_wbal_km = wp_j, 0.0
    walk_m = 0.0
    capped_frames = []  # km, gdzie polityka przycieła moc (tempo)
    cf_on_climbs = []

    climb_ranges = [(c.get("i"), float(c.get("a_km") or 0), float(c.get("b_km") or 0))
                    for c in (climbs or [])]
    climb_state = {i: {"in": None, "min": 100.0, "capped": False} for i, _, _ in climb_ranges}

    def _rest(dur_s, cp_eff):
        nonlocal wbal, t_s, rest_s_total
        deficit = wp_j - wbal
        wbal = wp_j - deficit * math.exp(-dur_s / _tau_s(cp_eff, 0.0))
        t_s += dur_s
        rest_s_total += dur_s

    n = len(frames)
    for i in range(1, n):
        d0, d1 = frames[i - 1][0], frames[i][0]
        L = d1 - d0
        if L <= 0:
            continue
        km = d1 / 1000.0
        grade = (smoothed[i] - smoothed[i - 1]) / L * 100.0
        cat = _cat_lookup(ribbon, km)
        crr = CRR.get(cat, CRR_DEFAULT)
        sclass = "paved" if cat == 1 else ("unpaved" if cat in (2, 3, 4, 5) else None)
        temp = _temp_lookup(weather_per, km)
        cf = _heat_cf(temp)
        cp_eff = cp * cf
        wp_eff = wp_j * cf
        if wbal > wp_eff:
            wbal = wp_eff

        in_climb = None
        for ci, a, b in climb_ranges:
            if a <= km <= b:
                in_climb = ci
                break
        if in_climb is not None:
            cf_on_climbs.append(cf)
            if climb_state[in_climb]["in"] is None:
                climb_state[in_climb]["in"] = 100.0 * wbal / wp_j

        v = segment_speed_kmh(grade, sclass, mode)
        p = power_req(grade, v, mass, crr)

        if p > cp_eff:
            t_frame = L / (v / 3.6)
            cost = (p - cp_eff) * t_frame
            if wbal - cost < WBAL_SAFE_PCT / 100.0 * wp_eff:
                # polityka: przytnij do tempa (TEMPO_FRAC * cp_eff), zwolnij
                p_cap = TEMPO_FRAC * cp_eff
                lo, hi = V_FLOOR_HARD_KMH, max(v, V_FLOOR_HARD_KMH + 0.1)
                for _ in range(30):
                    mid = (lo + hi) / 2.0
                    if power_req(grade, mid, mass, crr) > p_cap:
                        hi = mid
                    else:
                        lo = mid
                v = max(lo, V_FLOOR_HARD_KMH)
                p = power_req(grade, v, mass, crr)
                capped_frames.append(km)
                if in_climb is not None:
                    climb_state[in_climb]["capped"] = True
        if wbal <= 0.0 and p > cp_eff:
            # bak pusty a wciaz ponad CP -> pchanie
            v = WALK_KMH
            p = WALK_P_W
            walk_m += L

        t_frame = L / (v / 3.6)
        if p > cp_eff:
            wbal -= (p - cp_eff) * t_frame
            wbal = max(wbal, 0.0)
        else:
            deficit = wp_eff - wbal
            wbal = wp_eff - deficit * math.exp(-t_frame / _tau_s(cp_eff, p))
        t_s += t_frame
        move_s += t_frame

        if wbal < min_wbal:
            min_wbal, min_wbal_km = wbal, km
        if in_climb is not None:
            climb_state[in_climb]["min"] = min(climb_state[in_climb]["min"],
                                               100.0 * wbal / wp_j)

        # przerwy kanonu (mikro rozproszone co 1 km, krotkie co 9 km, dlugie wg pozycji)
        if km >= next_micro_km:
            _rest(micro_rest_s_per_km, cp_eff)
            next_micro_km += 1.0
        if km >= next_short_km:
            _rest(short_rest_s, cp_eff)
            next_short_km += short_every_km
        while li < len(long_positions) and km >= long_positions[li]:
            _rest(long_each_s, cp_eff)
            li += 1

        if km >= next_series_km:
            series.append((round(km, 2), round(100.0 * wbal / wp_j)))
            next_series_km += SERIES_STEP_KM

    series.append((round(total_km, 2), round(100.0 * wbal / wp_j)))

    # per podjazd: tryb z symulacji
    per_climb = []
    n_tempo = 0
    first_tempo = None
    for ci, _a, _b in climb_ranges:
        st = climb_state[ci]
        if st["in"] is None:
            continue
        mode_c = "tempo" if st["capped"] else "atak"
        if mode_c == "tempo":
            n_tempo += 1
            if first_tempo is None:
                first_tempo = ci
        per_climb.append({"i": ci, "mode": mode_c,
                          "wbal_in_pct": round(st["in"]),
                          "wbal_min_pct": round(st["min"])})

    min_pct = round(100.0 * min_wbal / wp_j)
    avg_cf = (sum(cf_on_climbs) / len(cf_on_climbs)) if cf_on_climbs else 1.0
    heat_cut_pct = round((1.0 - avg_cf) * 100.0)

    if n_tempo == 0:
        verdict = ("Symulacja calej trasy: mozesz atakowac wszystkie podjazdy - "
                   "min W\u2032 ~%d%% (km %.1f)." % (min_pct, min_wbal_km))
    else:
        ataki = [str(o["i"]) for o in per_climb if o["mode"] == "atak"]
        verdict = ("Symulacja calej trasy: atakuj %s; od #%s jedz tempem "
                   "(min W\u2032 ~%d%% przy km %.1f)."
                   % ((", ".join("#" + a for a in ataki) or "\u2014"),
                      first_tempo, min_pct, min_wbal_km))
    if heat_cut_pct >= 2:
        verdict += " Upal tnie efektywne CP na podjazdach o ~%d%%." % heat_cut_pct
    if walk_m >= 50:
        verdict += " Ryzyko pchania: ~%d m." % round(walk_m)

    return {"verdict": verdict, "per_climb": per_climb,
            "series": [[a, b] for a, b in series],
            "min_wbal_pct": min_pct, "min_wbal_km": round(min_wbal_km, 1),
            "heat_cut_pct": heat_cut_pct, "walk_m": round(walk_m),
            "moving_h": round(move_s / 3600.0, 2),
            "total_h": round((move_s + rest_s_total) / 3600.0, 2),
            "params": {"cp_w": round(cp), "wprime_kj": round(wp_j / 1000.0, 1),
                       "frame_m": 50, "mode": mode,
                       "long_stops": n_long,
                       "long_stop_min_total": round(float(long_stop_min_total or 0.0))}}
