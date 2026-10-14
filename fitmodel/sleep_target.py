"""Wlasny cel snu QBota + pobudki przed budzikiem ([GARMIN-DANE] Etap 5, decyzje 2026-10-14).

Dlaczego nie potrzeba snu Garmina: to regula (baza z wieku 7:50 -> 7:30 od 01.2026 + flagi +20..60 min),
a dodatek "historia snu" dziala w kolko (krotszy sen -> wieksza potrzeba -> wiekszy dlug). Garmin tylko do porownan.

CEL SNU:
  baza  = z Twoich danych (365 dni, zwykle dni: XSS dnia przed < 150): prog T (405..510 min, co 15),
          ktory najmocniej rozdziela HRV NASTEPNEJ nocy (sredni HRV-vs-norma dla snu >= T minus < T),
          min. 25 nocy po obu stronach; liczony na biezaco, przyciety 420..510; brak danych -> 465 (7:45).
          Dane 14.10.2026: T = 465 (>= 7:45: +3,6 ms, < 7:45: -0,5 ms).
  dodatki (UMOWNE, jak u Garmina; do kalibracji po ~6 mies.), lacznie max +60:
          +30 ciezki dzien (XSS ModelQ dzis >= 150)
          +30 HRV QBota 'ponizej'/'nisko' LUB sygnal 'Organizm pod obciazeniem' (fitmodel/hrv_status, body_signal)
  pora snu = budzik (07:10) - cel - 15 min na zasniecie.
POBUDKI PRZED BUDZIKIEM: przycisk w porannej wiadomosci (tr:wake:RRRRMMDD) -> qbot_v2.sleep_wake_label.
  Nieoznaczona noc = normalna (praca/delegacja/inny budzik nie psuja danych).
  Analiza miesieczna porownuje oznaczone noce z reszta; poki oznaczen < 10 -- historia z reguly
  "w domu bez porannej jazdy" (lokalna jazda <25 km od domu rozpoczeta >= 7:30, pobudka < 6:50, sen < 7 h).
Dok.: docs/GARMIN_DANE.md
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ALARM = (7, 10)
FALL_ASLEEP_MIN = 15
BASE_DEFAULT = 465
BASE_CLAMP = (420, 510)
HEAVY_XSS = 150
ADD_MIN = 30
ADD_CAP = 60
MIN_LABELS = 10
HOME = (52.34, 21.11)
SQL_FILE = Path("/opt/qbot/app/sql/sleep_v1.sql")


# ---------- pomocnicze: dzialaja z polaczeniem psycopg3, kursorem psycopg2/3, wiersze krotki lub slowniki ----------
def _cur(cx):
    return cx.cursor() if hasattr(cx, "cursor") else cx


def _rows(cx, sql: str, params: tuple = ()) -> list[dict]:
    cur = _cur(cx)
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]


def hm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60} h {m % 60:02d}"


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SQL_FILE.read_text())
    conn.commit()


# ---------- baza z danych ----------
SQL_BASE = """
WITH w AS (SELECT date, sleep_duration_min dur,
                  hrv_ms - avg(hrv_ms) OVER (ORDER BY date ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING) dh
           FROM qbot_v2.qbot_wellness_daily WHERE source='garmin' AND sleep_duration_min > 180)
