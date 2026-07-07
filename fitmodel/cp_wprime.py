from __future__ import annotations

"""FITMODEL -- CP i LTP z krzywej mocy (MMP) wykonanych jazd.

Zrodlo: qbot_v2.training_sessions.mmp_*_w (Garmin API, maxAvgPower_N, juz
pobierane co 15 min przez import_garmin_training.py -- zero nowych wywolan API).

Metoda: envelope (najlepsza wartosc per duracja w oknie, NIE z jednej jazdy)
-> model 2-parametrowy Monod-Scherrer P(t) = W'/t + CP, linearyzowany jako
Work(t) = P(t)*t = CP*t + W' -> regresja liniowa najmniejszych kwadratow.

DWA DOPASOWANIA (od Kroku 1, 2026-07-05):
- CP  z KROTKICH okien 120/300/600 s -> prawdziwe CP (~= FTP). Kolumna cp_modelq_w.
- LTP z DLUGICH  okien 300/600/1200/1800 s -> asymptota trwala (Long Term Power),
  odpowiednik Xert LTP. Kolumna ltp_modelq_w.
Wczesniej pojedyncze dlugie dopasowanie zapisywalo LTP mylnie jako cp_modelq_w
(cp_modelq_w == Xert LTP, delta ~0). Rozdzielone -- patrz DECISIONS.md 2026-07-05.

W' (wprime_modelq_kj): od Kroku 2 -- oportunistyczny harvest near-max z okien
{60,120,300} (patrz _wprime_harvest). Brak swiezego twardego fragmentu -> null +
przedzial 13-22 kJ + confidence:low. Zawyzony intercept LTP (~34.8 kJ) porzucony.

UWAGA (uczciwie): to sa najlepsze fragmenty ZWYKLYCH jazd, nie testy maksymalne.
Moze to nieco zanizac realne CP/LTP. Traktowac jako estymator, nie pomiar.
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitmodel.ftp_resolver import _db_connect, _coerce_date, load_params

try:
    import fitparse as _fitparse
except Exception:
    _fitparse = None

CP_DURATIONS = (120, 300, 600)          # krotkie okna -> prawdziwe CP (~FTP)
LTP_DURATIONS = (300, 600, 1200, 1800)  # dlugie okna  -> LTP (asymptota trwala)
CP_MIN_POINTS = 3
LTP_MIN_POINTS = 3
WINDOW_DAYS = 90

# --- Ratchet + zanik CP/LTP/W' (DECISIONS.md 2026-07-07 (3)) ---
CP_LTP_GRACE_DAYS = 60   # dni pelnego zaufania od ustanowienia rekordu
CP_LTP_DECAY_DAYS = 60   # kolejne dni liniowego zaniku do podlogi (FTP_est)

# --- W' harvest (Krok 2) ---
WPRIME_WINDOWS = (60, 120, 300)   # okna do W' (30s psuje fit -- inna fizjologia)
WPRIME_NEARMAX_FRAC = 0.92        # jazda 'twarda' gdy P60 lub P120 >= frac*best w oknie
WPRIME_FRESH_DAYS = 60            # <= tyle dni -> uzywalne; wyzej -> przedzial
WPRIME_HIGH_DAYS = 30
WPRIME_HIGH_FRAC = 0.95           # high: swieza <=30d i P120 >= frac*best
WPRIME_RANGE_LO = 13.0
WPRIME_RANGE_HI = 22.0
WPRIME_DECAY_DAYS = 60   # dni 60->120 liniowy zanik do podlogi WPRIME_RANGE_LO

# --- Kotwica z drogi (Warstwa 1, Krok 2 domkniecie) ---
# Zdarzenie QExt2 W'bal=0% NIE jest niezaleznym dowodem na wartosc W' (Karoo
# dostaje ta sama liczbe z /ride-readiness) -- ale moc PO zdarzeniu JEST
# niezalezna: jesli rider dalej ciagnie powyzej CP dlugo po "0%", W' bylo
# niedoszacowane. Jesli moc realnie spadla do/ponizej CP -- model sie zgadza.
ROAD_ANCHOR_FRESH_DAYS = 14        # tylko bardzo swieze zdarzenie (test na zywo, nie archiwum)
ROAD_ANCHOR_WINDOW_S = 90          # ile sekund po zdarzeniu 0% sprawdzamy moc
ROAD_ANCHOR_MARGIN = 1.05          # >5% nad CP w oknie -> uznane za "dalej ciagnal"
FIT_DIR_FOR_ANCHOR = "/opt/qbot/app/outgoing/michal/hammerhead_originals"

# --- Peak Power (Krok "a", warstwa 1 sygnatury) ---
PP_MAIN_WINDOW = 5      # mmp_5_w -> glowna PP (stabilna, standard sprintu)
PP_INSTANT_WINDOW = 1   # mmp_1_w -> PP instant (obok, moze byc artefakt)
PP_FRESH_DAYS = 60      # najlepszy sprint 5s <= tyle dni -> high, wyzej -> low


def _envelope_curve(db_conn, as_of: date, window_days: int, durations: tuple[int, ...]) -> tuple[dict[int, float], int]:
    """Najlepsza (max) wartosc mmp_{d}_w w oknie [as_of-window_days, as_of], per duracja.

    Envelope = najlepszy fragment SPOSROD WIELU jazd, nie pojedyncza jazda --
    tak buduje sie realna krzywa mocy w oknie czasowym.
    """
    cols = ",".join(f"max(mmp_{d}_w)" for d in durations)
    with db_conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {cols}, count(*)
            FROM qbot_v2.training_sessions
            WHERE date >= %s AND date <= %s
              AND (sport_type IS NULL OR sport_type NOT LIKE %s)
            """,
            (as_of - timedelta(days=window_days), as_of, "%virtual%"),
        )
        row = cur.fetchone()
    n_rides = row[-1] or 0
    curve = {d: float(v) for d, v in zip(durations, row[:-1]) if v is not None}
    return curve, n_rides


