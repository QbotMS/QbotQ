"""route_xss_phys.py -- FIZYCZNY XSS PLANOWANEJ trasy (jedno zrodlo: planer + raport).
Modul-lisc: bez zaleznosci od qbot_web ani route_report_canonical (dane w argumentach).
Przeniesione bajt-w-bajt z qbot_web.py (Tor1 unifikacja XSS 2026-07-20):
_wind_clim_for_route, _estimate_route_xss_phys. Dodane: _build_route_sig, _route_physics_xss.
"""


def _wind_clim_for_route(conn, seg_in, month):
    """Klimatologia wiatru dla rejonu trasy w danym miesiacu (wielolecie ERA5,
    open-meteo archive). Zwraca (ws_efektywny_na_wysokosci_jezdzca, kierunek_z_ktorego).
    Cache w qbot_v2.route_wind_clim per (centroid~1km, miesiac). None gdy brak danych."""
    import math as _m, json as _j, urllib.request as _u, urllib.parse as _up, calendar as _cal
    WIND_FACTOR = 0.65   # 10 m -> ~1.5 m (wysokosc jezdzca)
    YEARS = [2023, 2024, 2025]
    lats = [float(s.get("mid_lat") or 0.0) for s in seg_in if s.get("mid_lat")]
    lons = [float(s.get("mid_lon") or 0.0) for s in seg_in if s.get("mid_lon")]
    if not lats or not lons:
        return None
    lat_k = round(sorted(lats)[len(lats) // 2], 2)
    lon_k = round(sorted(lons)[len(lons) // 2], 2)
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS qbot_v2.route_wind_clim(
            lat_key double precision, lon_key double precision, month int,
            mean_ws double precision, prevail_deg double precision,
            updated_at timestamptz DEFAULT now(),
            PRIMARY KEY(lat_key, lon_key, month))""")
        conn.commit()
        r = conn.execute("SELECT mean_ws, prevail_deg FROM qbot_v2.route_wind_clim "
                         "WHERE lat_key=%s AND lon_key=%s AND month=%s", (lat_k, lon_k, month)).fetchone()
        if r:
            return (float(r["mean_ws"]) * WIND_FACTOR, float(r["prevail_deg"]))
    except Exception:
        try: conn.rollback()
        except Exception: pass
    ARCH = "https://archive-api.open-meteo.com/v1/archive"
    ws_all = []; u = 0.0; vv = 0.0
    for y in YEARS:
        last = _cal.monthrange(y, month)[1]
        p = {"latitude": lat_k, "longitude": lon_k,
             "hourly": "wind_speed_10m,wind_direction_10m", "windspeed_unit": "ms",
             "timezone": "UTC", "start_date": "%04d-%02d-01" % (y, month),
             "end_date": "%04d-%02d-%02d" % (y, month, last)}
        try:
            req = _u.Request(ARCH + "?" + _up.urlencode(p), headers={"User-Agent": "QBot/1.0"})
            with _u.urlopen(req, timeout=25) as rr:
                d = _j.loads(rr.read().decode())
            h = d["hourly"]
            for sp, dr in zip(h["wind_speed_10m"], h["wind_direction_10m"]):
                if sp is None or dr is None:
                    continue
                ws_all.append(sp); u += sp * _m.sin(_m.radians(dr)); vv += sp * _m.cos(_m.radians(dr))
        except Exception:
            continue
    if not ws_all:
        return None
    mean_ws = sum(ws_all) / len(ws_all)
    prevail = (_m.degrees(_m.atan2(u, vv)) + 360) % 360
    try:
        conn.execute("""INSERT INTO qbot_v2.route_wind_clim(lat_key,lon_key,month,mean_ws,prevail_deg)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(lat_key,lon_key,month)
            DO UPDATE SET mean_ws=EXCLUDED.mean_ws, prevail_deg=EXCLUDED.prevail_deg, updated_at=now()""",
            (lat_k, lon_k, month, mean_ws, prevail))
        conn.commit()
    except Exception:
        try: conn.rollback()
        except Exception: pass
    return (mean_ws * WIND_FACTOR, prevail)


def _estimate_route_xss_phys(seg_in, sig, mass, mode="normalny", wind=None):
    """XSS PLANOWANEJ trasy z FIZYKI (bez IF, bez kotwic):
    per segment 50 m: predkosc v2 (segment_speed_kmh) -> moc z fizyki
    (grawitacja + toczenie z Crr wg nawierzchni + opor powietrza z WIATREM wg
    azymutu ramki; zjazd -> 0 = luz) -> prawdziwy compute_xss. Ta sama waluta co CTL.
    Zwalidowane: Castagneto 238/242 (1.7%), 12.07 gravel 325/328 (Crr 0.015)."""
    from datetime import datetime, timedelta
    import math as _m
    from qbot_route_time_tools import segment_speed_kmh, surface_class
    from fitmodel.modelq2.xss import compute_xss
    from tools.rwgps.route_weather import _rel_wind
    if sig is None or not seg_in:
        return None
    CRR = {"paved": 0.010, "unpaved": 0.018}   # kalibr. na jazdach: asfalt~0.010, gravel~0.018; nieznana->0.014
    RHO, CDA, EFF, G = 1.2, 0.4, 0.97, 9.81
    ws_eff = prevail = None
    if wind:
        ws_eff, prevail = wind
    lats = [float(s.get("mid_lat") or 0.0) for s in seg_in]
    lons = [float(s.get("mid_lon") or 0.0) for s in seg_in]
    n = len(seg_in)

    def _bearing(a1, o1, a2, o2):
        la1, lo1, la2, lo2 = map(_m.radians, [a1, o1, a2, o2]); dl = lo2 - lo1
        x = _m.sin(dl) * _m.cos(la2)
        y = _m.cos(la1) * _m.sin(la2) - _m.sin(la1) * _m.cos(la2) * _m.cos(dl)
        return (_m.degrees(_m.atan2(x, y)) + 360) % 360

    powers = []
    for i, s in enumerate(seg_in):
        ln = float(s.get("len_m") or 0.0)
        if ln <= 0:
            continue
        g = float(s.get("grade_pct") or 0.0)
        sc = s.get("surface")
        sc = sc if sc in ("paved", "unpaved") else surface_class(sc)
        crr = CRR.get(sc, 0.014)
        v = max(0.5, float(segment_speed_kmh(g, sc, mode)) / 3.6)
        tail = None
        if ws_eff and prevail is not None:
            j = min(n - 1, i + 3)
            if lats[i] and lats[j] and (lats[i] != lats[j] or lons[i] != lons[j]):
                hd = _bearing(lats[i], lons[i], lats[j], lons[j])
                tail, _cross, _delta = _rel_wind(hd, prevail, ws_eff)
        vair = v if tail is None else (v - tail)   # tail>0 = z tylu -> mniejsze czolo
        grav = mass * G * (g / 100.0) * v
        roll = mass * G * crr * v
        aero = 0.5 * RHO * CDA * vair * abs(vair) * v
        p = max(0.0, (grav + roll + aero) / EFF)
        dt = int(round(ln / v))
        if dt < 1:
            dt = 1
        powers.extend([p] * dt)
    if not powers:
        return None
    base = datetime(2020, 1, 1)
    rows = [(base + timedelta(seconds=i), powers[i]) for i in range(len(powers))]
    x = compute_xss(rows, sig)
    return x.low + x.high + x.peak


def _build_route_sig(conn, ftp, wprime_kj):
    """Signature MQ2 z FTP/W' + peak power (max mmp_1_w) z training_sessions. None gdy brak wejsc."""
    if not ftp or not wprime_kj:
        return None
    try:
        from fitmodel.modelq2.signature import Signature
        _pk = conn.execute("SELECT max(mmp_1_w) AS pp FROM qbot_v2.training_sessions "
                           "WHERE mmp_1_w IS NOT NULL").fetchone()
        _pp = float(_pk["pp"]) if (_pk and _pk.get("pp")) else float(ftp) * 2.5
        if _pp <= float(ftp):
            _pp = float(ftp) * 2.5
        return Signature.from_kj(float(ftp), float(wprime_kj), _pp)
    except Exception:
        return None


def _route_physics_xss(conn, route_id, ftp, wprime_kj, mass, mode="normalny", month=None):
    """Kanoniczny XSS PLANOWANEJ trasy z fizyki (siatka 50 m -> predkosc v2 -> moc -> compute_xss).
    Jedno zrodlo dla raportu trasy i planera. ftp/wprime_kj/mass podaje caller (bez zaleznosci od
    route_report_canonical). Zwraca float XSS albo None (brak siatki/sygnatury -> caller robi fallback)."""
    try:
        from qbot3.routes.route_segments_50m import load_canonical_segments_50m
    except Exception:
        return None
    try:
        out = load_canonical_segments_50m(route_id=str(route_id))
    except Exception:
        return None
    if not out or out.get("status") != "OK" or not out.get("segments"):
        return None
    segs = out["segments"]
    sig = _build_route_sig(conn, ftp, wprime_kj)
    if sig is None:
        return None
    try:
        _mass = float(mass) if mass else 100.0
    except Exception:
        _mass = 100.0
    wind = None
    if month:
        try:
            wind = _wind_clim_for_route(conn, segs, int(month))
        except Exception:
            wind = None
    return _estimate_route_xss_phys(segs, sig, _mass, mode, wind)
