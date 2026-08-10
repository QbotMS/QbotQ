#!/usr/bin/env python3
"""Zniwiarka podjazdow z historii jazd -> qbot_v2.ride_climb_efforts.

Detekcja podjazdow w strumieniu 1Hz (activity_record) TYM SAMYM silnikiem co
dla planowanych tras (qbot3.routes.route_elevation_engine.detect_route_climb_events)
- dzieki temu 'podjazd na trasie' i 'podjazd przejechany' to to samo pojecie.

Dla kazdego podjazdu liczy: moc/W/kg, HR + dryf, kadencje, biegi (numer pozycji
= kanon; zeby przez qbot_v2.ride_cassette), temperature, W'bal na wejsciu
(KANON: fitmodel.wbal_replay.replay_wbal, replika QExt2), prace przed
podjazdem, oraz detekcje PCHANIA roweru (wolno + brak kadencji + niska moc).

Uzycie:
  .venv/bin/python3 scripts/ride_climb_harvest.py [--since 2026-01-01] [--only ID] [--limit N]
"""
import argparse
import os
import sys

sys.path.insert(0, "/opt/qbot/app")
os.environ.setdefault("QBOT3_ENABLED", "1")

from fitmodel.api import _db_connect  # noqa: E402
from fitmodel.wbal_replay import replay_wbal  # noqa: E402  (kanon W'bal, replika QExt2)
from qbot3.routes.route_elevation_engine import (  # noqa: E402
    ElevationSample, detect_route_climb_events)

DETECTION_VERSION = "ride_karoo_400_3_v1"
WALK_SPEED_MPS = 1.4      # < 5.0 km/h
WALK_CAD_MAX = 15
WALK_POWER_MAX = 60
STOP_SPEED_MPS = 0.3
MOVING_SPEED_MPS = 0.5
FRONT_FALLBACK_T = 36
LTHR_BPM = 132.0  # prog mleczanowy HR (athlete profile); klasyfikacja wysilku


def classify_effort(pct_cp, pct_lthr, hr_drift):
    """Rozroznia 'jechane z zapasem' od 'na limicie' (uwaga uzytkownika:
    czasem sie oszczedzam wiedzac co przede mna - niska moc != brak mozliwosci).

    na_limicie: HR >= ~Z4 (>=95%% LTHR) LUB moc >= 95%% CP LUB wyrazny dryf HR.
    z_zapasem:  HR w Z1-Z2 (<90%% LTHR) i moc < 85%% CP.
    posrednie:  reszta."""
    if pct_lthr is None and pct_cp is None:
        return None
    if (pct_lthr is not None and pct_lthr >= 95.0) or        (pct_cp is not None and pct_cp >= 95.0) or        (hr_drift is not None and hr_drift >= 5.0):
        return "na_limicie"
    if (pct_lthr is not None and pct_lthr < 90.0) and        (pct_cp is None or pct_cp < 85.0):
        return "z_zapasem"
    return "posrednie"


def load_records(cur, aid):
    cur.execute("""
        select sec, ts, distance_m, altitude_m, power_w, hr_bpm, cadence_rpm,
               speed_mps, temperature_c, gear_rear_num, gear_front_t, lat, lon
        from qbot_v2.activity_record
        where external_id=%s order by sec
    """, (aid,))
    return cur.fetchall()


def build_samples(recs):
    """Probki wysokosci po dystansie (rosnaco, bez duplikatow z postoju)."""
    out, last_d = [], -1.0
    for r in recs:
        d, alt = r[2], r[3]
        if d is None or alt is None:
            continue
        d = float(d)
        if d <= last_d:
            continue
        out.append(ElevationSample(sample_index=len(out), distance_m=d,
                                   lat=r[11] or 0.0, lon=r[12] or 0.0,
                                   elevation_m=float(alt), source="ride"))
        last_d = d
    return out


