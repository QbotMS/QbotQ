"""Straznik miernika mocy (P@HR) -- proteza brakujacego MagicZero.

DLACZEGO ISTNIEJE
-----------------
Miernik (SRAM Force E1 DUB-PWR, jednostronny w osi) NIE MA auto-zerowania
w trakcie jazdy (MagicZero niedostepne na spindle -- instrukcja Quarq).
Dryf zera po porannej kalibracji jest niekorygowalny i niewidoczny dla
uzytkownika. Historia: 22-30.07 zanizanie 15-25%%, 2.08 zawyzanie ~20 W
(kalibracje -171 -> -90). Oba epizody wykrylismy z opoznieniem, recznie,
z P@HR -- ten modul robi to automatycznie po kazdej jezdzie.

ZASADA
------
Tetno to niezalezny czujnik. Mediana mocy w koszyku HR 115-135 (pedalowanie:
cad>=40, v>=3 m/s, P>0) jest stabilna. Dwa testy na kazdej nowej jezdzie:
  1. CALA JAZDA vs baza TEGO SAMEGO MIERNIKA (od 2026-09-24, DECISIONS):
     mediana P@HR jazdy vs mediana z jazd tym samym miernikiem (klucz
     ant:<ANT id> lub sn:<serial> z activity_device, device_type=bike_power),
     warunkowana temperatura. Rozne mierniki (Force DUB-PWR, Quarq, Favero)
     mierza rozna skala -- wspolna baza dawala seryjne falszywe alarmy.
     Stopniowanie: PROG_SILNY od razu; PROG_TREND dwie kolejne jazdy TYM
     SAMYM miernikiem w te sama strone.
  2. WEWNATRZ JAZDY: ostatnia cwiartka vs pierwsza. Fizjologia = P@HR
     SPADA; wzrost > PROG_CWIARTKI -> alert (dryf zera w trakcie).
     Ten test nie potrzebuje bazy -- dziala tez dla nowego miernika.
Werdykty: OK / ALERT / SKIP / BAZA (nowy miernik: zbieram baze, bez alertu
z testu 1). Wyniki w qbot_v2.power_meter_guard; alert na Telegram raz.

OGRANICZENIA
------------
- Chlod podnosi P@HR, upal obniza -- baza warunkowana temperatura.
- Brak device_info w pliku FIT -> miernik nieznany -> SKIP testu 1.
- To detektor ANOMALII, nie dowod: alert = "sprawdz kalibracje", decyzja
  o kwarantannie pozostaje reczna (DECISIONS).
"""
from __future__ import annotations

import statistics as st
import datetime as dt

HR_LO, HR_HI = 115, 135
MIN_S_JAZDA = 600        # min. 10 min probek w koszyku, inaczej SKIP
MIN_S_CWIARTKA = 300     # min. 5 min w cwiartce dla testu wewnatrz jazdy
PROG_SILNY = 0.20        # |dev| >= 20% jednej jazdy -> alert od razu
PROG_TREND = 0.08        # |dev| >= 8% DWIE kolejne jazdy (ten sam miernik) -> alert
PROG_CWIARTKI = 0.25     # +25% cw.4 vs cw.1 (fizjologia kaze spadac) -> alert
BAZA_DNI = 450           # ~15 miesiecy
TEMP_OKNO = 5            # +-C: baza z jazd o podobnej temperaturze
MIN_JAZD_TEMP = 10       # min. jazd w oknie temp, inaczej okno x2 / cala baza miernika
MIN_JAZD_MIERNIKA = 10   # ponizej: werdykt BAZA (zbieram baze), bez alertu z testu 1

_METER_SQL = ("COALESCE('ant:' || d.ant_device_number::text, "
              "'sn:' || d.serial_number::text)")