SELECT a.dur, b.dh AS nx
FROM w a JOIN w b ON b.date = a.date + 1
WHERE a.date BETWEEN %s AND %s AND b.dh IS NOT NULL
  AND (SELECT coalesce(sum(xss_total),0) FROM qbot_v2.modelq2_ride m WHERE m.ride_date = a.date - 1) < %s"""


def pick_base(pairs: list[tuple[float, float]]) -> int:
    """pairs: (sen_min, HRV nastepnej nocy vs norma). Prog najmocniej rozdzielajacy; brak -> BASE_DEFAULT."""
    best, best_t = None, BASE_DEFAULT
    for t in range(405, 511, 15):
        ge = [h for d, h in pairs if d >= t]
        lt = [h for d, h in pairs if d < t]
        if len(ge) < 25 or len(lt) < 25:
            continue
        diff = sum(ge) / len(ge) - sum(lt) / len(lt)
        if best is None or diff > best:
            best, best_t = diff, t
    return max(BASE_CLAMP[0], min(BASE_CLAMP[1], best_t))


def base_minutes(cx, today: date) -> int:
    rs = _rows(cx, SQL_BASE, (today - timedelta(days=365), today, HEAVY_XSS))
    return pick_base([(float(r["dur"]), float(r["nx"])) for r in rs])


# ---------- cel na dzisiejsza noc ----------
def compose(base: int, heavy: bool, strain: bool) -> dict[str, Any]:
    reasons, add = [], 0
    if heavy:
        add += ADD_MIN; reasons.append("ciężki dzień")
    if strain:
        add += ADD_MIN; reasons.append("organizm pod obciążeniem")
    add = min(add, ADD_CAP)
    target = base + add
    alarm = datetime(2000, 1, 2, *ALARM)
    bed = alarm - timedelta(minutes=target + FALL_ASLEEP_MIN)
    return {"base": base, "add": add, "reasons": reasons, "target": target, "bedtime": bed.strftime("%H:%M"),
            "alarm": alarm.strftime("%H:%M")}


def target_for(cx, today: date) -> dict[str, Any]:
    base = base_minutes(cx, today)
    x = _rows(cx, "SELECT coalesce(sum(xss_total),0) AS x FROM qbot_v2.modelq2_ride WHERE ride_date = %s", (today,))
    heavy = float(x[0]["x"] or 0) >= HEAVY_XSS
    strain = False
    try:
        from fitmodel.hrv_status import current as hrv_cur
        nights = [(r["date"], float(r["hrv_ms"])) for r in _rows(
            cx, "SELECT date, hrv_ms FROM qbot_v2.qbot_wellness_daily WHERE source='garmin' AND hrv_ms > 0 "
                "AND date BETWEEN %s AND %s ORDER BY date", (today - timedelta(days=80), today))]
        hs = hrv_cur(nights)
        strain = bool(hs and hs["date"] == today.isoformat() and hs["status"] in ("ponizej", "nisko"))
    except Exception:
        pass
    try:
        from fitmodel.body_signal import today_signal
        bs = today_signal(_cur(cx), today)
        strain = strain or bool(bs and bs["signal"])
    except Exception:
        pass
    return compose(base, heavy, strain)


def evening_line(cx, today: date) -> str:
    t = target_for(cx, today)
    why = f" (+{t['add']} min: {', '.join(t['reasons'])})" if t["add"] else ""
    return f"😴 Sen: cel {hm(t['target'])}{why} → spać ok. {t['bedtime']} (budzik {t['alarm']})"


# ---------- przycisk + oznaczenie ----------
def wake_button(today: date) -> list:
    return [[{"text": "😳 Pobudka przed budzikiem", "callback_data": f"tr:wake:{today.strftime('%Y%m%d')}"}]]


def mark_early_wake(cx, arg: str) -> str:
    d = datetime.strptime(arg, "%Y%m%d").date()
    _cur(cx).execute("INSERT INTO qbot_v2.sleep_wake_label (date, early_wake) VALUES (%s, true) "
                     "ON CONFLICT (date) DO UPDATE SET early_wake = true, created_at = now()", (d,))
    r = _rows(cx, "SELECT (sleep_end AT TIME ZONE 'Europe/Warsaw')::time AS en FROM qbot_v2.qbot_sleep_daily "
                  "WHERE date = %s AND source = 'garmin'", (d,))
    en = f" (Garmin: pobudka {r[0]['en'].strftime('%H:%M')})" if r and r[0]["en"] else ""
    return f"😳 Zapisane: {d.strftime('%d.%m')} pobudka przed budzikiem{en}. Przyczyny sprawdzę w miesięcznym rozliczeniu."


# ---------- rozliczenia ----------
def week_line(cx, d0: date, d1: date) -> str | None:
    rs = _rows(cx, "SELECT avg(sleep_duration_min) AS s, count(*) AS n FROM qbot_v2.qbot_wellness_daily "
                   "WHERE source='garmin' AND sleep_duration_min > 180 AND date BETWEEN %s AND %s", (d0, d1))
    if not rs or not rs[0]["n"]:
        return None
    base = base_minutes(cx, d1)
    try:
        nl = _rows(cx, "SELECT count(*) AS n FROM qbot_v2.sleep_wake_label WHERE early_wake AND date BETWEEN %s AND %s",
                   (d0, d1))[0]["n"]
    except Exception:
        nl = 0
    s = float(rs[0]["s"])
    dd = abs(s - base)
    dtxt = f"{dd:.0f} min" if dd < 60 else hm(dd)   # _fmt_diff
    return (f"😴 Sen tygodnia: średnio {hm(s)} vs cel {hm(base)} ({'+' if s >= base else '−'}{dtxt})"
            + (f", pobudek przed budzikiem: {nl}" if nl else "") + ".")


SQL_FACTORS = """
WITH s AS (SELECT q.date, q.sleep_start AT TIME ZONE 'Europe/Warsaw' AS sst, q.sleep_end AT TIME ZONE 'Europe/Warsaw' AS en,
                  q.sleep_duration_min AS dur FROM qbot_v2.qbot_sleep_daily q
           WHERE q.source='garmin' AND q.date BETWEEN %(a)s AND %(b)s AND q.sleep_duration_min > 180),
