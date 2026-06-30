#!/usr/bin/env python3
"""Ingest pełnych danych wykonanych jazd: summary (jsonb) + surowy FIT + rekordy(z pozycja) + lapy + eventy.

CLI:
  python qbot_activity_ingest.py one                      # najnowsza jazda (test)
  python qbot_activity_ingest.py backfill [N] [START] [SINCE]  # masowo, idempotentnie, resumable
Tylko cycling/biking (w tym virtual/indoor). Surowy FIT: /opt/qbot/artifacts/fit/<id>.fit
TWARDY CUTOFF: domyslnie tylko jazdy od SINCE=2025-01-01 (jazdy sprzed -> pomijane,
paginacja zatrzymywana, bo lista jest malejaca po dacie). Zmiana: QBOT_ACT_SINCE albo arg CLI.
"""
from __future__ import annotations
import io, os, sys, json, hashlib, zipfile
from datetime import datetime, timezone

sys.path.insert(0, "/opt/qbot/app")
try:
    import psycopg2 as pg
except ModuleNotFoundError:
    import psycopg as pg
from fitparse import FitFile
import fitparse.base as _fb
import fitparse.records as _fr

# Tolerancja developer-fields (Connect IQ): gdy brak deklaracji dev-pola,
# zwracamy placeholder 1-bajtowy -> parser KONSUMUJE wlasciwa liczbe bajtow
# (rozmiar znany z definicji) i czyta dalej STANDARDOWE pola (moc/HR/pozycja).
# Bez tego fitparse rzuca "No such field N for dev_data_index M" na ~2% jazd.
_BYTE_BT = next((bt for bt in _fr.BASE_TYPES.values() if getattr(bt, "size", None) == 1), None)
_ORIG_GET_DEV_TYPE = _fb.get_dev_type


def _safe_get_dev_type(dev_data_index, field_def_num):
    try:
        return _ORIG_GET_DEV_TYPE(dev_data_index, field_def_num)
    except Exception:
        return _fr.DevField(
            dev_data_index=dev_data_index, def_num=field_def_num, type=_BYTE_BT,
            name="unknown_dev_%s_%s" % (dev_data_index, field_def_num),
            units=None, native_field_num=None,
        )


_fb.get_dev_type = _safe_get_dev_type

from garminconnect import Garmin
from garmin_auth import garmin_client

FIT_DIR = "/opt/qbot/artifacts/fit"
SEMI = 180.0 / (2 ** 31)
SINCE = os.getenv("QBOT_ACT_SINCE", "2025-01-01")  # twardy limit historii


def _db():
    return pg.connect(host="127.0.0.1", dbname="qbot", user="qbot", password="")


def _is_cycling(act: dict) -> bool:
    tk = (act.get("activityType") or {}).get("typeKey", "") or ""
    return ("cycl" in tk) or ("bik" in tk)


def _act_date(a: dict):
    s = a.get("startTimeGMT")
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").date()
    except Exception:
        return None


def _semi(v):
    return (v * SEMI) if isinstance(v, (int, float)) else None


def _fv(msg, *names):
    for n in names:
        try:
            val = msg.get_value(n)
        except Exception:
            val = None
        if val is not None:
            return val
    return None