def _current_ftp_floor(db_conn, as_of: date) -> float | None:
    """Ostatnia znana wartosc FTP_est (<=as_of) -- podloga zaniku CP/LTP. Brak -> None
    (wolajacy spada na ftp_anchor_w z fitmodel_param)."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT ftp_est_w FROM qbot_v2.fitmodel_daily "
            "WHERE day <= %s AND ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1",
            (as_of,),
        )
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _decayed_value(value: float, set_on: date, as_of: date, floor: float,
                    grace_days: int = CP_LTP_GRACE_DAYS, decay_days: int = CP_LTP_DECAY_DAYS) -> float:
    """Ratchet + liniowy zanik (DECISIONS.md 2026-07-07 (3)): 0..grace_days pelna wartosc,
    grace_days..grace_days+decay_days liniowo do floor, dalej floor."""
    age = (as_of - set_on).days
    if age <= grace_days:
        return value
    if age >= grace_days + decay_days:
        return floor
    frac = (age - grace_days) / float(decay_days)
    return value - (value - floor) * frac


def _best_effort_asof(db_conn, duration_s: int, as_of: date) -> tuple[float, date] | None:
    """Najlepszy wynik mmp_{d}_w W CALEJ HISTORII <= as_of, bez okna czasowego. To samo w sobie
    jest ratchetem -- MAX() nad rosnacym zakresem dat moze tylko rosnac albo trwac, nigdy spadac
    -- wiec NIE trzeba trzymac osobnej tabeli z rekordami. Liczone na zywo za kazdym razem, zeby
    dzialalo poprawnie tez przy przeliczaniu historii (backfill) -- bez podgladania przyszlosci."""
    with db_conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT date, mmp_{duration_s}_w FROM qbot_v2.training_sessions
            WHERE mmp_{duration_s}_w IS NOT NULL AND date <= %s
              AND (sport_type IS NULL OR sport_type NOT LIKE %s)
            ORDER BY mmp_{duration_s}_w DESC LIMIT 1
            """,
            (as_of, "%virtual%"),
        )
        row = cur.fetchone()
    if not row or row[1] is None:
        return None
    return float(row[1]), row[0]


