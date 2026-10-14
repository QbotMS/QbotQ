"""Dryf tetna i czas w upale ([GARMIN-DANE] Etap 7, decyzja 2026-10-14).

Dryf (decoupling, Pa:HR): jazda > 1,5 h, pomijamy pierwsze 10 min, dzielimy na polowy;
    EF = srednia moc / srednie tetno;  dryf = (EF1 - EF2) / EF1 * 100  [%]
    < 5% = dobra baza tlenowa; rosnie w upale i przy zmeczeniu.
Upal = minuty z temperatura Karoo >= 25 C (NIE srednia jazdy -- dlugie jazdy zaczynasz w chlodzie, srednia rozmywa;
    czujnik na sloncu zawyza wartosci szczytowe, np. 49 C, dlatego prog i czas, nie maksimum).
TYLKO probki w pasmie 0.55-0.92 CP (wytrzymalosc) -- inaczej teren falszuje (podjazd/zjazd w roznych polowach).
Dane 2025-2026 (jazdy > 1,5 h, pasmo): bez upalu mediana 0,6% (107), 10-60 min > 25 C 1,0% (20), >= 1 h > 25 C 2,9% (19).
(Pierwsza wersja bez pasma: 2,7 / 3,4 / 8,8% -- zawyzona przez teren, odrzucona 2026-10-14.)
Upal NIE podnosi sredniego tetna przy tej samej mocy (forma latem > zima) -- dlatego dryf, nie HR@moc.
Typowo = mediana dryfu w tej samej grupie upalu z 365 dni (bez tej jazdy).
Cache: qbot_v2.ride_heat_drift (sql/heat_drift_v1.sql); historia: scripts/heat_drift_backfill.py.
Dok.: docs/GARMIN_DANE.md
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

MIN_DUR_S = 5400
SKIP_S = 600
BAND_LO, BAND_HI = 0.55, 0.92   # pasmo mocy (x CP ModelQ dnia jazdy); brak CP -> 240 W
CP_FALLBACK = 240.0
HOT_C = 25.0
SQL_FILE = Path("/opt/qbot/app/sql/heat_drift_v1.sql")

SQL_HALVES = """
SELECT ar.sec < %(half)s AS h1, avg(ar.power_w) AS p, avg(ar.hr_bpm) AS hr, count(*) AS n,
       count(*) FILTER (WHERE ar.temperature_c >= %(hot)s) AS hot, avg(ar.temperature_c) AS tc
