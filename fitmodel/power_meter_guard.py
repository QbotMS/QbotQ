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
cad>=40, v>=3 m/s, P>0) jest u Michala stabilna od 15 miesiecy (~185-210 W).
Dwa testy na kazdej nowej jezdzie:
  1. CALA JAZDA vs baza: mediana P@HR jazdy vs mediana median z 450 dni
     (bez jazd z kwarantanny). Odchyl > PROG_CALOSC (12%%) w KTORAKOLWIEK
     strone -> alert. Lapie stabilne zanizanie/zawyzanie (typ 22-30.07).
  2. WEWNATRZ JAZDY: ostatnia cwiartka vs pierwsza (obie >= MIN_S_CWIARTKA
     probek w koszyku). Fizjologia dlugiej jazdy = P@HR SPADA (dryf sercowy);
     wzrost > PROG_CWIARTKI (15%%) jest przeciw fizjologii -> alert.
     Lapie dryf w trakcie (typ 2.08: cw.4 +30%% vs cw.3).
Wyniki idempotentnie w qbot_v2.power_meter_guard; alert na Telegram raz.

OGRANICZENIA
------------
- Chlod podnosi P@HR (zima 219-225), upal obniza -- prog 12%% dobrany tak,
  by sezonowosc nie strzelala (max sezonowy odchyl od mediany ~10%%).
- Jazdy regeneracyjne moga nie miec 10 min w koszyku HR -> SKIP, nie alert.
- To detektor ANOMALII, nie dowod: alert = "sprawdz kalibracje", decyzja
  o kwarantannie pozostaje reczna (DECISIONS).
"""
from __future__ import annotations

import statistics as st
import datetime as dt

HR_LO, HR_HI = 115, 135
MIN_S_JAZDA = 600        # min. 10 min probek w koszyku, inaczej SKIP
MIN_S_CWIARTKA = 300     # min. 5 min w cwiartce dla testu wewnatrz jazdy
# Logika stopniowana (kalibrowana na historii 06-08.2026, patrz DECISIONS):
# pojedynczy prog 12% dawal 13/29 falszywych alertow (mocny dzien = "zawyza",
# upalna regeneracja = "zaniza"), a dryf lipcowy vs baza temperaturowa to
# ledwie -8..-11% na jazde. Dlatego:
PROG_SILNY = 0.20        # |dev| >= 20% jednej jazdy -> alert od razu
PROG_TREND = 0.08        # |dev| >= 8% DWIE kolejne jazdy w TA SAMA strone -> alert
PROG_CWIARTKI = 0.25     # +25% cw.4 vs cw.1 (fizjologia kaze spadac) -> alert
BAZA_DNI = 450           # ~15 miesiecy
TEMP_OKNO = 5            # +-C: baza z jazd o podobnej temperaturze
MIN_JAZD_TEMP = 10       # min. jazd w oknie temp, inaczej okno x2 / globalna
MIN_JAZD_BAZY = 20       # bez sensownej bazy nie oceniamy


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
                verdict      text,        -- OK / ALERT / SKIP
                note         text,
                checked_at   timestamptz NOT NULL DEFAULT now()
            )
        """)
    conn.commit()


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


def _baseline_rides(cur, before_date) -> list:
    """(P@HR, temp) per czysta jazda z BAZA_DNI przed data (bez kwarantanny)."""
    cur.execute(
        "SELECT t.external_id FROM qbot_v2.training_sessions t "
        "WHERE t.date >= %s::date - %s * interval '1 day' AND t.date < %s "
        "AND t.avg_power_w IS NOT NULL AND t.duration_s > 1800 "
        "AND NOT EXISTS (SELECT 1 FROM qbot_v2.fitmodel_ride_quarantine k "
        "                WHERE k.external_id = t.external_id AND k.released IS NULL)",
        (before_date, BAZA_DNI, before_date))
    out = []
    for (eid,) in cur.fetchall():
        m = _ride_metrics(cur, eid)
        if m:
            out.append((m["p"], m["temp"]))
    return out


