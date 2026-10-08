"""Dynamiczne LTHR (tetno progowe) -- liczone codziennie z jazd (decyzja Michala 2026-10-08).

DLACZEGO: kanon LTHR=132 bpm (QExt2/hr_xss/raporty) byl o ~18 ud. za niski -- spokojna jazda wychodzila "nad progiem".
Backtest 01.2025-10.2026 (DECISIONS 2026-10-08): wartosci 147-155, dzis ~150. Nigdy ponizej 147.

METODA (wybrana backtestem; "wysilek progowy 25 min >= 90 % CP" nie wystapil ANI RAZU w historii, a zwykla regresja
z 6 tygodni skakala 120-166):
  - okna 8 min rownej jazdy (bez toczenia: <= 5 % probek < 30 W), od 10. minuty jazdy, tetno = mediana z ostatnich 4 min;
  - %CP = srednia moc okna / TP ModelQ z dnia jazdy (modelq2_signature);
  - kazde okno 70-110 % CP przeliczone na "tetno przy 100 % CP": HR + k * (1 - %CP),
    k = mediana nachylen HR(%CP) W OBREBIE jazd z 365 dni (start 80 ud. na 100 % CP, przeliczane co miesiac);
  - surowe LTHR = mediana z okna 120 dni; wymagane >= 12 okien z >= 4 jazd, inaczej zostaje poprzednie;
  - pomijane: jazdy w aktywnej kwarantannie miernika, okres wady miernika (METER_BAD), upal (mediana temp. okna >= 26 C).
PUBLIKACJA (lthr_daily.lthr_bpm, liczba calkowita): zmiana dopiero przy roznicy >= 2 ud. i najwyzej o 3 ud. wzgledem
wartosci sprzed 7 dni. Start/fallback: 150.
KTO CZYTA: get_lthr() -- hr_xss (XSS z tetna, wraz z K kalibrowanymi tu: calibrate_hr_xss), raport jazdy, Trener,
qbot_api -> QExt2 (lthrBpm), Albert, threshold_sync -> intervals.icu -> Hammerhead/Karoo.
LTHR (bpm) od treningu prawie sie nie zmienia -- rosnie moc przy nim (CP). Automat lapie dryf i bledy, nie "forme".
"""
from __future__ import annotations

import datetime as dt
from statistics import median

SEED_BPM = 150
WINDOW_DAYS = 120
W_S, STEP_S, WARMUP_S = 480, 120, 600
PCT_MIN, PCT_MAX = 0.70, 1.10
HOT_C = 26.0
MIN_WINDOWS, MIN_RIDES = 12, 4
HYST_BPM, MAX_WEEK_BPM = 2, 3
SLOPE_DEFAULT, SLOPE_DAYS, SLOPE_MIN_RIDES = 80.0, 365, 8
METER_BAD = [(dt.date(2026, 7, 1), dt.date(2026, 8, 25))]   # DECISIONS 2026-08-04..2026-10-08 (wada osi AHP29525)
SERIES_FROM = dt.date(2025, 3, 1)
K_CALIB_DAYS, K_CALIB_MAX_AGE = 365, 28

DDL = [
    """CREATE TABLE IF NOT EXISTS qbot_v2.lthr_ride (external_id text PRIMARY KEY, ride_date date, started_at timestamptz,
         n_samples integer, n_windows integer, computed_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS qbot_v2.lthr_window (external_id text, start_sec integer, ride_date date,
         p_avg real, hr real, temp_c real, PRIMARY KEY (external_id, start_sec))""",
    """CREATE TABLE IF NOT EXISTS qbot_v2.lthr_daily (day date PRIMARY KEY, lthr_bpm integer NOT NULL, raw_bpm real,
         n_windows integer, n_rides integer, slope real, note text, computed_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS qbot_v2.hr_xss_calib (day date PRIMARY KEY, k_low real, k_high real, n_low integer,
         n_high integer, lthr_bpm integer, err_p25 real, err_p75 real, computed_at timestamptz DEFAULT now())""",
    "ALTER TABLE qbot_v2.hr_xss_calib ADD COLUMN IF NOT EXISTS temp_a real, ADD COLUMN IF NOT EXISTS temp_b real, "
    "ADD COLUMN IF NOT EXISTS n_temp integer, ADD COLUMN IF NOT EXISTS err_t_p25 real, ADD COLUMN IF NOT EXISTS err_t_p75 real",
]


