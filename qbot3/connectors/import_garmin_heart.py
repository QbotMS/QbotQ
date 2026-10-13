#!/usr/bin/env python3
"""import_garmin_heart.py -- Serce (2026-10-12): cisnienie + EKG z Garmina, tetno przy stalej mocy.

Uruchamia straznik Garmina (scripts/garmin_watch.py) po imporcie jazd, a takze
qbot-withings-sync zaraz po wyslaniu nowego pomiaru cisnienia do Garmina.

  1. Cisnienie: Garmin get_blood_pressure (tam trafia z Withings) -> qbot_v2.blood_pressure
  2. EKG: ghs.connect.garmin.com/ghs/ecg/v1/ecg/list (ten sam adres co strona
     Garmin Connect, ta sama sesja QBota) -> qbot_v2.ecg_recording
  3. Tetno przy stalej mocy: jazdy bez wpisu w qbot_v2.hr_at_power liczone z activity_record
     (HR w sekundach z moca 140-180 W, od 15. do 120. minuty jazdy).

Wszystko idempotentne (UNIQUE / ON CONFLICT). Kazda czesc ma wlasny try: awaria jednej
nie blokuje pozostalych, ale konczy sie kodem 1 (straznik ponowi).

Uzycie:
    .venv/bin/python3 qbot3/connectors/import_garmin_heart.py            # cisnienie 30 dni
    .venv/bin/python3 qbot3/connectors/import_garmin_heart.py --days 1500
    .venv/bin/python3 qbot3/connectors/import_garmin_heart.py --only bp|ecg|hrp
Dokumentacja: docs/SERCE.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path("/opt/qbot/app")
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("QBOT3_ENABLED", "1")

ECG_LIST_URL = "https://ghs.connect.garmin.com/ghs/ecg/v1/ecg/list"
ECG_FIRST_DAY = "2020-01-01"
HRP_BAND = (140, 180)        # W
HRP_SEC_FROM = 15 * 60       # bez rozgrzewki
HRP_SEC_TO = 120 * 60        # bez dryfu dlugiej jazdy


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def _db():
    from fitmodel.api import _db_connect
    return _db_connect()


def _parse_ts(value) -> datetime | None:
    """Garmin podaje znaczniki czasu jako ISO (z 'T' lub bez) albo milisekundy epoki."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0, timezone.utc).replace(tzinfo=None)
    s = str(value).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1]
    try:
        return datetime.fromisoformat(s.split("+")[0])
    except ValueError:
        return None


def _int(v):
    try:
        return int(round(float(v))) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- cisnienie

def import_bp(g, conn, days: int) -> int:
    end = date.today()
    start = end - timedelta(days=days)
    n = 0
    # Garmin przyjmuje ograniczony zakres -- kawalki po 180 dni.
    cur_end = end
    rows = []
    while cur_end >= start:
        cur_start = max(start, cur_end - timedelta(days=179))
        data = g.get_blood_pressure(cur_start.isoformat(), cur_end.isoformat()) or {}
        for day in data.get("measurementSummaries") or []:
            for m in day.get("measurements") or []:
                rows.append(m)
        cur_end = cur_start - timedelta(days=1)

    with conn.cursor() as cur:
        for m in rows:
            sys_ = _int(m.get("systolic"))
            dia = _int(m.get("diastolic"))
            if not sys_ or not dia:
                continue
            gmt = _parse_ts(m.get("measurementTimestampGMT"))
            loc = _parse_ts(m.get("measurementTimestampLocal"))
            if gmt is None or loc is None:
                continue
            src_id = str(m.get("samplePk") or m.get("measurementTimestampGMT"))
            cur.execute(
                """INSERT INTO qbot_v2.blood_pressure
                       (measured_at, measured_local, systolic, diastolic, pulse, source, source_id, raw_json)
                   VALUES (%s, %s, %s, %s, %s, 'garmin', %s, %s::jsonb)
                   ON CONFLICT (source, source_id) DO UPDATE SET
                       systolic = EXCLUDED.systolic, diastolic = EXCLUDED.diastolic,
                       pulse = EXCLUDED.pulse, raw_json = EXCLUDED.raw_json""",
                (gmt.replace(tzinfo=timezone.utc), loc, sys_, dia, _int(m.get("pulse")),
                 src_id, json.dumps(m, default=str)),
            )
            n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------- EKG