FROM qbot_v2.activity_record ar
WHERE ar.external_id = %(id)s AND ar.sec >= %(skip)s AND ar.power_w BETWEEN %(lo)s AND %(hi)s AND ar.hr_bpm > 60
GROUP BY 1"""


def _cur(cx):
    return cx.cursor() if hasattr(cx, "cursor") else cx


def _rows(cx, sql, params=()):
    cur = _cur(cx)
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SQL_FILE.read_text())
    conn.commit()


def bucket(hot_min: float | None) -> int:
    h = hot_min or 0
    return 0 if h < 10 else 1 if h < 60 else 2


def drift_from_halves(h1: dict, h2: dict) -> float | None:
    """EF polowek -> dryf %. None gdy za malo danych (min. 10 min w kazdej polowie)."""
    if not h1 or not h2 or min(h1["n"], h2["n"]) < 600 or not h1["hr"] or not h2["hr"]:
        return None
    ef1, ef2 = float(h1["p"]) / float(h1["hr"]), float(h2["p"]) / float(h2["hr"])
    return round((ef1 - ef2) / ef1 * 100, 1) if ef1 > 0 else None


def compute_ride(cx, external_id: str, duration_s: int, ride_date: date | None = None) -> dict[str, Any] | None:
    cp = None
    if ride_date:
        r = _rows(cx, "SELECT cp_modelq_w FROM qbot_v2.fitmodel_daily WHERE day <= %s AND cp_modelq_w IS NOT NULL "
                      "ORDER BY day DESC LIMIT 1", (ride_date,))
        cp = float(r[0]["cp_modelq_w"]) if r else None
    cp = cp or CP_FALLBACK
    hv = _rows(cx, SQL_HALVES, {"half": duration_s / 2, "hot": HOT_C, "id": str(external_id), "skip": SKIP_S,
                               "lo": BAND_LO * cp, "hi": BAND_HI * cp})
    h1 = next((r for r in hv if r["h1"]), None)
    h2 = next((r for r in hv if not r["h1"]), None)
    d = drift_from_halves(h1, h2)
    if d is None:
        return None
    hr_ = _rows(cx, "SELECT count(*) FILTER (WHERE temperature_c >= %s) AS hot FROM qbot_v2.activity_record "
                   "WHERE external_id = %s", (HOT_C, str(external_id)))
    hot = float(hr_[0]["hot"] or 0) / 60.0   # czas w upale z CALEJ jazdy (nie tylko pasma)
    tcs = [float(x["tc"]) for x in (h1, h2) if x["tc"] is not None]
    return {"drift_pct": d, "hot_min": round(hot, 1), "temp_avg": round(sum(tcs) / len(tcs), 1) if tcs else None}


def ensure_rides(cx, d0: date, d1: date, limit: int = 40) -> int:
    """Liczy brakujace jazdy (> 1,5 h z plikiem) w zakresie i zapisuje do cache. Zwraca liczbe policzonych."""
    todo = _rows(cx, """
        SELECT t.external_id, t.date, t.duration_s FROM qbot_v2.training_sessions t
        WHERE t.date BETWEEN %s AND %s AND t.duration_s > %s
          AND EXISTS (SELECT 1 FROM qbot_v2.activity_record ar WHERE ar.external_id = t.external_id AND ar.sec = 0)
          AND NOT EXISTS (SELECT 1 FROM qbot_v2.ride_heat_drift h WHERE h.external_id = t.external_id)
        ORDER BY t.date DESC LIMIT %s""", (d0, d1, MIN_DUR_S, limit))
    n = 0
    for r in todo:
        res = compute_ride(cx, r["external_id"], int(r["duration_s"]), r["date"])
        _cur(cx).execute("""
            INSERT INTO qbot_v2.ride_heat_drift (external_id, ride_date, duration_s, drift_pct, hot_min, temp_avg)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (external_id) DO UPDATE SET drift_pct=EXCLUDED.drift_pct,
              hot_min=EXCLUDED.hot_min, temp_avg=EXCLUDED.temp_avg, computed_at=now()""",
            (str(r["external_id"]), r["date"], r["duration_s"], res and res["drift_pct"], res and res["hot_min"],
             res and res["temp_avg"]))
        n += 1
    return n


def typical(cx, ride_date: date, hot_min: float | None, exclude_id: str | None = None) -> float | None:
    """Mediana dryfu w tej samej grupie upalu z 365 dni przed jazda (min. 8 jazd)."""
    rs = _rows(cx, "SELECT external_id, drift_pct, hot_min FROM qbot_v2.ride_heat_drift "
                   "WHERE drift_pct IS NOT NULL AND ride_date BETWEEN %s AND %s", (ride_date - timedelta(days=365), ride_date))
    b = bucket(hot_min)
    xs = sorted(float(r["drift_pct"]) for r in rs if bucket(r["hot_min"]) == b and str(r["external_id"]) != str(exclude_id))
    if len(xs) < 8:
        return None
    m = len(xs) // 2
    return round(xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2, 1)


def ride_block(cx, external_id: str) -> dict[str, Any] | None:
    """Dla raportu jazdy: {drift_pct, hot_min, temp_avg, typical}; liczy i zapisuje gdy brak w cache."""
    r = _rows(cx, "SELECT ride_date, drift_pct, hot_min, temp_avg FROM qbot_v2.ride_heat_drift WHERE external_id = %s",
              (str(external_id),))
    if not r:
        t = _rows(cx, "SELECT date, duration_s FROM qbot_v2.training_sessions WHERE external_id = %s", (str(external_id),))
        if not t or (t[0]["duration_s"] or 0) <= MIN_DUR_S:
            return None
        ensure_rides(cx, t[0]["date"], t[0]["date"])
        r = _rows(cx, "SELECT ride_date, drift_pct, hot_min, temp_avg FROM qbot_v2.ride_heat_drift WHERE external_id = %s",
                  (str(external_id),))
    if not r or r[0]["drift_pct"] is None:
        return None
    x = r[0]
    return {"drift_pct": float(x["drift_pct"]), "hot_min": float(x["hot_min"] or 0),
            "temp_avg": x["temp_avg"], "typical": typical(cx, x["ride_date"], x["hot_min"], external_id)}


def add_drift(cx, series: list[dict]) -> list[dict]:
    """Dopisuje do serii Formy: drift_pct / drift_hot_min (najdluzsza jazda dnia > 1,5 h z dryfem)."""
    if not series:
        return series
    days = [s["day"] for s in series if s.get("day")]
    rs = _rows(cx, "SELECT ride_date, drift_pct, hot_min, duration_s FROM qbot_v2.ride_heat_drift "
                   "WHERE drift_pct IS NOT NULL AND ride_date BETWEEN %s AND %s", (min(days), max(days)))
    best = {}
    for r in rs:
        k = r["ride_date"].isoformat()
        if k not in best or (r["duration_s"] or 0) > (best[k]["duration_s"] or 0):
            best[k] = r
    for s in series:
        b = best.get(str(s.get("day")))
        s["drift_pct"] = float(b["drift_pct"]) if b else None
        s["drift_hot_min"] = float(b["hot_min"] or 0) if b else None
    return series


def acclimation(cx, until: date, days: int = 28) -> dict[str, Any] | None:
    """Przygotowanie do goracego wydarzenia: dryf z jazd >= 1 h w upale z ostatnich `days` dni vs norma w upale (365 dni)."""
    rs = _rows(cx, "SELECT ride_date, drift_pct, hot_min FROM qbot_v2.ride_heat_drift WHERE drift_pct IS NOT NULL "
                   "AND hot_min >= 60 AND ride_date BETWEEN %s AND %s ORDER BY ride_date", (until - timedelta(days=365), until))
    recent = [r for r in rs if r["ride_date"] >= until - timedelta(days=days)]
    norm = typical(cx, until, 60)
    if not recent:
        return {"recent": [], "norm": norm, "text": f"Brak jazd z ≥ 1 h w upale w ostatnich {days} dniach — "
                                                    "przed gorącym wyjazdem warto zrobić 2–3 dłuższe jazdy w cieple."}
    avg = sum(float(r["drift_pct"]) for r in recent) / len(recent)
    verdict = ("lepiej niż Twoja norma w upale — organizm dobrze znosi ciepło" if norm is not None and avg < norm - 1
               else "gorzej niż Twoja norma w upale — dawkuj tempo i nawadnianie" if norm is not None and avg > norm + 1
               else "na poziomie Twojej normy w upale")
    return {"recent": [{"date": r["ride_date"].isoformat(), "drift_pct": float(r["drift_pct"]), "hot_min": float(r["hot_min"])}
                       for r in recent], "avg": round(avg, 1), "norm": norm,
            "text": f"Upał: dryf tętna na {len(recent)} gorących jazdach z {days} dni średnio {_pl(avg)}% "
                    f"(norma w upale {_pl(norm) if norm is not None else '—'}%) — {verdict}."}


def _pl(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")
