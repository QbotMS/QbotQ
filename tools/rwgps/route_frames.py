#!/usr/bin/env python3
"""FAZA A — budowa siatki pudelek (~80 m) z trasy planowanej RWGPS.

Czyta GPX trasy (route_artifacts.artifact_path), RESAMPLUJE slad na rowne
pudelka stalej dlugosci (interpolacja na granicach), liczy per pudelko:
nachylenie, kierunek jazdy (heading), wspolrzedne; naklada nawierzchnie z
qbot_v2.route_surface_segments (najblizszy segment). Zapis do qbot_v2.route_frames.

Uzycie:
  .venv/bin/python -m tools.rwgps.route_frames --artifact-id 278 [--frame-size 80] [--dry-run] [--show 8]
  .venv/bin/python -m tools.rwgps.route_frames --route-id 55559108

Buduje OBOK starej tasmy G (nic nie nadpisuje w starym stacku).
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2

BUILDER_VERSION = "route_frames-v2"


def _load_env_local() -> None:
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
    kwargs = {
        "host": os.getenv("PGHOST", "127.0.0.1"),
        "port": int(os.getenv("PGPORT", "5432")),
        "user": os.getenv("PGUSER", "qbot"),
        "dbname": os.getenv("PGDATABASE", "qbot"),
    }
    pw = os.getenv("PGPASSWORD")
    if pw:
        kwargs["password"] = pw
    return psycopg2.connect(**kwargs)


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _bearing(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _interp(a, b, t):
    la = a[0] + t * (b[0] - a[0])
    lo = a[1] + t * (b[1] - a[1])
    if a[2] is None or b[2] is None:
        el = a[2] if a[2] is not None else b[2]
    else:
        el = a[2] + t * (b[2] - a[2])
    return (la, lo, el)


def _parse_gpx(path: str):
    pts = []
    for _ev, el in ET.iterparse(path, events=("end",)):
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("trkpt", "rtept"):
            try:
                lat = float(el.get("lat"))
                lon = float(el.get("lon"))
            except (TypeError, ValueError):
                el.clear()
                continue
            ele = None
            for ch in el:
                if ch.tag.rsplit("}", 1)[-1] == "ele" and ch.text:
                    try:
                        ele = float(ch.text)
                    except ValueError:
                        ele = None
            pts.append((lat, lon, ele))
            el.clear()
    return pts


def _build_frames(pts, frame_size: float):
    """Resampluje slad na rowne granice co frame_size (interpolacja) i tworzy pudelka."""
    if len(pts) < 2:
        return [], 0.0
    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + _haversine(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]))
    total = cum[-1]

    # punkty na rownych granicach: 0, fs, 2fs, ... + koncowy
    bounds = [pts[0]]
    bound_dist = [0.0]
    target = frame_size
    i = 1
    while target < total and i < len(pts):
        while i < len(pts) and cum[i] < target:
            i += 1
        if i >= len(pts):
            break
        seg_len = cum[i] - cum[i - 1]
        t = (target - cum[i - 1]) / seg_len if seg_len > 0 else 0.0
        bounds.append(_interp(pts[i - 1], pts[i], t))
        bound_dist.append(target)
        target += frame_size
    if bounds[-1][:2] != pts[-1][:2]:
        bounds.append(pts[-1])
        bound_dist.append(total)

    frames = []
    for j in range(1, len(bounds)):
        s, e = bounds[j - 1], bounds[j]
        seg_len = bound_dist[j] - bound_dist[j - 1]
        ele_s, ele_e = s[2], e[2]
        gain = (ele_e - ele_s) if (ele_s is not None and ele_e is not None) else None
        grade = (gain / seg_len * 100.0) if (gain is not None and seg_len > 0) else None
        mid = _interp(s, e, 0.5)
        frames.append({
            "frame_index": j - 1,
            "dist_start_m": bound_dist[j - 1], "dist_end_m": bound_dist[j], "frame_len_m": seg_len,
            "start_lat": s[0], "start_lon": s[1],
            "mid_lat": mid[0], "mid_lon": mid[1],
            "end_lat": e[0], "end_lon": e[1],
            "ele_start_m": ele_s, "ele_end_m": ele_e,
            "elev_gain_m": gain, "avg_grade_pct": grade,
            "heading_deg": _bearing(s[0], s[1], e[0], e[1]),
        })
    return frames, total


def _load_surface_segments(cur, route_id: str):
    cur.execute(
        "SELECT s.surface, s.confidence, s.start_lat, s.start_lon, s.end_lat, s.end_lon "
        "FROM qbot_v2.route_surface_segments s "
        "JOIN qbot_v2.route_surface_profiles p ON p.id = s.route_surface_profile_id "
        "JOIN qbot_v2.route_artifacts a ON a.id = p.route_artifact_id "
        "WHERE a.route_id = %s ORDER BY p.enriched_at DESC, s.segment_index",
        (route_id,),
    )
    segs = []
    for surf, conf, sla, slo, ela, elo in cur.fetchall():
        if sla is None or slo is None:
            continue
        mla = (sla + ela) / 2 if ela is not None else sla
        mlo = (slo + elo) / 2 if elo is not None else slo
        segs.append((mla, mlo, surf, conf))
    return segs


def _assign_surface(frame, segs):
    if not segs:
        return None, None
    fm_la, fm_lo = frame["mid_lat"], frame["mid_lon"]
    best, best_d = None, float("inf")
    for mla, mlo, surf, conf in segs:
        d = _haversine(fm_la, fm_lo, mla, mlo)
        if d < best_d:
            best_d, best = d, (surf, conf)
    return best if best else (None, None)


def build(artifact_id=None, route_id=None, frame_size=80.0, dry_run=False, show=0):
    conn = _db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    if artifact_id is not None:
        cur.execute("SELECT id, route_id, artifact_path FROM qbot_v2.route_artifacts WHERE id=%s", (artifact_id,))
    else:
        cur.execute(
            "SELECT id, route_id, artifact_path FROM qbot_v2.route_artifacts "
            "WHERE route_id=%s AND export_format='gpx_track' ORDER BY id DESC LIMIT 1",
            (route_id,),
        )
    row = cur.fetchone()
    if not row:
        print("BLAD: nie znaleziono route_artifacts dla podanego klucza")
        return 2
    art_id, rid, path = row
    if not path or not os.path.exists(path):
        print(f"BLAD: brak pliku GPX na dysku: {path}")
        return 2

    pts = _parse_gpx(path)
    frames, total = _build_frames(pts, frame_size)
    if not frames:
        print(f"BLAD: za malo punktow w GPX ({len(pts)})")
        return 2

    segs = _load_surface_segments(cur, rid)
    surf_hits = 0
    for fr in frames:
        s, c = _assign_surface(fr, segs)
        fr["surface"], fr["surface_confidence"] = s, c
        if s:
            surf_hits += 1

    lens = [f["frame_len_m"] for f in frames]
    grades = [f["avg_grade_pct"] for f in frames if f["avg_grade_pct"] is not None]
    print(f"Trasa route_id={rid} artifact_id={art_id}")
    print(f"  punkty GPX: {len(pts)} | dlugosc: {total/1000:.2f} km | pudelka ({int(frame_size)}m): {len(frames)}")
    print(f"  dlugosc pudelka: min {min(lens):.0f}m  max {max(lens):.0f}m  sr {sum(lens)/len(lens):.0f}m")
    print(f"  nawierzchnia: {len(segs)} segmentow zrodlowych, dopasowano do {surf_hits}/{len(frames)} pudelek")
    if grades:
        print(f"  nachylenie: min {min(grades):.1f}%  max {max(grades):.1f}%  sr {sum(grades)/len(grades):.2f}%")
    if show:
        print(f"  --- pierwsze {show} pudelek ---")
        for fr in frames[:show]:
            g = f"{fr['avg_grade_pct']:.1f}%" if fr["avg_grade_pct"] is not None else "n/a"
            print(f"   #{fr['frame_index']:>3} {fr['dist_start_m']:.0f}-{fr['dist_end_m']:.0f}m "
                  f"len={fr['frame_len_m']:.0f} grade={g} head={fr['heading_deg']:.0f} surf={fr['surface']}")

    if dry_run:
        print("  [DRY-RUN] nie zapisuje do bazy")
        conn.rollback()
        return 0

    cur.execute("DELETE FROM qbot_v2.route_frames WHERE route_artifact_id=%s AND frame_size_m=%s",
                (art_id, int(frame_size)))
    for fr in frames:
        cur.execute(
            "INSERT INTO qbot_v2.route_frames "
            "(route_artifact_id, route_id, frame_size_m, frame_index, dist_start_m, dist_end_m, frame_len_m, "
            " start_lat, start_lon, mid_lat, mid_lon, end_lat, end_lon, ele_start_m, ele_end_m, elev_gain_m, "
            " avg_grade_pct, heading_deg, surface, surface_confidence, builder_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (art_id, rid, int(frame_size), fr["frame_index"], fr["dist_start_m"], fr["dist_end_m"], fr["frame_len_m"],
             fr["start_lat"], fr["start_lon"], fr["mid_lat"], fr["mid_lon"], fr["end_lat"], fr["end_lon"],
             fr["ele_start_m"], fr["ele_end_m"], fr["elev_gain_m"], fr["avg_grade_pct"], fr["heading_deg"],
             fr["surface"], fr["surface_confidence"], BUILDER_VERSION),
        )
    conn.commit()
    print(f"  ZAPISANO {len(frames)} pudelek do qbot_v2.route_frames")
    return 0


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--artifact-id", type=int)
    g.add_argument("--route-id", type=str)
    ap.add_argument("--frame-size", type=float, default=80.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    sys.exit(build(a.artifact_id, a.route_id, a.frame_size, a.dry_run, a.show))


if __name__ == "__main__":
    main()
