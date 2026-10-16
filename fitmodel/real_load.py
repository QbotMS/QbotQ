from __future__ import annotations

"""Faktyczne zmeczenie i swiezosc (2026-09-29): ATL/CTL z treningow + stan ciala + samopoczucie.

    zmeczenie_f = ATL_surowe + BETA * B * CTL          (w jednostkach ATL, dziala w OBIE strony)
    swiezosc_f  = CTL - zmeczenie_f
    forma_f     = CTL (bez korekty - wydolnosc po infekcji 09.2026 nie spadla, brak danych na korekte formy)
B = stan ciala (B > 0 zmeczone, B < 0 wypoczete) = srednia z dostepnych sygnalow (KAZDY przyciety do +-CLIP).
    KAZDY SYGNAL RAZ (audyt 16.10.2026, docs/audit/sygnaly_ciala_2026-10-16.md):
    -gotowosc OBIEKTYWNA z 3 dni = srednia readiness_score (HRV/RHR/sen) - BEZ samopoczucia i choroby (te wchodza nizej,
     bezposrednio) i BEZ osobnego skladnika tetna (tetno jest juz w gotowosci, waga 35%; dawny skladnik 'tetno' usuniety),
    Body Battery jako AKUMULATOR (2026-10-16, decyzja Michala): dlug z 3 ostatnich nocy =
    suma(ubylo w dzien poprzedni - przybylo w noc) / (3 * typowe dzienne zuzycie) * 2 (qbot_v2.wellness_daily
    body_battery_drained / body_battery_charged). Rano = ile noc doladowala, koniec dnia = jak ciezki byl dzien.
    Zastepuje dawne odchylenie porannego poziomu od mediany (sufit 100 + pomieszane definicje dawaly skoki, np. 16.10: +55).
    + infekcja: ILL_W (1.2 od 16.10 - wczesniej 1.0, ale choroba liczyla sie drugi raz w gotowosci) w dniach choroby,
      potem liniowo do 0 przez 14 dni (waga dobrana tak, by wplyw infekcji zostal jak przed usunieciem dubla)
    + samopoczucie z Kalendarza (tylko gdy != 0): -FEEL_K * feel  (feel -2..+2; -2 = bardzo zle)
BETA = 0.5 wybrane na znanych epizodach 2026 (infekcje 05 i 09, Toskania 06, odpoczynek po niej): 0.3 za slabe
(w chorobie 'neutralnie'), 0.8 za mocne (Toskania -145, tydzien po +50). Statystyczna kalibracja niemozliwa -
wynik pojedynczej jazdy za bardzo zaszumiony (r ~ 0 dla wszystkich wariantow). Dostrajanie: wpisy samopoczucia.
Liczone dla calej historii w apply_hidden_fatigue (po readiness).
"""

import datetime as dt
import json
from statistics import median, pstdev, mean

BETA = 0.5
FEEL_K = 0.3
ILL_W, ILL_TAIL = 1.2, 14
NORM_DAYS, NORM_MIN = 60, 20
CLIP = 2.0            # 2026-10-16: pojedynczy sygnal ciala nie moze wywrocic wyniku
BB_NIGHTS = 3         # dlug akumulatora z tylu ostatnich nocy


def bb_debt_z(day, W, typ):
    """Dlug akumulatora Body Battery -> z (dodatni = noce nie nadrabiaja dnia). W: {data: (charged, drained)}."""
    debt, n = 0.0, 0
    for k in range(BB_NIGHTS):
        d = day - dt.timedelta(days=k)
        ch = (W.get(d) or (None, None))[0]
        dr = (W.get(d - dt.timedelta(days=1)) or (None, None))[1]
        if ch is not None and dr is not None:
            debt += float(dr) - float(ch); n += 1
    if not n or not typ:
        return None, None
    return max(-CLIP, min(CLIP, debt / (BB_NIGHTS * typ) * 2)), round(debt)


def _t(rows):
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]


def _c(v):
    return max(-CLIP, min(CLIP, v))


def body_score(r3, rhr7, rhr_n, rhr_s, bb, bb_n, bb_s, ill_w, feel, bb_z=None):
    """Czysta funkcja: (B, skladniki). bb_z = gotowy z akumulatora (bb_debt_z) - ma pierwszenstwo przed
    starym odchyleniem porannego poziomu (bb, bb_n, bb_s - zostaje tylko dla zgodnosci/testow)."""
    z, parts = [], {}
    if r3 is not None:
        v = _c(-r3); z.append(v); parts["gotowosc_3d"] = round(v, 2)
    if rhr7 is not None and rhr_n is not None:
        v = _c((rhr7 - rhr_n) / (rhr_s or 1.0)); z.append(v); parts["tetno"] = round(v, 2)
    if bb_z is not None:
        z.append(bb_z); parts["body_battery"] = round(bb_z, 2)
    elif bb is not None and bb_n is not None:
        v = _c(-(bb - bb_n) / (bb_s or 1.0)); z.append(v); parts["body_battery"] = round(v, 2)
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
    cur.execute("SELECT day, atl_raw, ctl_xss, readiness_score FROM qbot_v2.fitmodel_daily ORDER BY day")
    rows = _t(cur.fetchall())
    if not rows:
        return {"updated": 0}
    cur.execute("SELECT date, body_battery_charged, body_battery_drained FROM qbot_v2.wellness_daily "
                "WHERE body_battery_charged IS NOT NULL OR body_battery_drained IS NOT NULL")
    WB = {d: (ch, dr) for d, ch, dr in _t(cur.fetchall())}
    _dr = sorted(float(v[1]) for v in WB.values() if v[1] is not None and float(v[1]) > 20)
    typ = _dr[len(_dr) // 2] if _dr else None
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
    rsc = {d: float(s) for d, _a, _c, s in rows if s is not None}

    n = 0
    for d, atl, ctl, _s in rows:
        r3v = [rsc[d - dt.timedelta(days=k)] for k in range(3) if (d - dt.timedelta(days=k)) in rsc]
        r3 = mean(r3v) if r3v else None   # gotowosc obiektywna z 3 dni (bez subiektywu - ten nizej, raz)
        bz, debt = bb_debt_z(d, WB, typ)
        past = [e for e in ends if e <= d]
        iw = ILL_W if d in ill else (ILL_W * (1 - (d - past[-1]).days / float(ILL_TAIL)) if past and (d - past[-1]).days <= ILL_TAIL else 0.0)
        fl = mean(feel[d]) if d in feel else 0.0
        b, parts = body_score(r3, None, None, None, None, None, None, iw, fl, bb_z=bz)
        if debt is not None:
            parts["bb_dlug_3_nocy"] = debt
        if atl is None or ctl is None:
            continue
        atl_f = float(atl) + BETA * b * float(ctl)
        cur.execute("UPDATE qbot_v2.fitmodel_daily SET body_load=%s, body_load_parts=%s, atl_real=%s, tsb_real=%s, ctl_real=%s WHERE day=%s",
                    (round(b, 3), json.dumps(parts, ensure_ascii=False), round(atl_f, 1), round(float(ctl) - atl_f, 1), round(float(ctl), 1), d))
        n += 1
    conn.commit()
    return {"updated": n, "beta": BETA, "bb_typowe_zuzycie": typ}
