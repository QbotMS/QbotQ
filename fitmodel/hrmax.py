"""Automat tetna maksymalnego (HRmax) -- liczony codziennie z jazd (decyzja Michala 2026-10-20, sesja hrmax-2010).

DLACZEGO: HRmax byl ustawiony recznie w kilku miejscach i sie rozjechal: intervals.icu/Karoo 173 (poprawione 04.10),
QBot (fitmodel_param.hr_max_bpm) i QExt2 (RIDER_MAX_HR_BPM) dalej 184. 181 z 02.05.2026 to artefakt starego paska
(HR 93->181->115 w 90 s przy ~70 W). Realne maksima 2025-2026: 171-173 utrzymane 10 s (DECISIONS 2026-10-04).

METODA (szczyt z jazdy, tylko wiarygodny):
  - tetno UTRZYMANE >= 10 s (minimum z 10 kolejnych sekund), w zakresie 120..210;
  - fizjologiczne tempo: 20 s przed oknem tetno nizsze najwyzej o 40 ud., 30 s po oknie spadek najwyzej o 40 ud.;
  - realny wysilek: srednia moc z 120 s przed koncem okna >= 80 % TP ModelQ z dnia jazdy (brak mocy = odrzut).
  Tetno z pliku jazdy Karoo; gdy na Karoo jest pas Polar H10 (ANT+), to jest tetno z pasa.
PUBLIKACJA (hrmax_daily.hrmax_bpm): najwyzszy wiarygodny szczyt z 365 dni.
  W GORE od razu; W DOL tylko gdy przez 365 dni zaden szczyt nie byl blizej niz 3 ud. od obecnej wartosci.
  Start: 173 (wartosc z intervals.icu po 04.10), gdy brak szczytow.
ZMIANA -> fitmodel_param.hr_max_bpm (pasma tetna odcinkow 0.60-0.85 HRmax w fit_ingest) + przeliczenie odcinkow
  (kopia fitmodel_segment_bak_hrmax_<data>, czyszczenie fitmodel_segment i fitmodel_ingest_status -> ingest w tym samym
  przebiegu daily_job odbudowuje) + Telegram. KTO CZYTA get_hrmax(): fit_ingest (przez fitmodel_param), raport jazdy
  (%HRmax), /ride-readiness -> QExt2 (maxHrBpm), threshold_sync.run_lthr -> intervals.icu max_hr i gorna strefa -> Karoo.
Dok.: docs/HRMAX.md.
"""
from __future__ import annotations

import datetime as dt

SEED_BPM = 173
WINDOW_DAYS = 365
SUSTAIN_S = 10
PRE_S, POST_S, JUMP_BPM = 20, 30, 40
EFFORT_S, EFFORT_FRAC = 120, 0.80
HR_MIN, HR_MAX = 120, 210
LOWER_TOL = 3
SINCE = dt.date(2025, 1, 1)

DDL = [
    """CREATE TABLE IF NOT EXISTS qbot_v2.hrmax_peak (external_id text PRIMARY KEY, ride_date date, started_at timestamptz,
         peak_bpm integer, peak_sec integer, effort_w real, cp_w real, note text, computed_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS qbot_v2.hrmax_daily (day date PRIMARY KEY, hrmax_bpm integer NOT NULL, best_bpm integer,
         best_ride text, best_date date, note text, computed_at timestamptz DEFAULT now())""",
]


def _t(rows):
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in rows]


def ensure(conn) -> None:
    cur = conn.cursor()
    for q in DDL:
        cur.execute(q)
    conn.commit()


# ---------------------------------------------------------------- czyste funkcje (tests/test_hrmax.py)
def _at(secs, vals, t):
    """Wartosc w sekundzie t (dokladnie), inaczej None."""
    import bisect
    i = bisect.bisect_left(secs, t)
    if i < len(secs) and secs[i] == t:
        return vals[i]
    return None


