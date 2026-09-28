from __future__ import annotations

"""Niezalezna kontrola miernika mocy z FIZYKI na podjazdach (2026-09-28).

Na podjazdach (okno 60 s, nachylenie >= 4 %, 1.8-9 m/s, kadencja > 40) moc wynika glownie z grawitacji:
    P = m*g*v*(nachylenie + Crr) + 0.5*rho*CdA*v^3 + dEk/dt
m = waga dnia + rower/sprzet (EXTRA_KG) + bagaz (LUGGAGE, wg Michala). rho z temperatury.
ratio = mediana(moc z miernika / moc z fizyki) dla jazdy. Na sprawnym mierniku ~1.0 (wiosna 2026: 0.99).
Walidacja 2026: wiosna 0.99, maj 1.03, Toskania 1.08 (bagaz 10 kg), lipiec 1.11, Opolskie 1.24, Sycylia 1.37
-> blad osi AHP29525 narastal od lipca. Dokladnosc metody ok. +-10 % (rozrzut na sprawnym mierniku 0.87-1.12).
Uzycie: estymacja wydolnosci (moc przy tetnie) w okresie wady: P@HR_est = P@HR * ref_ratio / ratio.
Wymaga podjazdow - jazdy po plaskim nie maja wyniku (n_windows < MIN_WINDOWS).
"""

import datetime as dt
from statistics import median

G, CDA, CRR, EXTRA_KG = 9.81, 0.45, 0.009, 14.0
MIN_GRADE, V_MIN, V_MAX, CAD_MIN, WIN_S = 0.04, 1.8, 9.0, 40, 60
MIN_WINDOWS = 5
ACCURACY = 0.10
# bagaz wg Michala (2026-09-28): Toskania ~10 kg, Opolszczyzna ~6 kg (nie wazone dokladnie)
LUGGAGE = [(dt.date(2026, 6, 5), dt.date(2026, 6, 11), 10.0), (dt.date(2026, 8, 1), dt.date(2026, 8, 3), 6.0)]

DDL = """CREATE TABLE IF NOT EXISTS qbot_v2.meter_phys (
    external_id text PRIMARY KEY, ride_date date, n_windows integer, ratio real,
    mass_kg real, luggage_kg real, computed_at timestamptz DEFAULT now())"""


def _t(rows):
    """psycopg2 (krotki) i psycopg3 dict_row (slowniki) -> krotki."""
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]


def luggage_kg(d) -> float:
    return next((k for a, b, k in LUGGAGE if a <= d <= b), 0.0)


def ride_ratio(rows, mass):
    """rows: [(sec, alt, dist, power, cad, speed, temp)] posortowane po sec. Zwraca (n_okien, mediana ratio)."""
    ratios, i = [], 0
    while i + WIN_S < len(rows):
        a, b = rows[i], rows[i + WIN_S]
        if None in (a[1], b[1], a[2], b[2]) or b[0] - a[0] != WIN_S or (b[2] - a[2]) < V_MIN * WIN_S:
            i += WIN_S // 2
            continue
        dist = b[2] - a[2]
        grade, v = (b[1] - a[1]) / dist, dist / float(WIN_S)
        seg = rows[i:i + WIN_S + 1]
        pw = [r[3] for r in seg if r[3] is not None]
        cad = [r[4] for r in seg if r[4] is not None]
        if grade < MIN_GRADE or v > V_MAX or len(pw) < WIN_S * 0.8 or not cad or median(cad) < CAD_MIN:
            i += WIN_S // 2
            continue
        t = [r[6] for r in seg if r[6] is not None]
        rho = 1.225 * 288.15 / (273.15 + (median(t) if t else 15.0))
        va, vb = (a[5] or v), (b[5] or v)
        p_est = mass * G * v * (grade + CRR) + 0.5 * rho * CDA * v ** 3 + 0.5 * mass * (vb * vb - va * va) / WIN_S
        p_meas = sum(pw) / len(pw)
        if p_est > 80 and p_meas > 50:
            ratios.append(p_meas / p_est)
        i += WIN_S
    return len(ratios), (median(ratios) if ratios else None)


def ensure(conn, since, limit: int = 400) -> int:
    """Licz dla jazd z moca od `since`, ktorych nie ma jeszcze w meter_phys. Zwraca liczbe policzonych."""
    cur = conn.cursor()
    cur.execute(DDL)
    cur.execute("""SELECT t.external_id, t.date FROM qbot_v2.training_sessions t
                   WHERE t.sport_type='cycling' AND t.date >= %s AND t.avg_power_w IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.meter_phys m WHERE m.external_id=t.external_id)
                   ORDER BY t.date LIMIT %s""", (since, limit))
    todo = _t(cur.fetchall())
    for eid, d in todo:
        cur.execute("SELECT weight_kg FROM qbot_v2.fitmodel_daily WHERE day<=%s AND weight_kg IS NOT NULL ORDER BY day DESC LIMIT 1", (d,))
        w = _t([cur.fetchone()])[0] if cur.rowcount else None
        lug = luggage_kg(d)
        mass = (float(w[0]) if w else 101.0) + EXTRA_KG + lug
        cur.execute("SELECT sec, altitude_m, distance_m, power_w, cadence_rpm, speed_mps, temperature_c "
                    "FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec", (eid,))
        n, r = ride_ratio(_t(cur.fetchall()), mass)
        cur.execute("INSERT INTO qbot_v2.meter_phys (external_id, ride_date, n_windows, ratio, mass_kg, luggage_kg) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (external_id) DO NOTHING",
                    (eid, d, n, (round(r, 3) if r is not None and n >= MIN_WINDOWS else None), round(mass, 1), lug))
    conn.commit()
    return len(todo)


def reference_ratio(conn, bad_from=None, bad_to=None):
    """Wzorzec: mediana ratio jazd POZA okresem wady miernika i bez bagazu (n_windows >= MIN_WINDOWS)."""
    cur = conn.cursor()
    # tylko jazdy BEZ bagazu (opor sakw i dokladna masa bagazu niepewne)
    cur.execute("SELECT ride_date, ratio FROM qbot_v2.meter_phys WHERE ratio IS NOT NULL AND n_windows >= %s "
                "AND COALESCE(luggage_kg, 0) = 0", (MIN_WINDOWS,))
    xs = [float(r) for d, r in _t(cur.fetchall()) if not (bad_from and bad_from <= d <= bad_to)]
    return (round(median(xs), 3), len(xs)) if xs else (None, 0)
