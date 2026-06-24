#!/usr/bin/env python3
"""FAZA A — briefing planowanej trasy (czytelna analiza przed jazda).

Spina pudelka (route_frames) + prognoze (route_frame_weather) + forme (fitmodel_daily)
w plain-language podsumowanie: droga, nawierzchnia, podjazdy, pogoda, wiatr per km
(ktore kilometry w twarz), forma. Tylko ODCZYT.

Uzycie:
  .venv/bin/python -m tools.rwgps.route_brief --artifact-id 274
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2

PAVED = {"asfalt", "beton", "kostka brukowa", "concrete:plates"}


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


def _wind_stretches(rows, sign, thr=1.5, min_km=1.0):
    """Znajdz ciagle odcinki wiatru. sign=-1 w twarz, +1 w plecy."""
    out = []
    run_start = None
    last_dist = None
    for (_fi, d0, d1, _eg, _gr, _sf, _t, _p, comp, _ws) in rows:
        hit = comp is not None and ((sign < 0 and comp <= -thr) or (sign > 0 and comp >= thr))
        if hit and run_start is None:
            run_start = d0
        if not hit and run_start is not None:
            if (last_dist - run_start) / 1000.0 >= min_km:
                out.append((run_start / 1000.0, last_dist / 1000.0))
            run_start = None
        last_dist = d1
    if run_start is not None and (last_dist - run_start) / 1000.0 >= min_km:
        out.append((run_start / 1000.0, last_dist / 1000.0))
    return out


def build(artifact_id=None, route_id=None, frame_size=80):
    conn = _db_connect()
    cur = conn.cursor()
    where = "f.route_artifact_id=%s" if artifact_id is not None else "f.route_id=%s"
    key = artifact_id if artifact_id is not None else route_id
    cur.execute(
        f"SELECT f.frame_index, f.dist_start_m, f.dist_end_m, f.elev_gain_m, f.avg_grade_pct, f.surface, "
        f"       w.temp_c, w.precip_mm, w.wind_component_ms, w.wind_speed_ms "
        f"FROM qbot_v2.route_frames f "
        f"LEFT JOIN qbot_v2.route_frame_weather w "
        f"  ON w.route_artifact_id=f.route_artifact_id AND w.frame_size_m=f.frame_size_m "
        f"     AND w.frame_index=f.frame_index AND w.kind='forecast' "
        f"WHERE {where} AND f.frame_size_m=%s ORDER BY f.frame_index",
        (key, int(frame_size)),
    )
    rows = cur.fetchall()
    if not rows:
        print("Brak pudelek dla tej trasy — najpierw zbuduj siatke (route_frames).")
        return 2

    total_km = rows[-1][2] / 1000.0
    ascent = sum(r[3] for r in rows if r[3] and r[3] > 0)
    descent = -sum(r[3] for r in rows if r[3] and r[3] < 0)
    steep_m = sum((r[2] - r[1]) for r in rows if r[4] is not None and r[4] >= 4.0)
    max_grade = max((r[4] for r in rows if r[4] is not None), default=None)

    surf_m = {}
    for r in rows:
        seg = r[2] - r[1]
        surf_m[r[5] or "nieznana"] = surf_m.get(r[5] or "nieznana", 0.0) + seg
    paved_m = sum(m for s, m in surf_m.items() if s in PAVED)
    total_m = sum(surf_m.values()) or 1.0

    lines = []
    lines.append(f"📋 ANALIZA PLANOWANEJ TRASY")
    lines.append(f"Dystans: {total_km:.1f} km | podjazdy: +{ascent:.0f} m / zjazdy: -{descent:.0f} m")
    if max_grade is not None:
        lines.append(f"Stromizny: maks {max_grade:.0f}%, stromo (>=4%) na ~{steep_m/1000:.1f} km")
    top_surf = sorted(surf_m.items(), key=lambda kv: kv[1], reverse=True)[:3]
    surf_txt = ", ".join(f"{s} {m/total_m*100:.0f}%" for s, m in top_surf)
    lines.append(f"Nawierzchnia: {paved_m/total_m*100:.0f}% utwardzona | {surf_txt}")

    have_weather = any(r[6] is not None for r in rows)
    if have_weather:
        temps = [r[6] for r in rows if r[6] is not None]
        precip = sum(r[7] for r in rows if r[7] is not None)
        lines.append("")
        lines.append(f"🌤  Pogoda (prognoza): {min(temps):.0f}–{max(temps):.0f}°C, "
                     f"opady ~{precip:.1f} mm na trasie")
        head = _wind_stretches(rows, sign=-1)
        tail = _wind_stretches(rows, sign=+1)
        if head:
            txt = "; ".join(f"km {a:.0f}–{b:.0f}" for a, b in head)
            lines.append(f"   💨 Pod wiatr (oszczedzaj sie wczesniej): {txt}")
        if tail:
            txt = "; ".join(f"km {a:.0f}–{b:.0f}" for a, b in tail)
            lines.append(f"   🍃 Wiatr w plecy: {txt}")
        if not head and not tail:
            lines.append("   Wiatr slaby / zmienny — bez istotnych odcinkow.")
    else:
        lines.append("")
        lines.append("🌤  Pogoda: nie policzona — uruchom route_weather z data jazdy.")

    # forma — ostatni sensowny wiersz fitmodel_daily
    cur.execute("SELECT day, ftp_est_w, w_per_kg, glycogen_g, glycogen_pct "
                "FROM qbot_v2.fitmodel_daily WHERE ftp_est_w IS NOT NULL ORDER BY day DESC LIMIT 1")
    fr = cur.fetchone()
    lines.append("")
    if fr and fr[1]:
        day, ftp, wkg, gg, gpct = fr
        extra = f", glikogen {gg:.0f} g ({gpct:.0f}%)" if gg else ""
        lines.append(f"💪 Forma (FitModel, {day}): FTP {ftp:.0f} W"
                     + (f", {wkg:.2f} W/kg" if wkg else "") + extra)
        lines.append("   (wellness z dnia jazdy oceniany bedzie na miejscu)")
    else:
        lines.append("💪 Forma: brak swiezych danych FTP w FitModel — miarka niepelna.")

    print("\n".join(lines))
    return 0


def build_detail(artifact_id=None, route_id=None, frame_size=80, climb_grade=3.0, climb_min_m=200.0, land_cover=False):
    # FAZA A — SZCZEGOLOWY ale ZWIEZLY profil z ramek (mocno < 4000 znakow = limit relay Alberta). Tylko ODCZYT.
    conn = _db_connect()
    cur = conn.cursor()
    where = "route_artifact_id=%s" if artifact_id is not None else "route_id=%s"
    key = artifact_id if artifact_id is not None else route_id
    cur.execute(
        f"SELECT frame_index, dist_start_m, dist_end_m, ele_start_m, ele_end_m, elev_gain_m, avg_grade_pct, surface "
        f"FROM qbot_v2.route_frames WHERE {where} AND frame_size_m=%s ORDER BY frame_index",
        (key, int(frame_size)),
    )
    rows = cur.fetchall()
    if not rows:
        print("Brak pudelek dla tej trasy — najpierw zbuduj siatke (route_frames).")
        return 2
    _guess = _infer_unknown_frame_surfaces(rows, artifact_id, route_id, frame_size)
    total_km = rows[-1][2] / 1000.0
    ascent = sum(r[5] for r in rows if r[5] and r[5] > 0)
    descent = -sum(r[5] for r in rows if r[5] and r[5] < 0)
    grades = [r[6] for r in rows if r[6] is not None]
    max_grade = max(grades) if grades else 0.0
    steep_m = sum((r[2] - r[1]) for r in rows if r[6] is not None and r[6] >= 4.0)
    lines = []
    lines.append("SZCZEGOLOWY PROFIL TRASY (z ramek %d m)" % int(frame_size))
    lines.append("Dystans %.1f km | %d ramek | +%.0f m / -%.0f m | max %.0f%% | stromo(>=4%%) ~%.1f km" % (total_km, len(rows), ascent, descent, max_grade, steep_m/1000.0))
    if land_cover:
        try:
            from tools.rwgps.surface_landcover import build_sectors as _bs, annotate_sectors as _an, render_sectors_text as _rt
            _sectors = _bs(artifact_id=artifact_id, route_id=route_id, frame_size=int(frame_size))
            _an(_sectors, want_landcover=True, want_surface_cascade=True)
            lines.append("")
            lines.append("Nawierzchnia + pokrycie terenu (OSM):")
            lines.append(_rt(_sectors))
        except Exception:
            # fallback: zostaw dotychczasowy listing nawierzchni
            # --- Nawierzchnia odcinkami: scal sasiednie + absorbuj mikro-odcinki (kasuje szum "nieznana") ---
            merged = []
            for r in rows:
                surf = r[7] or _guess.get(r[0]) or "nieznana"
                if merged and merged[-1][2] == surf:
                    merged[-1][1] = r[2]
                else:
                    merged.append([r[1], r[2], surf])
            min_seg = 250.0
            cleaned = []
            for seg in merged:
                if cleaned and (seg[1] - seg[0]) < min_seg:
                    cleaned[-1][1] = seg[1]
                else:
                    cleaned.append([seg[0], seg[1], seg[2]])
            final = []
            for seg in cleaned:
                if final and final[-1][2] == seg[2]:
                    final[-1][1] = seg[1]
                else:
                    final.append(seg)
            lines.append("")
            lines.append("Nawierzchnia (odcinki >= %.1f km):" % (min_seg/1000.0))
            for s0, e0, surf in final:
                lines.append("  km %.1f-%.1f (%.1f): %s" % (s0/1000.0, e0/1000.0, (e0-s0)/1000.0, surf))
    else:
        # --- Nawierzchnia odcinkami: scal sasiednie + absorbuj mikro-odcinki (kasuje szum "nieznana") ---
        merged = []
        for r in rows:
            surf = r[7] or _guess.get(r[0]) or "nieznana"
            if merged and merged[-1][2] == surf:
                merged[-1][1] = r[2]
            else:
                merged.append([r[1], r[2], surf])
        min_seg = 250.0
        cleaned = []
        for seg in merged:
            if cleaned and (seg[1] - seg[0]) < min_seg:
                cleaned[-1][1] = seg[1]
            else:
                cleaned.append([seg[0], seg[1], seg[2]])
        final = []
        for seg in cleaned:
            if final and final[-1][2] == seg[2]:
                final[-1][1] = seg[1]
            else:
                final.append(seg)
        lines.append("")
        lines.append("Nawierzchnia (odcinki >= %.1f km):" % (min_seg/1000.0))
        for s0, e0, surf in final:
            lines.append("  km %.1f-%.1f (%.1f): %s" % (s0/1000.0, e0/1000.0, (e0-s0)/1000.0, surf))
    # --- Wysokosci: zwiezle, tylko km z istotna zmiana netto ---
    from collections import OrderedDict
    kmg = OrderedDict()
    for r in rows:
        b = int(r[1] // 1000)
        kmg.setdefault(b, 0.0)
        if r[5] is not None:
            kmg[b] += r[5]
    notable = [(b, g) for b, g in kmg.items() if abs(g) >= 6.0]
    lines.append("")
    lines.append("Wysokosci — kilometry z istotna zmiana netto (|>=6 m|):")
    if notable:
        for b, g in notable:
            lines.append("  km %d-%d: %+.0f m" % (b, b+1, g))
    else:
        lines.append("  brak — teren faluje w granicach kilku metrow na km (plasko)")
    # --- Podjazdy ---
    climbs = []
    run_s = None
    run_gain = 0.0
    run_gr = []
    last_d = None
    for r in rows:
        gr = r[6]
        up = gr is not None and gr >= climb_grade
        if up and run_s is None:
            run_s = r[1]
            run_gain = 0.0
            run_gr = []
        if up:
            run_gain += (r[5] or 0.0)
            run_gr.append(gr)
        if not up and run_s is not None:
            if (last_d - run_s) >= climb_min_m:
                climbs.append((run_s, last_d, run_gain, max(run_gr)))
            run_s = None
        last_d = r[2]
    if run_s is not None and run_gr and (last_d - run_s) >= climb_min_m:
        climbs.append((run_s, last_d, run_gain, max(run_gr)))
    lines.append("")
    lines.append("Podjazdy (>= %.0f%%, min %.0f m):" % (climb_grade, climb_min_m))
    if climbs:
        for s0, e0, g, mx in climbs:
            lines.append("  km %.1f-%.1f (%.1f km): +%.0f m, max %.0f%%" % (s0/1000.0, e0/1000.0, (e0-s0)/1000.0, g, mx))
    else:
        lines.append("  brak istotnych podjazdow — plasko")
    print("\n".join(lines))
    return 0


def _map_guess_to_frames(rows, sectors):
    """Mapuje surface_guess z sektorow OSM na ramki o NIEZNANEJ nawierzchni (po srodku ramki).
    rows: krotki route_frames (frame_index, dist_start_m, dist_end_m, ele_start_m, ele_end_m,
    elev_gain_m, avg_grade_pct, surface). Zwraca {frame_index: 'guess (szac.)'} tylko dla ramek
    bez wlasnej nawierzchni. Funkcja czysta (bez sieci) — testowalna."""
    guesses = [
        (float(s["s_m"]), float(s["e_m"]), s.get("surface_guess"))
        for s in sectors
        if s.get("surface_guess") and s.get("s_m") is not None and s.get("e_m") is not None
    ]
    out: dict = {}
    if not guesses:
        return out
    for r in rows:
        if r[7]:  # ramka ma wlasna nawierzchnie z OSM 'surface'
            continue
        mid = (float(r[1]) + float(r[2])) / 2.0
        for s0, e0, g in guesses:
            if s0 <= mid < e0:
                out[r[0]] = g
                break
    return out


def _infer_unknown_frame_surfaces(rows, artifact_id=None, route_id=None, frame_size=80):
    """Uzupelnia NIEZNANE nawierzchnie metoda map-match PUNKT PO PUNKCIE (TASK 14):
    dla kazdej nieznanej ramki pyta Overpass o droge wokol srodka ramki (mid_lat/mid_lon)
    i mapuje surface/typ drogi na etykiete PL z sufiksem '(szac.)'. Sieciowo TYLKO gdy istnieja
    nieznane ramki; przy kazdym bledzie zwraca {} (wtedy zostaje 'nieznana')."""
    unknown_idx = [r[0] for r in rows if r[7] in (None, "", "nieznana")]
    if not unknown_idx:
        return {}
    try:
        from tools.rwgps.surface_landcover import _fetch_highway_for_point
        conn = _db_connect()
        cur = conn.cursor()
        where = "route_artifact_id=%s" if artifact_id is not None else "route_id=%s"
        key = artifact_id if artifact_id is not None else route_id
        cur.execute(
            f"SELECT frame_index, mid_lat, mid_lon FROM qbot_v2.route_frames "
            f"WHERE {where} AND frame_size_m=%s AND frame_index = ANY(%s) ORDER BY frame_index",
            (key, int(frame_size), list(unknown_idx)),
        )
        coords = cur.fetchall()
        guesses: dict = {}
        for fi, mid_lat, mid_lon in coords:
            if mid_lat is None or mid_lon is None:
                continue
            label = _fetch_highway_for_point(float(mid_lat), float(mid_lon))
            if label:
                guesses[int(fi)] = label + " (szac.)"
        return guesses
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--artifact-id", type=int)
    g.add_argument("--route-id", type=str)
    ap.add_argument("--frame-size", type=int, default=80)
    a = ap.parse_args()
    sys.exit(build(a.artifact_id, a.route_id, a.frame_size))


if __name__ == "__main__":
    main()
