import csv as _csv
import math
import os
import xml.etree.ElementTree as ET

ARTIFACTS_ROOT = "/opt/qbot/artifacts"
GPX_DIR = os.path.join(ARTIFACTS_ROOT, "exports", "rwgps")

def _haversine_m(la1, lo1, la2, lo2):
    R = 6371000.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def _read_gpx_points(gpx_path):
    pts = []
    for el in ET.parse(gpx_path).getroot().iter():
        if el.tag.split('}')[-1] != "trkpt":
            continue
        lat, lon = float(el.get("lat")), float(el.get("lon"))
        ele = 0.0
        for ch in el:
            if ch.tag.split('}')[-1] == "ele" and ch.text:
                ele = float(ch.text); break
        pts.append((lat, lon, ele))
    return pts

def _smooth(ele, w=5):
    if w < 3 or len(ele) < w:
        return ele
    half = w // 2
    out = []
    for i in range(len(ele)):
        lo = max(0, i - half)
        hi = min(len(ele), i + half + 1)
        out.append(sum(ele[lo:hi]) / (hi - lo))
    return out

def build_profile_segments(gpx_path, km_from=0.0, km_to=None,
                           sample_m=100.0, grade_min_run_m=40.0, ele_smooth_window=5):
    pts = _read_gpx_points(gpx_path)
    if len(pts) < 2:
        raise ValueError("GPX < 2 punkty")
    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + _haversine_m(pts[i-1][0], pts[i-1][1],
                                          pts[i][0], pts[i][1]))
    ele = _smooth([p[2] for p in pts], ele_smooth_window)
    total_m = cum[-1]

    def interp(d):
        if d <= cum[0]: return ele[0]
        if d >= cum[-1]: return ele[-1]
        lo, hi = 0, len(cum) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if cum[mid] <= d: lo = mid
            else: hi = mid
        span = cum[hi] - cum[lo]
        f = 0.0 if span <= 0 else (d - cum[lo]) / span
        return ele[lo] + f * (ele[hi] - ele[lo])

    start_m = max(0.0, km_from * 1000.0)
    end_m = total_m if km_to is None else min(total_m, km_to * 1000.0)
    segs, s0 = [], start_m
    while s0 < end_m - 1e-6:
        s1 = min(s0 + sample_m, end_m)
        e0, e1 = interp(s0), interp(s1)
        run = s1 - s0
        prof = [(s0, e0)] + [(cum[i], ele[i]) for i in range(len(cum))
                             if s0 < cum[i] < s1] + [(s1, e1)]
        gain = loss = 0.0
        for i in range(1, len(prof)):
            de = prof[i][1] - prof[i-1][1]
            gain += de if de > 0 else 0.0
            loss += -de if de < 0 else 0.0
        maxg, n = None, len(prof)
        for a in range(n):
            b = a + 1
            while b < n and (prof[b][0] - prof[a][0]) < grade_min_run_m:
                b += 1
            if b < n:
                rr = prof[b][0] - prof[a][0]
                if rr > 0:
                    g = (prof[b][1] - prof[a][1]) / rr * 100.0
                    if maxg is None or g > maxg: maxg = g
        avg = (e1 - e0) / run * 100.0 if run > 0 else 0.0
        if maxg is None: maxg = avg
        segs.append({
            "km_start": round(s0/1000.0, 3), "km_end": round(s1/1000.0, 3),
            "ele_start": round(e0, 1), "ele_end": round(e1, 1),
            "delta_m": round(e1 - e0, 1),
            "gain_m": round(gain, 1), "loss_m": round(loss, 1),
            "avg_grade_pct": round(avg, 1), "max_grade_pct": round(maxg, 1),
        })
        s0 = s1
    return segs, total_m

_COLS = ["km_start","km_end","ele_start","ele_end","delta_m",
         "gain_m","loss_m","avg_grade_pct","max_grade_pct"]

def write_csv(segs, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=_COLS)
        w.writeheader()
        for s in segs: w.writerow(s)

def write_markdown(segs, path, route_id, total_m):
    gain = sum(s["gain_m"] for s in segs)
    loss = sum(s["loss_m"] for s in segs)
    mx = max((s["max_grade_pct"] for s in segs), default=0.0)
    lines = [
        "# RWGPS %s -- profil co 100 m" % route_id, "",
        "- segmenty: %d" % len(segs),
        "- dystans: %.2f km" % (total_m/1000.0),
        "- gain: %.0f m | loss: %.0f m | max grade: %.1f%%" % (gain, loss, mx),
        "",
        "| km_start | km_end | ele0 | ele1 | delta | gain | loss | avg% | max% |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in segs:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            s["km_start"], s["km_end"], s["ele_start"], s["ele_end"],
            s["delta_m"], s["gain_m"], s["loss_m"],
            s["avg_grade_pct"], s["max_grade_pct"]))
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

def export_route_profile_csv(route_id, project_id="tuscany_2026",
                             km_from=0.0, km_to=None, sample_m=100.0,
                             gpx_path=None, artifact_store=None):
    if gpx_path is None:
        gpx_path = os.path.join(GPX_DIR, "rwgps_%s.gpx" % route_id)
    if not os.path.exists(gpx_path):
        raise FileNotFoundError(gpx_path)
    out_dir = os.path.join(ARTIFACTS_ROOT, "projects", str(project_id))
    os.makedirs(out_dir, exist_ok=True)
    base = "rwgps_%s_profile_%dm" % (route_id, int(sample_m))
    csv_path = os.path.join(out_dir, base + ".csv")
    md_path = os.path.join(out_dir, base + ".md")
    segs, total_m = build_profile_segments(gpx_path, km_from, km_to, sample_m)
    write_csv(segs, csv_path)
    write_markdown(segs, md_path, route_id, total_m)
    meta = {
        "route_id": route_id, "project_id": project_id,
        "csv_path": csv_path, "md_path": md_path,
        "segment_count": len(segs),
        "total_gain": round(sum(s["gain_m"] for s in segs), 1),
        "total_loss": round(sum(s["loss_m"] for s in segs), 1),
        "max_grade": max((s["max_grade_pct"] for s in segs), default=0.0),
        "total_km": round(total_m/1000.0, 2),
        "artifact_id": {},
    }
    if artifact_store is not None:
        for fmt, path, mime in [("csv", csv_path, "text/csv"),
                                ("md", md_path, "text/markdown")]:
            artifact_id = artifact_store.register(
                project_id=project_id, artifact_type="export",
                title="RWGPS %s profile %dm" % (route_id, int(sample_m)),
                filename=os.path.basename(path),
                file_path=os.path.relpath(path, ARTIFACTS_ROOT),
                mime_type=mime,
            )
            if artifact_id:
                meta["artifact_id"][fmt] = artifact_id
    return meta