def harvest_one(cur, aid):
    recs = load_records(cur, aid)
    if len(recs) < 120:
        return "ZA_KROTKA", 0
    samples = build_samples(recs)
    if len(samples) < 50:
        return "BEZ_PROFILU", 0
    events = detect_route_climb_events(samples, source="ride")
    # indeks: dystans -> sec (pierwszy rekord z dystansem >= d)
    dist_sec = [(float(r[2]), r[0]) for r in recs if r[2] is not None]

    def sec_at(dist):
        lo, hi = 0, len(dist_sec) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if dist_sec[mid][0] < dist:
                lo = mid + 1
            else:
                hi = mid
        return dist_sec[lo][1]

    # kaseta i W'bal
    cur.execute("select cassette_code from qbot_v2.ride_cassette where external_id=%s", (aid,))
    row = cur.fetchone()
    cassette = row[0] if row else None
    cogs = None
    if cassette:
        cur.execute("select cogs from qbot_v2.gear_cassette where code=%s", (cassette,))
        cogs = cur.fetchone()[0]
    # W'bal: KANON (fitmodel.wbal_replay = replika QExt2: moc 3s, cf ciepla/dryfu,
    # odbudowa tau na postojach). UWAGA (od uzytkownika): W' bylo wielokrotnie
    # przeskalowywane i nie zawsze odpowiadalo realnym mozliwosciom - traktowac
    # jako ceche POMOCNICZA, nie etykiete porazki. Twarda prawda = pchanie/stop.
    _rw = replay_wbal(aid, verbose=False, collect_series=True)
    wbal_by_sec = dict(_rw.get("series") or []) if _rw.get("status") == "OK" else {}
    ftp_base = float(_rw["ftp_base_w"]) if _rw.get("status") == "OK" and _rw.get("ftp_base_w") else None
    # kwarantanna miernika mocy: moc z tych jazd NIE moze uczyc modelu
    cur.execute("select 1 from qbot_v2.fitmodel_ride_quarantine "
                "where external_id=%s and released is null", (aid,))
    quarantined = cur.fetchone() is not None

    sec_index = {r[0]: i for i, r in enumerate(recs)}
    kj_cum, acc = {}, 0.0
    for i, r in enumerate(recs):
        acc += (r[4] or 0) / 1000.0
        kj_cum[i] = acc

    cur.execute("delete from qbot_v2.ride_climb_efforts where external_id=%s", (aid,))
    n = 0
    for ev in events:
        s_sec, e_sec = sec_at(ev.start_m), sec_at(ev.end_m)
        if e_sec <= s_sec:
            continue
        i0, i1 = sec_index.get(s_sec, 0), sec_index.get(e_sec, len(recs) - 1)
        cut = recs[i0:i1 + 1]
        dur = e_sec - s_sec
        pw = [r[4] for r in cut if r[4] is not None]
        hr = [r[5] for r in cut if r[5] is not None]
        cad = [r[6] for r in cut if r[6] is not None]
        tmp = [r[8] for r in cut if r[8] is not None]
        spd = [(r[7] or 0.0) for r in cut]
        moving = sum(1 for v in spd if v > MOVING_SPEED_MPS)
        stopped = sum(1 for v in spd if v <= STOP_SPEED_MPS)
        walked = sum(1 for r in cut
                     if (r[7] or 0) > STOP_SPEED_MPS and (r[7] or 0) < WALK_SPEED_MPS
                     and (r[6] or 0) <= WALK_CAD_MAX and (r[4] or 0) <= WALK_POWER_MAX)
        gears = [r[9] for r in cut if r[9] is not None]
        min_pos = min(gears) if gears else None
        sec_easiest = sum(1 for g in gears if g == 1) if gears else None
        front_t = next((r[10] for r in cut if r[10]), FRONT_FALLBACK_T)
        easiest_cog = ratio_min = None
        if min_pos and cogs and 1 <= min_pos <= len(cogs):
            easiest_cog = cogs[len(cogs) - min_pos]  # pozycja 1 = ostatnia z listy
            ratio_min = round(front_t / easiest_cog, 3)
        hrd = None
        if len(hr) >= 60:
            half = len(hr) // 2
            a, b = sum(hr[:half]) / half, sum(hr[half:]) / (len(hr) - half)
            hrd = round((b - a) / a * 100.0, 1) if a else None
        avg_p = round(sum(pw) / len(pw), 1) if pw else None
        avg_h = round(sum(hr) / len(hr), 1) if hr else None
        pct_cp = round(avg_p / ftp_base * 100.0, 1) if (avg_p and ftp_base) else None
        pct_lthr = round(avg_h / LTHR_BPM * 100.0, 1) if avg_h else None
        eclass = classify_effort(pct_cp, pct_lthr, hrd)
        vam = round(ev.elevation_gain_m / (moving or dur) * 3600.0, 0) if dur else None
        wstart = wmin = None
        if wbal_by_sec:
            seg = [wbal_by_sec[r[0]] for r in cut if r[0] in wbal_by_sec]
            if seg:
                wstart, wmin = round(seg[0], 2), round(min(seg), 2)
        cur.execute("""
            insert into qbot_v2.ride_climb_efforts
            (external_id, event_index, start_sec, end_sec, start_m, end_m,
             length_m, gain_m, avg_pct, max_pct, duration_s, moving_s, vam_mh,
             avg_power_w, wkg, avg_hr, hr_drift_pct, avg_cadence,
             min_gear_pos, sec_at_easiest, cassette_code, easiest_cog, gear_ratio_min,
             avg_temp_c, wbal_start_kj, wbal_min_kj, kj_before, km_from_ride_start,
             walked_s, stopped_s, walked, detection_version,
             ftp_base_w, pct_cp, pct_lthr, effort_class, quarantined)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (aid, ev.event_index, s_sec, e_sec, ev.start_m, ev.end_m,
              ev.length_m, ev.elevation_gain_m, ev.avg_gradient_pct, ev.max_gradient_pct,
              dur, moving, vam,
              avg_p, None, avg_h, hrd,
              round(sum(cad) / len(cad), 1) if cad else None,
              min_pos, sec_easiest, cassette, easiest_cog, ratio_min,
              round(sum(tmp) / len(tmp), 1) if tmp else None,
              wstart, wmin, round(kj_cum.get(i0, 0.0), 1),
              round(ev.start_m / 1000.0, 2),
              walked, stopped, walked >= 30, DETECTION_VERSION,
              ftp_base, pct_cp, pct_lthr, eclass, quarantined))
        n += 1
    return "OK", n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2025-01-01")
    ap.add_argument("--only", default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    with _db_connect() as conn:
        cur = conn.cursor()
        if args.only:
            aids = [(args.only,)]
        else:
            cur.execute("""select external_id from qbot_v2.activity_fit_raw
                           where started_at >= %s order by started_at""", (args.since,))
            aids = cur.fetchall()
            if args.limit:
                aids = aids[:args.limit]
        print("jazd: %d" % len(aids), flush=True)
        stat, total = {}, 0
        for (aid,) in aids:
            try:
                st, n = harvest_one(cur, aid)
                conn.commit()
            except Exception as e:
                conn.rollback()
                st, n = "BLAD:%s" % type(e).__name__, 0
            stat[st] = stat.get(st, 0) + 1
            total += n
            print("  %s %-12s podjazdow=%d" % (aid, st, n), flush=True)
        print("PODSUMOWANIE:", stat, "podjazdow lacznie:", total)


if __name__ == "__main__":
    main()
