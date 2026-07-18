from __future__ import annotations

"""ModelQ -- wskaznik gotowosci (readiness) z sygnalow wellness.

Backstage (nic tego jeszcze nie wyswietla). Liczy dzienny wskaznik gotowosci
z 3 sygnalow Garmina: HRV, RHR (tetno spoczynkowe), sen. Kazdy sygnal jako
odchylenie (z-score) od KROCZACEGO baseline 60 dni -> lapie zmiane wzgledem
biezacej formy, nie wzgledem staej historii. Wygladzanie mediana 3 dni tlumi
falszywe alarmy z jednej zlej nocy. Wagi: HRV 40% / RHR 35% / sen 25%.

Kalibracja INDYWIDUALNA: baseline to wlasne dane uzytkownika, nie progi
populacyjne. To odroznia od starego qbot_readiness.py (progi sztywne + Body
Battery/Firstbeat, uznane za niewiarygodne).

Wynik: score (float) + label {swiezy|neutralny|zmeczony} + note (rozbicie z).
Progi etykiet: score >= +0.4 swiezy, <= -0.4 zmeczony, inaczej neutralny.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median, pstdev, mean
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2

W_HRV, W_RHR, W_SLEEP = 0.40, 0.35, 0.25
BASELINE_DAYS = 60
SMOOTH_DAYS = 3
MIN_BASELINE_N = 20
FRESH_THR = 0.4
TIRED_THR = -0.4

# L2 subiektyw (feel/choroba) -> readiness_effective (osobne kolumny; obiektyw nietkniety)
W_SUBJ_FEEL = 0.15   # na 1 punkt feel (feel -2..+2 -> +-0.30)
ILLNESS_DELTA = -0.30  # aktywna choroba danego dnia
SUBJ_CAP = 0.50        # limit laczny |subj_delta|


def _db_connect():
    kwargs: dict[str, Any] = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return psycopg2.connect(**kwargs)


def _coerce_date(value) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _fetch_series(cur, as_of: date, col: str, days: int) -> dict[date, float]:
    start = as_of - timedelta(days=days)
    cur.execute(
        f"""
        SELECT date, {col} FROM qbot_v2.qbot_wellness_daily
        WHERE source='garmin' AND {col} IS NOT NULL
          AND date > %s AND date <= %s
        ORDER BY date
        """,
        (start, as_of),
    )
    return {r[0]: float(r[1]) for r in cur.fetchall()}


def _z_for(cur, as_of: date, col: str, invert: bool = False) -> float | None:
    # baseline: 60 dni KONCZACE sie dzien przed as_of (bez dnia biezacego)
    base = _fetch_series(cur, as_of - timedelta(days=1), col, BASELINE_DAYS)
    if len(base) < MIN_BASELINE_N:
        return None
    vals = list(base.values())
    mu = mean(vals)
    sd = pstdev(vals)
    if sd == 0:
        return None
    recent = _fetch_series(cur, as_of, col, SMOOTH_DAYS)
    if not recent:
        return None
    cur_val = median(list(recent.values()))
    z = (cur_val - mu) / sd
    return -z if invert else z


def compute_readiness(db_conn, as_of: date | None = None) -> dict[str, Any]:
    """Policz wskaznik gotowosci na dany dzien. Zwraca dict (score/label/note/z_*)."""
    as_of = _coerce_date(as_of)
    with db_conn.cursor() as cur:
        z_hrv = _z_for(cur, as_of, "hrv_ms", invert=False)
        z_rhr = _z_for(cur, as_of, "resting_hr_bpm", invert=True)  # wyzsze RHR = gorzej
        z_slp = _z_for(cur, as_of, "sleep_duration_min", invert=False)

    parts = [(W_HRV, z_hrv, "hrv"), (W_RHR, z_rhr, "rhr"), (W_SLEEP, z_slp, "sen")]
    avail = [(w, z) for w, z, _ in parts if z is not None]
    out: dict[str, Any] = {
        "day": as_of.isoformat(),
        "readiness_score": None, "readiness_label": None, "readiness_note": None,
        "z_hrv": round(z_hrv, 2) if z_hrv is not None else None,
        "z_rhr": round(z_rhr, 2) if z_rhr is not None else None,
        "z_sleep": round(z_slp, 2) if z_slp is not None else None,
    }
    if not avail:
        out["readiness_note"] = "brak wystarczajacych danych wellness (baseline < 20 dni)"
        return out

    wsum = sum(w for w, _ in avail)
    score = sum(w * z for w, z in avail) / wsum
    if score >= FRESH_THR:
        label = "swiezy"
    elif score <= TIRED_THR:
        label = "zmeczony"
    else:
        label = "neutralny"

    bits = []
    if z_hrv is not None:
        bits.append(f"HRV {z_hrv:+.2f}")
    if z_rhr is not None:
        bits.append(f"RHR {z_rhr:+.2f}")
    if z_slp is not None:
        bits.append(f"sen {z_slp:+.2f}")
    note = f"baseline 60d, mediana 3d; z-score: {', '.join(bits)}"
    if len(avail) < 3:
        note += f" (tylko {len(avail)}/3 sygnalow)"

    out["readiness_score"] = round(score, 3)
    out["readiness_label"] = label
    out["readiness_note"] = note
    return out


def _raw_wellness_for_day(cur, as_of: date) -> dict[str, Any]:
    """Surowe wartosci wellness dnia -> kolumny fitmodel_daily. Waga: carry-forward."""
    cur.execute(
        """SELECT sleep_duration_min, hrv_ms, resting_hr_bpm, weight_kg
           FROM qbot_v2.qbot_wellness_daily WHERE date=%s
           ORDER BY source_priority ASC, imported_at DESC LIMIT 1""",
        (as_of,),
    )
    r = cur.fetchone()
    sleep_h = hrv = rhr = weight = None
    if r:
        sd, hv, rh, wt = r
        sleep_h = float(sd) / 60.0 if sd is not None else None
        hrv = float(hv) if hv is not None else None
        rhr = int(rh) if rh is not None else None
        weight = float(wt) if wt is not None else None
    if weight is None:
        cur.execute(
            """SELECT weight_kg FROM qbot_v2.qbot_wellness_daily
               WHERE weight_kg IS NOT NULL AND date<=%s
               ORDER BY date DESC LIMIT 1""",
            (as_of,),
        )
        w2 = cur.fetchone()
        weight = float(w2[0]) if w2 and w2[0] is not None else None
    return {"sleep_h": sleep_h, "hrv_night": hrv, "rhr": rhr, "weight_kg": weight}


def _subjective_for_day(cur, as_of: date):
    """L2 subiektyw dla ZAPISU dziennego: feel z DOKLADNIE tego dnia (brak=0) +
    aktywna choroba obejmujaca ten dzien. Zwraca (subj_delta_zaokr, note|None).
    NIE dotyka readiness_score ani bazy 60d (ta liczy sie z qbot_wellness_daily)."""
    cur.execute(
        "SELECT feel FROM qbot_v2.calendar_entry "
        "WHERE kind='feel' AND feel IS NOT NULL AND day=%s "
        "ORDER BY id DESC LIMIT 1",
        (as_of,),
    )
    r = cur.fetchone()
    feel = int(r[0]) if r and r[0] is not None else 0
    cur.execute(
        "SELECT 1 FROM qbot_v2.calendar_entry "
        "WHERE kind='illness' AND day<=%s AND COALESCE(end_day, day)>=%s LIMIT 1",
        (as_of, as_of),
    )
    ill = cur.fetchone() is not None

    feel_delta = feel * W_SUBJ_FEEL
    illness_delta = ILLNESS_DELTA if ill else 0.0
    raw = feel_delta + illness_delta
    subj = max(-SUBJ_CAP, min(SUBJ_CAP, raw))
    if feel == 0 and not ill:
        return 0.0, None
    bits = []
    if feel != 0:
        bits.append("feel %+d (%+.2f)" % (feel, feel_delta))
    if ill:
        bits.append("choroba (%+.2f)" % illness_delta)
    capped = (" [cap %+.2f]" % subj) if abs(raw) > SUBJ_CAP + 1e-9 else ""
    note = "subiektyw: " + ", ".join(bits) + capped
    return round(subj, 3), note


def save_readiness(db_conn, as_of: date | None = None) -> dict[str, Any]:
    """Policz i zapisz gotowosc + surowe wellness (sen/HRV/RHR/waga) do fitmodel_daily."""
    d = _coerce_date(as_of)
    row = compute_readiness(db_conn, d)
    with db_conn.cursor() as cur:
        row.update(_raw_wellness_for_day(cur, d))
        subj_delta, subj_note = _subjective_for_day(cur, d)
        base = row.get("readiness_score")
        if base is not None:
            eff = round(float(base) + subj_delta, 3)
            if eff >= FRESH_THR:
                eff_label = "swiezy"
            elif eff <= TIRED_THR:
                eff_label = "zmeczony"
            else:
                eff_label = "neutralny"
            eff_note = subj_note if subj_note else "subiektyw neutralny (brak wpisu)"
        else:
            eff = None
            eff_label = None
            eff_note = "brak obiektywnej bazy readiness"
        row["readiness_effective"] = eff
        row["readiness_effective_label"] = eff_label
        row["readiness_subj_delta"] = subj_delta
        row["readiness_effective_note"] = eff_note
        cur.execute(
            """
            INSERT INTO qbot_v2.fitmodel_daily (day, readiness_score, readiness_label, readiness_note,
                sleep_h, hrv_night, rhr, weight_kg,
                readiness_effective, readiness_effective_label, readiness_subj_delta, readiness_effective_note)
            VALUES (%(day)s, %(readiness_score)s, %(readiness_label)s, %(readiness_note)s,
                %(sleep_h)s, %(hrv_night)s, %(rhr)s, %(weight_kg)s,
                %(readiness_effective)s, %(readiness_effective_label)s, %(readiness_subj_delta)s, %(readiness_effective_note)s)
            ON CONFLICT (day) DO UPDATE SET
                readiness_score = EXCLUDED.readiness_score,
                readiness_label = EXCLUDED.readiness_label,
                readiness_note = EXCLUDED.readiness_note,
                readiness_effective = EXCLUDED.readiness_effective,
                readiness_effective_label = EXCLUDED.readiness_effective_label,
                readiness_subj_delta = EXCLUDED.readiness_subj_delta,
                readiness_effective_note = EXCLUDED.readiness_effective_note,
                sleep_h = EXCLUDED.sleep_h,
                hrv_night = EXCLUDED.hrv_night,
                rhr = EXCLUDED.rhr,
                weight_kg = COALESCE(EXCLUDED.weight_kg, qbot_v2.fitmodel_daily.weight_kg)
            """,
            row,
        )
    db_conn.commit()
    return row


if __name__ == "__main__":
    conn = _db_connect()
    d = sys.argv[1] if len(sys.argv) > 1 else None
    print(save_readiness(conn, d))
    conn.close()