w AS (SELECT date, skin_temp_dev_c AS t,
             hrv_ms - avg(hrv_ms) OVER (ORDER BY date ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING) AS dh,
             resting_hr_bpm - avg(resting_hr_bpm) OVER (ORDER BY date ROWS BETWEEN 60 PRECEDING AND 1 PRECEDING) AS dr
      FROM qbot_v2.qbot_wellness_daily WHERE source='garmin'),
st AS (SELECT DISTINCT ON (r.external_id) r.external_id, r.lat, r.lon FROM qbot_v2.activity_record r
       JOIN qbot_v2.training_sessions t ON t.external_id = r.external_id AND t.date BETWEEN %(a)s AND %(b)s
       WHERE r.lat IS NOT NULL AND r.sec < 120 ORDER BY r.external_id, r.sec),
rides AS (SELECT t.date, min(t.started_at AT TIME ZONE 'Europe/Warsaw') AS fs,
                 bool_or(111*sqrt(power(st.lat-%(hla)s,2)+power((st.lon-%(hlo)s)*0.61,2)) < 25) AS lokal
          FROM qbot_v2.training_sessions t JOIN st ON st.external_id = t.external_id GROUP BY t.date)
SELECT s.date, s.dur, s.en, extract(epoch FROM (s.sst - (s.date - 1 + time '18:00')))/60 AS st_min,
       w.t, w.dh, w.dr,
       (SELECT stress_avg FROM qbot_v2.wellness_daily d WHERE d.date = s.date - 1) AS stres,
       (SELECT coalesce(sum(xss_total),0) FROM qbot_v2.modelq2_ride m WHERE m.ride_date = s.date - 1) AS xss,
       (SELECT max((t2.started_at + make_interval(secs => t2.duration_s)) AT TIME ZONE 'Europe/Warsaw')::time
          FROM qbot_v2.training_sessions t2 WHERE t2.date = s.date - 1) AS last_end,
       r.lokal, r.fs, lb.early_wake AS label
