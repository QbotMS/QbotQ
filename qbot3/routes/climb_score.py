"""[PODJAZDY-SKALA] Ocena podjazdu w skali -2..+2, wyskalowana do formy uzytkownika.

Skala (pomysl uzytkownika, 2026-08-10):
  +2 na pelnej / +1 spokojnie / 0 podjade / -1 ledwo / -2 nie podjade

Zasady projektowe (uzgodnione):
- SKALOWALNOSC DO CP: krzywa "mocy osiagalnej" to kwantyle %CP z historii
  (qbot_v2.ride_climb_efforts), mnozone przez CP z dnia oceny.
- Krzywa uczy sie WYLACZNIE na wysilkach effort_class='na_limicie' i bez
  kwarantanny miernika (jazdy z oszczedzaniem sie nie zanizaja sufitu).
- W'bal NIE jest wyrocznia (bylo przeskalowywane) -- W' uzywamy tylko jako
  budzetu deficytu przy rozstrzyganiu -1 vs -2.
- Nawierzchnia: Crr per 100 m segment (pole 'sk' z raportu, kategorie 1-5).
- Biegi: minimalna godna predkosc = kadencja ~55 na najlzejszym biegu
  przypisanej kasety; twarde dno = 4.3 km/h (granica rownowagi).
"""
from __future__ import annotations

import math
import time

CRR = {1: 0.006, 2: 0.010, 3: 0.014, 4: 0.020, 5: 0.028}
CRR_DEFAULT = 0.010
WHEEL_CIRC_M = 2.18          # 700c z opona ~50 mm
BIKE_GEAR_KG = 14.0          # rower + osprzet + bidony
V_FLOOR_HARD_KMH = 4.3       # ponizej tego rownowaga/pchanie
CAD_DIGN_RPM = 55.0          # "spokojna minimalna" kadencja
V_DIGN_MIN_KMH = 6.0         # godne minimum tempa; ponizej = mielenie/rownowaga
LABELS = {2: "na pelnej", 1: "spokojnie", 0: "podjade", -1: "ledwo", -2: "nie podjade"}

_CACHE = {"ts": 0.0, "pts": None}
_CACHE_TTL_S = 900.0
# fallback gdy baza niedostepna (stan na 2026-08-10, P75/P90 %CP)
_FALLBACK = [(120, 105.6, 117.9), (270, 98.6, 107.4), (540, 95.2, 100.5), (1080, 84.8, 99.1)]


def achievable_curve(conn):
    """Punkty (t_mid_s, p75_pct_cp, p90_pct_cp) z czystej historii; cache 15 min."""
    now = time.time()
    if _CACHE["pts"] and now - _CACHE["ts"] < _CACHE_TTL_S:
        return _CACHE["pts"]
    try:
        rows = conn.execute(
            "with b as (select case when moving_s < 180 then 120 "
            " when moving_s < 360 then 270 when moving_s < 720 then 540 "
            " else 1080 end tmid, pct_cp from qbot_v2.ride_climb_efforts "
            " where not quarantined and effort_class='na_limicie' "
            " and pct_cp is not null and moving_s >= 60) "
            "select tmid, percentile_cont(0.75) within group (order by pct_cp) as p75, "
            " percentile_cont(0.9) within group (order by pct_cp) as p90, count(*) as n "
            "from b group by tmid having count(*) >= 5 order by tmid").fetchall()

        def _g(r, key, idx):
            try:
                return float(r[key])
            except (TypeError, KeyError, IndexError):
                return float(r[idx])
        pts = [(_g(r, "tmid", 0), _g(r, "p75", 1), _g(r, "p90", 2)) for r in rows]
        if len(pts) >= 2:
            _CACHE.update(ts=now, pts=pts)
            return pts
    except Exception:
        pass
    return _FALLBACK


