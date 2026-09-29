from __future__ import annotations

"""Faktyczne zmeczenie i swiezosc (2026-09-29): ATL/CTL z treningow + stan ciala + samopoczucie.

    zmeczenie_f = ATL_surowe + BETA * B * CTL          (w jednostkach ATL, dziala w OBIE strony)
    swiezosc_f  = CTL - zmeczenie_f
    forma_f     = CTL (bez korekty - wydolnosc po infekcji 09.2026 nie spadla, brak danych na korekte formy)
B = stan ciala (B > 0 zmeczone, B < 0 wypoczete) = srednia z dostepnych sygnalow:
    -gotowosc z 3 dni, (tetno spocz. 7 dni - mediana 60 dni) / odch., -(Body Battery rano - mediana 60 dni) / odch.
    + infekcja: 1.0 w dniach choroby, potem liniowo do 0 przez 14 dni
    + samopoczucie z Kalendarza (tylko gdy != 0): -FEEL_K * feel  (feel -2..+2; -2 = bardzo zle)
BETA = 0.5 wybrane na znanych epizodach 2026 (infekcje 05 i 09, Toskania 06, odpoczynek po niej): 0.3 za slabe
(w chorobie 'neutralnie'), 0.8 za mocne (Toskania -145, tydzien po +50). Statystyczna kalibracja niemozliwa -
wynik pojedynczej jazdy za bardzo zaszumiony (r ~ 0 dla wszystkich wariantow). Dostrajanie: wpisy samopoczucia.
Liczone dla calej historii w apply_hidden_fatigue (po day_status, bo korzysta z readiness_3d).
"""

import datetime as dt
import json
from statistics import median, pstdev, mean

BETA = 0.5
FEEL_K = 0.3
ILL_W, ILL_TAIL = 1.0, 14
NORM_DAYS, NORM_MIN = 60, 20


def _t(rows):
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]


def body_score(r3, rhr7, rhr_n, rhr_s, bb, bb_n, bb_s, ill_w, feel):
    """Czysta funkcja: (B, skladniki)."""
    z, parts = [], {}
    if r3 is not None:
        z.append(-r3); parts["gotowosc_3d"] = round(-r3, 2)
    if rhr7 is not None and rhr_n is not None:
        v = (rhr7 - rhr_n) / (rhr_s or 1.0); z.append(v); parts["tetno"] = round(v, 2)
    if bb is not None and bb_n is not None:
        v = -(bb - bb_n) / (bb_s or 1.0); z.append(v); parts["body_battery"] = round(v, 2)
    b = mean(z) if z else 0.0
    if ill_w:
        b += ill_w; parts["infekcja"] = round(ill_w, 2)
    if feel:
        b += -FEEL_K * feel; parts["samopoczucie"] = round(-FEEL_K * feel, 2)
    return b, parts


def apply_real_load(conn) -> dict:
    cur = conn.cursor()
    cur.execute("ALTER TABLE qbot_v2.fitmodel_daily ADD COLUMN IF NOT EXISTS body_load NUMERIC, "
                "ADD COLUMN IF NOT EXISTS body_load_parts TEXT, ADD COLUMN IF NOT EXISTS atl_real NUMERIC, "
                "ADD COLUMN IF NOT EXISTS tsb_real NUMERIC, ADD COLUMN IF NOT EXISTS ctl_real NUMERIC")
    conn.commit()
    cur.execute("SELECT day, atl_raw, ctl_xss, readiness_3d, rhr FROM qbot_v2.fitmodel_daily ORDER BY day")
    rows = _t(cur.fetchall())
    if not rows:
        return {"updated": 0}
    cur.execute("SELECT date, body_battery_start FROM qbot_v2.qbot_wellness_daily WHERE body_battery_start IS NOT NULL")
    BB = {d: float(v) for d, v in _t(cur.fetchall())}
    cur.execute("SELECT day, COALESCE(end_day, day), kind, feel FROM qbot_v2.calendar_entry WHERE kind IN ('illness','feel')")
    ill, ends, feel = set(), [], {}
    for a, b, kind, fv in _t(cur.fetchall()):
        d = a
        while d <= b:
            if kind == "illness":
                ill.add(d)
            elif fv is not None and int(fv) != 0:
                feel.setdefault(d, []).append(int(fv))
            d += dt.timedelta(days=1)
        if kind == "illness":
            ends.append(b)
    ends.sort()
    rhr = {d: float(r) for d, _a, _c, _r3, r in rows if r is not None}

    def norm(src, d):
        v = [src[d - dt.timedelta(days=k)] for k in range(1, NORM_DAYS + 1) if (d - dt.timedelta(days=k)) in src]
        return (median(v), pstdev(v) or 1.0) if len(v) >= NORM_MIN else (None, None)

    n = 0
    for d, atl, ctl, r3, _r in rows:
        v7 = [rhr[d - dt.timedelta(days=k)] for k in range(7) if (d - dt.timedelta(days=k)) in rhr]
        rn, rs = norm(rhr, d)
        bn, bs = norm(BB, d)
        past = [e for e in ends if e <= d]
        iw = ILL_W if d in ill else (ILL_W * (1 - (d - past[-1]).days / float(ILL_TAIL)) if past and (d - past[-1]).days <= ILL_TAIL else 0.0)
        fl = mean(feel[d]) if d in feel else 0.0
        b, parts = body_score(float(r3) if r3 is not None else None, mean(v7) if len(v7) >= 3 else None, rn, rs,
                              BB.get(d), bn, bs, iw, fl)
        if atl is None or ctl is None:
            continue
        atl_f = float(atl) + BETA * b * float(ctl)
        cur.execute("UPDATE qbot_v2.fitmodel_daily SET body_load=%s, body_load_parts=%s, atl_real=%s, tsb_real=%s, ctl_real=%s WHERE day=%s",
                    (round(b, 3), json.dumps(parts, ensure_ascii=False), round(atl_f, 1), round(float(ctl) - atl_f, 1), round(float(ctl), 1), d))
        n += 1
    conn.commit()
    return {"updated": n, "beta": BETA}