def _ecg_list(g) -> list[dict]:
    # Sesja jest swieza po wywolaniu przez connectapi (odswiezanie tokenu robi biblioteka).
    g.get_device_last_used()
    c = g.client
    out: list[dict] = []
    params = {"firstDay": ECG_FIRST_DAY, "lastDay": date.today().isoformat(), "pageSize": 100}
    r = c._api_session.get(ECG_LIST_URL, params=params, headers=c.get_api_headers(), timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"EKG: HTTP {r.status_code}")
    body = r.json() or {}
    out.extend(body.get("content") or [])
    return out


def import_ecg(g, conn) -> int:
    items = _ecg_list(g)
    n = 0
    with conn.cursor() as cur:
        for e in items:
            did = e.get("detailId")
            if not did:
                continue
            loc = _parse_ts(e.get("startTimeLocal"))
            gmt = _parse_ts(e.get("startTime"))
            dev = e.get("deviceInfo") or {}
            device = ((dev.get("productName") or dev.get("deviceName") or dev.get("displayName"))
                      if isinstance(dev, dict) else (str(dev) if dev else None))
            hrv = e.get("rmssdHrv")
            cur.execute(
                """INSERT INTO qbot_v2.ecg_recording
                       (detail_id, started_at, started_local, classification, hr_avg, rmssd_hrv,
                        symptoms, device, raw_json)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                   ON CONFLICT (detail_id) DO UPDATE SET
                       classification = EXCLUDED.classification, symptoms = EXCLUDED.symptoms,
                       raw_json = EXCLUDED.raw_json""",
                (str(did), gmt.replace(tzinfo=timezone.utc) if gmt else None, loc,
                 e.get("rhythmClassification"), _int(e.get("heartRateAverage")),
                 float(hrv) if hrv is not None else None,
                 json.dumps(e.get("symptoms") or []), device, json.dumps(e, default=str)),
            )
            n += 1
    conn.commit()
    _ecg_details(g, conn)
    return n


ECG_DETAIL_URL = "https://ghs.connect.garmin.com/ghs/ecg/v1/ecg/{}"


def _ecg_details(g, conn) -> None:
    """Przebieg (reading.samples) dla nagran bez niego + analiza uderzen (qbot_ecg); przeliczenie przy nowej wersji analizy."""
    import qbot_ecg as Q
    c = g.client
    with conn.cursor() as cur:
        cur.execute("SELECT detail_id FROM qbot_v2.ecg_recording WHERE samples IS NULL")
        todo = [r[0] for r in cur.fetchall()]
    for did in todo:
        r = c._api_session.get(ECG_DETAIL_URL.format(did), headers=c.get_api_headers(), timeout=20)
        if r.status_code != 200:
            log(f"EKG {did[:8]}: szczegoly HTTP {r.status_code}")
            continue
        rd = (r.json() or {}).get("reading") or {}
        smp, fs = rd.get("samples") or [], float(rd.get("sampleRate") or 0)
        an = Q.analyze(smp, fs)
        with conn.cursor() as cur:
            cur.execute("UPDATE qbot_v2.ecg_recording SET samples=%s::jsonb, sample_rate=%s, lead=%s, analysis=%s::jsonb WHERE detail_id=%s",
                        (json.dumps(smp), fs, rd.get("leadType"), json.dumps(an), did))
        conn.commit()
        log(f"EKG {did[:8]}: przebieg {len(smp)} probek, uderzen {an.get('n_beats')}, nieregularne {an.get('n_irregular', 0)}")
    with conn.cursor() as cur:   # nowa wersja analizy -> przelicz z zapisanego przebiegu (bez pobierania)
        cur.execute("SELECT detail_id, samples, sample_rate FROM qbot_v2.ecg_recording WHERE samples IS NOT NULL "
                    "AND coalesce((analysis->>'v')::int, 0) <> %s", (Q.VERSION,))
        for did, smp, fs in cur.fetchall():
            cur.execute("UPDATE qbot_v2.ecg_recording SET analysis=%s::jsonb WHERE detail_id=%s",
                        (json.dumps(Q.analyze(smp, fs)), did))
    conn.commit()


# ---------------------------------------------------------------- SpO2 nocne