def download_fit(gc, aid) -> bytes:
    raw = gc.download_activity(aid, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
    if raw[:2] == b"PK":  # zip
        zf = zipfile.ZipFile(io.BytesIO(raw))
        fit_name = next((n for n in zf.namelist() if n.lower().endswith(".fit")), None)
        if not fit_name:
            raise ValueError("brak .fit w zipie ORIGINAL")
        return zf.read(fit_name)
    return raw  # juz surowy fit


def parse_fit(fit_bytes: bytes):
    fit = FitFile(io.BytesIO(fit_bytes))
    records, laps, events = [], [], []
    for m in fit.get_messages("record"):
        ts = _fv(m, "timestamp")
        if ts is None:
            continue
        records.append({
            "ts": ts,
            "lat": _semi(_fv(m, "position_lat")),
            "lon": _semi(_fv(m, "position_long")),
            "alt": _fv(m, "enhanced_altitude", "altitude"),
            "dist": _fv(m, "distance"),
            "power": _fv(m, "power"),
            "hr": _fv(m, "heart_rate"),
            "cad": _fv(m, "cadence"),
            "spd": _fv(m, "enhanced_speed", "speed"),
            "temp": _fv(m, "temperature"),
        })
    for m in fit.get_messages("lap"):
        laps.append({
            "idx": _fv(m, "message_index"),
            "start_ts": _fv(m, "start_time"),
            "dist": _fv(m, "total_distance"),
            "moving": _fv(m, "total_timer_time"),
            "elapsed": _fv(m, "total_elapsed_time"),
            "avg_power": _fv(m, "avg_power"),
            "max_power": _fv(m, "max_power"),
            "avg_hr": _fv(m, "avg_heart_rate"),
            "avg_spd": _fv(m, "enhanced_avg_speed", "avg_speed"),
            "s_lat": _semi(_fv(m, "start_position_lat")),
            "s_lon": _semi(_fv(m, "start_position_long")),
            "e_lat": _semi(_fv(m, "end_position_lat")),
            "e_lon": _semi(_fv(m, "end_position_long")),
        })
    for m in fit.get_messages("event"):
        events.append({
            "ts": _fv(m, "timestamp"),
            "event": _fv(m, "event"),
            "event_type": _fv(m, "event_type"),
        })
    return records, laps, events


def _to_int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def store(conn, aid, summary, fit_bytes, records, laps, events):
    # 1) surowy FIT na dysk
    fit_path = os.path.join(FIT_DIR, f"{aid}.fit")
    with open(fit_path, "wb") as f:
        f.write(fit_bytes)
    sha = hashlib.sha256(fit_bytes).hexdigest()

    # 2) rekordy 1 Hz: dedup po sekundzie od startu
    first_ts = records[0]["ts"] if records else None
    rec_rows = {}
    has_pos = False
    for r in records:
        if first_ts is None:
            break
        sec = int((r["ts"] - first_ts).total_seconds())
        if r["lat"] is not None:
            has_pos = True
        rec_rows[sec] = (aid, sec, r["ts"], r["lat"], r["lon"], r["alt"], r["dist"],
                         _to_int(r["power"]), _to_int(r["hr"]), _to_int(r["cad"]),
                         r["spd"], r["temp"])

    lap_rows = []
    for i, lp in enumerate(laps):
        idx = lp["idx"] if isinstance(lp["idx"], int) else i
        lap_rows.append((aid, idx, lp["start_ts"], lp["dist"], lp["moving"], lp["elapsed"],
                         lp["avg_power"], lp["max_power"], lp["avg_hr"], lp["avg_spd"],
                         lp["s_lat"], lp["s_lon"], lp["e_lat"], lp["e_lon"]))

    ev_rows = []
    for i, ev in enumerate(events):
        ev_rows.append((aid, i, ev["ts"], str(ev["event"]) if ev["event"] is not None else None,
                        str(ev["event_type"]) if ev["event_type"] is not None else None))

    start_ts = None
    sg = summary.get("startTimeGMT")
    if sg:
        start_ts = datetime.strptime(sg, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

    with conn.cursor() as cur:
        cur.execute("DELETE FROM qbot_v2.activity_record WHERE external_id=%s", (aid,))
        cur.execute("DELETE FROM qbot_v2.activity_lap WHERE external_id=%s", (aid,))
        cur.execute("DELETE FROM qbot_v2.activity_event WHERE external_id=%s", (aid,))
        if rec_rows:
            cur.executemany(
                "INSERT INTO qbot_v2.activity_record "
                "(external_id,sec,ts,lat,lon,altitude_m,distance_m,power_w,hr_bpm,cadence_rpm,speed_mps,temperature_c) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                list(rec_rows.values()))
        if lap_rows:
            cur.executemany(
                "INSERT INTO qbot_v2.activity_lap "
                "(external_id,lap_index,start_ts,distance_m,moving_s,elapsed_s,avg_power_w,max_power_w,"
                "avg_hr_bpm,avg_speed_mps,start_lat,start_lon,end_lat,end_lon) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", lap_rows)
        if ev_rows:
            cur.executemany(
                "INSERT INTO qbot_v2.activity_event (external_id,idx,ts,event,event_type) "
                "VALUES (%s,%s,%s,%s,%s)", ev_rows)
        cur.execute(
            "INSERT INTO qbot_v2.activity_fit_raw "
            "(external_id,activity_name,sport_type,started_at,summary,fit_path,fit_sha256,fit_bytes,"
            "n_records,n_laps,n_events,has_position,parse_error,fetched_at) "
            "VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,NULL,now()) "
            "ON CONFLICT (external_id) DO UPDATE SET summary=EXCLUDED.summary,fit_path=EXCLUDED.fit_path,"
            "fit_sha256=EXCLUDED.fit_sha256,fit_bytes=EXCLUDED.fit_bytes,n_records=EXCLUDED.n_records,"
            "n_laps=EXCLUDED.n_laps,n_events=EXCLUDED.n_events,has_position=EXCLUDED.has_position,"
            "parse_error=NULL,fetched_at=now()",
            (aid, (summary.get("activityName") or "")[:200],
             (summary.get("activityType") or {}).get("typeKey", "other"),
             start_ts, json.dumps(summary, default=str), fit_path, sha, len(fit_bytes),
             len(rec_rows), len(lap_rows), len(ev_rows), has_pos))
    conn.commit()
    return {"records": len(rec_rows), "laps": len(lap_rows), "events": len(ev_rows),
            "has_position": has_pos, "fit_bytes": len(fit_bytes)}


def ingest_one(gc, conn, summary) -> dict:
    aid = str(summary.get("activityId"))
    fit_bytes = download_fit(gc, aid)
    records, laps, events = parse_fit(fit_bytes)
    res = store(conn, aid, summary, fit_bytes, records, laps, events)
    res["aid"] = aid
    res["name"] = summary.get("activityName")
    return res


def _already(conn, aid) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM qbot_v2.activity_fit_raw WHERE external_id=%s AND parse_error IS NULL", (aid,))
        return cur.fetchone() is not None


def backfill(limit=2000, start=0, since=SINCE):
    cutoff = datetime.strptime(since, "%Y-%m-%d").date()
    gc = garmin_client()
    conn = _db()
    page, off, done, skipped, errors, stop = 100, start, 0, 0, 0, False
    while off < start + limit and not stop:
        acts = gc.get_activities(off, min(page, start + limit - off))
        if not acts:
            break
        for a in acts:
            if not isinstance(a, dict):
                continue
            d = _act_date(a)
            if d is not None and d < cutoff:  # lista malejaca po dacie -> koniec
                stop = True
                break
            if not _is_cycling(a):
                continue
            aid = str(a.get("activityId"))
            if _already(conn, aid):
                skipped += 1
                continue
            try:
                r = ingest_one(gc, conn, a)
                done += 1
                print(f"OK {aid} {r['name']!r} rec={r['records']} lap={r['laps']} ev={r['events']} pos={r['has_position']}")
            except Exception as e:
                errors += 1
                conn.rollback()
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO qbot_v2.activity_fit_raw (external_id,parse_error,fetched_at) "
                        "VALUES (%s,%s,now()) ON CONFLICT (external_id) DO UPDATE SET parse_error=EXCLUDED.parse_error",
                        (aid, str(e)[:300]))
                conn.commit()
                print(f"ERR {aid}: {type(e).__name__}: {str(e)[:160]}")
        off += len(acts)
    conn.close()
    print(f"\nDONE: ingested={done} skipped={skipped} errors={errors} (cutoff={since})")


def _one():
    gc = garmin_client()
    conn = _db()
    acts = gc.get_activities(0, 15)
    cyc = next((a for a in acts if isinstance(a, dict) and _is_cycling(a)), None)
    if not cyc:
        print("brak jazdy w 15 ostatnich"); return
    r = ingest_one(gc, conn, cyc)
    print("INGESTED:", json.dumps(r, default=str))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), count(lat) FROM qbot_v2.activity_record WHERE external_id=%s", (r["aid"],))
        c, cp = cur.fetchone()
        cur.execute("SELECT count(*) FROM qbot_v2.activity_event WHERE external_id=%s AND lower(event)='timer'", (r["aid"],))
        timers = cur.fetchone()[0]
        cur.execute("SELECT sec,lat,lon,power_w,hr_bpm,speed_mps,temperature_c FROM qbot_v2.activity_record "
                    "WHERE external_id=%s ORDER BY sec LIMIT 3", (r["aid"],))
        sample = cur.fetchall()
    print(f"DB: records={c} with_pos={cp} timer_events={timers}")
    print("sample:", sample)
    conn.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "one"
    if cmd == "backfill":
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
        st = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        sn = sys.argv[4] if len(sys.argv) > 4 else SINCE
        backfill(lim, st, sn)
    else:
        _one()
