#!/usr/bin/env python3
"""Generator bloku DATA raport-v2: dokłada chart.surface_cat (5 kategorii, model 2026-07-03)
czytany z route_surface_layer przez te SAME funkcje co endpoint /surface-categories
(qbot_web._load_surface_buckets + _coalesce_categories) -> zero rozjazdu logiki.

Uzycie:
  python build_raport_v2_surface_cat.py <route_id> [--write]
Bez --write: DRY-RUN (buduje i drukuje surface_cat, NIC nie zapisuje).
Z --write:  wstrzykuje "surface_cat":[...] do bloku DATA w web/public/raport-v2.html
            (addytywnie, przed istniejacym "surface"; reszta DATA nietknieta).
Deterministyczny przebieg DB->DATA (bez fetch w przegladarce, bez Overpass).
"""
import sys, os, glob, json, re, io

HTML_PATH = "/opt/qbot/web/public/raport-v2.html"

def _load_env():
    for envf in sorted(glob.glob("/etc/qbot/*.env")):
        for line in open(envf, encoding="utf-8"):
            st = line.strip()
            if st and not st.startswith("#") and "=" in st:
                k, v = st.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def build_surface_cat(route_id: str):
    _load_env()
    sys.path.insert(0, "/opt/qbot/app")
    from qbot_web import _db_conn, _load_surface_buckets, _coalesce_categories
    conn = _db_conn()
    try:
        base = conn.execute(
            "SELECT route_base_id FROM qbot_v2.route_base WHERE route_id=%s",
            (route_id,),
        ).fetchone()
        if not base:
            raise SystemExit(f"Trasa {route_id} nie znaleziona w route_base")
        rbid = base["route_base_id"]
        buckets = _load_surface_buckets(conn, rbid)
    finally:
        conn.close()
    ribbon = _coalesce_categories(buckets)
    cat = [{
        "a": round(float(r["km_from"]), 2),
        "b": round(float(r["km_to"]), 2),
        "k": r["category"],
        "label": r.get("label"),
        "reason": r.get("reason"),
    } for r in ribbon if r.get("category") is not None]
    return rbid, cat

def main():
    if len(sys.argv) < 2:
        raise SystemExit("uzycie: build_raport_v2_surface_cat.py <route_id> [--write]")
    route_id = sys.argv[1]
    do_write = "--write" in sys.argv[2:]
    rbid, cat = build_surface_cat(route_id)
    hist = {}
    for c in cat:
        hist[c["k"]] = round(hist.get(c["k"], 0.0) + (c["b"] - c["a"]), 2)
    print(f"route_id={route_id} rbid={rbid} | odcinkow wstazki={len(cat)} | km_by_cat={hist}")
    for c in cat[:4]:
        print("  ", c)
    if not do_write:
        print("DRY-RUN — nic nie zapisano. Dodaj --write aby wstrzyknac do raport-v2.html")
        return
    html = io.open(HTML_PATH, encoding="utf-8").read()
    payload = json.dumps(cat, ensure_ascii=False)
    if '"surface_cat"' in html:
        # podmien istniejacy
        html2 = re.sub(r'"surface_cat":\s*\[.*?\],\s*(?="surface")', f'"surface_cat": {payload}, ', html, count=1, flags=re.S)
        assert html2 != html, "nie udalo sie podmienic istniejacego surface_cat"
        html = html2
    else:
        anchor = ', "surface": ['
        assert html.count(anchor) == 1, f"kotwica {anchor!r} wystepuje {html.count(anchor)}x (oczekiwano 1)"
        html = html.replace(anchor, f', "surface_cat": {payload}, "surface": [', 1)
    io.open(HTML_PATH, "w", encoding="utf-8").write(html)
    print(f"OK wstrzyknieto surface_cat ({len(cat)} odc.) do {HTML_PATH} | bytes={os.path.getsize(HTML_PATH)}")

if __name__ == "__main__":
    main()
