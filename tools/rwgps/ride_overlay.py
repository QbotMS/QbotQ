#!/usr/bin/env python3
"""FAZA B — naloz przejazd (FIT) na pudelka planu + diff trasa-vs-plan.

1. Czyta FIT (GPS + moc/HR/kadencja/predkosc per sekunda).
2. Auto-kojarzy z planowana trasa po PUNKCIE STARTU (najblizszy route_frames#0),
   przy remisie preferuje najnowszy artefakt.
3. Przypisuje kazda sekunde do najblizszego pudelka planu (okno przesuwne),
   liczy odleglosc od planu (diff) i srednie streamu per pudelko.
4. Zapis do qbot_v2.ride_frames. off_plan = mediana odleglosci > 60 m.

Uzycie:
  .venv/bin/python -m tools.rwgps.ride_overlay --latest [--dry-run] [--show 8]
  .venv/bin/python -m tools.rwgps.ride_overlay --fit /sciezka/plik.fit
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import sys
from datetime import timezone
from pathlib import Path
from statistics import median

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2

from fitparse import FitFile

SEMI = 180.0 / (2 ** 31)
FIT_DIR = "/opt/qbot/artifacts/fit"
BUILDER_VERSION = "ride_overlay-v1"
OFF_PLAN_M = 60.0
MATCH_START_MAX_M = 2000.0


def _load_env_local():
    p = Path(__file__).resolve().parents[2] / ".env.local"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)


def _db_connect():
    _load_env_local()
    kwargs = {"host": os.getenv("PGHOST", "127.0.0.1"), "port": int(os.getenv("PGPORT", "5432")),
              "user": os.getenv("PGUSER", "qbot"), "dbname": os.getenv("PGDATABASE", "qbot")}
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return psycopg2.connect(**kwargs)


def _hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _read_fit(path):
    out = []
    for m in FitFile(path).get_messages("record"):
        d = {x.name: x.value for x in m}
        lat, lon, ts = d.get("position_lat"), d.get("position_long"), d.get("timestamp")
        if lat is None or lon is None or ts is None:
            continue
        out.append({
            "ts": ts, "lat": lat * SEMI, "lon": lon * SEMI,
            "power": d.get("power"), "hr": d.get("heart_rate"),
            "cad": d.get("cadence"), "speed": d.get("speed"), "dist": d.get("distance"),
        })
    out.sort(key=lambda s: s["ts"])
    return out


def _find_route(cur, slat, slon):
    cur.execute("SELECT route_artifact_id, route_id, start_lat, start_lon "
                "FROM qbot_v2.route_frames WHERE frame_index=0 AND frame_size_m=80")
    best, bestd, brid = None, float("inf"), None
    for aid, rid, la, lo in cur.fetchall():
        if la is None:
            continue
        d = _hav(slat, slon, la, lo)
        if d < bestd:
            bestd, best, brid = d, aid, rid
    if best is not None and bestd <= MATCH_START_MAX_M:
        return best, brid, bestd
    return None, None, bestd


def _avg(vals):
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None


def build(fit_path=None, use_latest=False, frame_size=80, dry_run=False, show=0):
    if use_latest:
        files = sorted(glob.glob(os.path.join(FIT_DIR, "*.fit")), key=os.path.getmtime)
        if not files:
            print("BLAD: brak plikow FIT w " + FIT_DIR)
            return 2
        fit_path = files[-1]
    if not fit_path or not os.path.exists(fit_path):
        print(f"BLAD: brak pliku FIT: {fit_path}")
        return 2
    ride_key = os.path.basename(fit_path)

    samples = _read_fit(fit_path)
    if len(samples) < 10:
        print(f"BLAD: za malo punktow GPS w FIT ({len(samples)})")
        return 2

    conn = _db_connect()
    conn.autocommit = False
    cur = conn.cursor()

    aid, rid, startd = _find_route(cur, samples[0]["lat"], samples[0]["lon"])
    if aid is None:
        print(f"Brak dopasowanego planu (najblizszy start {startd:.0f} m > {MATCH_START_MAX_M:.0f} m). "
              f"Jazda bez planu — tryb fallback (do zrobienia osobno).")
        return 3

    cur.execute("SELECT frame_index, mid_lat, mid_lon FROM qbot_v2.route_frames "
                "WHERE route_artifact_id=%s AND frame_size_m=%s ORDER BY frame_index", (aid, int(frame_size)))
    frames = cur.fetchall()
    nf = len(frames)

    # przypisz kazda sekunde do najblizszego pudelka (okno przesuwne)
    groups = {}
    last_fi = 0
    for s in samples:
        lo = max(0, last_fi - 40)
        hi = min(nf, last_fi + 120)
        bi, bd = lo, float("inf")
        for k in range(lo, hi):
            d = _hav(s["lat"], s["lon"], frames[k][1], frames[k][2])
            if d < bd:
                bd, bi = d, k
        last_fi = bi
        fidx = frames[bi][0]
        groups.setdefault(fidx, []).append((s, bd))

    out_rows = []
    for fidx in sorted(groups):
        g = groups[fidx]
        ss = [x[0] for x in g]
        ds = [x[1] for x in g]
        ts_sorted = sorted(x["ts"] for x in ss)
        t_start = ts_sorted[0]
        t_mid = ts_sorted[len(ts_sorted) // 2]
        med_d = median(ds)
        out_rows.append((
            ride_key, fit_path, aid, int(frame_size), fidx, len(ss), t_start, t_mid,
            _avg([x["power"] for x in ss]), _avg([x["hr"] for x in ss]),
            _avg([x["cad"] for x in ss]), _avg([x["speed"] for x in ss]),
            med_d, med_d > OFF_PLAN_M, BUILDER_VERSION,
        ))

    off = sum(1 for r in out_rows if r[13])
    pw = _avg([r[8] for r in out_rows])
    sp = _avg([r[11] for r in out_rows])
    print(f"FIT: {ride_key}")
    print(f"  dopasowany plan: route_id={rid} artifact_id={aid} (start {startd:.0f} m)")
    print(f"  sekund GPS: {len(samples)} | pudelek przejechanych: {len(out_rows)}/{nf}")
    print(f"  poza planem (>{OFF_PLAN_M:.0f} m): {off} pudelek")
    if pw:
        print(f"  srednia moc: {pw:.0f} W | srednia predkosc: {sp*3.6:.1f} km/h" if sp else f"  srednia moc: {pw:.0f} W")
    if show:
        print(f"  --- pierwsze {show} pudelek ---")
        for r in out_rows[:show]:
            p = f"{r[8]:.0f}W" if r[8] is not None else "--"
            h = f"{r[9]:.0f}" if r[9] is not None else "--"
            spd = f"{r[11]*3.6:.1f}" if r[11] is not None else "--"
            flag = " [POZA PLANEM]" if r[13] else ""
            print(f"   #{r[4]:>3} n={r[5]:>2} moc={p} hr={h} v={spd}km/h dist_plan={r[12]:.0f}m{flag}")

    if dry_run:
        print("  [DRY-RUN] nie zapisuje")
        conn.rollback()
        return 0

    cur.execute("DELETE FROM qbot_v2.ride_frames WHERE ride_key=%s AND frame_size_m=%s", (ride_key, int(frame_size)))
    for r in out_rows:
        cur.execute(
            "INSERT INTO qbot_v2.ride_frames "
            "(ride_key, fit_path, route_artifact_id, frame_size_m, frame_index, n_samples, t_start, t_mid, "
            " avg_power_w, avg_hr_bpm, avg_cadence_rpm, avg_speed_ms, dist_from_plan_m, off_plan, builder_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", r)
    conn.commit()
    print(f"  ZAPISANO {len(out_rows)} pudelek przejazdu do qbot_v2.ride_frames")
    return 0


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--fit", type=str)
    g.add_argument("--latest", action="store_true")
    ap.add_argument("--frame-size", type=int, default=80)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    sys.exit(build(a.fit, a.latest, a.frame_size, a.dry_run, a.show))


if __name__ == "__main__":
    main()