def _envelope_curve_decayed(db_conn, as_of: date, durations: tuple[int, ...],
                             floor_w: float | None) -> tuple[dict[int, float], int]:
    """Krzywa envelope BEZ OKNA (najlepszy wynik w calej historii <=as_of) + zanik wg wieku
    rekordu wzgledem as_of. Zastepuje _envelope_curve() (okno 90d) dla CP/LTP."""
    curve: dict[int, float] = {}
    for d in durations:
        found = _best_effort_asof(db_conn, d, as_of)
        if found is None:
            continue
        best_w, best_date = found
        curve[d] = best_w if floor_w is None else _decayed_value(best_w, best_date, as_of, floor_w)
    return curve, len(curve)


def _fit_model(curve: dict[int, float], min_points: int) -> tuple[float | None, float | None, float | None]:
    """Regresja Work(t) = P*t + W' na punktach envelope. Zwraca (asymptota_w, wprime_j, r2).

    asymptota_w = nachylenie (CP dla krotkich okien / LTP dla dlugich).
    """
    pts = sorted(curve.items())
    n = len(pts)
    if n < min_points:
        return None, None, None

    ts = [float(t) for t, _ in pts]
    ws = [p * t for t, p in pts]  # Work = Power * time

    mean_t = sum(ts) / n
    mean_w = sum(ws) / n
    sxx = sum((t - mean_t) ** 2 for t in ts)
    sxy = sum((t - mean_t) * (w - mean_w) for t, w in zip(ts, ws))
    if sxx == 0:
        return None, None, None

    slope = sxy / sxx           # asymptota (CP / LTP)
    wprime = mean_w - slope * mean_t

    ss_tot = sum((w - mean_w) ** 2 for w in ws)
    if ss_tot == 0:
        r2 = None
    else:
        ss_res = sum((w - (slope * t + wprime)) ** 2 for t, w in zip(ts, ws))
        r2 = 1 - ss_res / ss_tot

    return slope, wprime, r2