def _t(rows):
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]


def ensure(conn) -> None:
    cur = conn.cursor()
    for q in DDL:
        cur.execute(q)
    conn.commit()


def _bad(d) -> bool:
    return any(a <= d <= b for a, b in METER_BAD)


# ---------------------------------------------------------------- okna (czyste funkcje)
def ride_windows(rows) -> list:
    """rows: [(sec, power_w, hr_bpm, temp_c)] po sec. Zwraca [(start_sec, p_avg, hr_med, temp_med)]."""
    out, n = [], len(rows)
    secs = [r[0] for r in rows]
    for i in range(WARMUP_S, n - W_S, STEP_S):
        if secs[i + W_S - 1] - secs[i] != W_S - 1:
            continue
        seg = rows[i:i + W_S]
        p = [r[1] or 0 for r in seg]
        if sum(1 for v in p if v < 30) > W_S * 0.05:
            continue
        pa = sum(p) / W_S
        if pa < 80:
            continue
        h = [r[2] for r in seg[W_S // 2:] if r[2]]
        if len(h) < W_S * 0.4:
            continue
        t = [r[3] for r in seg if r[3] is not None]
        out.append((int(secs[i]), round(pa, 1), float(median(h)), float(median(t)) if t else None))
    return out


def within_ride_slope(points) -> tuple:
    """points: [(eid, pct, hr)]. Mediana nachylen HR(%CP) w obrebie jazd -> (k, n_jazd)."""
    by = {}
    for eid, pct, hr in points:
        by.setdefault(eid, []).append((pct, hr))
    sl = []
    for L in by.values():
        if len(L) < 4:
            continue
        xs = [a for a, _ in L]
        if max(xs) - min(xs) < 0.15:
            continue
        mx, my = sum(xs) / len(xs), sum(b for _, b in L) / len(L)
        sxx = sum((a - mx) ** 2 for a in xs)
        sl.append(sum((a - mx) * (b - my) for a, b in L) / sxx)
    if len(sl) < SLOPE_MIN_RIDES:
        return SLOPE_DEFAULT, len(sl)
    return float(median(sl)), len(sl)


def raw_estimate(points, k) -> tuple:
    """points: [(eid, pct, hr, temp)] z okna 120 dni. -> (raw|None, n_okien, n_jazd)."""
    use = [(e, p, h) for e, p, h, t in points if PCT_MIN <= p <= PCT_MAX and (t is None or t < HOT_C)]
    nr = len({e for e, _, _ in use})
    if len(use) < MIN_WINDOWS or nr < MIN_RIDES:
        return None, len(use), nr
    return float(median(h + k * (1.0 - p) for _, p, h in use)), len(use), nr


def publish_step(raw, prev_pub, pub_7d_ago) -> int:
    """Histereza i limit tempa zmian. prev_pub/pub_7d_ago: int|None."""
    if prev_pub is None:
        return int(round(raw)) if raw is not None else SEED_BPM
    if raw is None or abs(raw - prev_pub) < HYST_BPM:
        return prev_pub
    ref = pub_7d_ago if pub_7d_ago is not None else prev_pub
    return int(round(min(max(raw, ref - MAX_WEEK_BPM), ref + MAX_WEEK_BPM)))


# ---------------------------------------------------------------- baza
def collect_new(conn, since=dt.date(2025, 1, 1), until=None) -> int:
    """Okna dla jazd jeszcze niepoliczonych (lthr_ride)."""
    cur = conn.cursor()
    cur.execute("""SELECT t.external_id, t.date, t.started_at FROM qbot_v2.training_sessions t
                   WHERE t.sport_type IN ('cycling','gravel_cycling') AND t.duration_s >= 1800 AND t.date >= %s
                     AND t.date <= %s
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.lthr_ride r WHERE r.external_id = t.external_id)""",
                (since, until or dt.date.today()))
    todo = _t(cur.fetchall())
    for eid, d, st in todo:
        cur.execute("SELECT sec, power_w, hr_bpm, temperature_c FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec", (eid,))
        R = _t(cur.fetchall())
        W = ride_windows(R) if R else []
        for s, pa, hr, tc in W:
            cur.execute("INSERT INTO qbot_v2.lthr_window (external_id, start_sec, ride_date, p_avg, hr, temp_c) "
                        "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (eid, s, d, pa, hr, tc))
        cur.execute("INSERT INTO qbot_v2.lthr_ride (external_id, ride_date, started_at, n_samples, n_windows) "
                    "VALUES (%s,%s,%s,%s,%s) ON CONFLICT (external_id) DO NOTHING", (eid, d, st, len(R), len(W)))
    conn.commit()
    return len(todo)


def _load_points(conn, d_from, d_to) -> list:
    """[(ride_date, eid, pct, hr, temp)] -- bez kwarantanny, bez METER_BAD, ta sama jazda (godzina startu) raz."""
    cur = conn.cursor()
    cur.execute("""SELECT w.ride_date, w.external_id, w.p_avg / s.tp_w, w.hr, w.temp_c, r.started_at, r.n_samples
                   FROM qbot_v2.lthr_window w JOIN qbot_v2.lthr_ride r USING (external_id)
                   JOIN qbot_v2.modelq2_signature s ON s.day = w.ride_date
                   WHERE w.ride_date BETWEEN %s AND %s
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine q
                                     WHERE q.external_id = w.external_id AND q.released IS NULL)""", (d_from, d_to))
    rows = _t(cur.fetchall())
    best = {}
    for d, eid, pct, hr, tc, st, n in rows:
        key = st or eid
        if key not in best or (n or 0) > best[key][1]:
            best[key] = (eid, n or 0)
    keep = {v[0] for v in best.values()}
    return sorted((d, eid, float(pct), float(hr), tc) for d, eid, pct, hr, tc, st, n in rows if eid in keep and not _bad(d))


def publish_series(conn, d_from, d_to) -> dict:
    cur = conn.cursor()
    pts = _load_points(conn, d_from - dt.timedelta(days=SLOPE_DAYS), d_to)
    cur.execute("SELECT day, lthr_bpm FROM qbot_v2.lthr_daily WHERE day < %s AND day >= %s ORDER BY day",
                (d_from, d_from - dt.timedelta(days=8)))
    pub = {d: int(v) for d, v in _t(cur.fetchall())}
    cur.execute("SELECT lthr_bpm FROM qbot_v2.lthr_daily WHERE day < %s ORDER BY day DESC LIMIT 1", (d_from,))
    r = cur.fetchone()
    prev = int(_t([r])[0][0]) if r else None
    k, k_n, k_month, d, n = SLOPE_DEFAULT, 0, None, d_from, 0
    while d <= d_to:
        if k_month != (d.year, d.month):
            k, k_n = within_ride_slope([(e, p, h) for dd, e, p, h, t in pts if d - dt.timedelta(days=SLOPE_DAYS) < dd <= d])
            k_month = (d.year, d.month)
        win = [(e, p, h, t) for dd, e, p, h, t in pts if d - dt.timedelta(days=WINDOW_DAYS) < dd <= d]
        raw, nw, nr = raw_estimate(win, k)
        p7 = pub.get(d - dt.timedelta(days=7))
        val = publish_step(raw, prev, p7)
        note = ("k=%.0f z %d jazd" % (k, k_n)) + ("" if raw is not None else "; za malo okien -- bez zmian")
        cur.execute("""INSERT INTO qbot_v2.lthr_daily (day, lthr_bpm, raw_bpm, n_windows, n_rides, slope, note)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (day) DO UPDATE SET lthr_bpm=EXCLUDED.lthr_bpm,
                       raw_bpm=EXCLUDED.raw_bpm, n_windows=EXCLUDED.n_windows, n_rides=EXCLUDED.n_rides,
                       slope=EXCLUDED.slope, note=EXCLUDED.note, computed_at=now()""",
                    (d, val, round(raw, 1) if raw is not None else None, nw, nr, round(k, 1), note))
        pub[d], prev = val, val
        d += dt.timedelta(days=1)
        n += 1
    conn.commit()
    return {"days": n, "lthr": prev, "slope": round(k, 1)}


def get_lthr(conn=None, day=None) -> int:
    """Opublikowane LTHR na dzien (domyslnie dzis). Fallback SEED_BPM."""
    own = conn is None
    if own:
        from fitmodel.ftp_resolver import _db_connect
        conn = _db_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT lthr_bpm FROM qbot_v2.lthr_daily WHERE day <= %s ORDER BY day DESC LIMIT 1",
                    (day or dt.date.today(),))
        r = cur.fetchone()
        return int(_t([r])[0][0]) if r else SEED_BPM
    except Exception:
        return SEED_BPM
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------- kalibracja XSS z tetna
def calibrate_hr_xss(conn, day=None) -> dict:
    """K_LOW/K_HIGH dla XSS z tetna przy dynamicznym LTHR: mediany XSS_moc/HR_surowe na czystych jazdach z 365 dni."""
    from fitmodel.modelq2.hr_xss import compute_hr_xss_split
    day = day or dt.date.today()
    cur = conn.cursor()
    cur.execute("""SELECT m.external_id, m.ride_date, m.xss_low, m.xss_high + m.xss_peak FROM qbot_v2.modelq2_ride m
                   WHERE COALESCE(m.xss_source,'power')='power' AND m.ride_date > %s AND m.ride_date <= %s
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine q
                                     WHERE q.external_id=m.external_id AND q.released IS NULL)""",
                (day - dt.timedelta(days=K_CALIB_DAYS), day))
    rides = [r for r in _t(cur.fetchall()) if not _bad(r[1])]
    acc = []
    for eid, d, xl, xh in rides:
        cur.execute("SELECT ts, hr_bpm, speed_mps, temperature_c FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY ts", (eid,))
        R = [(a, float(b) if b is not None else None, float(v) if v is not None else None) for a, b, v, _ in _t(cur.fetchall())]
        lo, hi = compute_hr_xss_split(R, lthr_bpm=get_lthr(conn, d), k_low=1.0, k_high=1.0)
        cur.execute("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY temperature_c) FROM qbot_v2.activity_record "
                    "WHERE external_id=%s AND temperature_c IS NOT NULL", (eid,))
        tm = _t([cur.fetchone()])[0][0]
        acc.append((float(xl or 0), float(xh or 0), lo, hi, float(tm) if tm is not None else None))
    lows = [a / c for a, b, c, d, _ in acc if c > 5]
    highs = [b / d for a, b, c, d, _ in acc if d > 1.0]
    if len(lows) < 30:
        return {"calib": "za malo jazd", "n": len(lows)}
    k_low = float(median(lows))
    k_high = float(median(highs)) if len(highs) >= 15 else None
    if k_high is None:
        cur.execute("SELECT k_high FROM qbot_v2.hr_xss_calib ORDER BY day DESC LIMIT 1")
        r = cur.fetchone()
        k_high = float(_t([r])[0][0]) if r else 1.0
    err = sorted(((k_low * c + k_high * d) - (a + b)) / (a + b) for a, b, c, d, _ in acc if a + b > 20)
    # korekta temperatury: ratio = XSS_tetno/XSS_moc ~ a + b*(T - 15), OLS na jazdach z temperatura (ratio przyciete 0.5-2)
    from fitmodel.modelq2.hr_xss import TEMP_REF_C, temp_factor
    pts = [(t - TEMP_REF_C, max(0.5, min(2.0, (k_low * c + k_high * d) / (a + b)))) for a, b, c, d, t in acc
           if t is not None and a + b > 20]
    ta = tb = None
    err_t = None
    if len(pts) >= 40 and len([x for x, _ in pts if x > 0]) >= 15:
        mx = sum(x for x, _ in pts) / len(pts); my = sum(y for _, y in pts) / len(pts)
        sxx = sum((x - mx) ** 2 for x, _ in pts)
        tb = sum((x - mx) * (y - my) for x, y in pts) / sxx
        ta = my - tb * mx
        err_t = sorted(((k_low * c + k_high * d) * temp_factor(t, ta, tb) - (a + b)) / (a + b)
                       for a, b, c, d, t in acc if t is not None and a + b > 20)
    lthr = get_lthr(conn, day)
    cur.execute("""INSERT INTO qbot_v2.hr_xss_calib (day, k_low, k_high, n_low, n_high, lthr_bpm, err_p25, err_p75,
                   temp_a, temp_b, n_temp, err_t_p25, err_t_p75)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (day) DO UPDATE SET k_low=EXCLUDED.k_low,
                   k_high=EXCLUDED.k_high, n_low=EXCLUDED.n_low, n_high=EXCLUDED.n_high, lthr_bpm=EXCLUDED.lthr_bpm,
                   err_p25=EXCLUDED.err_p25, err_p75=EXCLUDED.err_p75, temp_a=EXCLUDED.temp_a, temp_b=EXCLUDED.temp_b,
                   n_temp=EXCLUDED.n_temp, err_t_p25=EXCLUDED.err_t_p25, err_t_p75=EXCLUDED.err_t_p75, computed_at=now()""",
                (day, round(k_low, 3), round(k_high, 3), len(lows), len(highs), lthr,
                 round(err[len(err) // 4], 3), round(err[3 * len(err) // 4], 3),
                 round(ta, 4) if ta is not None else None, round(tb, 5) if tb is not None else None, len(pts),
                 round(err_t[len(err_t) // 4], 3) if err_t else None, round(err_t[3 * len(err_t) // 4], 3) if err_t else None))
    conn.commit()
    return {"k_low": round(k_low, 3), "k_high": round(k_high, 3), "n_low": len(lows), "n_high": len(highs),
            "lthr": lthr, "blad_25_75": [round(err[len(err) // 4], 2), round(err[3 * len(err) // 4], 2)],
            "temp": {"a": round(ta, 3) if ta is not None else None, "b_na_C": round(tb, 4) if tb is not None else None,
                     "n": len(pts), "blad_po_korekcie_25_75": [round(err_t[len(err_t) // 4], 2), round(err_t[3 * len(err_t) // 4], 2)] if err_t else None}}


def run_daily(conn) -> dict:
    """Krok daily_job: nowe okna -> LTHR (ostatnie 14 dni od nowa) -> kalibracja K gdy stara/LTHR inne -> Telegram przy zmianie."""
    ensure(conn)
    today = dt.date.today()
    new = collect_new(conn)
    cur = conn.cursor()
    cur.execute("SELECT max(day) FROM qbot_v2.lthr_daily")
    last = _t([cur.fetchone()])[0][0]
    start = SERIES_FROM if last is None else min(last + dt.timedelta(days=1), today - dt.timedelta(days=14))
    before = get_lthr(conn, today - dt.timedelta(days=1))
    res = publish_series(conn, start, today)
    now = get_lthr(conn, today)
    cur.execute("SELECT day, lthr_bpm FROM qbot_v2.hr_xss_calib ORDER BY day DESC LIMIT 1")
    c = cur.fetchone()
    calib = None
    if c is None or (today - _t([c])[0][0]).days >= K_CALIB_MAX_AGE or int(_t([c])[0][1] or 0) != now:
        calib = calibrate_hr_xss(conn, today)
    if now != before:
        try:
            from fitmodel.power_meter_guard import _telegram_send
            _telegram_send("❤️ LTHR (tetno progowe) zmienione: %d -> %d ud./min (z jazd z 120 dni). Strefy tetna i XSS "
                           "z tetna licza sie od nowej wartosci; intervals.icu/Karoo przy synchronizacji progu." % (before, now))
        except Exception as e:  # noqa: BLE001
            res["telegram_error"] = str(e)[:120]
    return {"nowe_jazdy": new, "lthr": now, "wczoraj": before, **res, "kalibracja_xss_hr": calib}