FROM s LEFT JOIN w ON w.date = s.date LEFT JOIN rides r ON r.date = s.date
LEFT JOIN qbot_v2.sleep_wake_label lb ON lb.date = s.date
ORDER BY s.date"""

FACTORS = [  # (klucz, opis, prog roznicy wartym wzmianki, format)
    ("xss", "obciążenie dnia przed (XSS)", 25, "{:.0f}"),
    ("late", "jazda kończona po 18:30 (%)", 15, "{:.0f}"),
    ("alk", "alkohol dzień przed (%)", 15, "{:.0f}"),
    ("stres", "stres dnia (Garmin)", 5, "{:.0f}"),
    ("t", "temp. skóry (°C)", 0.15, "{:+.1f}"),
    ("dh", "HRV vs norma (ms)", 4, "{:+.0f}"),
    ("dr", "tętno spocz. vs norma", 2, "{:+.1f}"),
    ("st_min", "pora zaśnięcia (min od 18:00)", 20, "{:.0f}"),
]


def _avg(xs):
    xs = [float(x) for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def compare(rows: list[dict], alk_days: set) -> tuple[str, dict, dict, int, int]:
    """Dzieli noce na pobudki/reszta (etykiety albo regula historyczna) i liczy srednie czynnikow."""
    labeled = [r for r in rows if r.get("label")]
    if len(labeled) >= MIN_LABELS:
        mode = "oznaczenia"
        early = labeled
        rest = [r for r in rows if not r.get("label")]
    else:
        mode = "reguła: dom, bez porannej jazdy"
        home = [r for r in rows if r.get("lokal") and r.get("fs") and r["fs"].time() >= datetime(2000, 1, 1, 7, 30).time()]
        early = [r for r in home if r["en"] and r["en"].time() < datetime(2000, 1, 1, 6, 50).time() and r["dur"] < 420]
        rest = [r for r in home if r not in early]
    for r in rows:
        r["late"] = 100.0 if (r.get("last_end") and r["last_end"] >= datetime(2000, 1, 1, 18, 30).time()) else 0.0
        r["alk"] = 100.0 if (r["date"] - timedelta(days=1)) in alk_days else 0.0
    a = {k: _avg(r.get(k) for r in early) for k, *_ in FACTORS}
    b = {k: _avg(r.get(k) for r in rest) for k, *_ in FACTORS}
    return mode, a, b, len(early), len(rest)


def month_line(cx, month_start: date, alk_days: set | None = None) -> str | None:
    """Analiza: pobudki przed budzikiem vs reszta (okno 12 mies. do konca miesiaca)."""
    m_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    rows = _rows(cx, SQL_FACTORS, {"a": m_end - timedelta(days=365), "b": m_end, "hla": HOME[0], "hlo": HOME[1]})
    if alk_days is None:
        try:
            import qbot_food_plan as FP
            alk_days = FP.alcohol_days(cx, m_end - timedelta(days=366), m_end)
        except Exception:
            alk_days = set()
    mode, a, b, ne, nr = compare(rows, alk_days)
    try:
        n_month = _rows(cx, "SELECT count(*) AS n FROM qbot_v2.sleep_wake_label WHERE early_wake AND date BETWEEN %s AND %s",
                        (month_start, m_end))[0]["n"]
    except Exception:
        n_month = 0
    if ne < 5 or nr < 5:
        return f"😳 Pobudki przed budzikiem ({month_start.strftime('%m.%Y')}): {n_month}. Za mało danych do analizy przyczyn."
    diffs = []
    for k, label, thr, fmt in FACTORS:
        if a[k] is None or b[k] is None:
            continue
        if abs(a[k] - b[k]) >= thr:
            diffs.append(f"{label}: {fmt.format(a[k])} vs {fmt.format(b[k])}")
    head = (f"😳 Pobudki przed budzikiem ({month_start.strftime('%m.%Y')}): {n_month}. "
            f"Analiza 12 mies. ({mode}: {ne} pobudek vs {nr} nocy): ")
    return head + ("; ".join(diffs) + "." if diffs else "żaden mierzony czynnik się nie wyróżnia.")
