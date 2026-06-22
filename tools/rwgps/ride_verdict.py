#!/usr/bin/env python3
"""FAZA B — realna pogoda + wnioskowanie o wietrze + werdykt jazdy.

1. Dolicza realna pogode (kind=actual) per pudelko z czasow FIT (Open-Meteo;
   archiwum jako fallback), skladowa wiatru wzgledem heading planu.
2. Wnioskowanie o wietrze: na plaskich pudelkach liczy NADWYZKE predkosci
   (reszta po odjeciu wplywu mocy) i koreluje ja z wind_component.
3. Werdykt krotki, przylozony do formy (ostatni pelny FTP z fitmodel_daily).

Uzycie:
  .venv/bin/python -m tools.rwgps.ride_verdict --ride latest [--dry-run]
  .venv/bin/python -m tools.rwgps.ride_verdict --ride <ride_key>
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timezone
from pathlib import Path

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2

import httpx

sys.path.insert(0, "/opt/qbot/app")
from tools.rwgps.route_weather import _rel_wind, _db_connect  # noqa: E402

OM_FC = "https://api.open-meteo.com/v1/forecast"
OM_ARCH = "https://archive-api.open-meteo.com/v1/archive"


def _fetch_hourly(url, lat, lon, day):
    params = {"latitude": round(lat, 4), "longitude": round(lon, 4),
              "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m",
              "wind_speed_unit": "ms", "timezone": "auto", "start_date": day, "end_date": day}
    r = httpx.get(url, params=params, timeout=25.0)
    r.raise_for_status()
    h = r.json().get("hourly", {})
    times = h.get("time", [])
    out = {}
    for i, ts in enumerate(times):
        out[ts[:13]] = {"temp": h.get("temperature_2m", [None]*len(times))[i],
                        "precip": h.get("precipitation", [None]*len(times))[i],
                        "wspeed": h.get("wind_speed_10m", [None]*len(times))[i],
                        "wdir": h.get("wind_direction_10m", [None]*len(times))[i]}
    return out


def _fetch_actual(lat, lon, day):
    for url, label in ((OM_FC, "open-meteo/recent"), (OM_ARCH, "open-meteo/archive")):
        try:
            m = _fetch_hourly(url, lat, lon, day)
            if m:
                return m, label
        except Exception as e:
            print(f"  (pogoda {label} nieudana: {e!r})")
    return {}, "brak"


def _linreg(xs, ys):
    n = len(xs)
    if n < 5:
        return None, None, None
    mx = sum(xs)/n; my = sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs); sxy = sum((xs[i]-mx)*(ys[i]-my) for i in range(n))
    syy = sum((y-my)**2 for y in ys)
    if sxx == 0 or syy == 0:
        return None, None, None
    slope = sxy/sxx
    intercept = my - slope*mx
    r = sxy/((sxx*syy) ** 0.5)
    return slope, intercept, r


def build(ride="latest", frame_size=80, dry_run=False):
    conn = _db_connect()
    conn.autocommit = False
    cur = conn.cursor()

    if ride == "latest":
        cur.execute("SELECT ride_key FROM qbot_v2.ride_frames WHERE frame_size_m=%s "
                    "ORDER BY t_start DESC LIMIT 1", (int(frame_size),))
        row = cur.fetchone()
        if not row:
            print("BLAD: brak jazd w ride_frames")
            return 2
        ride = row[0]

    cur.execute(
        "SELECT r.frame_index, r.t_mid, r.avg_power_w, r.avg_hr_bpm, r.avg_speed_ms, r.off_plan, "
        "       r.route_artifact_id, rf.heading_deg, rf.avg_grade_pct, rf.surface, rf.mid_lat, rf.mid_lon "
        "FROM qbot_v2.ride_frames r "
        "JOIN qbot_v2.route_frames rf ON rf.route_artifact_id=r.route_artifact_id "
        "  AND rf.frame_size_m=r.frame_size_m AND rf.frame_index=r.frame_index "
        "WHERE r.ride_key=%s AND r.frame_size_m=%s ORDER BY r.frame_index",
        (ride, int(frame_size)),
    )
    rows = cur.fetchall()
    if not rows:
        print(f"BLAD: brak pudelek dla jazdy {ride}")
        return 2
    art_id = rows[0][6]
    day = rows[0][1].strftime("%Y-%m-%d")
    lats = [r[10] for r in rows if r[10] is not None]
    lons = [r[11] for r in rows if r[11] is not None]
    clat, clon = sum(lats)/len(lats), sum(lons)/len(lons)

    # 1. realna pogoda
    hourly, wsource = _fetch_actual(clat, clon, day)
    wx = {}  # frame_index -> (temp, precip, wspeed, wdir, tail)
    if hourly:
        from datetime import datetime
        for (fi, tmid, _p, _h, _v, _op, _aid, head, _g, _s, _la, _lo) in rows:
            key = tmid.strftime("%Y-%m-%dT%H")
            w = hourly.get(key) or hourly[min(hourly, key=lambda k: abs(datetime.strptime(k, "%Y-%m-%dT%H") - tmid.replace(tzinfo=None)))]
            tail, _c, rel = _rel_wind(head, w["wdir"], w["wspeed"])
            wx[fi] = (w["temp"], w["precip"], w["wspeed"], w["wdir"], rel, tail)
        if not dry_run:
            cur.execute("DELETE FROM qbot_v2.route_frame_weather WHERE route_artifact_id=%s AND frame_size_m=%s AND kind='actual'",
                        (art_id, int(frame_size)))
            for (fi, tmid, *_rest) in rows:
                if fi in wx:
                    t, p, ws, wd, rel, tail = wx[fi]
                    cur.execute(
                        "INSERT INTO qbot_v2.route_frame_weather (route_artifact_id, frame_size_m, frame_index, kind, "
                        "valid_at, temp_c, precip_mm, wind_speed_ms, wind_dir_from_deg, wind_rel_deg, wind_component_ms, source) "
                        "VALUES (%s,%s,%s,'actual',%s,%s,%s,%s,%s,%s,%s,%s)",
                        (art_id, int(frame_size), fi, tmid, t, p, ws, wd, rel, tail, wsource))
            conn.commit()

    # 2. wnioskowanie o wietrze: nadwyzka predkosci (po odjeciu mocy) vs wind_component, na plaskim
    flat = [(r[2], r[4], wx.get(r[0], (None,)*6)[5]) for r in rows
            if r[8] is not None and -1 <= r[8] <= 1 and r[2] and r[4]]
    wind_msg = "Wnioskowanie o wietrze: za malo danych."
    if len(flat) >= 10 and all(f[2] is not None for f in flat):
        pw = [f[0] for f in flat]; sp = [f[1] for f in flat]; wc = [f[2] for f in flat]
        slope_pw, inter_pw, _r1 = _linreg(pw, sp)  # predkosc ~ moc
        if slope_pw is not None:
            resid = [sp[i] - (inter_pw + slope_pw * pw[i]) for i in range(len(sp))]
            s2, _i2, r2 = _linreg(wc, resid)        # nadwyzka ~ wind_component
            if s2 is not None:
                per_ms = s2 * 3.6  # km/h na 1 m/s skladowej
                if abs(r2) >= 0.2 and per_ms > 0.1:
                    wind_msg = (f"Wnioskowanie o wietrze: na plaskim wiatr w plecy dodawal "
                                f"~{per_ms:.1f} km/h na kazdy 1 m/s skladowej (korelacja r={r2:.2f}). "
                                f"Czyli roznice tempa czesciowo tlumaczy wiatr, nie tylko forma.")
                else:
                    wind_msg = (f"Wnioskowanie o wietrze: brak wyraznego zwiazku predkosci z wiatrem "
                                f"(r={r2:.2f}) — tempo wynikalo glownie z mocy/terenu.")

    # 3. forma — ostatni pelny FTP
    cur.execute("SELECT day, ftp_est_w FROM qbot_v2.fitmodel_daily WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1")
    fr = cur.fetchone()
    ftp = float(fr[1]) if fr and fr[1] else None

    # agregaty jazdy
    powers = [r[2] for r in rows if r[2] is not None]
    speeds = [r[4] for r in rows if r[4] is not None]
    hrs = [r[3] for r in rows if r[3] is not None]
    off = sum(1 for r in rows if r[5])
    avg_pw = sum(powers)/len(powers) if powers else None
    avg_sp = sum(speeds)/len(speeds)*3.6 if speeds else None
    surf_m = {}
    for r in rows:
        surf_m[r[9] or "nieznana"] = surf_m.get(r[9] or "nieznana", 0) + 1
    top_surf = sorted(surf_m.items(), key=lambda kv: kv[1], reverse=True)[:3]

    print(f"🏁 WERDYKT JAZDY  ({ride[:40]}…, {day})")
    line = f"Przejechano {len(rows)} pudelek"
    if avg_pw:
        line += f" | śr. moc {avg_pw:.0f} W"
    if avg_sp:
        line += f" | śr. prędkość {avg_sp:.1f} km/h"
    if hrs:
        line += f" | śr. HR {sum(hrs)/len(hrs):.0f}"
    print(line)
    if ftp and avg_pw:
        intensity = avg_pw / ftp
        klas = ("regeneracyjna" if intensity < 0.55 else "tlenowa/wytrzymalosciowa" if intensity < 0.75
                else "tempo" if intensity < 0.9 else "progowa+")
        print(f"Forma (miarka): FTP {ftp:.0f} W → śr. moc to {intensity*100:.0f}% FTP = jazda {klas}.")
    elif not ftp:
        print("Forma: brak pelnego FTP — miarka niepelna.")
    print(f"Zgodnosc z planem: {len(rows)-off}/{len(rows)} pudelek na trasie, {off} poza planem.")
    surf_txt = ", ".join(f"{s} {m/len(rows)*100:.0f}%" for s, m in top_surf)
    print(f"Nawierzchnia (jechana): {surf_txt}")
    if hourly:
        temps = [wx[k][0] for k in wx if wx[k][0] is not None]
        if temps:
            print(f"Pogoda realna ({wsource}): {min(temps):.0f}–{max(temps):.0f}°C")
    print(wind_msg)

    if dry_run:
        print("[DRY-RUN] pogoda nie zapisana")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ride", type=str, default="latest")
    ap.add_argument("--frame-size", type=int, default=80)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(build(a.ride, a.frame_size, a.dry_run))


if __name__ == "__main__":
    main()