def ride_peak(rows, cp_w):
    """rows: [(sec, power_w, hr_bpm)] po sec. -> (peak_bpm, peak_sec, effort_w, powod) ; peak None gdy brak wiarygodnego."""
    secs = [int(r[0]) for r in rows]
    pw = [r[1] for r in rows]
    hr = [r[2] for r in rows]
    n = len(rows)
    cands = []
    for i in range(0, n - SUSTAIN_S + 1):
        if secs[i + SUSTAIN_S - 1] - secs[i] != SUSTAIN_S - 1:
            continue
        seg = hr[i:i + SUSTAIN_S]
        if any(v is None or v <= 0 for v in seg):
            continue
        m = min(seg)
        if HR_MIN <= m <= HR_MAX:
            cands.append((m, i))
    if not cands:
        return None, None, None, "brak 10 s tetna w zakresie"
    cands.sort(key=lambda x: (-x[0], x[1]))
    why = "brak"
    seen = 0
    for m, i in cands:
        seen += 1
        if seen > 300:
            break
        s0, s1 = secs[i], secs[i + SUSTAIN_S - 1]
        pre = _at(secs, hr, s0 - PRE_S)
        post = _at(secs, hr, s1 + POST_S)
        if pre and m - pre > JUMP_BPM:
            why = "skok przed (%d->%d)" % (pre, m); continue
        if post and m - post > JUMP_BPM:
            why = "spadek po (%d->%d)" % (m, post); continue
        import bisect
        j0, j1 = bisect.bisect_left(secs, s1 - EFFORT_S), bisect.bisect_right(secs, s1)
        pv = [pw[j] for j in range(j0, j1) if pw[j] is not None]
        if len(pv) < EFFORT_S * 0.7:
            why = "brak mocy"; continue
        eff = sum(pv) / len(pv)
        if not cp_w or eff < EFFORT_FRAC * cp_w:
            why = "bez wysilku (%.0f W)" % eff; continue
        return int(m), s0, round(eff, 1), "ok"
    return None, None, None, why


def publish_value(prev, peaks_365):
    """prev: int|None; peaks_365: [(bpm, eid, date)] z 365 dni. -> (wartosc, najlepszy szczyt|None, notka)."""
    best = max(peaks_365, key=lambda x: (x[0], x[2])) if peaks_365 else None
    if prev is None:
        return (best[0] if best else SEED_BPM), best, "start"
    if best and best[0] > prev:
        return best[0], best, "w gore: szczyt %d" % best[0]
    if best and best[0] < prev - LOWER_TOL:
        return best[0], best, "w dol: od roku nic blizej niz %d ud." % LOWER_TOL
    if not best:
        return prev, None, "brak szczytow z roku -- bez zmian"
    return prev, best, "bez zmian"


# ---------------------------------------------------------------- baza
def collect_new(conn) -> int:
    cur = conn.cursor()
    cur.execute("""SELECT t.external_id, t.date, t.started_at FROM qbot_v2.training_sessions t
                   WHERE t.sport_type IN ('cycling','gravel_cycling') AND t.duration_s >= 1200 AND t.date >= %s
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.hrmax_peak p WHERE p.external_id = t.external_id)""", (SINCE,))
    todo = _t(cur.fetchall())
    for eid, d, st in todo:
        cur.execute("SELECT tp_w FROM qbot_v2.modelq2_signature WHERE day <= %s ORDER BY day DESC LIMIT 1", (d,))
        r = cur.fetchone()
        cp = float(_t([r])[0][0]) if r and _t([r])[0][0] else None
        cur.execute("SELECT sec, power_w, hr_bpm FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec", (eid,))
        rows = _t(cur.fetchall())
        pk, ps, eff, why = ride_peak(rows, cp) if rows else (None, None, None, "brak danych 1 Hz")
        cur.execute("""INSERT INTO qbot_v2.hrmax_peak (external_id, ride_date, started_at, peak_bpm, peak_sec, effort_w, cp_w, note)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (external_id) DO NOTHING""",
                    (eid, d, st, pk, ps, eff, cp, why))
    conn.commit()
    return len(todo)


def _peaks(conn, day):
    """Wiarygodne szczyty z 365 dni; ta sama jazda (godzina startu) raz -- najwyzszy."""
    cur = conn.cursor()
    cur.execute("""SELECT peak_bpm, external_id, ride_date, started_at FROM qbot_v2.hrmax_peak
                   WHERE peak_bpm IS NOT NULL AND ride_date > %s AND ride_date <= %s""",
                (day - dt.timedelta(days=WINDOW_DAYS), day))
    best = {}
    for b, e, d, st in _t(cur.fetchall()):
        k = st or e
        if k not in best or b > best[k][0]:
            best[k] = (int(b), e, d)
    return list(best.values())