def _wprime_harvest(db_conn, as_of: date, window_days: int = WINDOW_DAYS) -> dict[str, Any]:
    """W' z oportunistycznego harvestu near-max (warstwa 2) + przedzial (warstwa 3).

    Szuka w oknie jazd z prawdziwie twardym krotkim fragmentem (P60/P120 blisko
    najlepszego w oknie), liczy W' z {60,120,300} i bierze NAJWYZSZE (W' ujawnia sie
    tylko przy pelnym wyczerpaniu). Brak swiezego twardego fragmentu -> null + przedzial.
    Warstwa 1 (kotwica z drogi: zdarzenie QExt2 W'bal=0%) dojdzie ze Strona B -- tu nie ma.
    """
    out: dict[str, Any] = {
        "wprime_modelq_kj": None, "wprime_lo_kj": None, "wprime_hi_kj": None,
        "wprime_confidence": "low", "wprime_source": None,
    }

    def _range(reason: str) -> dict[str, Any]:
        out["wprime_lo_kj"] = WPRIME_RANGE_LO
        out["wprime_hi_kj"] = WPRIME_RANGE_HI
        out["wprime_source"] = f"przedzial {WPRIME_RANGE_LO:.0f}-{WPRIME_RANGE_HI:.0f} ({reason})"
        return out

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT date, mmp_60_w, mmp_120_w, mmp_300_w
            FROM qbot_v2.training_sessions
            WHERE date >= %s AND date <= %s
              AND mmp_60_w > 0 AND mmp_120_w > 0 AND mmp_300_w > 0
              AND (sport_type IS NULL OR sport_type NOT LIKE %s)
            ORDER BY date
            """,
            (as_of - timedelta(days=window_days), as_of, "%virtual%"),
        )
        rides = cur.fetchall()

    if not rides:
        return _range(f"brak danych MMP w oknie {window_days}d")

    best60 = max(float(r[1]) for r in rides)
    best120 = max(float(r[2]) for r in rides)

    def _wprime_kj(p60, p120, p300):
        pts = [(60.0, float(p60)), (120.0, float(p120)), (300.0, float(p300))]
        ts = [t for t, _ in pts]
        ws = [pw * t for t, pw in pts]
        n = 3
        mt = sum(ts) / n
        mw = sum(ws) / n
        sxx = sum((t - mt) ** 2 for t in ts)
        if sxx == 0:
            return None
        cp = sum((t - mt) * (w - mw) for t, w in zip(ts, ws)) / sxx
        return (mw - cp * mt) / 1000.0

    nearmax = []
    for d, p60, p120, p300 in rides:
        if float(p60) >= WPRIME_NEARMAX_FRAC * best60 or float(p120) >= WPRIME_NEARMAX_FRAC * best120:
            wp = _wprime_kj(p60, p120, p300)
            if wp is not None and wp > 0:
                nearmax.append((wp, d, float(p120)))

    if not nearmax:
        return _range(f"brak twardego fragmentu w oknie {window_days}d")

    nearmax.sort(reverse=True)
    best_wp, best_day, best_p120 = nearmax[0]
    age = (as_of - best_day).days

    # --- Zanik zamiast twardego skoku na przedzial (DECISIONS.md 2026-07-07 (3)) ---
    if age > WPRIME_FRESH_DAYS + WPRIME_DECAY_DAYS:
        out["wprime_modelq_kj"] = round(WPRIME_RANGE_LO, 2)
        out["wprime_lo_kj"] = WPRIME_RANGE_LO
        out["wprime_hi_kj"] = WPRIME_RANGE_HI
        out["wprime_confidence"] = "low"
        out["wprime_source"] = (
            f"pelny zanik -- ostatni twardy fragment {best_day} ({age}d temu), "
            f"podloga {WPRIME_RANGE_LO:.0f} kJ"
        )
        return out

    if age > WPRIME_FRESH_DAYS:
        frac = (age - WPRIME_FRESH_DAYS) / float(WPRIME_DECAY_DAYS)
        decayed = best_wp - (best_wp - WPRIME_RANGE_LO) * frac
        out["wprime_modelq_kj"] = round(decayed, 2)
        out["wprime_lo_kj"] = WPRIME_RANGE_LO
        out["wprime_hi_kj"] = WPRIME_RANGE_HI
        out["wprime_confidence"] = "low"
        out["wprime_source"] = (
            f"zanik z harvestu {best_day} ({age}d temu, {round(frac * 100)}% do podlogi "
            f"{WPRIME_RANGE_LO:.0f} kJ)"
        )
        return out

    conf = "high" if (age <= WPRIME_HIGH_DAYS and best_p120 >= WPRIME_HIGH_FRAC * best120) else "medium"
    out["wprime_modelq_kj"] = round(best_wp, 2)
    out["wprime_confidence"] = conf
    out["wprime_source"] = (
        f"harvest 60/120/300, jazda {best_day} ({age}d temu), "
        f"{len(nearmax)} twardych w oknie {window_days}d"
    )
    return out



def _robust_qext2_records(fit_path: str) -> list[dict[str, Any]]:
    """Parsuj rekordy FIT odporne na dev-field bledy fitparse (patrz DECISIONS.md
    2026-07-06 -- naiwne fit.get_messages('record') moze wywalic sie/zwrocic pusto
    na plikach z developer fields QExt2). Zwraca timestamp/power/qext2_* per sekunda."""
    if _fitparse is None:
        return []
    try:
        fit = _fitparse.FitFile(fit_path)
    except Exception:
        return []
    recs: list[dict[str, Any]] = []
    while not fit._complete:
        try:
            msg = fit._parse_message()
        except Exception:
            continue
        if msg is None or getattr(msg, "name", None) != "record":
            continue
        if type(msg).__name__ != "DataMessage":
            continue
        d: dict[str, Any] = {}
        try:
            for f in msg:
                try:
                    d[f.name] = f.value
                except Exception:
                    continue
        except Exception:
            continue
        if "timestamp" in d:
            recs.append(d)
    return recs


def _road_anchor_check(db_conn, as_of: date, fresh_days: int = ROAD_ANCHOR_FRESH_DAYS) -> dict[str, Any] | None:
    """Sprawdz najswiezsze zdarzenie QExt2 W'bal=0% (Strona B): czy moc PO zdarzeniu
    realnie spadla do/ponizej CP (model potwierdzony), czy rider dalej ciagnal powyzej
    CP (W' prawdopodobnie niedoszacowane). Zwraca None gdy brak swiezego zdarzenia."""
    if _fitparse is None:
        return None
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT ride_id, wbal_zero_seconds, cp_eff_final
            FROM qbot_v2.fitmodel_qext2_ride
            WHERE wbal_zero_seconds > 0
            ORDER BY ingested_at DESC LIMIT 5
            """
        )
        candidates = cur.fetchall()
    if not candidates:
        return None

    for ride_id, wbal_zero_seconds, cp_eff_final in candidates:
        fit_path = f"{FIT_DIR_FOR_ANCHOR}/{ride_id}.fit"
        recs = _robust_qext2_records(fit_path)
        if not recs:
            continue
        recs.sort(key=lambda r: r["timestamp"])
        ride_date = recs[0]["timestamp"].date()
        age = (as_of - ride_date).days
        if age > fresh_days or age < 0:
            continue  # nie ten kandydat -- za stary (albo z przyszlosci wzgledem as_of)

        first_idx = None
        for i, r in enumerate(recs):
            z = r.get("qext2_wbal_zero")
            if z is not None and float(z) >= 1:
                first_idx = i
                break
        if first_idx is None:
            continue

        cp_eff = recs[first_idx].get("qext2_cp_eff_w") or cp_eff_final
        if not cp_eff:
            continue
        window = recs[first_idx: first_idx + ROAD_ANCHOR_WINDOW_S]
        powers = [r.get("power") for r in window if r.get("power") is not None]
        if len(powers) < ROAD_ANCHOR_WINDOW_S * 0.5:
            continue  # za malo danych mocy w oknie -- nie ufaj

        avg_p = sum(powers) / len(powers)
        cp_eff = float(cp_eff)
        event_ts = recs[first_idx]["timestamp"]

        if avg_p > cp_eff * ROAD_ANCHOR_MARGIN:
            excess_kj = round((avg_p - cp_eff) * len(powers) / 1000.0, 1)
            return {
                "status": "contradicted", "ride_id": ride_id, "ride_date": str(ride_date),
                "event_ts": str(event_ts), "cp_eff_w": round(cp_eff), "avg_power_after_w": round(avg_p),
                "window_s": len(powers), "excess_kj": excess_kj,
                "note": (
                    f"kotwica z drogi {ride_date}: PO zdarzeniu W'bal=0% moc srednio "
                    f"{round(avg_p)}W przez {len(powers)}s (CP_eff={round(cp_eff)}W) -- rider dalej "
                    f"ciagnal powyzej CP, ~{excess_kj}kJ ponad model -> W' PRAWDOPODOBNIE NIEDOSZACOWANE"
                ),
            }
        else:
            return {
                "status": "confirmed", "ride_id": ride_id, "ride_date": str(ride_date),
                "event_ts": str(event_ts), "cp_eff_w": round(cp_eff), "avg_power_after_w": round(avg_p),
                "window_s": len(powers),
                "note": (
                    f"kotwica z drogi {ride_date}: PO zdarzeniu W'bal=0% moc spadla do "
                    f"{round(avg_p)}W (<=CP_eff={round(cp_eff)}W) przez {len(powers)}s -- model potwierdzony"
                ),
            }
    return None


def _peak_power(db_conn, as_of: date, window_days: int = WINDOW_DAYS) -> dict[str, Any]:
    """Peak Power = max sprint z envelope. Glowna 5s (stabilna), instant 1s (obok).

    Flaga swiezosci: gdy najlepszy sprint 5s w oknie jest swiezy (<=PP_FRESH_DAYS),
    PP jest wiarygodne (high). Bez swiezego sprintu -> zanizone (low), bo PP ujawnia
    sie tylko przy realnym maksymalnym wysilku.
    """
    out: dict[str, Any] = {
        "pp_modelq_w": None, "pp_instant_w": None,
        "pp_confidence": "low", "pp_note": None,
    }
    start = as_of - timedelta(days=window_days)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT max(mmp_5_w), max(mmp_1_w), count(*)
            FROM qbot_v2.training_sessions
            WHERE date >= %s AND date <= %s
              AND (sport_type IS NULL OR sport_type NOT LIKE %s)
            """,
            (start, as_of, "%virtual%"),
        )
        pp5, pp1, n = cur.fetchone()
        # data najlepszego sprintu 5s -> swiezosc
        cur.execute(
            """
            SELECT date, mmp_5_w FROM qbot_v2.training_sessions
            WHERE date >= %s AND date <= %s AND mmp_5_w IS NOT NULL
              AND (sport_type IS NULL OR sport_type NOT LIKE %s)
            ORDER BY mmp_5_w DESC LIMIT 1
            """,
            (start, as_of, "%virtual%"),
        )
        bestrow = cur.fetchone()

    if pp5 is None:
        out["pp_note"] = f"brak sprintow 5s w oknie {window_days}d (n_jazd={n or 0})"
        return out

    out["pp_modelq_w"] = round(float(pp5), 1)
    out["pp_instant_w"] = round(float(pp1), 1) if pp1 is not None else None

    if bestrow:
        best_date, best_val = bestrow
        age = (as_of - best_date).days
        if age <= PP_FRESH_DAYS:
            out["pp_confidence"] = "high"
            out["pp_note"] = (
                f"PP 5s={round(float(pp5))} W (instant 1s={round(float(pp1)) if pp1 else 'n/a'} W); "
                f"najlepszy sprint {age}d temu -> swiezy, wiarygodny"
            )
        else:
            out["pp_confidence"] = "low"
            out["pp_note"] = (
                f"PP 5s={round(float(pp5))} W; najlepszy sprint {age}d temu (>{PP_FRESH_DAYS}d) "
                f"-> prawdopodobnie zanizone, brak swiezego maksa"
            )
    return out