def ach_pct(pts, t_s: float, q: str = "p75") -> float:
    """Interpolacja %CP osiagalnego dla czasu t_s (liniowo po log t, z klamra)."""
    idx = 1 if q == "p75" else 2
    t = max(60.0, float(t_s))
    if t <= pts[0][0]:
        return pts[0][idx]
    if t >= pts[-1][0]:
        return pts[-1][idx]
    for (t0, *v0), (t1, *v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            f = (math.log(t) - math.log(t0)) / (math.log(t1) - math.log(t0))
            return v0[idx - 1] + f * (v1[idx - 1] - v0[idx - 1])
    return pts[-1][idx]


def power_req(grade_pct: float, v_kmh: float, mass_total: float, crr: float) -> float:
    """Moc wymagana [W]: grawitacja + toczenie + powietrze (jak _climb_power,
    ale z Crr zaleznym od nawierzchni)."""
    v = max(0.5, float(v_kmh)) / 3.6
    grav = mass_total * 9.81 * (float(grade_pct) / 100.0) * v
    roll = mass_total * 9.81 * crr * v
    air = 0.5 * 1.2 * 0.4 * v ** 3
    return max(0.0, grav + roll + air)


def _v_at_cadence(cad_rpm: float, front_t: int, cog_t: int) -> float:
    """Predkosc [km/h] przy danej kadencji na przelozeniu front/cog."""
    return cad_rpm / 60.0 * (front_t / cog_t) * WHEEL_CIRC_M * 3.6


def _cadence_at_v(v_kmh: float, front_t: int, cog_t: int) -> float:
    return v_kmh / 3.6 / WHEEL_CIRC_M * 60.0 / (front_t / cog_t)


def _seg_stats(segments):
    """(sr. nachylenie wazone, sr. Crr wazone, crux: max nachylenie 2 kolejnych
    segmentow ~200 m + jego Crr)."""
    tot = g_acc = c_acc = 0.0
    grades, crrs, lens = [], [], []
    for sg in segments or []:
        L = float(sg.get("len_m") or 0)
        if L <= 0:
            continue
        g = float(sg.get("grade") if sg.get("grade") is not None else 0.0)
        crr = CRR.get(sg.get("sk"), CRR_DEFAULT)
        tot += L
        g_acc += g * L
        c_acc += crr * L
        grades.append(g)
        crrs.append(crr)
        lens.append(L)
    if tot <= 0:
        return None
    crux_g, crux_crr = grades[0], crrs[0]
    for i in range(len(grades)):
        if i + 1 < len(grades):
            g2 = (grades[i] * lens[i] + grades[i + 1] * lens[i + 1]) / (lens[i] + lens[i + 1])
            c2 = max(crrs[i], crrs[i + 1])
        else:
            g2, c2 = grades[i], crrs[i]
        if g2 > crux_g:
            crux_g, crux_crr = g2, c2
    return g_acc / tot, c_acc / tot, crux_g, crux_crr, tot


def score_climb(conn, climb: dict, cp_w: float, wprime_kj: float | None,
                mass_rider_kg: float, cogs, front_t: int, cassette_code: str | None):
    """Ocena -2..+2 dla podjazdu z raportu (dict z segments/length_m/avg_pct)."""
    if not cp_w:
        return None
    st = _seg_stats(climb.get("segments"))
    if st is None:
        avg_g = float(climb.get("avg_pct") or 0.0)
        crux_g, crr, crux_crr = float(climb.get("max_pct") or avg_g), CRR_DEFAULT, CRR_DEFAULT
        length = float(climb.get("length_m") or 0.0)
    else:
        avg_g, crr, crux_g, crux_crr, length = st
    if length < 100:
        return None
    mass = float(mass_rider_kg) + BIKE_GEAR_KG
    cp = float(cp_w)
    pts = achievable_curve(conn)
    easiest = cogs[-1] if cogs else None
    v_dign = max(V_DIGN_MIN_KMH,
                 _v_at_cadence(CAD_DIGN_RPM, front_t, easiest) if easiest else 0.0)

    # rownowaga: predkosc, przy ktorej moc wymagana = osiagalna (P75)
    lo, hi = V_FLOOR_HARD_KMH, 30.0
    for _ in range(40):
        mid = (lo + hi) / 2.0
        t_est = length / (mid / 3.6)
        w_ach = cp * ach_pct(pts, t_est) / 100.0
        if power_req(avg_g, mid, mass, crr) > w_ach:
            hi = mid
        else:
            lo = mid
    v_sust = lo
    t_est = length / (max(v_sust, V_FLOOR_HARD_KMH) / 3.6)
    w_ach = cp * ach_pct(pts, t_est) / 100.0

    p_dign = power_req(avg_g, v_dign, mass, crr)
    e = p_dign / w_ach if w_ach > 0 else 9.9

    if e <= 0.70:
        score = 2
    elif e <= 0.85:
        score = 1
    elif e <= 1.00:
        score = 0
    else:
        t_floor = length / (V_FLOOR_HARD_KMH / 3.6)
        w_ach_floor = cp * ach_pct(pts, t_floor) / 100.0
        p_floor = power_req(avg_g, V_FLOOR_HARD_KMH, mass, crr)
        deficit_kj = max(0.0, p_floor - w_ach_floor) * t_floor / 1000.0
        budget = 0.8 * float(wprime_kj or 20.0)
        score = -1 if deficit_kj <= budget else -2

    # crux: najstromsze ~200 m musi byc przejezdne chocby zrywem (P90 @2min)
    p_crux_floor = power_req(crux_g, V_FLOOR_HARD_KMH, mass, crux_crr)
    p90_short = cp * ach_pct(pts, 120.0, "p90") / 100.0
    if p_crux_floor > p90_short:
        score = min(score, -1)
        if p_crux_floor > 1.2 * p90_short:
            score = -2

    cad_floor = _cadence_at_v(V_FLOOR_HARD_KMH, front_t, easiest) if easiest else None
    why = ("~%d W przy %.1f km/h (%.0f%% osiagalnego ~%d W, ~%s), "
           "crux ~%d W; min. %.1f km/h = %s rpm na %s/%s%s") % (
        round(p_dign), v_dign, e * 100.0, round(w_ach), _fmt_t(t_est),
        round(p_crux_floor), V_FLOOR_HARD_KMH,
        (str(int(round(cad_floor))) if cad_floor else "?"),
        front_t, (easiest or "?"),
        (" (kaseta zal. %s)" % cassette_code) if cassette_code else "")
    return {"score": score, "label": LABELS[score], "why": why,
            "v_sust_kmh": round(v_sust, 1), "w_ach_w": round(w_ach),
            "p_dign_w": round(p_dign), "effort_pct": round(e * 100.0)}


def _fmt_t(t_s: float) -> str:
    m = int(round(t_s / 60.0))
    return "%d min" % max(1, m)