def _baseline(rides: list, temp) -> tuple:
    """Baza warunkowana temperatura: mediana z jazd o medianie temperatury
    w oknie +-TEMP_OKNO stopni. Chlod podnosi P@HR, upal obniza -- globalna
    mediana dawala falszywe alerty (13/29 w tescie 06-08.2026). Gdy w oknie
    za malo jazd, okno poszerzane x2, ostatecznie baza globalna z notka."""
    if len(rides) < MIN_JAZD_BAZY:
        return None, ""
    if temp is not None:
        for okno in (TEMP_OKNO, TEMP_OKNO * 2):
            sel = [p for p, t in rides if t is not None and abs(t - temp) <= okno]
            if len(sel) >= MIN_JAZD_TEMP:
                return st.median(sel), f"baza {len(sel)} jazd w {temp:.0f}C+-{okno}"
    return st.median([p for p, _ in rides]), f"baza globalna ({len(rides)} jazd)"


def check_new_rides(conn, lookback_days: int = 7, send=None) -> dict:
    """Sprawdza jazdy z ostatnich N dni bez wpisu w power_meter_guard.
    send: opcjonalna funkcja send(msg) (Telegram); None = tylko zapis/print."""
    ensure_table(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT t.external_id, t.date FROM qbot_v2.training_sessions t "
        "WHERE t.date >= CURRENT_DATE - %s * interval '1 day' "
        "AND t.avg_power_w IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM qbot_v2.power_meter_guard g "
        "                WHERE g.external_id = t.external_id) "
        "ORDER BY t.date",
        (lookback_days,))
    todo = cur.fetchall()
    out = {"checked": 0, "alerts": 0, "skipped": 0}
    rides_cache: dict = {}
    for eid, d in todo:
        m = _ride_metrics(cur, eid)
        if m is None:
            cur.execute(
                "INSERT INTO qbot_v2.power_meter_guard "
                "(external_id, ride_date, verdict, note) VALUES (%s,%s,'SKIP',"
                "'za malo probek w koszyku HR (jazda krotka/regeneracyjna)') "
                "ON CONFLICT (external_id) DO NOTHING", (eid, d))
            out["skipped"] += 1
            continue
        if d not in rides_cache:
            rides_cache[d] = _baseline_rides(cur, d)
        base, base_note = _baseline(rides_cache[d], m.get("temp"))
        if base is None:
            cur.execute(
                "INSERT INTO qbot_v2.power_meter_guard "
                "(external_id, ride_date, verdict, note) VALUES (%s,%s,'SKIP',"
                "'brak bazy (za malo czystych jazd)') "
                "ON CONFLICT (external_id) DO NOTHING", (eid, d))
            out["skipped"] += 1
            continue
        dev = (m["p"] - base) / base
        q_dev = None
        if m["q1"] and m["q4"]:
            q_dev = (m["q4"] - m["q1"]) / m["q1"]
        reasons = []
        kier = "ZAWYZA" if dev > 0 else "ZANIZA"
        if abs(dev) >= PROG_SILNY:
            reasons.append(f"cala jazda mocno {kier}: P@HR {m['p']:.0f} W vs {base:.0f} W ({dev:+.0%}; {base_note})")
        else:
            # trend: poprzednia SPRAWDZONA jazda z odchylem w te sama strone
            cur.execute(
                "SELECT dev_pct FROM qbot_v2.power_meter_guard "
                "WHERE ride_date < %s AND dev_pct IS NOT NULL "
                "ORDER BY ride_date DESC LIMIT 1", (d,))
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
        verdict = "ALERT" if reasons else "OK"
        note = "; ".join(reasons) if reasons else "w normie"
        cur.execute(
            "INSERT INTO qbot_v2.power_meter_guard "
            "(external_id, ride_date, p_at_hr_w, baseline_w, dev_pct, q1_w, q4_w, q_dev_pct, verdict, note) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (external_id) DO NOTHING",
            (eid, d, round(m["p"], 1), round(base, 1), round(dev * 100, 1),
             m["q1"] and round(m["q1"], 1), m["q4"] and round(m["q4"], 1),
             q_dev is not None and round(q_dev * 100, 1) or None, verdict, note))
        out["checked"] += 1
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
