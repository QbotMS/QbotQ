"""HRV z jazdy: DFA a1 z odstepow RR pasa Polar H10 -> prog tlenowy (LTP) i okolice TP z mocy.

20.10.2026 (sesja hrv-h10-2010, TODO [HRV-JAZDA] etap 3, dok. docs/HRV_JAZDA.md).
Wejscie: qbot_v2.qext2_hrv_rr (surowe RR z QExt2) + qbot_v2.activity_record (1 Hz: moc, tetno, predkosc).
Wyjscie: qbot_v2.hrv_ride_result (sql/hrv_rr_v2.sql) + qext2_hrv_rr.session_id.

Kroki:
 1. Dopasowanie do jazdy: activity_fit_raw.started_at w +-15 min od startu zapisu w pasie; przesuniecie czasu
    z najlepszej zgodnosci tetna z pasa i tetna z Karoo (+-180 s). Zla zgodnosc (r<0.5) -> wynik oznaczony.
 2. Czyszczenie: RR poza 300..2000 ms albo odchylone >20% od mediany 11 sasiednich = bledne uderzenie;
    do obliczen zastapione interpolacja. Odsetek blednych = kondycja paska / jakosc sygnalu.
 3. DFA a1: okna 120 s co 15 s, skale 4..16 uderzen (standard z badan, Rogers/Gronwald). Okno z >5% blednych odpada.
 4. Rowna jazda: w oknie postoj/brak predkosci <5% s, toczenie bez mocy <15% s, zmiennosc mocy (srednie 10 s) CV<0.20.
 5. a1 ~ moc (regresja liniowa z jednokrotnym odrzuceniem odstajacych >2.5 SD): moc przy a1=0.75 -> LTP z HRV,
    przy a1=0.5 -> okolice TP (tylko gdy byly okna z a1<0.6). Pewnosc z liczby okien, korelacji i tego, czy 0.75
    lezy w zakresie zmierzonych a1 (bez ekstrapolacji).
 6. Zmeczenie: a1 w tym samym pasmie mocy (p25..p75) w 1. vs 2. polowie jazdy. Rozgrzewka: srednie a1 z 15 min.
NIE wplywa na ModelQ (etap 5: walidacja, decyzja Michala).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

WIN_S = 120
STEP_S = 15
MAX_ART = 0.05
SCALES = np.arange(4, 17)
A1_LTP = 0.75
A1_TP = 0.50
MATCH_MS = 15 * 60 * 1000
VERSION = 1


# ---------------- czyste funkcje (testy: tests/test_hrv_ride.py) ----------------

def clean_rr(rr) -> tuple[np.ndarray, np.ndarray]:
    """-> (rr po korekcie, maska blednych). Bledne: poza 300..2000 ms albo >20% od mediany 11 sasiednich."""
    x = np.asarray(rr, dtype=float)
    n = len(x)
    bad = (x < 300) | (x > 2000)
    if n >= 5:
        pad = np.pad(np.where(bad, np.nan, x), 5, mode="edge")
        win = np.lib.stride_tricks.sliding_window_view(pad, 11)
        med = np.nanmedian(win, axis=1)
        bad |= np.abs(x - med) > 0.20 * med
    y = x.copy()
    good = ~bad
    if good.sum() >= 2 and bad.any():
        idx = np.arange(n)
        y[bad] = np.interp(idx[bad], idx[good], x[good])
    return y, bad


def dfa_a1(rr) -> float | None:
    """Krotkoterminowy wykladnik DFA (skale 4..16 uderzen). None gdy za malo danych."""
    x = np.asarray(rr, dtype=float)
    if len(x) < 4 * SCALES[-1]:
        return None
    y = np.cumsum(x - x.mean())
    F = []
    for s in SCALES:
        nb = len(y) // s
        seg = y[: nb * s].reshape(nb, s)
        t = np.arange(s)
        A = np.vstack([t, np.ones(s)]).T
        coef, *_ = np.linalg.lstsq(A, seg.T, rcond=None)
        res = seg - (A @ coef).T
        F.append(np.sqrt(np.mean(res ** 2)))
    F = np.asarray(F)
    if np.any(F <= 0):
        return None
    return float(np.polyfit(np.log(SCALES), np.log(F), 1)[0])


def windows(beat_t_s, rr_clean, bad, t_end_s) -> list[dict]:
    """Okna 120 s co 15 s na osi czasu jazdy (s od startu nagrania). -> [{t0, t1, a1, art, hr}]"""
    out = []
    t0 = 0.0
    while t0 + WIN_S <= t_end_s:
        i0, i1 = np.searchsorted(beat_t_s, [t0, t0 + WIN_S])
        if i1 - i0 >= 60:
            art = float(bad[i0:i1].mean())
            a1 = dfa_a1(rr_clean[i0:i1]) if art <= MAX_ART else None
            out.append({"t0": t0, "t1": t0 + WIN_S, "a1": a1, "art": art,
                        "hr": 60000.0 / float(np.mean(rr_clean[i0:i1]))})
        t0 += STEP_S
    return out


def fit_threshold(P, A1, target) -> float | None:
    if len(P) < 3:
        return None
    b, a = np.polyfit(P, A1, 1)
    if b >= 0:
        return None
    return float((target - a) / b)


def regress(P, A1) -> dict:
    """a1 ~ moc, jednokrotne odrzucenie odstajacych (>2.5 SD reszt). -> {n, r, ltp_w, tp_w, conf_ltp, conf_tp}"""
    P = np.asarray(P, float); A1 = np.asarray(A1, float)
    out = {"n": int(len(P)), "r": None, "ltp_w": None, "tp_w": None, "conf_ltp": "brak", "conf_tp": "brak"}
    if len(P) < 6 or np.ptp(P) < 20:
        return out
    b, a = np.polyfit(P, A1, 1)
    res = A1 - (a + b * P)
    keep = np.abs(res) <= 2.5 * res.std() if res.std() > 0 else np.ones(len(P), bool)
    P, A1 = P[keep], A1[keep]
    out["n"] = int(len(P))
    r = float(np.corrcoef(P, A1)[0, 1]) if len(P) > 2 else 0.0
    out["r"] = round(r, 2)
    ltp = fit_threshold(P, A1, A1_LTP)
    if ltp is not None and 50 < ltp < 600:
        out["ltp_w"] = round(ltp)
        bracket = A1.min() < A1_LTP - 0.05 and A1.max() > A1_LTP + 0.05
        loose = A1.min() < A1_LTP + 0.05 and A1.max() > A1_LTP - 0.05
        if len(P) >= 20 and bracket and r <= -0.5:
            out["conf_ltp"] = "wysoka"
        elif len(P) >= 10 and loose and r <= -0.3:
            out["conf_ltp"] = "srednia"
        else:
            out["conf_ltp"] = "niska"
    if A1.min() < 0.60:
        tp = fit_threshold(P, A1, A1_TP)
        if tp is not None and 50 < tp < 700:
            out["tp_w"] = round(tp)
            out["conf_tp"] = "srednia" if (len(P) >= 15 and A1.min() < A1_TP + 0.05 and r <= -0.5) else "niska"
    return out


def steady(power_1hz, speed_1hz) -> tuple[bool, float | None]:
    """Czy okno to rowna jazda; -> (tak/nie, srednia moc)."""
    p = np.asarray(power_1hz, float); v = np.asarray(speed_1hz, float)
    if len(p) < WIN_S * 0.8 or np.isnan(p).mean() > 0.1:
        return False, None
    p = np.nan_to_num(p); v = np.nan_to_num(v)
    if (v < 1.5).mean() > 0.05 or (p < 10).mean() > 0.15:
        return False, None
    m10 = np.convolve(p, np.ones(10) / 10, mode="valid")
    cv = m10.std() / m10.mean() if m10.mean() > 0 else 9
    return bool(cv < 0.20), float(p.mean())


# ---------------- baza ----------------

def _db():
    from fitmodel.api import _db_connect
    return _db_connect()


def _match_session(cur, rec_start_ms: int):
    cur.execute("SELECT external_id, started_at FROM qbot_v2.activity_fit_raw "
                "WHERE abs(extract(epoch FROM started_at) * 1000 - %s) < %s "
                "ORDER BY abs(extract(epoch FROM started_at) * 1000 - %s) LIMIT 1",
                (rec_start_ms, MATCH_MS, rec_start_ms))
    return cur.fetchone()


def _best_lag(beat_abs_s, rr, rec_ts, rec_hr) -> tuple[int, float]:
    """Przesuniecie (s) tetna z pasa wzgledem Karoo o najlepszej korelacji, +-180 s."""
    if len(rec_ts) < 300:
        return 0, float("nan")
    t0 = int(rec_ts[0])
    sec = np.floor(beat_abs_s - t0).astype(int)
    n = int(rec_ts[-1] - t0) + 1
    hr_strap = np.full(n, np.nan)
    ok = (sec >= 0) & (sec < n)
    sums = np.bincount(sec[ok], weights=60000.0 / rr[ok], minlength=n)
    cnt = np.bincount(sec[ok], minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        hr_strap = np.where(cnt > 0, sums / np.maximum(cnt, 1), np.nan)
    hr_k = np.full(n, np.nan)
    hr_k[(rec_ts - t0).astype(int)] = rec_hr
    best, best_r = 0, -2.0
    for lag in range(-180, 181, 2):
        a = hr_strap[max(0, lag): n + min(0, lag)]
        b = hr_k[max(0, -lag): n - max(0, lag)]
        m = ~np.isnan(a) & ~np.isnan(b) & (b > 0)
        if m.sum() < 300:
            continue
        r = np.corrcoef(a[m], b[m])[0, 1]
        if r > best_r:
            best, best_r = lag, r
    return best, float(best_r)


def analyze(exercise_id: str, conn=None) -> dict:
    own = conn is None
    conn = conn or _db()
    cur = conn.cursor()
    cur.execute("SELECT rec_start_ms, rr_ms, battery_pct FROM qbot_v2.qext2_hrv_rr WHERE exercise_id=%s", (exercise_id,))
    row = cur.fetchone()
    if not row:
        raise KeyError(exercise_id)
    rec_start_ms, rr_raw, battery = int(row[0]), list(row[1]), row[2]
    rr_c, bad = clean_rr(rr_raw)
    beat_rel = np.cumsum(np.asarray(rr_raw, float)) / 1000.0     # czas uderzen od startu zapisu (s), surowe RR = os czasu
    res = {"exercise_id": exercise_id, "version": VERSION, "n_rr": len(rr_raw),
           "dur_min": round(float(beat_rel[-1]) / 60, 1) if len(rr_raw) else 0,
           "artifact_pct": round(100 * float(bad.mean()), 2) if len(rr_raw) else None,
           "battery_pct": battery, "session_id": None, "lag_s": None, "hr_corr": None}
    m = _match_session(cur, rec_start_ms)
    wins = windows(beat_rel, rr_c, bad, float(beat_rel[-1]) if len(rr_raw) else 0)
    res["n_windows"] = len(wins)
    res["n_a1"] = sum(1 for w in wins if w["a1"] is not None)
    steady_rows = []
    if m:
        sid, started = m
        res["session_id"] = sid
        cur.execute("SELECT extract(epoch FROM ts), power_w, hr_bpm, speed_mps FROM qbot_v2.activity_record "
                    "WHERE external_id=%s AND ts IS NOT NULL ORDER BY ts", (sid,))
        rec = np.array([[float(a), np.nan if b is None else b, np.nan if c is None else c, np.nan if d is None else d]
                        for a, b, c, d in cur.fetchall()], float).reshape(-1, 4)
        if len(rec):
            # activity_record.ts bywa przesuniete o strefe czasowa wzgledem started_at (20.10: 13:21+02 zamiast 15:21+02).
            # Korekta = roznica zaokraglona do 15 min (strefa); sekundy reszty lapie dopasowanie tetna (_best_lag).
            tz_fix = round((started.timestamp() - rec[0, 0]) / 900.0) * 900.0
            rec[:, 0] += tz_fix
            res["tz_fix_s"] = int(tz_fix)
            beat_abs = rec_start_ms / 1000.0 + beat_rel
            lag, r = _best_lag(beat_abs, np.asarray(rr_c), rec[:, 0], rec[:, 2])
            res["lag_s"], res["hr_corr"] = lag, (round(r, 3) if r == r else None)
            # lag L: tetno z pasa w chwili t+L = tetno Karoo w chwili t -> czas jazdy = czas pasa - L
            off = rec_start_ms / 1000.0 - lag
            res["lag_edge"] = abs(lag) >= 178             # najlepsze na granicy zakresu = dopasowanie niepewne
            for w in wins:
                if w["a1"] is None:
                    continue
                lo, hi = np.searchsorted(rec[:, 0], [off + w["t0"], off + w["t1"]])
                ok, pw = steady(rec[lo:hi, 1], rec[lo:hi, 3])
                w["p"] = round(pw) if pw is not None else None
                w["steady"] = ok
                if ok:
                    steady_rows.append((w["t0"], pw, w["a1"], w["hr"]))
    res["n_steady"] = len(steady_rows)
    if steady_rows:
        S = np.array(steady_rows)
        res.update(regress(S[:, 1], S[:, 2]))
        hrfit = regress(S[:, 3], S[:, 2])            # ta sama metoda dla tetna (prog w uderzeniach/min)
        res["ltp_hr"] = hrfit.get("ltp_w")
        if len(S) >= 10:
            lo, hi = np.percentile(S[:, 1], [25, 75])
            band = (S[:, 1] >= lo) & (S[:, 1] <= hi)
            half = S[:, 0] < np.median(S[:, 0])
            a, b = S[band & half, 2], S[band & ~half, 2]
            if len(a) >= 5 and len(b) >= 5:
                res["drift_a1"] = round(float(b.mean() - a.mean()), 3)
                res["drift_band_w"] = [round(lo), round(hi)]
    warm = [w["a1"] for w in wins if w["a1"] is not None and w["t1"] <= 900]
    res["warmup_a1"] = round(float(np.mean(warm)), 3) if len(warm) >= 3 else None
    cur.execute("SELECT ltp_modelq_w, ftp_est_w FROM qbot_v2.fitmodel_daily WHERE day <= %s "
                "ORDER BY day DESC LIMIT 1", (datetime.fromtimestamp(rec_start_ms / 1000, timezone.utc).date(),))
    mq = cur.fetchone()
    res["ltp_modelq_w"] = float(mq[0]) if mq and mq[0] is not None else None
    res["tp_modelq_w"] = float(mq[1]) if mq and mq[1] is not None else None
    res["windows"] = [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in w.items()} for w in wins]
    _save(cur, res)
    conn.commit()
    if own:
        conn.close()
    return res


def _save(cur, r: dict) -> None:
    cur.execute("UPDATE qbot_v2.qext2_hrv_rr SET session_id=%s WHERE exercise_id=%s", (r["session_id"], r["exercise_id"]))
    cur.execute("""INSERT INTO qbot_v2.hrv_ride_result (exercise_id, session_id, version, lag_s, hr_corr, artifact_pct,
                       n_windows, n_steady, ltp_w, ltp_conf, ltp_hr, tp_w, tp_conf, r_power, drift_a1, warmup_a1,
                       ltp_modelq_w, tp_modelq_w, details, computed_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                   ON CONFLICT (exercise_id) DO UPDATE SET session_id=EXCLUDED.session_id, version=EXCLUDED.version,
                       lag_s=EXCLUDED.lag_s, hr_corr=EXCLUDED.hr_corr, artifact_pct=EXCLUDED.artifact_pct,
                       n_windows=EXCLUDED.n_windows, n_steady=EXCLUDED.n_steady, ltp_w=EXCLUDED.ltp_w,
                       ltp_conf=EXCLUDED.ltp_conf, ltp_hr=EXCLUDED.ltp_hr, tp_w=EXCLUDED.tp_w, tp_conf=EXCLUDED.tp_conf,
                       r_power=EXCLUDED.r_power, drift_a1=EXCLUDED.drift_a1, warmup_a1=EXCLUDED.warmup_a1,
                       ltp_modelq_w=EXCLUDED.ltp_modelq_w, tp_modelq_w=EXCLUDED.tp_modelq_w,
                       details=EXCLUDED.details, computed_at=now()""",
                (r["exercise_id"], r["session_id"], r["version"], r.get("lag_s"), r.get("hr_corr"), r.get("artifact_pct"),
                 r.get("n_windows"), r.get("n_steady"), r.get("ltp_w"), r.get("conf_ltp"), r.get("ltp_hr"),
                 r.get("tp_w"), r.get("conf_tp"), r.get("r"), r.get("drift_a1"), r.get("warmup_a1"),
                 r.get("ltp_modelq_w"), r.get("tp_modelq_w"), json.dumps(r)))


def process_pending(conn=None, days: int = 7) -> list[str]:
    """Nagrania z ostatnich dni bez wyniku albo bez dopasowanej jazdy (jazda mogla dojsc pozniej)."""
    own = conn is None
    conn = conn or _db()
    cur = conn.cursor()
    cur.execute("""SELECT r.exercise_id FROM qbot_v2.qext2_hrv_rr r
                   LEFT JOIN qbot_v2.hrv_ride_result h ON h.exercise_id = r.exercise_id
                   WHERE r.received_at > now() - make_interval(days => %s)
                     AND (h.exercise_id IS NULL OR h.session_id IS NULL OR h.version < %s)
                   ORDER BY r.rec_start_ms""", (days, VERSION))
    done = []
    for (ex,) in cur.fetchall():
        try:
            analyze(ex, conn)
            done.append(ex)
        except Exception as e:  # jedna zla paczka nie blokuje reszty
            conn.rollback()
            print(f"hrv_ride {ex}: {e!r}", flush=True)
    if own:
        conn.close()
    return done


def result_for_ride(conn, started) -> dict | None:
    """Do powiadomien: wynik dla jazdy o danym starcie (+-15 min)."""
    ms = int(started.timestamp() * 1000)
    cur = conn.cursor()
    cur.execute("""SELECT h.ltp_w, h.ltp_conf, h.tp_w, h.tp_conf, h.artifact_pct, h.n_steady, h.ltp_modelq_w, h.drift_a1
                   FROM qbot_v2.qext2_hrv_rr r JOIN qbot_v2.hrv_ride_result h ON h.exercise_id = r.exercise_id
                   WHERE abs(r.rec_start_ms - %s) < %s ORDER BY abs(r.rec_start_ms - %s) LIMIT 1""", (ms, MATCH_MS, ms))
    r = cur.fetchone()
    if not r:
        return None
    keys = ["ltp_w", "ltp_conf", "tp_w", "tp_conf", "artifact_pct", "n_steady", "ltp_modelq_w", "drift_a1"]
    return dict(zip(keys, r))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        out = analyze(sys.argv[1])
        out.pop("windows", None)
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    else:
        print("przeliczone:", process_pending())