def compute_cp_wprime(db_conn, as_of: date | None = None, window_days: int = WINDOW_DAYS) -> dict[str, Any]:
    """Policz CP (krotkie okna) i LTP (dlugie okna) na dzien as_of (bez zapisu)."""
    as_of = _coerce_date(as_of)

    out: dict[str, Any] = {
        "day": as_of,
        "cp_modelq_w": None, "cp_wprime_r2": None, "cp_wprime_note": None,
        "ltp_modelq_w": None, "ltp_modelq_r2": None, "ltp_modelq_note": None,
        "wprime_modelq_kj": None, "wprime_lo_kj": None, "wprime_hi_kj": None,
        "wprime_confidence": "low", "wprime_source": None,
        "pp_modelq_w": None, "pp_instant_w": None,
        "pp_confidence": "low", "pp_note": None,
    }

    # --- Podloga zaniku CP/LTP = biezacy FTP_est (fallback: ftp_anchor_w) ---
    floor_w = _current_ftp_floor(db_conn, as_of)
    if floor_w is None:
        floor_w = load_params(db_conn).get("ftp_anchor_w")

    # --- CP: krotkie okna 120/300/600 (ratchet + zanik, DECISIONS.md 2026-07-07 (3)) ---
    cp_curve, cp_n = _envelope_curve_decayed(db_conn, as_of, CP_DURATIONS, floor_w)
    if len(cp_curve) < CP_MIN_POINTS:
        out["cp_wprime_note"] = (
            f"za malo krotkich rekordow w ratchecie "
            f"(mam {len(cp_curve)}/{len(CP_DURATIONS)}: {sorted(cp_curve.keys())}, min={CP_MIN_POINTS})"
        )
    else:
        cp, _cp_wp_j, cp_r2 = _fit_model(cp_curve, CP_MIN_POINTS)
        if cp is None or cp <= 0:
            out["cp_wprime_r2"] = round(cp_r2, 3) if cp_r2 is not None else None
            out["cp_wprime_note"] = f"fit CP niewiarygodny (cp={cp}) -- odrzucony"
        else:
            clamp_note = ""
            if floor_w is not None and cp < floor_w:
                clamp_note = (
                    f" [UWAGA: surowy fit {round(cp, 1)}W ponizej podlogi -- "
                    f"niefizjologiczne gdy czesc punktow krzywej jest juz w pelni zdryfowana "
                    f"do tej samej podlogi (degenerowany fit); podniesione do FTP_est]"
                )
                cp = floor_w
            out["cp_modelq_w"] = round(cp, 1)
            out["cp_wprime_r2"] = round(cp_r2, 3) if cp_r2 is not None else None
            out["cp_wprime_note"] = (
                f"CP z ratchetu (rekordy {sorted(cp_curve.keys())}, {CP_LTP_GRACE_DAYS}d pelne zaufanie "
                f"+ {CP_LTP_DECAY_DAYS}d liniowy zanik do FTP_est="
                f"{round(floor_w, 1) if floor_w is not None else 'brak'}W), "
                f"r2={round(cp_r2, 3) if cp_r2 is not None else 'n/a'} "
                f"-- najlepsze fragmenty zwyklych jazd, nie testy maksymalne{clamp_note}"
            )

    # --- LTP: dlugie okna 300/600/1200/1800 (ratchet + zanik, DECISIONS.md 2026-07-07 (3)) ---
    ltp_curve, ltp_n = _envelope_curve_decayed(db_conn, as_of, LTP_DURATIONS, floor_w)
    if len(ltp_curve) < LTP_MIN_POINTS:
        out["ltp_modelq_note"] = (
            f"za malo dlugich rekordow w ratchecie "
            f"(mam {len(ltp_curve)}/{len(LTP_DURATIONS)}: {sorted(ltp_curve.keys())}, min={LTP_MIN_POINTS})"
        )
    else:
        ltp, _ltp_wp_j, ltp_r2 = _fit_model(ltp_curve, LTP_MIN_POINTS)
        if ltp is None or ltp <= 0:
            out["ltp_modelq_r2"] = round(ltp_r2, 3) if ltp_r2 is not None else None
            out["ltp_modelq_note"] = f"fit LTP niewiarygodny (ltp={ltp}) -- odrzucony"
        else:
            clamp_note = ""
            if floor_w is not None and ltp < floor_w:
                clamp_note = (
                    f" [UWAGA: surowy fit {round(ltp, 1)}W ponizej podlogi -- "
                    f"niefizjologiczne gdy czesc punktow krzywej jest juz w pelni zdryfowana "
                    f"do tej samej podlogi (degenerowany fit); podniesione do FTP_est]"
                )
                ltp = floor_w
            out["ltp_modelq_w"] = round(ltp, 1)
            out["ltp_modelq_r2"] = round(ltp_r2, 3) if ltp_r2 is not None else None
            out["ltp_modelq_note"] = (
                f"LTP z ratchetu (rekordy {sorted(ltp_curve.keys())}, {CP_LTP_GRACE_DAYS}d pelne zaufanie "
                f"+ {CP_LTP_DECAY_DAYS}d liniowy zanik do FTP_est="
                f"{round(floor_w, 1) if floor_w is not None else 'brak'}W), "
                f"r2={round(ltp_r2, 3) if ltp_r2 is not None else 'n/a'} "
                f"-- odpowiednik Xert LTP{clamp_note}"
            )

    # --- W' -- harvest near-max + przedzial (Krok 2), zastepuje intercept LTP ---
    out.update(_wprime_harvest(db_conn, as_of, window_days))

    # --- Kotwica z drogi (Warstwa 1) -- weryfikacja mocy PO zdarzeniu QExt2 W'bal=0% ---
    anchor = _road_anchor_check(db_conn, as_of)
    out["wprime_road_anchor"] = anchor
    if anchor is not None:
        if anchor["status"] == "confirmed" and out.get("wprime_confidence") == "medium":
            out["wprime_confidence"] = "high"
            out["wprime_source"] = f"{out.get('wprime_source') or ''}; {anchor['note']} -> pewnosc podniesiona"
        elif anchor["status"] == "contradicted":
            # NIE obnizamy automatycznie ani nie zmieniamy liczby -- tylko jawna flaga do przegladu.
            out["wprime_source"] = f"{out.get('wprime_source') or ''}; UWAGA: {anchor['note']}"

    # --- Peak Power (Krok "a") -- domkniecie Fitness Signature ---
    out.update(_peak_power(db_conn, as_of, window_days))

    return out