def ensure_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS qbot_v2.power_meter_guard (
                external_id  text PRIMARY KEY,
                ride_date    date,
                p_at_hr_w    numeric,
                baseline_w   numeric,
                dev_pct      numeric,
                q1_w         numeric,
                q4_w         numeric,
                q_dev_pct    numeric,
                verdict      text,        -- OK / ALERT / SKIP / BAZA
                note         text,
                checked_at   timestamptz NOT NULL DEFAULT now()
            )
        """)
        cur.execute("ALTER TABLE qbot_v2.power_meter_guard "
                    "ADD COLUMN IF NOT EXISTS meter_key text")
    conn.commit()


def meter_key(cur, external_id: str):
    """Klucz miernika mocy jazdy: 'ant:<id>' / 'sn:<serial>' albo None."""
    cur.execute(
        f"SELECT {_METER_SQL} FROM qbot_v2.activity_device d "
        "WHERE d.external_id=%s AND d.device_type='bike_power' "
        f"AND {_METER_SQL} IS NOT NULL ORDER BY d.device_index LIMIT 1",
        (external_id,))
    r = cur.fetchone()
    return r[0] if r else None


def meter_key_from_axs(cur, external_id: str, ride_date):
    """Zapas: FIT bez czujnikow (np. zapis po restarcie Karoo w domu, 2026-09-24),
    ale sa zmiany biegow AXS -> rower AXS -> ostatni miernik z jazd z AXS
    (device_type 34) do tej daty. Mechanik (Monster) nie ma zmian biegow."""
    cur.execute("SELECT count(*) FROM qbot_v2.activity_event "
                "WHERE external_id=%s AND lower(event)='rear_gear_change'", (external_id,))
    if (cur.fetchone()[0] or 0) < 10:
        return None
    cur.execute(
        f"SELECT {_METER_SQL} FROM qbot_v2.activity_device d "
        "JOIN qbot_v2.training_sessions t ON t.external_id = d.external_id "
        f"WHERE d.device_type='bike_power' AND {_METER_SQL} IS NOT NULL "
        "AND t.date <= %s AND d.external_id <> %s "
        "AND EXISTS (SELECT 1 FROM qbot_v2.activity_device a WHERE a.external_id = d.external_id "
        "            AND a.manufacturer='sram' AND a.device_type='34') "
        "ORDER BY t.date DESC LIMIT 1", (ride_date, external_id))
    r = cur.fetchone()
    return r[0] if r else None


def _p_at_hr(rows) -> list:
    return [p for p, h, c, v in rows
            if p and p > 0 and h and HR_LO <= h < HR_HI
            and (c or 0) >= 40 and (v or 0) >= 3.0]


def _ride_metrics(cur, external_id: str):
    cur.execute(
        "SELECT power_w, hr_bpm, cadence_rpm, speed_mps, temperature_c "
        "FROM qbot_v2.activity_record WHERE external_id=%s ORDER BY sec",
        (external_id,))
    raw = cur.fetchall()
    if len(raw) < 1200:
        return None
    rows = [(p, h, c, v) for p, h, c, v, t in raw]
    full = _p_at_hr(rows)
    if len(full) < MIN_S_JAZDA:
        return None
    temps = [t for *_, t in raw if t is not None]
    q = len(rows) // 4
    q1 = _p_at_hr(rows[:q])
    q4 = _p_at_hr(rows[3 * q:])
    return {
        "p": st.median(full),
        "temp": st.median(temps) if temps else None,
        "q1": st.median(q1) if len(q1) >= MIN_S_CWIARTKA else None,
        "q4": st.median(q4) if len(q4) >= MIN_S_CWIARTKA else None,
    }


def _baseline_rides(cur, before_date, meter: str, mcache: dict | None = None) -> list:
    """(P@HR, temp) per czysta jazda TYM miernikiem z BAZA_DNI przed data."""
    cur.execute(
        "SELECT t.external_id FROM qbot_v2.training_sessions t "
        "WHERE t.date >= %s::date - %s * interval '1 day' AND t.date < %s "
        "AND t.avg_power_w IS NOT NULL AND t.duration_s > 1800 "
        "AND NOT EXISTS (SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine k "
        "                WHERE k.external_id = t.external_id AND k.released IS NULL) "
        "AND EXISTS (SELECT 1 FROM qbot_v2.activity_device d "
        "            WHERE d.external_id = t.external_id AND d.device_type='bike_power' "
        f"            AND {_METER_SQL} = %s)",
        (before_date, BAZA_DNI, before_date, meter))
    out = []
    mcache = {} if mcache is None else mcache
    for (eid,) in cur.fetchall():
        if eid not in mcache:
            mcache[eid] = _ride_metrics(cur, eid)
        m = mcache[eid]
        if m:
            out.append((m["p"], m["temp"]))
    return out


def _baseline(rides: list, temp, meter: str) -> tuple:
    """Baza miernika warunkowana temperatura (okno +-5C, potem x2, potem
    cala baza miernika). Za malo jazd miernika -> (None, notka BAZA)."""
    if len(rides) < MIN_JAZD_MIERNIKA:
        return None, (f"nowy miernik {meter}: zbieram baze "
                      f"({len(rides)}/{MIN_JAZD_MIERNIKA} jazd)")
    if temp is not None:
        for okno in (TEMP_OKNO, TEMP_OKNO * 2):
            sel = [p for p, t in rides if t is not None and abs(t - temp) <= okno]
            if len(sel) >= MIN_JAZD_TEMP:
                return st.median(sel), f"baza {meter}: {len(sel)} jazd w {temp:.0f}C+-{okno}"
    return st.median([p for p, _ in rides]), f"baza {meter}: cala ({len(rides)} jazd)"


_UPSERT = (
    "INSERT INTO qbot_v2.power_meter_guard "
    "(external_id, ride_date, p_at_hr_w, baseline_w, dev_pct, q1_w, q4_w, q_dev_pct, "
    " verdict, note, meter_key) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON CONFLICT (external_id) DO UPDATE SET ride_date=EXCLUDED.ride_date, "
    "p_at_hr_w=EXCLUDED.p_at_hr_w, baseline_w=EXCLUDED.baseline_w, dev_pct=EXCLUDED.dev_pct, "
    "q1_w=EXCLUDED.q1_w, q4_w=EXCLUDED.q4_w, q_dev_pct=EXCLUDED.q_dev_pct, "
    "verdict=EXCLUDED.verdict, note=EXCLUDED.note, meter_key=EXCLUDED.meter_key, "
    "checked_at=now()")


def _r1(x):
    return None if x is None else round(x, 1)


def check_new_rides(conn, lookback_days: int = 7, send=None, recheck: bool = False) -> dict:
    """Sprawdza jazdy z ostatnich N dni bez wpisu w power_meter_guard.
    recheck=True: przelicza WSZYSTKIE jazdy z okna (nadpisuje wpisy).
    send: opcjonalna funkcja send(msg) (Telegram); None = tylko zapis/print."""
    ensure_table(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT t.external_id, t.date FROM qbot_v2.training_sessions t "
        "WHERE t.date >= CURRENT_DATE - %s * interval '1 day' "
        "AND t.avg_power_w IS NOT NULL "
        + ("" if recheck else
           "AND NOT EXISTS (SELECT 1 FROM qbot_v2.power_meter_guard g "
           "                WHERE g.external_id = t.external_id) ")
        + "ORDER BY t.date, t.external_id",
        (lookback_days,))
    todo = cur.fetchall()
    out = {"checked": 0, "alerts": 0, "skipped": 0, "baza": 0}
    rides_cache: dict = {}
    mcache: dict = {}
    for eid, d in todo:
        meter = meter_key(cur, eid)
        meter_guess = False
        if meter is None:
            meter = meter_key_from_axs(cur, eid, d)
            meter_guess = meter is not None
        m = _ride_metrics(cur, eid)
        if m is None:
            cur.execute(_UPSERT, (eid, d, None, None, None, None, None, None, "SKIP",
                                  "za malo probek w koszyku HR (jazda krotka/regeneracyjna)", meter))
            out["skipped"] += 1
            continue
        q_dev = None
        if m["q1"] and m["q4"]:
            q_dev = (m["q4"] - m["q1"]) / m["q1"]
        reasons = []
        base, base_note, dev = None, "", None
        if meter is None:
            base_note = "brak danych o mierniku mocy w pliku FIT -- test calej jazdy pominiety"
        else:
            ck = (d, meter)
            if ck not in rides_cache:
                rides_cache[ck] = _baseline_rides(cur, d, meter, mcache)
            base, base_note = _baseline(rides_cache[ck], m.get("temp"), meter)
            if meter_guess:
                base_note += "; miernik ustalony z biegow AXS (brak czujnikow w FIT)"
        if base is not None:
            dev = (m["p"] - base) / base
            kier = "ZAWYZA" if dev > 0 else "ZANIZA"
            if abs(dev) >= PROG_SILNY:
                reasons.append(f"cala jazda mocno {kier}: P@HR {m['p']:.0f} W vs {base:.0f} W ({dev:+.0%}; {base_note})")
            else:
                # trend: poprzednia SPRAWDZONA jazda TYM SAMYM miernikiem
                cur.execute(
                    "SELECT dev_pct FROM qbot_v2.power_meter_guard "
                    "WHERE ride_date < %s AND dev_pct IS NOT NULL AND meter_key = %s "
                    "ORDER BY ride_date DESC LIMIT 1", (d, meter))
                prev = cur.fetchone()
                if (prev and prev[0] is not None and abs(dev) >= PROG_TREND
                        and abs(float(prev[0])) >= PROG_TREND * 100
                        and (dev > 0) == (float(prev[0]) > 0)):
                    reasons.append(
                        f"TREND: druga jazda z rzedu {kier} (poprz. {float(prev[0]):+.0f}%, "
                        f"ta {dev:+.0%}; P@HR {m['p']:.0f} W vs {base:.0f} W, {base_note})")
        if q_dev is not None and q_dev > PROG_CWIARTKI:
            reasons.append(
                f"P@HR ROSNIE w trakcie: cw.1 {m['q1']:.0f} -> cw.4 {m['q4']:.0f} W "
                f"({q_dev:+.0%}; fizjologicznie powinno spadac -- podejrzenie dryfu zera)")
        if reasons:
            verdict, note = "ALERT", "; ".join(reasons)
        elif base is None:
            verdict, note = ("BAZA" if meter else "SKIP"), base_note
        else:
            verdict, note = "OK", f"w normie ({base_note})"
        cur.execute(_UPSERT, (
            eid, d, _r1(m["p"]), _r1(base), None if dev is None else round(dev * 100, 1),
            _r1(m["q1"]), _r1(m["q4"]), None if q_dev is None else round(q_dev * 100, 1),
            verdict, note, meter))
        out["checked"] += 1
        if verdict == "BAZA":
            out["baza"] += 1
        if verdict == "ALERT":
            out["alerts"] += 1
            msg = (f"STRAZNIK MIERNIKA -- jazda {d} ({eid}):\n" + "\n".join(reasons)
                   + "\nSprawdz kalibracje (zero-offset) i rozwaz kwarantanne jazdy.")
            if send is not None:
                try:
                    send(msg)
                except Exception as exc:
                    print(f"power_meter_guard: telegram error: {exc}")
            else:
                print(msg)
    conn.commit()
    return out


def _telegram_send(msg: str) -> None:
    import httpx, sys
    sys.path.insert(0, "/opt/qbot/app")
    import qbot_config as cfg
    for i in range(0, len(msg), 4000):
        r = httpx.post(f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage",
                       json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": msg[i:i + 4000]},
                       timeout=10)
        r.raise_for_status()


def run(conn, lookback_days: int = 7) -> dict:
    """Wejscie dla daily_job: sprawdz + alertuj na Telegram."""
    return check_new_rides(conn, lookback_days=lookback_days, send=_telegram_send)


if __name__ == "__main__":
    # Reczne przeliczenie historii BEZ Telegrama:
    #   .venv/bin/python3 fitmodel/power_meter_guard.py --recheck 40
    import os, sys
    sys.path.insert(0, "/opt/qbot/app")
    os.environ.setdefault("QBOT3_ENABLED", "1")
    from fitmodel.api import _db_connect
    days = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--recheck" else 7
    c = _db_connect()
    try:
        print(check_new_rides(c, lookback_days=days, send=None,
                              recheck=(len(sys.argv) > 1 and sys.argv[1] == "--recheck")))
    finally:
        c.close()
