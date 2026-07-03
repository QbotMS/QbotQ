"""qbot-web - publiczny serwis HTML (Faza 1: statyczna strona + proste API tras)."""
import os
import json
import urllib.request
import psycopg
from psycopg.rows import dict_row
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

WEB_ROOT = os.environ.get("QBOT_WEB_ROOT", "/opt/qbot/web/public")
HOST = os.environ.get("QBOT_WEB_HOST", "0.0.0.0")
PORT = int(os.environ.get("QBOT_WEB_PORT", "30181"))
VALHALLA_ROUTE = "https://valhalla1.openstreetmap.de/route"
VALHALLA_TRACE_ATTRIBUTES = "https://valhalla1.openstreetmap.de/trace_attributes"
RISKY_GAP_MERGE_KM = 0.2  # ryzykowne odcinki oddzielone krotszym "dobrym" proseckiem laczymy w jeden
MIN_RISKY_SEGMENT_KM = 0.2  # ponizej tej dlugosci NIE zglaszamy jako osobny alert (szum/mikro-fragmenty)
VALHALLA_RISKY_SURFACES = {"dirt", "path", "impassable"}
VALHALLA_GOOD_SURFACES = {"paved_smooth", "paved", "compacted", "gravel"}
DEFAULT_ANCHOR_BUFFER_KM = 0.3  # jak daleko cofamy punkty startu/konca objazdu w dobra nawierzchnie
ESCALATION_BUFFERS_KM = [0.3, 1.0, 2.0, 3.0]  # promienie probkowania - patrz UWAGA #6 nizej
REPLACED_LENGTH_MAX_RATIO = 1.15  # kandydat nie moze byc dluzszy niz 115% dlugosci ZASTEPOWANEGO oryginalnego odcinka (miedzy kotwicami) - "na potrzeby sprawdzenia" wg ustalen 2026-07-01
# UWAGA architektoniczna (2026-07-01, wersja 4 - reguła "A wygrywa"):
# Eskalacja do 0.75/1.5/3km zostala WYCOFANA. Dowod (trasa 55798129, segment 4):
# przy szerokim buforze objazd porzucal fragmenty trasy, ktorych System A
# (route_surface_layer, tagi OSM) NIGDY nie oznaczyl jako ryzykowne, bo System B
# (wewnetrzny model nawierzchni Valhalli) ocenial te same "dobre" fragmenty jako
# w duzej mierze "dirt" (zweryfikowane trace_attributes: 60% dirt na odcinku,
# ktory System A klasyfikuje w 53% jako jawnie otagowany OSM z realnym dirt=1%).
# Rozjazd dwoch niezaleznych systemow oceny nawierzchni oznacza, ze pozwalanie
# Valhalli szukac szeroko = pozwalanie jej przepisywac trase wg INNEGO kanonu
# niz ten, ktory napedza raport i alerty. Zasada: objazd wolno ruszac WYLACZNIE
# w obrebie strefy, ktora System A oznaczyl jako ryzykowna - reszta trasy
# przypieta na sztywno. Stad tylko jeden, minimalny bufor (0.3km) - czysto
# techniczny margines do zaczepienia geometrii, nie przestrzen poszukiwan.
# Konsekwencja: czesc odcinkow, ktore wczesniej "udalo sie naprawic" dzieki
# szerokiemu buforowi (np. segmenty 4, 5, 17 na trasie testowej), wroca do
# statusu "brak realnej alternatywy" - swiadomy kompromis: mniej "sukcesow",
# ale zaden z nich nie bedzie fałszywy.
#
# UWAGA #5 (2026-07-01, korekta po feedbacku): calkowite wylaczenie eskalacji
# okazalo sie za bardzo zachowawcze - odcinek ktory mial oczywisty, bliski
# asfalt (dawny segment 17/18, 67.05-68.35km) przestal go w ogole probowac
# znalezc, bo asfalt byl osiagalny dopiero przy buforze 1.0km (0.3km: 80% dirt,
# 1.0km: 70% paved_smooth).
#
# UWAGA #6 (2026-07-01, "nie tepe jak pruski kapral"): sztywny sufit promienia
# (1.0km) to wciaz slepe zgadywanie - albo trafi w tym limicie, albo poddaje sie
# bez wzgledu na to jak blisko sukcesu bylo. WRACAMY do szerokiego zakresu
# probkowania (0.3/1.0/2.0/3.0km) bez zadnego limitu dlugosci per-kandydat.
#
# UWAGA #7 (2026-07-01, doprecyzowanie): probowano dodac limit proporcji
# dlugosci (candidate_km vs replaced_km) i zostal COFNIETY - nieporozumienie.
# Uzytkownik jasno: dlugi objazd (nawet 10km) jest OK, jesli prowadzi dobra
# nawierzchnia - jedyny akceptowalny cap to calkowita dlugosc CALEJ TRASY
# (nie pojedynczego kandydata), i to jest osobne, PRZYSZLE zadanie, nie teraz.
# Dzis jedynym kryterium akceptacji kandydata jest still_risky=False.
# replaced_km jest nadal zwracane w odpowiedzi (przejrzystosc - ile oryginalnej
# trasy miedzy kotwicami dany kandydat obejmuje), ale NIE wplywa na wybor ani
# na flage no_real_alternative. Stala REPLACED_LENGTH_MAX_RATIO ponizej NIE
# jest juz uzywana w logice - zostawiona jako udokumentowany, swiadomy false
# start na wypadek gdyby przyszly cap-na-cala-trase mial z niej korzystac.

app = FastAPI(title="qbot-web", docs_url=None, redoc_url=None)


def _env():
    env = {}
    for ef in ["/opt/qbot/app/.env", "/opt/qbot/app/.env.local", "/etc/qbot/qbot-api.env"]:
        try:
            for line in open(ef):
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env[k] = v
        except Exception:
            pass
    return env