def upsert_into_daily(db_conn, row: dict[str, Any]) -> None:
    """Zapisz cp/ltp/wprime do istniejacego (lub nowego) wiersza fitmodel_daily.day."""
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO qbot_v2.fitmodel_daily
                (day, cp_modelq_w, wprime_modelq_kj, cp_wprime_r2, cp_wprime_note,
                 ltp_modelq_w, ltp_modelq_r2, ltp_modelq_note,
                 wprime_lo_kj, wprime_hi_kj, wprime_confidence, wprime_source,
                 pp_modelq_w, pp_instant_w, pp_confidence, pp_note)
            VALUES
                (%(day)s, %(cp_modelq_w)s, %(wprime_modelq_kj)s, %(cp_wprime_r2)s, %(cp_wprime_note)s,
                 %(ltp_modelq_w)s, %(ltp_modelq_r2)s, %(ltp_modelq_note)s,
                 %(wprime_lo_kj)s, %(wprime_hi_kj)s, %(wprime_confidence)s, %(wprime_source)s,
                 %(pp_modelq_w)s, %(pp_instant_w)s, %(pp_confidence)s, %(pp_note)s)
            ON CONFLICT (day) DO UPDATE SET
                cp_modelq_w = EXCLUDED.cp_modelq_w,
                wprime_modelq_kj = EXCLUDED.wprime_modelq_kj,
                cp_wprime_r2 = EXCLUDED.cp_wprime_r2,
                cp_wprime_note = EXCLUDED.cp_wprime_note,
                ltp_modelq_w = EXCLUDED.ltp_modelq_w,
                ltp_modelq_r2 = EXCLUDED.ltp_modelq_r2,
                ltp_modelq_note = EXCLUDED.ltp_modelq_note,
                wprime_lo_kj = EXCLUDED.wprime_lo_kj,
                wprime_hi_kj = EXCLUDED.wprime_hi_kj,
                wprime_confidence = EXCLUDED.wprime_confidence,
                wprime_source = EXCLUDED.wprime_source,
                pp_modelq_w = EXCLUDED.pp_modelq_w,
                pp_instant_w = EXCLUDED.pp_instant_w,
                pp_confidence = EXCLUDED.pp_confidence,
                pp_note = EXCLUDED.pp_note
            """,
            row,
        )
    db_conn.commit()


def run_daily(db_conn, as_of: date | None = None, window_days: int = WINDOW_DAYS, dry_run: bool = False) -> dict[str, Any]:
    row = compute_cp_wprime(db_conn, as_of, window_days)
    if not dry_run:
        upsert_into_daily(db_conn, row)
    return row


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FITMODEL CP (krotkie okna) i LTP (dlugie okna) z krzywej mocy (MMP)")
    parser.add_argument("--as-of", default=None, help="data odniesienia YYYY-MM-DD (domyslnie dzis)")
    parser.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = _db_connect()
    try:
        row = run_daily(conn, as_of=args.as_of, window_days=args.window_days, dry_run=args.dry_run)
        print("DRY-RUN (bez zapisu):" if args.dry_run else "ZAPISANO:")
        for k, v in row.items():
            print(f"  {k} = {v}")
    finally:
        conn.close()