def get_hrmax(conn=None, day=None) -> int:
    own = conn is None
    if own:
        from fitmodel.ftp_resolver import _db_connect
        conn = _db_connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT hrmax_bpm FROM qbot_v2.hrmax_daily WHERE day <= %s ORDER BY day DESC LIMIT 1",
                    (day or dt.date.today(),))
        r = cur.fetchone()
        return int(_t([r])[0][0]) if r else SEED_BPM
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return SEED_BPM
    finally:
        if own:
            conn.close()


def _reset_segments(conn, day) -> str:
    """Kopia + czyszczenie odcinkow i statusu ingestu -> fit_ingest przelicza wszystkie jazdy (nowe pasmo HR)."""
    cur = conn.cursor()
    bak = "fitmodel_segment_bak_hrmax_%s" % day.strftime("%Y%m%d")
    cur.execute("CREATE TABLE IF NOT EXISTS qbot_v2.%s AS TABLE qbot_v2.fitmodel_segment" % bak)
    cur.execute("DELETE FROM qbot_v2.fitmodel_segment")
    cur.execute("DELETE FROM qbot_v2.fitmodel_ingest_status")
    conn.commit()
    return bak


def run_daily(conn, send=None, day=None, reset_segments=True) -> dict:
    ensure(conn)
    day = day or dt.date.today()
    n_new = collect_new(conn)
    cur = conn.cursor()
    cur.execute("SELECT hrmax_bpm FROM qbot_v2.hrmax_daily WHERE day < %s ORDER BY day DESC LIMIT 1", (day,))
    r = cur.fetchone()
    prev = int(_t([r])[0][0]) if r else None
    cur.execute("SELECT value FROM qbot_v2.fitmodel_param WHERE key='hr_max_bpm'")
    r = cur.fetchone()
    param = int(round(float(_t([r])[0][0]))) if r else None
    val, best, note = publish_value(prev, _peaks(conn, day))
    cur.execute("""INSERT INTO qbot_v2.hrmax_daily (day, hrmax_bpm, best_bpm, best_ride, best_date, note)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (day) DO UPDATE SET hrmax_bpm=EXCLUDED.hrmax_bpm,
                   best_bpm=EXCLUDED.best_bpm, best_ride=EXCLUDED.best_ride, best_date=EXCLUDED.best_date,
                   note=EXCLUDED.note, computed_at=now()""",
                (day, val, best[0] if best else None, best[1] if best else None, best[2] if best else None, note))
    conn.commit()
    out = {"hrmax": val, "prev": prev, "param_was": param, "new_rides": n_new, "note": note,
           "best": (best[0], best[1], str(best[2])) if best else None}
    if param != val:
        cur.execute("""INSERT INTO qbot_v2.fitmodel_param (key, value, updated_at, source) VALUES ('hr_max_bpm', %s, now(), 'hrmax_auto')
                       ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now(), source=EXCLUDED.source""",
                    (float(val),))
        conn.commit()
        out["segments_backup"] = _reset_segments(conn, day) if reset_segments else None
        if send:
            try:
                bt = (" (szczyt %d ud./min z %s)" % (best[0], best[2].strftime("%d.%m.%Y"))) if best else ""
                send("❤️ Tętno maksymalne: %s → %d ud./min%s. Zmieniam w QBocie, QExt2 i na Karoo (intervals.icu); "
                     "odcinki analizy przeliczą się dziś." % (param if param is not None else "—", val, bt))
            except Exception:
                pass
    return out


if __name__ == "__main__":
    import json, os, sys
    sys.path.insert(0, "/opt/qbot/app")
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    c = _db_connect()
    if "--dry" in sys.argv:
        ensure(c)
        print("nowe jazdy:", collect_new(c))
        print(json.dumps(publish_value(None, _peaks(c, dt.date.today())), default=str))
        cur = c.cursor()
        cur.execute("SELECT ride_date, peak_bpm, effort_w, cp_w, note FROM qbot_v2.hrmax_peak WHERE peak_bpm IS NOT NULL "
                    "ORDER BY peak_bpm DESC, ride_date DESC LIMIT 12")
        for row in _t(cur.fetchall()):
            print(row)
        cur.execute("SELECT note, count(*) FROM qbot_v2.hrmax_peak GROUP BY 1 ORDER BY 2 DESC LIMIT 8")
        print(_t(cur.fetchall()))
    else:
        print(run_daily(c))