def _db_conn():
    e = _env()
    return psycopg.connect(
        host=os.getenv("PGHOST", e.get("PGHOST", "127.0.0.1")),
        port=os.getenv("PGPORT", e.get("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", e.get("PGDATABASE", "qbot")),
        user=os.getenv("PGUSER", e.get("PGUSER", "qbot")),
        password=os.getenv("PGPASSWORD", e.get("PGPASSWORD", "")),
        row_factory=dict_row,
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/routes/ready")
def routes_ready():
    """Trasy z routes store, dla ktorych etap nawierzchni jest w pelni policzony (Wariant A)."""
    conn = _db_conn()
    try:
        rows = conn.execute(
            """
            SELECT route_id, distance_m, name, finished_at FROM (
                SELECT DISTINCT ON (rb.route_id) rb.route_id, rb.distance_m,
                       a.metadata_json->>'route_name' AS name,
                       j.finished_at
                FROM qbot_v2.route_base rb
                JOIN qbot_v2.route_precompute_jobs j
                    ON j.route_base_id = rb.route_base_id
                   AND j.job_type = 'route_surface'
                   AND j.status = 'complete'
                LEFT JOIN qbot_v2.route_artifacts a ON a.id = rb.route_artifact_id
                ORDER BY rb.route_id, j.finished_at DESC
            ) t ORDER BY finished_at DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return {
        "routes": [
            {
                "route_id": r["route_id"],
                "name": r.get("name") or f"Trasa {r['route_id']}",
                "distance_km": round((r["distance_m"] or 0) / 1000, 1),
            }
            for r in rows
        ]
    }


@app.get("/api/routes/{route_id}/geometry")
def route_geometry(route_id: str):
    """Przebieg trasy (lat/lon) z route_axis_segments, do narysowania na mapie."""
    conn = _db_conn()
    try:
        base = conn.execute(
            """
            SELECT rb.route_base_id, rb.distance_m,
                   a.metadata_json->>'route_name' AS name
            FROM qbot_v2.route_base rb
            LEFT JOIN qbot_v2.route_artifacts a ON a.id = rb.route_artifact_id
            WHERE rb.route_id = %s
            ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1
            """,
            (route_id,),
        ).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
        segs = conn.execute(
            """
            SELECT segment_index, segment_geojson
            FROM qbot_v2.route_axis_segments
            WHERE route_base_id = %s
            ORDER BY segment_index
            """,
            (base["route_base_id"],),
        ).fetchall()
    finally:
        conn.close()

    coords: list[list[float]] = []
    for s in segs:
        geo = s["segment_geojson"] or {}
        for pt in geo.get("coordinates", []):
            lon, lat = pt[0], pt[1]
            latlon = [round(lat, 6), round(lon, 6)]
            if not coords or coords[-1] != latlon:
                coords.append(latlon)

    return {
        "route_id": route_id,
        "name": base.get("name") or f"Trasa {route_id}",
        "distance_km": round((base["distance_m"] or 0) / 1000, 1),
        "coordinates": coords,
    }


_PROBLEM_SURFACES = {"ground", "grass", "sand", "unknown", "unpaved"}
_OK_STATUSES = {"GOOD", "GOOD_INFERRED"}


def _load_surface_buckets(conn, route_base_id: int) -> list[dict]:
    """Odcinki nawierzchni (km_from/km_to z surface_meta_json) posortowane po km.

    UWAGA architektoniczna (2026-07-01): route_axis_segments (50m, ~1423 wierszy)
    i route_surface_layer (OSM way-segmenty, ~76 wierszy) maja NIEZALEZNA numeracje
    segment_index - to NIE jest ten sam podzial trasy. Jedyny wspolny klucz to
    kilometraz, dlatego dopasowanie idzie po km_from/km_to, nigdy po segment_index.
    """
    rows = conn.execute(
        """
        SELECT surface, highway, tracktype, coverage_status, confidence, surface_meta_json
        FROM qbot_v2.route_surface_layer
        WHERE route_base_id = %s
        ORDER BY segment_index
        """,
        (route_base_id,),
    ).fetchall()
    buckets = []
    for r in rows:
        meta = r.get("surface_meta_json") or {}
        try:
            km_from = float(meta.get("km_from"))
            km_to = float(meta.get("km_to"))
        except (TypeError, ValueError):
            continue
        surface = (r.get("surface") or "unknown").lower()
        coverage = r.get("coverage_status")
        highway = r.get("highway")
        tracktype = r.get("tracktype")
        # UWAGA (2026-07-01, regula "przyzwoity grade"): dla drog typu "track"
        # tracktype grade1-4 ZAWSZE wygrywa nad wywnioskowana etykieta "surface"
        # (ground/grass) - dowod na trasie testowej: 3 odcinki mialy jawny tag
        # tracktype=grade4 (przyzwoita, srednia droga gruntowa), a mimo to
        # wpadaly do "ryzykowne" tylko dlatego, ze surface wyszlo jako ground/
        # grass. Ryzykowne zostaje wylacznie: brak tracktype (None) LUB grade5.
        # Dla drog innych niz "track" (gdzie tracktype nie ma zastosowania)
        # zasada bez zmian - decyduje surface + coverage_status jak dotychczas.
        if highway == "track" and tracktype in {"grade1", "grade2", "grade3", "grade4"}:
            risky = False
        else:
            risky = surface in _PROBLEM_SURFACES or coverage not in _OK_STATUSES
        buckets.append({
            "km_from": km_from,
            "km_to": km_to,
            "risky": risky,
            "surface": surface,
            "surface_raw": meta.get("surface_raw") or surface,
            "coverage_status": coverage,
            "confidence": r.get("confidence"),
            "explanation": meta.get("explanation") or "",
            "highway": highway,
            "tracktype": tracktype,
            "surface_category": meta.get("surface_category"),
            "surface_category_label": meta.get("surface_category_label"),
            "surface_category_reason": meta.get("surface_category_reason"),
        })
    buckets.sort(key=lambda b: b["km_from"])
    return buckets


def _bucket_for_km(buckets: list[dict], km_mid: float) -> dict | None:
    for b in buckets:
        if b["km_from"] <= km_mid < b["km_to"]:
            return b
    return None


_SURFACE_LABEL_PL = {
    "asphalt": "asfalt",
    "paved": "nawierzchnia utwardzona",
    "paved_smooth": "gladki asfalt",
    "concrete": "beton",
    "paving_stones": "kostka brukowa",
    "compacted": "ubita nawierzchnia (dobra)",
    "gravel": "zwir",
    "fine_gravel": "drobny zwir",
    "dirt": "ubita ziemia / droga gruntowa",
    "ground": "goly grunt",
    "grass": "trawa",
    "sand": "piasek",
    "mixed": "nawierzchnia mieszana",
    "unpaved": "nieutwardzona",
    "path": "waska sciezka",
    "impassable": "nieprzejezdna",
    "unknown": "nieznana nawierzchnia",
}


def _surface_label_pl(surface: str | None) -> str:
    if not surface:
        return "nieznana nawierzchnia"
    return _SURFACE_LABEL_PL.get(surface.lower(), surface)


def _human_reason(b: dict | None) -> str:
    """Tlumaczy techniczny opis nawierzchni (tagi OSM, heurystyki) na zdanie
    po polsku - zbudowane na bazie realnych wzorcow explanation wystepujacych
    w danych (sprawdzone zapytaniem do route_surface_layer, nie zgadywane)."""
    if b is None:
        return "Brak danych o nawierzchni dla tego miejsca - z ostroznosci uznane za ryzykowne."
    surface = b.get("surface_raw") or b.get("surface") or "unknown"
    label = _surface_label_pl(surface)
    explanation = (b.get("explanation") or "").strip()
    confidence = b.get("confidence") or "brak"
    conf_pl = {"low": "niska", "medium": "srednia", "high": "wysoka"}.get(confidence, confidence)

    if "explicit OSM surface tag" in explanation:
        base = f"Nawierzchnia wprost oznaczona w danych OSM jako: {label}."
    elif "highway=track without surface/tracktype" in explanation:
        base = "Droga gruntowa (lesna/polna) bez podanej w OSM informacji o nawierzchni."
    elif "highway=path without surface" in explanation:
        base = "Waska sciezka bez podanej w OSM informacji o nawierzchni."
    elif "tracktype=grade5" in explanation:
        base = "Najgorsza klasa drogi gruntowej (grade 5) - zwykle blotnista, trawiasta lub piaszczysta."
    elif "tracktype=grade4" in explanation:
        base = "Slaba klasa drogi gruntowej (grade 4) - ziemia, trawa lub luzna nawierzchnia."
    elif "tracktype=grade3" in explanation:
        base = "Srednia klasa drogi gruntowej (grade 3) - zwykle zwir lub ubita ziemia."
    else:
        base = f"Nawierzchnia: {label}."

    if "sand_loose_ground_possible" in explanation:
        base += " W tej okolicy dodatkowo mozliwy piasek lub luzny grunt (wniosek z geologii terenu, nie z samego OSM)."

    return f"{base} Pewnosc oceny: {conf_pl}."


def _weighted_breakdown_pl(buckets: list[dict], km_from: float, km_to: float) -> list[dict]:
    """Rozklad nawierzchni ORYGINALNEGO odcinka [km_from, km_to] wazony dlugoscia
    nakladania sie z bucketami nawierzchni - do porownania z kandydatem."""
    totals: dict[str, float] = {}
    total_len = 0.0
    for b in buckets:
        overlap = min(km_to, b["km_to"]) - max(km_from, b["km_from"])
        if overlap <= 0:
            continue
        label = _surface_label_pl(b.get("surface_raw") or b.get("surface"))
        totals[label] = totals.get(label, 0.0) + overlap
        total_len += overlap
    if total_len <= 0:
        return []
    breakdown = sorted(
        [{"surface": k, "pct": round(v / total_len * 100)} for k, v in totals.items()],
        key=lambda x: -x["pct"],
    )
    return breakdown


def _describe_bucket(b: dict | None) -> str:
    if b is None:
        return "Brak dopasowanych danych OSM dla tego odcinka — traktowane jako ryzykowne z ostrożności."
    surface = b.get("surface_raw") or b.get("surface") or "nieznana"
    coverage = b.get("coverage_status") or "brak statusu"
    confidence = b.get("confidence") or "brak"
    explanation = b.get("explanation") or ""
    parts = [f"Nawierzchnia: {surface}", f"pokrycie danych: {coverage}", f"pewność: {confidence}"]
    if explanation:
        parts.append(explanation)
    return " · ".join(parts)


def _merge_close_risky(runs: list[dict], gap_km: float = RISKY_GAP_MERGE_KM) -> list[dict]:
    """Laczy sasiednie odcinki ryzykowne rozdzielone krotkim "dobrym" proseczkiem
    (< gap_km) w jeden odcinek - unika zasypywania tabeli mikro-fragmentami,
    ktore w praktyce jada sie jako jedno miejsce."""
    result: list[dict] = []
    i = 0
    n = len(runs)
    while i < n:
        run = runs[i]
        if not run["risky"]:
            result.append(run)
            i += 1
            continue
        merged_coords = list(run["coordinates"])
        km_to = run["km_to"]
        reasons = [run["reason"]] if run.get("reason") else []
        i += 1
        while (
            i + 1 < n
            and not runs[i]["risky"]
            and (runs[i]["km_to"] - runs[i]["km_from"]) < gap_km
            and runs[i + 1]["risky"]
        ):
            gap_run = runs[i]
            next_run = runs[i + 1]
            merged_coords += gap_run["coordinates"][1:] + next_run["coordinates"][1:]
            km_to = next_run["km_to"]
            if next_run.get("reason") and next_run["reason"] not in reasons:
                reasons.append(next_run["reason"])
            i += 2
        result.append({
            "risky": True,
            "km_from": run["km_from"],
            "km_to": km_to,
            "coordinates": merged_coords,
            "reason": " | ".join(reasons) if reasons else None,
        })
    return result


@app.get("/api/routes/{route_id}/surface-segments")
def route_surface_segments(route_id: str):
    """Trasa pocieta na ciagle odcinki dobra/ryzykowna wg nawierzchni, z uzasadnieniem
    i numeracja odcinkow ryzykownych (segment_no), po zlaczeniu bardzo bliskich."""
    conn = _db_conn()
    try:
        base = conn.execute(
            """
            SELECT rb.route_base_id, rb.distance_m,
                   a.metadata_json->>'route_name' AS name
            FROM qbot_v2.route_base rb
            LEFT JOIN qbot_v2.route_artifacts a ON a.id = rb.route_artifact_id
            WHERE rb.route_id = %s
            ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1
            """,
            (route_id,),
        ).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")

        axis_rows = conn.execute(
            """
            SELECT segment_index, km_from, km_to, segment_geojson
            FROM qbot_v2.route_axis_segments
            WHERE route_base_id = %s
            ORDER BY segment_index
            """,
            (base["route_base_id"],),
        ).fetchall()
        buckets = _load_surface_buckets(conn, base["route_base_id"])
    finally:
        conn.close()

    runs: list[dict] = []
    current_risky = None
    current_coords: list[list[float]] = []
    current_km_from = None
    current_km_to = None
    current_bucket_hits: dict[int, int] = {}
    bucket_by_id = {id(b): b for b in buckets}

    def _flush():
        if not current_coords:
            return
        rep_bucket = None
        if current_bucket_hits:
            best_id = max(current_bucket_hits, key=current_bucket_hits.get)
            rep_bucket = bucket_by_id.get(best_id)
        runs.append({
            "coordinates": current_coords,
            "risky": current_risky,
            "km_from": round(current_km_from, 2),
            "km_to": round(current_km_to, 2),
            "reason": _human_reason(rep_bucket) if current_risky else None,
        })

    for row in axis_rows:
        km_from = float(row["km_from"])
        km_to = float(row["km_to"])
        km_mid = (km_from + km_to) / 2.0
        bucket = _bucket_for_km(buckets, km_mid)
        risky = bucket["risky"] if bucket is not None else True
        geo = row["segment_geojson"] or {}
        seg_coords = [[round(pt[1], 6), round(pt[0], 6)] for pt in geo.get("coordinates", [])]
        if not seg_coords:
            continue
        if risky != current_risky:
            _flush()
            current_coords = [current_coords[-1]] if current_coords else []
            current_risky = risky
            current_km_from = km_from
            current_bucket_hits = {}
        current_coords.extend(seg_coords)
        current_km_to = km_to
        if bucket is not None:
            current_bucket_hits[id(bucket)] = current_bucket_hits.get(id(bucket), 0) + 1
    _flush()

    runs = _merge_close_risky(runs)

    # UWAGA (2026-07-01): odcinki ryzykowne krotsze niz MIN_RISKY_SEGMENT_KM (200m)
    # NIE sa zglaszane jako osobny alert - to szum (np. widziano 50m, 100m, 150m
    # fragmenty na trasie testowej), ktorego rowerzysta praktycznie nie zauwaza,
    # a ktory zasmieca tabele i generuje bezsensowne proby objazdu. Trafiaja z
    # powrotem do puli "dobra nawierzchnia" (nie usuwamy geometrii z mapy).
    filtered_runs = []
    for r in runs:
        if r["risky"] and (r["km_to"] - r["km_from"]) < MIN_RISKY_SEGMENT_KM:
            r = dict(r)
            r["risky"] = False
        filtered_runs.append(r)
    runs = filtered_runs

    segment_no = 1
    for r in runs:
        if r["risky"]:
            r["segment_no"] = segment_no
            segment_no += 1
            r["original_breakdown"] = _weighted_breakdown_pl(buckets, r["km_from"], r["km_to"])
        else:
            r["segment_no"] = None
            r["original_breakdown"] = None

    return {
        "route_id": route_id,
        "name": base.get("name") or f"Trasa {route_id}",
        "distance_km": round((base["distance_m"] or 0) / 1000, 1),
        "segments": runs,
    }


def _coalesce_categories(buckets: list[dict]) -> list[dict]:
    """Scala sasiednie bucket-y o tej samej surface_category w ciagle odcinki (wstazka 5-kat.)."""
    runs: list[dict] = []
    for b in buckets:
        cat = b.get("surface_category")
        if runs and runs[-1]["category"] == cat:
            runs[-1]["km_to"] = b["km_to"]
            runs[-1]["_surfs"].append(b.get("surface"))
        else:
            runs.append({
                "category": cat,
                "label": b.get("surface_category_label"),
                "km_from": b["km_from"],
                "km_to": b["km_to"],
                "reason": b.get("surface_category_reason"),
                "_surfs": [b.get("surface")],
            })
    for r in runs:
        surfs = [x for x in r.pop("_surfs") if x]
        r["dominant_surface"] = max(set(surfs), key=surfs.count) if surfs else None
        r["km_from"] = round(r["km_from"], 2)
        r["km_to"] = round(r["km_to"], 2)
    return runs


@app.get("/api/routes/{route_id}/surface-categories")
def route_surface_categories(route_id: str):
    """Nawierzchnia jako 5 kategorii (surface_category z route_surface_layer, model 2026-07-03).

    Zrodlo: route_surface_layer.surface_meta_json (pole surface_category liczone przez
    route_surface_category_store, przebieg DB->DB). Zwraca wstazke (scalone odcinki
    tej samej kategorii) + surowe bucket-y + histogram. Addytywny wzgledem
    /surface-segments (ryzyko binarne) - ten nie jest ruszany."""
    conn = _db_conn()
    try:
        base = conn.execute(
            "SELECT rb.route_base_id, rb.distance_m, "
            "a.metadata_json->>'route_name' AS name "
            "FROM qbot_v2.route_base rb "
            "LEFT JOIN qbot_v2.route_artifacts a ON a.id = rb.route_artifact_id "
            "WHERE rb.route_id = %s ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1",
            (route_id,),
        ).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
        buckets = _load_surface_buckets(conn, base["route_base_id"])
    finally:
        conn.close()

    ribbon = _coalesce_categories(buckets)
    histogram: dict[int, float] = {}
    for b in buckets:
        cat = b.get("surface_category")
        if cat is None:
            continue
        histogram[cat] = round(histogram.get(cat, 0.0) + (b["km_to"] - b["km_from"]), 2)
    has_cat = any(b.get("surface_category") is not None for b in buckets)
    return {
        "route_id": route_id,
        "name": base.get("name") or f"Trasa {route_id}",
        "distance_km": round((base["distance_m"] or 0) / 1000, 1),
        "has_category": has_cat,
        "ribbon": ribbon,
        "km_by_category": histogram,
        "segments": [
            {
                "km_from": b["km_from"], "km_to": b["km_to"],
                "category": b.get("surface_category"),
                "label": b.get("surface_category_label"),
                "reason": b.get("surface_category_reason"),
                "surface": b.get("surface"),
            }
            for b in buckets
        ],
    }


def _decode_valhalla_polyline(encoded: str, precision: int = 6) -> list[list[float]]:
    """Fallback: Valhalla czasem zwraca shape jako zakodowany polyline (string)
    mimo zadania shape_format=geojson - trzeba obsluzyc oba warianty (identyczna
    logika co w tools/route_generator.py::_decode_polyline / _parse_track)."""
    inv = 1.0 / 10**precision
    decoded = []
    lat = lon = 0
    i = 0
    while i < len(encoded):
        shift = result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        lat += (~(result >> 1) if (result & 1) else (result >> 1))
        shift = result = 0
        while True:
            b = ord(encoded[i]) - 63
            i += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        lon += (~(result >> 1) if (result & 1) else (result >> 1))
        decoded.append([lat * inv, lon * inv])
    return decoded


def _valhalla_alternative(origin: list[float], destination: list[float]) -> dict:
    """Wywoluje publiczna Valhalle (bicycle/Cross) z mocnym unikaniem zlej nawierzchni."""
    payload = {
        "locations": [
            {"lat": origin[0], "lon": origin[1]},
            {"lat": destination[0], "lon": destination[1]},
        ],
        "costing": "bicycle",
        "costing_options": {"bicycle": {
            "bicycle_type": "Cross",
            "use_roads": 0.7,
            "use_hills": 0.5,
            "avoid_bad_surfaces": 0.9,
        }},
        "directions_options": {"units": "km"},
        "shape_format": "geojson",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(VALHALLA_ROUTE, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read())
    shape = result["trip"]["legs"][0]["shape"]
    if isinstance(shape, str):
        coords = _decode_valhalla_polyline(shape)
    else:
        coords = [[c[1], c[0]] for c in shape["coordinates"]]
    distance_km = result["trip"]["summary"]["length"]
    return {"coordinates": coords, "distance_km": round(distance_km, 2)}


def _valhalla_surface_confidence(coordinates: list[list[float]]) -> dict:
    """Sprawdza realna nawierzchnie objazdu przez Valhalla trace_attributes
    (map-matching do krawedzi grafu OSM, ktorego uzywa sam routing) - zamiast
    zgadywac pewnosc, pytamy ten sam graf, ktory wyznaczyl objazd. Osobne API
    od Overpass (unikamy znanego throttlingu Overpass z wczesniejszych prob)."""
    payload = {
        "shape": [{"lat": lat, "lon": lon} for lat, lon in coordinates],
        "costing": "bicycle",
        "shape_match": "map_snap",
        "filters": {"attributes": ["edge.surface", "edge.length"], "action": "include"},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(VALHALLA_TRACE_ATTRIBUTES, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read())
    edges = result.get("edges") or []
    by_surface: dict[str, float] = {}
    total = 0.0
    for e in edges:
        surface = e.get("surface") or "unknown"
        length = float(e.get("length") or 0.0)
        by_surface[surface] = by_surface.get(surface, 0.0) + length
        total += length
    if total <= 0:
        return {"available": False, "still_risky": None, "risky_pct": None, "note": "Brak dopasowanych krawedzi grafu dla objazdu."}
    breakdown = sorted(
        [{"surface": s, "surface_pl": _surface_label_pl(s), "pct": round(l / total * 100)} for s, l in by_surface.items()],
        key=lambda x: -x["pct"],
    )
    dominant = breakdown[0]["surface"]
    risky_pct = sum(b["pct"] for b in breakdown if b["surface"] in VALHALLA_RISKY_SURFACES)
    still_risky = risky_pct >= 50 or dominant in VALHALLA_RISKY_SURFACES
    return {
        "available": True,
        "breakdown": breakdown,
        "dominant": dominant,
        "dominant_pct": breakdown[0]["pct"],
        "risky_pct": risky_pct,
        "still_risky": still_risky,
        "note": "Wg klasyfikacji nawierzchni Valhalli/OSM dla objazdu — inna skala niz reszta raportu, traktuj orientacyjnie.",
    }


def _anchor_point(conn, route_base_id: int, target_km: float, *, side: str) -> list[float] | None:
    """Znajduje punkt geometrii najblizszy zadanemu kilometrowi.
    side='before' -> szukamy segmentu konczacego sie <= target_km, bierzemy JEGO OSTATNI punkt
    side='after'  -> szukamy segmentu zaczynajacego sie >= target_km, bierzemy JEGO PIERWSZY punkt
    """
    if side == "before":
        row = conn.execute(
            """
            SELECT segment_geojson FROM qbot_v2.route_axis_segments
            WHERE route_base_id = %s AND km_to <= %s
            ORDER BY km_to DESC LIMIT 1
            """,
            (route_base_id, target_km),
        ).fetchone()
        idx = -1
    else:
        row = conn.execute(
            """
            SELECT segment_geojson FROM qbot_v2.route_axis_segments
            WHERE route_base_id = %s AND km_from >= %s
            ORDER BY km_from ASC LIMIT 1
            """,
            (route_base_id, target_km),
        ).fetchone()
        idx = 0
    if not row:
        return None
    geo = row["segment_geojson"] or {}
    coords = geo.get("coordinates", [])
    if not coords:
        return None
    pt = coords[idx]
    return [pt[1], pt[0]]


@app.get("/api/routes/{route_id}/segments/candidate")
def route_segment_candidate(
    route_id: str,
    km_from: float,
    km_to: float,
    buffer_km: float | None = Query(default=None),
):
    """Proponuje objazd dla wskazanego odcinka [km_from, km_to] przez publiczna Valhalle,
    wraz z informacja o pewnosci nawierzchni objazdu (trace_attributes).

    UWAGA architektoniczna (2026-07-01, wersja 3 - progresywne probkowanie):
    Test na trasie testowej 55798129 wykazal, ze pojedynczy staly bufor 0.3km
    czesto nie wystarcza - trasa ta zostala CELOWO ulozona po niepewnych drogach
    (zbieranie kwadratow StatsHunters), wiec trudnosc jest realna i oczekiwana.
    Zamiast jednego stalego bufora probkujemy PROGRESYWNIE rosnace promienie
    (ESCALATION_BUFFERS_KM) i zatrzymujemy sie na pierwszym, ktory daje dobra
    nawierzchnie (still_risky=False); jesli zaden nie wystarczy, zwracamy
    NAJLEPSZY znaleziony wariant (najnizszy risky_pct) z jawna informacja
    do jakiego promienia szukano - zamiast cichego "brak" po jednej probie.

    UWAGA #4 (2026-07-01, korekta use_roads): pierwotny test parametrow byl
    robiony TYLKO na waskim buforze 0.3km, gdzie zadna prawdziwa droga nie byla
    fizycznie osiagalna - stad blednie wygladalo, ze use_roads "nic nie zmienia".
    Przy szerszym buforze (1.5km+), gdzie realna droga asfaltowa BYLA w zasiegu,
    okazalo sie ze use_roads=0.3 aktywnie ODCIAGAL routing od tej drogi w strone
    sciezek/duktow (Valhalla: nizsze use_roads = preferuj sciezki nad drogami).
    Podniesienie do use_roads=0.7 znalazlo te sama widoczna na mapie droge
    asfaltowa (np. segment 17: 67% dirt -> 75% paved_smooth przy tym samym
    buforze 1.5km), bez pogorszenia wczesniej dzialajacych przypadkow.

    Jesli wywolujacy jawnie poda buffer_km, escalacja jest pomijana (uzywany
    jest dokladnie ten jeden bufor) - przydatne do debugowania/testow.
    """
    conn = _db_conn()
    try:
        base = conn.execute(
            "SELECT route_base_id, distance_m FROM qbot_v2.route_base WHERE route_id = %s ORDER BY route_modified_at DESC NULLS LAST LIMIT 1",
            (route_id,),
        ).fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
        route_max_km = (base["distance_m"] or 0) / 1000.0
        route_base_id = base["route_base_id"]

        buffers_to_try = [buffer_km] if buffer_km is not None else ESCALATION_BUFFERS_KM

        best = None
        tried_km: list[float] = []
        anchors_missing = False
        last_error: str | None = None
        for buf in buffers_to_try:
            anchor_from_km = max(0.0, km_from - buf)
            anchor_to_km = min(route_max_km, km_to + buf) if route_max_km else km_to + buf
            origin = _anchor_point(conn, route_base_id, anchor_from_km, side="before")
            destination = _anchor_point(conn, route_base_id, anchor_to_km, side="after")
            if not origin or not destination:
                anchors_missing = True
                continue
            tried_km.append(buf)
            try:
                candidate = _valhalla_alternative(origin, destination)
                confidence = _valhalla_surface_confidence(candidate["coordinates"])
            except Exception as exc:
                # UWAGA (2026-07-01): rozroznij "nie ma punktow zakotwiczenia" (problem
                # danych) od "publiczna Valhalla nie odpowiada/zwraca blad" (przejsciowa
                # awaria zewnetrznej uslugi, poza nasza kontrola) - wczesniej oba przypadki
                # dawaly ten sam mylacy komunikat "nie znaleziono punktow zakotwiczenia".
                last_error = str(exc)
                continue

            # UWAGA (2026-07-01, cofniete po wyjasnieniu): limit proporcji dlugosci
            # per-kandydat byl nieporozumieniem - uzytkownik akceptuje dlugie objazdy
            # (nawet 10km) jesli prowadza dobra nawierzchnia. replaced_km zostaje
            # jako informacja (przejrzystosc), ale NIE bierze udzialu w ocenie/
            # odrzucaniu kandydata. Ograniczenie calkowitej dlugosci TRASY (nie
            # pojedynczego kandydata) to osobne, przyszle zadanie - nie teraz.
            replaced_km = round(anchor_to_km - anchor_from_km, 2)
            still_risky = confidence.get("still_risky")

            risky_pct = confidence.get("risky_pct")
            score = risky_pct if risky_pct is not None else 100
            entry = {
                "buffer_km": buf,
                "anchor_from_km": round(anchor_from_km, 2),
                "anchor_to_km": round(anchor_to_km, 2),
                "replaced_km": replaced_km,
                "candidate": candidate,
                "confidence": confidence,
                "score": score,
            }
            if best is None or score < best["score"]:
                best = entry
            if still_risky is False:
                break  # znaleziono dobra nawierzchnie, koniec eskalacji
    finally:
        conn.close()

    if best is None:
        if last_error and not anchors_missing:
            raise HTTPException(
                status_code=503,
                detail=f"Publiczna Valhalla (silnik routingu) jest chwilowo niedostepna lub zwraca blad - sprobuj ponownie za chwile. Szczegol: {last_error}",
            )
        raise HTTPException(status_code=404, detail="Nie znaleziono punktow zakotwiczenia dla tego odcinka")

    candidate = best["candidate"]
    confidence = best["confidence"]
    original_km = round(km_to - km_from, 2)
    delta_km = round(candidate["distance_km"] - original_km, 2)
    still_risky = confidence.get("still_risky")

    return {
        "route_id": route_id,
        "km_from": km_from,
        "km_to": km_to,
        "buffer_km_used": best["buffer_km"],
        "escalation_tried_km": tried_km,
        "anchor_from_km": best["anchor_from_km"],
        "anchor_to_km": best["anchor_to_km"],
        "replaced_km": best["replaced_km"],
        "original_km": original_km,
        "candidate_km": candidate["distance_km"],
        "delta_km": delta_km,
        "coordinates": candidate["coordinates"],
        "confidence": confidence,
        "no_real_alternative": bool(still_risky),
    }



import re as _re
import html as _htmlmod


def _kanon_inline(s: str) -> str:
    s = _htmlmod.escape(s)
    s = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = _re.sub(r"_(.+?)_", r"<em>\1</em>", s)
    return s


def _kanon_md_to_html(md: str) -> str:
    lines = md.split("\n")
    out, i, n = [], 0, len(md.split("\n"))

    def is_row(l):
        return l.strip().startswith("|")

    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    while i < n:
        l = lines[i]
        s = l.strip()
        if s == "<!--RAW-->":
            i += 1
            raw = []
            while i < n and lines[i].strip() != "<!--/RAW-->":
                raw.append(lines[i]); i += 1
            i += 1
            out.append("\n".join(raw))
            continue
        if is_row(l):
            block = []
            while i < n and is_row(lines[i]):
                block.append(lines[i])
                i += 1
            header = cells(block[0])
            data = block[1:]
            if data:
                probe = data[0].replace("|", "").replace(":", "").replace("-", "").replace(" ", "")
                if probe == "":
                    data = data[1:]
            t = ["<table><thead><tr>"]
            t += [f"<th>{_kanon_inline(c)}</th>" for c in header]
            t.append("</tr></thead><tbody>")
            for r in data:
                t.append("<tr>" + "".join(f"<td>{_kanon_inline(c)}</td>" for c in cells(r)) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue
        if s.startswith("### "):
            out.append(f"<h3>{_kanon_inline(s[4:])}</h3>"); i += 1; continue
        if s.startswith("## "):
            out.append(f"<h2>{_kanon_inline(s[3:])}</h2>"); i += 1; continue
        if s.startswith("# "):
            out.append(f"<h1>{_kanon_inline(s[2:])}</h1>"); i += 1; continue
        if s.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(f"<li>{_kanon_inline(lines[i].strip()[2:])}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>"); continue
        if s == "":
            i += 1; continue
        out.append(f"<p>{_kanon_inline(s)}</p>"); i += 1
    return "\n".join(out)


_KANON_PAGE = """<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raport kanoniczny __RID__</title>
<style>
:root{color-scheme:light dark}
body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:920px;margin:0 auto;padding:16px;line-height:1.45}
h1{font-size:1.5rem;border-bottom:2px solid #888;padding-bottom:6px}
h2{font-size:1.15rem;margin-top:1.6em;border-bottom:1px solid #ccc;padding-bottom:3px}
h3{font-size:1rem;margin-top:1.2em}
table{border-collapse:collapse;width:100%;margin:10px 0;font-size:.9rem}
th,td{border:1px solid #bbb;padding:5px 8px;text-align:left;vertical-align:top}
th{background:rgba(128,128,128,.15)}
tr:nth-child(even) td{background:rgba(128,128,128,.06)}
em{opacity:.75;font-style:italic}
ul{margin:.4em 0}
.foot{margin-top:24px;font-size:.8rem;opacity:.6}
</style></head><body>
__BODY__
<div class="foot">qbot-web · raport kanoniczny (WIP) · /kanon?route_id=__RID__&start=YYYY-MM-DD+HH:MM</div>
</body></html>"""


@app.get("/kanon", response_class=HTMLResponse)
def kanon_report(route_id: str = Query(...), start: str | None = Query(None)):
    for _k, _v in _env().items():
        os.environ.setdefault(_k, _v)
    try:
        from qbot3.routes.route_report_canonical import build_canonical_report_v1
        md = build_canonical_report_v1(route_id, start=start, fmt="html")
    except Exception as exc:  # noqa: BLE001
        md = f"# Blad\n\nNie udalo sie zbudowac raportu dla {route_id}: {exc}"
    body = _kanon_md_to_html(md)
    page = _KANON_PAGE.replace("__BODY__", body).replace("__RID__", str(route_id))
    return HTMLResponse(page)


# ---------------------------------------------------------------------------
# Generator danych raportu trasy (raport-v2). Jedno zrodlo prawdy dla DATA:
# kazda trasa liczona samodzielnie z bazy + silnikow. Front (raport-render.js)
# tylko rysuje to, co tu policzone. Zmiany danych raportu = TYLKO tutaj.
# ---------------------------------------------------------------------------
def _report_sev(c):
    c = int(c or 0)
    if c >= 95: return 6
    if c in (80, 81, 82) or 61 <= c <= 67: return 5
    if 51 <= c <= 57 or 71 <= c <= 77: return 4
    if c in (45, 48) or c == 3: return 2
    if c in (1, 2): return 1
    return 0


def _report_icon(code, prob):
    c = int(code or 0)
    if c >= 95: return "storm"
    if c in (80, 81, 82) or 61 <= c <= 67 or 51 <= c <= 57: return "rain"
    if 71 <= c <= 77: return "snow"
    if c in (45, 48) or c == 3: return "cloud"
    if c in (1, 2): return "partcloud"
    if c == 0: return "cloud" if (prob or 0) >= 55 else "sun"
_COMPASS8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
_SKY_PL = {"sun": "słonecznie", "partcloud": "częściowe zachmurzenie",
           "cloud": "pochmurno", "rain": "deszcz", "storm": "burza",
           "snow": "śnieg", "fog": "mgła"}


def _comfort_cat(feels):
    if feels is None:
        return None
    if feels < 6:
        return "zimno"
    if feels < 13:
        return "chłodno"
    if feels < 26:
        return "komfort"
    return "gorąco"


def _absorb_short_surface(runs, min_km=0.3):
    """Wchlania krotkie (<min_km) odcinki nawierzchni w sasiada najblizszego
    KATEGORIA (remis -> dluzszy). Kategoria 5 (ryzyko/niepewne) nietykalna:
    nigdy nie wchlaniana i nigdy nie wchlania (sciana). Powtarza az nie ma
    wchlanialnego odcinka. Krok wizualny - te same dane co wykres i mapa."""
    runs = [dict(r) for r in runs]

    def length(r):
        return r["km_to"] - r["km_from"]

    def absorbable(r):
        c = r.get("category")
        return c is not None and c != 5 and length(r) < min_km

    guard = 0
    while True:
        guard += 1
        if guard > 10000:
            break
        idxs = sorted([i for i in range(len(runs)) if absorbable(runs[i])],
                      key=lambda i: length(runs[i]))
        if not idxs:
            break
        merged = False
        for i in idxs:
            cand = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(runs):
                    cj = runs[j].get("category")
                    if cj is not None and cj != 5:
                        cand.append(j)
            if not cand:
                continue
            ci = runs[i]["category"]
            best = min(cand, key=lambda j: (abs(runs[j]["category"] - ci), -length(runs[j])))
            b = runs[best]
            b["km_from"] = min(b["km_from"], runs[i]["km_from"])
            b["km_to"] = max(b["km_to"], runs[i]["km_to"])
            del runs[i]
            merged = True
            break
        if not merged:
            break
    out = []
    for r in runs:
        if out and out[-1].get("category") == r.get("category"):
            out[-1]["km_to"] = max(out[-1]["km_to"], r["km_to"])
            out[-1]["km_from"] = min(out[-1]["km_from"], r["km_from"])
        else:
            out.append(dict(r))
    return out


def _build_weather_head(weather, per):
    """Chip pogodowy do naglowka: ikona nieba, srednia odczuwalna + komfort,
    opady, wiatr bezwzgledny (kierunek 8-punktowy + m/s z METEO)."""
    import math as _m
    feels_vals = [w["feels"] for w in weather if w.get("feels") is not None]
    feels_avg = round(sum(feels_vals) / len(feels_vals), 1) if feels_vals else None
    icons = [w["icon"] for w in weather]
    if "storm" in icons:
        sky_icon = "storm"
    elif icons:
        sky_icon = max(set(icons), key=icons.count)
    else:
        sky_icon = "cloud"
    max_mm = max((w.get("mm") or 0) for w in weather) if weather else 0
    max_prob = max((w.get("rain") or 0) for w in weather) if weather else 0
    if "storm" in icons:
        precip_pl = "burza"
    elif max_mm >= 0.5:
        precip_pl = "deszcz"
    elif max_prob >= 40:
        precip_pl = "możliwy deszcz"
    else:
        precip_pl = "bez opadów"
    dirs = [(pp.get("wind_dir_deg"), pp.get("wind_speed_ms")) for pp in per
            if pp.get("wind_dir_deg") is not None and pp.get("wind_speed_ms") is not None]
    wind_dir = wind_ms = None
    if dirs:
        sx = sum(_m.sin(_m.radians(d)) * sp for d, sp in dirs)
        sy = sum(_m.cos(_m.radians(d)) * sp for d, sp in dirs)
        ang = (_m.degrees(_m.atan2(sx, sy)) + 360) % 360
        wind_dir = _COMPASS8[int((ang + 22.5) // 45) % 8]
        wind_ms = round(sum(sp for _, sp in dirs) / len(dirs), 1)
    return {"icon": sky_icon, "sky_pl": _SKY_PL.get(sky_icon, sky_icon),
            "feels": feels_avg, "comfort": _comfort_cat(feels_avg),
            "precip_pl": precip_pl, "wind_dir": wind_dir, "wind_ms": wind_ms}


def _build_report_data(conn, route_id, date_str, start_time, long_stops=0, long_stop_min=0):
    """Buduje pelny blok DATA (route/start/time/chart) dla jednej trasy."""
    base = conn.execute(
        "SELECT rb.route_base_id, rb.distance_m, rb.route_modified_at, "
        "a.metadata_json->>'route_name' AS name "
        "FROM qbot_v2.route_base rb "
        "LEFT JOIN qbot_v2.route_artifacts a ON a.id=rb.route_artifact_id "
        "WHERE rb.route_id=%s "
        "ORDER BY rb.route_modified_at DESC NULLS LAST LIMIT 1", (route_id,)).fetchone()
    if not base:
        raise HTTPException(status_code=404, detail="Trasa nie znaleziona w routes store")
    rbid = base["route_base_id"]
    dist_km = round((base["distance_m"] or 0) / 1000.0, 1)
    name = base["name"] or f"Trasa {route_id}"
    vmod = base.get("route_modified_at")
    version_modified = vmod.strftime("%Y-%m-%d %H:%M") if vmod else None

    # --- profil wysokosci (downsample ~220) ---
    erows = conn.execute(
        "SELECT distance_m, elevation_m FROM qbot_v2.route_elevation_samples "
        "WHERE route_base_id=%s ORDER BY sample_index", (rbid,)).fetchall()
    if not erows:
        raise HTTPException(status_code=422, detail="Brak profilu wysokosci dla tej trasy")
    step = max(1, len(erows) // 220)
    ele = []
    for i in range(0, len(erows), step):
        ele.append([round(erows[i]["distance_m"] / 1000.0, 3), round(erows[i]["elevation_m"], 1)])
    last_km = round(erows[-1]["distance_m"] / 1000.0, 3)
    if ele[-1][0] != last_km:
        ele.append([last_km, round(erows[-1]["elevation_m"], 1)])
    emin = min(p[1] for p in ele)
    emax = max(p[1] for p in ele)
    km_total = round(erows[-1]["distance_m"] / 1000.0, 1)

    # --- nawierzchnia: 5 kategorii (parytet z endpointem) ---
    ribbon = _absorb_short_surface(_coalesce_categories(_load_surface_buckets(conn, rbid)))
    surface_cat = [
        {"a": round(float(r["km_from"]), 2), "b": round(float(r["km_to"]), 2),
         "k": r["category"], "label": r.get("label"), "reason": r.get("reason")}
        for r in ribbon if r.get("category") is not None
    ]

    # --- lokalizacja startu (reverse-geocode + cache) ---
    latlon = None
    try:
        g = route_geometry(route_id)
        if g.get("coordinates"):
            latlon = (g["coordinates"][0][0], g["coordinates"][0][1])
    except Exception:
        pass
    from qbot3.routes import route_report_canonical as _rc
    adm = _rc._admin(conn, route_id, latlon) if latlon else \
        {"miejscowosc": None, "gmina": None, "powiat": None, "wojewodztwo": None}

    # --- przewyzszenie (kanoniczne, z fallbackiem z profilu) ---
    ascent = None
    try:
        from qbot_route_report_tool import _read_route_source
        rs = _read_route_source(route_id) or {}
        ascent = (rs.get("canonical_elevation_summary") or {}).get("ascent_smoothed_m")
    except Exception:
        pass
    if ascent is None:
        asc = 0.0
        for i in range(1, len(ele)):
            d = ele[i][1] - ele[i - 1][1]
            if d > 0:
                asc += d
        ascent = round(asc)
    else:
        ascent = round(float(ascent))

    # --- czas przejazdu (z deklaracja dlugich przerw) ---
    tmoving = ttotal = stops_min = stops_cnt = None
    long_min_val = None
    try:
        from qbot_route_time_tools import estimate_route_time_v2
        tt = estimate_route_time_v2(
            route_id=route_id, mode="normalny",
            planned_long_stops=int(long_stops or 0),
            planned_long_stop_min=float(long_stops or 0) * float(long_stop_min or 0), start_time=start_time)
        if isinstance(tt, dict):
            tmoving = tt.get("moving_h")
            ttotal = tt.get("total_h")
            stp = tt.get("stops") or {}
            stops_min = round((stp.get("mikro_min") or 0) + (stp.get("krotkie_min") or 0), 1)
            stops_cnt = stp.get("krotkie_liczba") or stp.get("liczba")
            dm = stp.get("dlugie_min") or 0
            long_min_val = dm if dm > 0 else None
    except Exception:
        pass

    # --- meteo: pogoda per okno + odczuwalna + wiatr gesty + ETA ---
    from qbot3.routes.route_meteo_engine import run_meteo_engine
    m = run_meteo_engine(route_id=route_id, date_str=date_str, start_time=start_time)
    per = m["per_segment"]
    weather = []
    for w in m["tabela_30min"]:
        a = float(w["km_od"]); b = float(w["km_do"])
        inwin = [pp for pp in per if a <= float(pp["km"]) <= b]
        codes = [pp.get("burza_kod") for pp in inwin if pp.get("burza_kod") is not None]
        code = max(codes, key=_report_sev) if codes else 0
        prob = (w.get("opad", {}) or {}).get("prob")
        tails = [pp.get("wind_tail_ms") for pp in inwin if pp.get("wind_tail_ms") is not None]
        crs = [abs(pp.get("wind_cross_ms")) for pp in inwin if pp.get("wind_cross_ms") is not None]
        fe = [float(pp["feels"]) for pp in inwin if pp.get("feels") is not None]
        weather.append({
            "t": w["okno"], "a": round(a, 2), "b": round(b, 2),
            "wbgt": round(float(w["wbgt_max"]), 1),
            "rain": int(prob) if prob is not None else None,
            "mm": round(float((w.get("opad", {}) or {}).get("mm") or 0), 1),
            "code": int(code), "icon": _report_icon(code, prob),
            "w_along": round(sum(tails) / len(tails), 1) if tails else None,
            "w_cross": round(sum(crs) / len(crs), 1) if crs else None,
            "feels": round(sum(fe) / len(fe), 1) if fe else None,
        })
    eta = [[w["a"], w["t"]] for w in weather]
    perw = [pp for pp in per if pp.get("wind_tail_ms") is not None]
    stepw = max(1, len(perw) // 200)
    wind = []
    for i in range(0, len(perw), stepw):
        pp = perw[i]
        wind.append([round(float(pp["km"]), 2), round(float(pp["wind_tail_ms"]), 1),
                     round(abs(float(pp.get("wind_cross_ms") or 0)), 1)])
    if perw and wind[-1][0] != round(float(perw[-1]["km"]), 2):
        pp = perw[-1]
        wind.append([round(float(pp["km"]), 2), round(float(pp["wind_tail_ms"]), 1),
                     round(abs(float(pp.get("wind_cross_ms") or 0)), 1)])

    weather_head = _build_weather_head(weather, per)

    return {
        "route": {"id": route_id, "name": name, "distance_km": dist_km,
                  "ascent_m": ascent, "source": "RWGPS GPX",
                  "version_modified": version_modified},
        "start": {"date": date_str, "time": start_time,
                  "miejscowosc": adm.get("miejscowosc"), "gmina": adm.get("gmina"),
                  "powiat": adm.get("powiat"), "wojewodztwo": adm.get("wojewodztwo")},
        "time": {"moving_h": tmoving, "total_h": ttotal, "stops_auto_min": stops_min,
                 "stops_count": stops_cnt, "long_stops_min": long_min_val, "accuracy_pct": 15},
        "weather_head": weather_head,
        "chart": {"km_total": km_total, "ele": ele, "ele_min": emin, "ele_max": emax,
                  "surface_cat": surface_cat, "weather": weather, "eta": eta, "wind": wind},
    }


@app.get("/api/report/data")
def report_data(route_id: str = Query(...), date: str = Query(...),
                time: str = Query("10:00"), long_stops: int = Query(0),
                long_stop_min: int = Query(0)):
    """Zwraca blok DATA raportu trasy (JSON) - generator w QBocie."""
    conn = _db_conn()
    try:
        return _build_report_data(conn, route_id, date, time, long_stops, long_stop_min)
    finally:
        conn.close()


app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
