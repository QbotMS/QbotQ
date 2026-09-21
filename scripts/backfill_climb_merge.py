#!/usr/bin/env python3
"""Backfill podjazdow po wprowadzeniu scalania (karoo_400_3_merge_v2).

Czyta GOTOWE probki z qbot_v2.route_elevation_samples (DEM sie nie zmienil),
przelicza tylko route_climb_events. --apply zapisuje, bez flagi = sucho.
Zakres: trasy o statusie 'active' (decyzja 2026-08-16: jazdy nie ruszamy).
"""
import argparse, os, sys
sys.path.insert(0, "/opt/qbot/app")
os.environ["QBOT3_ENABLED"] = "1"

from fitmodel.api import _db_connect
from qbot3.routes.route_elevation_engine import (
    ElevationSample, detect_route_climb_events, DETECTION_VERSION)
from qbot3.routes.route_elevation_store import build_rows, _replace_events


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    con = _db_connect()
    cur = con.cursor()
    cur.execute("""select route_base_id, route_id, route_version_key
      from qbot_v2.route_base where status='active' order by route_base_id""")
    bases = cur.fetchall()

    tot_old = tot_new = changed = 0
    for rb_id, route_id, rvk in bases:
        cur.execute("""select sample_index, distance_m, lat, lon, elevation_m, source
          from qbot_v2.route_elevation_samples where route_base_id=%s order by sample_index""", (rb_id,))
        rows = cur.fetchall()
        if len(rows) < 3:
            print(f"  SKIP base={rb_id} {route_id}: brak profilu ({len(rows)} probek)")
            continue
        samples = [ElevationSample(r[0], float(r[1]), float(r[2]), float(r[3]),
                                   (float(r[4]) if r[4] is not None else None), r[5]) for r in rows]
        cur.execute("select count(*), coalesce(sum(elevation_gain_m),0) "
                    "from qbot_v2.route_climb_events where route_base_id=%s", (rb_id,))
        n_old, gain_old = cur.fetchone()
        climbs = detect_route_climb_events(samples)
        gain_new = sum(c.elevation_gain_m for c in climbs)
        tot_old += n_old
        tot_new += len(climbs)
        if n_old != len(climbs):
            changed += 1
        flag = "ZMIANA" if n_old != len(climbs) else "  bez zmian"
        print(f"  base={rb_id:>4} {route_id:<22} podjazdy {n_old:>2} -> {len(climbs):>2}  "
              f"przewyzszenie {float(gain_old):>6.0f} -> {gain_new:>6.0f} m  {flag}")
        if args.apply:
            _, event_rows = build_rows(samples, climbs, rb_id, str(rvk))
            _replace_events(con, rb_id, event_rows)

    if args.apply:
        con.commit()
        print(f"\nZAPISANO. wersja={DETECTION_VERSION}")
    else:
        con.rollback()
        print(f"\nSUCHO (bez zapisu). wersja={DETECTION_VERSION}")
    print(f"tras: {len(bases)}, ze zmiana liczby podjazdow: {changed}, "
          f"podjazdy lacznie {tot_old} -> {tot_new}")
    cur.close(); con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