def import_spo2(g, conn, days: int = 3) -> int:
    """Srednia i najnizsza saturacja nocy (Garmin get_spo2_data) -> qbot_v2.spo2_daily."""
    n = 0
    for k in range(days):
        d = date.today() - timedelta(days=k)
        j = g.get_spo2_data(d.isoformat()) or {}
        if j.get("averageSpO2") is None and j.get("lowestSpO2") is None:
            continue
        keep = {kk: v for kk, v in j.items() if not isinstance(v, (list, dict))}
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO qbot_v2.spo2_daily (day, avg_spo2, sleep_avg_spo2, lowest_spo2, raw_json)
                           VALUES (%s,%s,%s,%s,%s::jsonb) ON CONFLICT (day) DO UPDATE SET avg_spo2=EXCLUDED.avg_spo2,
                           sleep_avg_spo2=EXCLUDED.sleep_avg_spo2, lowest_spo2=EXCLUDED.lowest_spo2, raw_json=EXCLUDED.raw_json, imported_at=now()""",
                        (d, j.get("averageSpO2"), j.get("avgSleepSpO2"), j.get("lowestSpO2"), json.dumps(keep, default=str)))
        n += 1
    conn.commit()
    return n


# ---------------------------------------------------------------- tetno przy mocy

def compute_hr_at_power(conn, recompute: bool = False) -> int:
    lo, hi = HRP_BAND
    with conn.cursor() as cur:
        if recompute:
            cur.execute("DELETE FROM qbot_v2.hr_at_power")
        cur.execute(
            """WITH todo AS (
                   SELECT s.external_id, max(s.date) AS ride_date
                   FROM qbot_v2.training_sessions s
                   WHERE s.external_id IS NOT NULL
                     AND NOT EXISTS (SELECT 1 FROM qbot_v2.hr_at_power h WHERE h.external_id = s.external_id)
                     AND EXISTS (SELECT 1 FROM qbot_v2.activity_record r WHERE r.external_id = s.external_id)
                   GROUP BY s.external_id
               ), agg AS (
                   SELECT r.external_id, count(*) AS sec, avg(r.hr_bpm) AS hr, avg(r.power_w) AS w,
                          avg(r.temperature_c) AS t
                   FROM qbot_v2.activity_record r
                   JOIN todo ON todo.external_id = r.external_id
                   WHERE r.power_w BETWEEN %s AND %s AND r.hr_bpm BETWEEN 80 AND 200
                     AND r.sec BETWEEN %s AND %s
                   GROUP BY r.external_id
               )
               INSERT INTO qbot_v2.hr_at_power
                   (external_id, ride_date, band_lo_w, band_hi_w, sec, hr_avg, power_avg, temp_avg)
               SELECT todo.external_id, todo.ride_date, %s, %s, coalesce(agg.sec, 0),
                      agg.hr, agg.w, agg.t
               FROM todo LEFT JOIN agg ON agg.external_id = todo.external_id
               ON CONFLICT (external_id) DO NOTHING""",
            (lo, hi, HRP_SEC_FROM, HRP_SEC_TO, lo, hi),
        )
        n = cur.rowcount
    conn.commit()
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Serce: cisnienie + EKG z Garmina, tetno przy mocy")
    ap.add_argument("--days", type=int, default=30, help="ile dni cisnienia wstecz")
    ap.add_argument("--only", choices=["bp", "ecg", "hrp", "spo2"])
    ap.add_argument("--spo2-days", type=int, default=3)
    ap.add_argument("--recompute-hrp", action="store_true")
    args = ap.parse_args()

    fails = 0
    conn = _db()
    g = None
    if args.only in (None, "bp", "ecg", "spo2"):
        try:
            from garmin_auth import garmin_client
            g = garmin_client()
        except Exception as exc:
            log(f"Garmin niedostepny: {type(exc).__name__}: {str(exc)[:150]}")
            fails += 1

    if g is not None and args.only in (None, "bp"):
        try:
            log(f"cisnienie: {import_bp(g, conn, args.days)} pomiarow (okno {args.days} dni)")
        except Exception as exc:
            conn.rollback()
            fails += 1
            log(f"cisnienie BLAD: {type(exc).__name__}: {str(exc)[:200]}")

    if g is not None and args.only in (None, "ecg"):
        try:
            log(f"EKG: {import_ecg(g, conn)} nagran")
        except Exception as exc:
            conn.rollback()
            fails += 1
            log(f"EKG BLAD: {type(exc).__name__}: {str(exc)[:200]}")

    if g is not None and args.only in (None, "spo2"):
        try:
            log(f"SpO2: {import_spo2(g, conn, args.spo2_days)} nocy")
        except Exception as exc:
            conn.rollback()
            fails += 1
            log(f"SpO2 BLAD: {type(exc).__name__}: {str(exc)[:200]}")

    if args.only in (None, "hrp"):
        try:
            log(f"tetno przy mocy: {compute_hr_at_power(conn, args.recompute_hrp)} nowych jazd")
        except Exception as exc:
            conn.rollback()
            fails += 1
            log(f"tetno przy mocy BLAD: {type(exc).__name__}: {str(exc)[:200]}")

    conn.close()
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
