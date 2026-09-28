# -*- coding: utf-8 -*-
"""Kontrole spojnosci ModelQ v2 na zywych danych (TYLKO ODCZYT). 2026-09-28.

Uzywane przez: tests/test_modelq2.py (klasa DB) oraz nocny daily_job (krok modelq2_integrity,
alert Telegram przy problemie). Kazda kontrola zwraca liste problemow (pusta = OK).

1) brakujace_xss  - jazda z danymi 1Hz (>=600 probek) bez wpisu w modelq2_ride
                    (poza duplikatem z ta sama godzina startu). Zlapalaby blad "1 jazda na dzien".
2) obciazenie_dnia - obciazenie dnia wyliczone z przyrostu ATL w fitmodel_daily
                    (L = ATL_wczoraj + 7*(ATL - ATL_wczoraj)) == suma XSS jazd dnia.
3) duplikaty      - dwie jazdy w modelq2_ride z identycznym startem (liczone podwojnie).
"""
import datetime as dt

TOL_LOAD = 3.0      # XSS; zaokraglenia ATL do 0.1 daja blad do ~0.7
MIN_TICKS = 600     # jak io.list_rides


def missing_xss(cur, days=400, lag_days=2):
    today = dt.date.today()
    cur.execute("""
        WITH ar AS (SELECT external_id, MIN(ts)::date AS d, COUNT(*) AS n FROM qbot_v2.activity_record
                    WHERE ts >= %s GROUP BY external_id HAVING COUNT(*) >= %s)
        SELECT ar.external_id, ar.d, ar.n FROM ar
        WHERE ar.d <= %s
          AND NOT EXISTS (SELECT 1 FROM qbot_v2.modelq2_ride m WHERE m.external_id = ar.external_id)
          AND NOT EXISTS (SELECT 1 FROM qbot_v2.training_sessions t JOIN qbot_v2.training_sessions t2 ON t2.started_at = t.started_at
                          JOIN qbot_v2.modelq2_ride m2 ON m2.external_id = t2.external_id
                          WHERE t.external_id = ar.external_id AND t2.external_id <> ar.external_id)
        ORDER BY ar.d""", (today - dt.timedelta(days=days), MIN_TICKS, today - dt.timedelta(days=lag_days)))
    return ["jazda %s (%s, %d probek 1Hz) bez XSS ModelQ" % (r[0], r[1], r[2]) for r in cur.fetchall()]


def daily_load_mismatch(cur, days=120, tol=TOL_LOAD):
    today = dt.date.today()
    cur.execute("SELECT day, atl_raw FROM qbot_v2.fitmodel_daily WHERE day BETWEEN %s AND %s AND atl_raw IS NOT NULL ORDER BY day",
                (today - dt.timedelta(days=days + 1), today - dt.timedelta(days=1)))
    atl = [(r[0], float(r[1])) for r in cur.fetchall()]
    cur.execute("SELECT ride_date, SUM(xss_total) FROM qbot_v2.modelq2_ride WHERE ride_date BETWEEN %s AND %s GROUP BY 1",
                (today - dt.timedelta(days=days + 1), today))
    xs = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
    out = []
    for (d0, a0), (d1, a1) in zip(atl, atl[1:]):
        if (d1 - d0).days != 1:
            continue
        implied = a0 + 7.0 * (a1 - a0)
        real = xs.get(d1, 0.0)
        if abs(implied - real) > tol:
            out.append("%s: obciazenie z modelu formy %.1f != suma XSS jazd %.1f" % (d1, implied, real))
    return out


def duplicate_rides(cur):
    cur.execute("""SELECT t.started_at, array_agg(m.external_id) FROM qbot_v2.modelq2_ride m
                   JOIN qbot_v2.training_sessions t ON t.external_id = m.external_id
                   WHERE t.started_at IS NOT NULL GROUP BY t.started_at HAVING COUNT(*) > 1""")
    return ["duplikat startu %s: %s" % (r[0], ", ".join(r[1])) for r in cur.fetchall()]


def run(conn):
    cur = conn.cursor()
    res = {"brakujace_xss": missing_xss(cur), "obciazenie_dnia": daily_load_mismatch(cur), "duplikaty": duplicate_rides(cur)}
    res["ok"] = not any(res[k] for k in ("brakujace_xss", "obciazenie_dnia", "duplikaty"))
    return res


def run_and_alert(conn, send=None):
    """Krok daily_job: przy problemie wysyla alert (Telegram). Zwraca skrot do logu."""
    res = run(conn)
    if not res["ok"] and send:
        lines = ["⚠️ ModelQ: kontrola spójności wykryła problem"]
        for k in ("brakujace_xss", "obciazenie_dnia", "duplikaty"):
            for x in res[k][:5]:
                lines.append("• " + x)
            if len(res[k]) > 5:
                lines.append("  … i %d więcej (%s)" % (len(res[k]) - 5, k))
        try:
            send("\n".join(lines))
        except Exception as exc:
            print("modelq2_integrity: telegram error: %s" % exc)
    return {k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}
