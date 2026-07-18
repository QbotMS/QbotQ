"""Deterministic attraction classification and ranking for planned routes.

The engine is deliberately independent from PostgreSQL, HTTP and WEB.  Source
adapters provide normalized dictionaries; both WEB consumers later read the
same persisted result produced here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable


ALGORITHM_VERSION = "route_attractions_v2.2"
CANDIDATES_PER_100_KM = 12.0
RECOMMENDED_PER_100_KM = 2.5

# base score, display label, estimated visit minutes, uniqueness
CATEGORY = {
    "castle_palace": (28, "zamek / pałac / dwór", 30, 9),
    "archaeology": (12, "archeologia", 20, 7),
    "fortification": (26, "fortyfikacje", 25, 8),
    "industrial_heritage": (25, "zabytek techniki", 20, 9),
    "open_air_museum": (23, "skansen", 50, 9),
    "historic_town": (28, "historyczne miejsce / rynek", 25, 8),
    "historic_site": (21, "miejsce historyczne", 20, 6),
    "cultural_landmark": (24, "wyjątkowe miejsce / konstrukcja", 25, 9),
    "unusual_local": (18, "nietypowe miejsce lokalne", 20, 8),
    "sacred_exception": (12, "wyjątkowy zabytek sakralny", 20, 4),
    "museum": (10, "muzeum", 55, 4),
    "nature": (6, "przyroda", 30, 3),
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def norm(value: Any) -> str:
    text = str(value or "").translate(str.maketrans({"ł": "l", "Ł": "L"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.asin(min(1.0, math.sqrt(value)))


def parse_source_tags(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items() if item not in (None, "")}
    tags: dict[str, str] = {}
    for item in str(value or "").split(";"):
        if "=" not in item:
            continue
        key, val = item.strip().split("=", 1)
        if key.strip() and val.strip():
            tags[key.strip()] = val.strip()
    return tags


def normalize_analyzer_candidates(items: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split analyze_route_poi_artifact attractions into open and Google rows."""
    open_rows: list[dict[str, Any]] = []
    google_rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("lat") is None or item.get("lon") is None:
            continue
        provider = str(item.get("provider") or item.get("open_source") or "").lower()
        is_google = provider in {"google", "google_places"} or item.get("osm_type") == "google_places"
        if is_google:
            google_rows.append(dict(item))
            continue
        name = str(item.get("name") or "").strip()
        if not name or re.match(r"^Attraction \d+$", name):
            continue
        tags = parse_source_tags(item.get("source_tags"))
        wiki = tags.get("wikipedia")
        if wiki and not wiki.startswith("http"):
            lang, _, title = wiki.partition(":")
            wiki = f"https://{lang or 'pl'}.wikipedia.org/wiki/{title.replace(' ', '_')}"
        open_rows.append({
            "name": name,
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "km": float(item.get("route_km") or 0.0),
            "dist": float(item.get("distance_to_track_m") or 0.0),
            "sources": {"osm"},
            "pageid": None,
            "wiki": wiki,
            "qid": tags.get("wikidata"),
            "extract": tags.get("description") or "",
            "image": tags.get("image"),
            "tags": tags,
            "osm_ids": [f"{item.get('osm_type')}:{item.get('osm_id')}"],
        })
    return open_rows, google_rows


def normalize_google_source_candidates(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Google rows to semantic candidates; classify() remains the gate."""
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("lat") is None or item.get("lon") is None:
            continue
        name = str(item.get("name") or item.get("google_name") or "").strip()
        if not name:
            continue
        place_id = str(item.get("google_place_id") or item.get("osm_id") or "").strip() or None
        tags = parse_source_tags(item.get("source_tags"))
        rows.append({
            "name": name,
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "km": float(item.get("route_km") or 0.0),
            "dist": float(item.get("distance_to_track_m") or 0.0),
            "sources": {"google"},
            "pageid": None,
            "wiki": None,
            "qid": None,
            "extract": str(item.get("g_type_pl") or ""),
            "image": None,
            "tags": tags,
            "osm_ids": [],
            "google_place_id": place_id,
        })
    return rows


def entity_text(entity: dict[str, Any]) -> str:
    values: list[str] = []
    for group in (entity.get("labels") or {}, entity.get("descriptions") or {}):
        values.extend(str(item.get("value") or "") for item in group.values())
    values.extend(str(value) for value in entity.get("types", []))
    return " ".join(values)


def has_claim(entity: dict[str, Any], prop: str) -> bool:
    return bool((entity.get("claims") or {}).get(prop))


def _merge_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["sources"] |= source["sources"]
    target["osm_ids"] = sorted(set(target.get("osm_ids", [])) | set(source.get("osm_ids", [])))
    target["tags"].update(source.get("tags") or {})
    for key in ("qid", "pageid", "wiki", "image"):
        if source.get(key) and not target.get(key):
            target[key] = source[key]
    if len(source.get("extract") or "") > len(target.get("extract") or ""):
        target["extract"] = source["extract"]
    if float(source["dist"]) < float(target["dist"]):
        target["km"], target["dist"] = source["km"], source["dist"]


def dedupe(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    qids: dict[str, dict[str, Any]] = {}
    for original in sorted(rows, key=lambda row: (
        not bool(row.get("pageid")), float(row["dist"]), norm(row.get("name")),
        float(row.get("lat") or 0), float(row.get("lon") or 0),
    )):
        row = dict(original)
        row["sources"] = set(row.get("sources") or [])
        row["osm_ids"] = list(row.get("osm_ids") or [])
        row["tags"] = dict(row.get("tags") or {})
        qid = row.get("qid")
        if qid and qid in qids:
            _merge_into(qids[qid], row)
            continue
        match = None
        row_name = norm(row["name"])
        for old in merged:
            distance = haversine_m(row["lat"], row["lon"], old["lat"], old["lon"])
            similarity = SequenceMatcher(None, row_name, norm(old["name"])).ratio()
            if ((distance <= 120 and similarity >= 0.55)
                    or (distance <= 500 and row_name == norm(old["name"]))
                    or (distance <= 1500 and similarity >= 0.78)):
                match = old
                break
        if match:
            _merge_into(match, row)
            if qid:
                qids[qid] = match
        else:
            merged.append(row)
            if qid:
                qids[qid] = row
    return merged


def classify(row: dict[str, Any], entity: dict[str, Any]) -> tuple[str | None, str]:
    tags = row.get("tags") or {}
    text = norm(" ".join([
        str(row.get("name") or ""), str(row.get("extract") or ""), entity_text(entity),
        " ".join(f"{key} {value}" for key, value in tags.items()),
    ]))
    wiki = bool(row.get("pageid") or row.get("wiki"))
    heritage = bool(tags.get("heritage") or tags.get("heritage:operator") or has_claim(entity, "P1435"))
    entity_kind = norm(entity_text(entity))
    name_text = norm(row.get("name"))
    is_city = ("miasto" in entity_kind or "city of poland" in entity_kind
               or "town in poland" in entity_kind or bool(re.search(
                   r"\b(miasto w polsce|city|town|stadt|ciudad|citt[aà]|ville)\b", entity_kind)))
    is_admin = bool(re.search(r"\b(gmina|powiat|wojewodztwo)\b", name_text)) and not is_city
    institutions = ("urzad gmin", "starostwo", "diecezja", "uniwersytet", "akademia nauk",
                    "szkola wyzsza", "nadlesnictwo", "parafia rzymskokatolicka")
    if is_admin or any(marker in text for marker in institutions):
        return None, "jednostka administracyjna lub instytucja"
    if name_text in {"palac", "dwor", "zamek", "fort"}:
        return None, "zbyt ogólna nazwa obiektu"
    if any(marker in name_text for marker in (
        "oficyna", "wozownia", "fontanna", "fontanny", "taras palacowy", "park przypalacowy",
        "budynek gospodarczy", "stajnia", "folwark",
    )):
        return None, "obiekt pomocniczy zespołu zabytkowego"
    if any(marker in text for marker in ("zoo", "ogrod zoologiczny", "theme park", "park rozrywki", "aquapark")):
        return None, "zoo / park rozrywki"
    if tags.get("historic") in {"memorial", "wayside_cross", "wayside_shrine", "tomb"}:
        return None, "pomnik, krzyż lub mogiła"
    if any(marker in text for marker in ("pomnik ", "figura sw ", "kolumna maryjna", "statue", "memorial")):
        return None, "pomnik lub figura"
    if any(marker in text for marker in ("pomnik przyrody", "wayside cross", "wayside shrine", "kapliczka", "mogiła")):
        return None, "drobny obiekt"
    if any(marker in name_text for marker in ("altana", "glorieta", "gazebo")) and not (wiki or heritage):
        return None, "samodzielna mała architektura"
    # Strong site-level evidence wins over incidental words in an article.  A
    # battlefield article may mention a church or chapel without being a
    # sacred attraction itself (e.g. Góra Strękowa / defence of Wizna).
    historic_landmark = (
        "pole bitwy", "battlefield", "bitwa", "battle of", "obrona ", "defence of", "defense of",
        "linia obron", "stanowisko bojowe", "war position", "miejsce pamieci narodowej",
    )
    if any(marker in text for marker in historic_landmark):
        return "historic_site", "ważne miejsce wydarzeń historycznych"
    sacred = any(marker in text for marker in ("kosciol", "kaplica", "parafia", "sanktuarium", "cerkiew",
                                                "church", "chapel", "cathedral", "basilica"))
    exceptional = any(marker in text for marker in ("unesco", "katedra", "cathedral", "bazylika", "basilica", "drewniany kosciol"))
    if sacred and not (wiki and heritage and exceptional):
        return None, "zwykły obiekt sakralny"
    if sacred:
        return "sacred_exception", "wyjątkowy obiekt sakralny"
    if wiki and is_city:
        return "historic_town", "miasto z własnym opisem encyklopedycznym"
    title_attraction = ("zamek", "palac", "dwor", "fort", "ruin", "grodzisk", "muzeum", "skansen")
    if re.search(r"\bwies w polsce\b", text) and not any(marker in name_text for marker in title_attraction):
        return None, "miejscowość bez wskazanej atrakcji"
    tests = [
        ("open_air_museum", ("skansen", "open air museum")),
        ("castle_palace", ("zamek", "palac", "dwor", "castle", "palace", "manor", "schloss", "chateau")),
        ("archaeology", ("archeolog", "grodzisk", "kurhan", "megalit", "archaeological", "prehistor")),
        ("fortification", ("fort ", "twierd", "fortress", "bunkier", "bunker", "schron", "pillbox", "casemate", "city gate", "brama miejska")),
        ("industrial_heritage", ("zabytek techniki", "kopaln", "huta", "fabryk", "browar", "mlyn", "wiatrak", "water tower", "wieza wodna", "industrial")),
        ("historic_town", ("rynek", "stare miasto", "old town", "market square", "ratusz", "town hall", "zabytkowe centrum")),
        ("historic_site", ("reduta", "bastion", "most kamienny", "dom wagi miejskiej")),
        ("cultural_landmark", (
            "historic route", "historic road", "historyczna droga", "walkway", "boardwalk", "footbridge",
            "pasarela", "kładka", "kladka", "caminito", "aqueduct", "acueducto", "viaduct", "wiadukt",
            "engineering landmark", "heritage railway", "kolej zabytkowa", "scenic route",
        )),
        ("museum", ("muzeum", "museum", "gallery", "galeria")),
        ("nature", ("rezerwat", "nature reserve", "park krajobrazowy")),
    ]
    for category, markers in tests:
        if any(marker in text for marker in markers):
            return category, CATEGORY[category][1]
    historic = tags.get("historic")
    if historic and historic not in {"memorial", "wayside_cross", "wayside_shrine", "tomb"}:
        return "historic_site", f"OSM historic={historic}"
    unusual = ("unikat", "jedyny", "nietypow", "zabytek", "atrakcja turystyczna", "osobliw")
    major_types = ("tourist attraction", "cultural heritage", "historic site", "landmark",
                   "heritage site", "monumento", "sehenswurdigkeit")
    if wiki and (heritage or tags.get("tourism") in {"attraction", "museum"}
                 or any(marker in text for marker in unusual)
                 or any(marker in entity_kind for marker in major_types)):
        return "unusual_local", "opisane miejsce o potwierdzonej wartości"
    return None, "za mało dowodów wartości"


def _google_match(row: dict[str, Any], google_rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    best: tuple[float, dict[str, Any]] | None = None
    for item in google_rows:
        if item.get("lat") is None or item.get("lon") is None:
            continue
        distance = haversine_m(row["lat"], row["lon"], float(item["lat"]), float(item["lon"]))
        if distance > 300:
            continue
        similarity = SequenceMatcher(None, norm(row["name"]), norm(item.get("name"))).ratio()
        if similarity < 0.34 and distance > 80:
            continue
        value = similarity - distance / 1000.0
        if best is None or value > best[0]:
            best = (value, item)
    return best[1] if best else None


def _google_score(rating: Any, count: Any) -> float:
    if rating is None or count is None:
        return 0.0
    number = max(0, int(count))
    bayes = (number * float(rating) + 80 * 4.4) / (number + 80)
    # Google is evidence, never the semantic gate.
    return 3.5 * clamp((bayes - 4.0) / 0.8, 0, 1) + 2.5 * clamp(math.log10(number + 1) / 3, 0, 1)


def _distance_penalty(distance_m: float) -> float:
    if distance_m <= 300:
        return 0.0
    if distance_m <= 800:
        return 6.0 * (distance_m - 300) / 500
    return 6.0 + 12.0 * clamp((distance_m - 800) / 1200, 0, 1)


def score(row: dict[str, Any], entity: dict[str, Any], google_rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    category, why = classify(row, entity)
    if not category:
        return None
    base, label, visit_min, uniqueness = CATEGORY[category]
    tags = row.get("tags") or {}
    text = norm(f"{row.get('name')} {row.get('extract')} {entity_text(entity)}")
    visible_archaeology = category == "archaeology" and any(
        marker in text for marker in ("ruin", "wieza", "wal ", "waly", "mur ", "mury", "rekonstruk", "zamek")
    )
    if visible_archaeology:
        base += 14
        why = "archeologia z widoczną pozostałością"
    elif category == "archaeology":
        # Feedback z trasy wzorcowej: same wpisy "grodzisko" byly zwykle
        # poprawne historycznie, ale nie dawaly nic czytelnego do zobaczenia.
        base -= 18
        why = "archeologia bez potwierdzonej widocznej pozostałości"
    history = min(20, 12 * has_claim(entity, "P1435") + 6 * bool(row.get("pageid") or row.get("wiki"))
                  + 5 * bool(tags.get("heritage") or tags.get("heritage:operator"))
                  + 4 * bool(tags.get("historic")) + 2 * has_claim(entity, "P571"))
    bike = 15 if visit_min <= 20 else 12 if visit_min <= 30 else 8 if visit_min <= 45 else 6
    source_count = len(row.get("sources") or []) + bool(row.get("qid")) + bool(row.get("pageid"))
    quality = min(14, 3.5 * source_count + 2 * bool(row.get("extract")))
    google = _google_match(row, google_rows)
    meta = (google or {}).get("meta") or google or {}
    rating = meta.get("g_rating")
    rating_count = meta.get("g_rating_n")
    google_value = _google_score(rating, rating_count)
    distance_penalty = _distance_penalty(float(row["dist"]))
    time_penalty = 0 if visit_min <= 30 else 4 if visit_min <= 45 else 10 if visit_min <= 60 else 100
    total = base + history + bike + quality + google_value + uniqueness - distance_penalty - time_penalty
    if visit_min > 60:
        return None
    # Discovery owns the 2.05 km corridor. Distance is a ranking penalty, not
    # a second hard 800 m gate that can erase an exceptional short detour.
    if float(row["dist"]) > 2050:
        return None
    out = dict(row)
    out.update(
        category=category,
        category_label=label,
        visit_min=visit_min,
        rating=rating,
        rating_count=rating_count,
        score=round(clamp(total, 0, 100), 1),
        why=why,
        components={
            "category": base, "history": history, "bike": bike, "data": quality,
            "google": round(google_value, 1), "unique": uniqueness,
            "distance_penalty": round(distance_penalty, 1), "time_penalty": time_penalty,
        },
    )
    return out


def collapse_stops(scored: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    stops: list[dict[str, Any]] = []
    tangible = {"castle_palace", "fortification", "industrial_heritage", "open_air_museum"}
    for source in sorted(scored, key=lambda row: (-float(row["score"]), candidate_key(row))):
        row = dict(source)
        match = None
        for old in stops:
            if abs(float(row["km"]) - float(old["km"])) <= 1.5 and haversine_m(row["lat"], row["lon"], old["lat"], old["lon"]) <= 450:
                if ((row["category"] == "historic_town" and old["category"] in tangible)
                        or (old["category"] == "historic_town" and row["category"] in tangible)):
                    continue
                match = old
                break
        if match is None:
            row["nearby"] = []
            stops.append(row)
        elif row["category"] == "historic_town" and match["category"] != "historic_town":
            row["nearby"] = list(dict.fromkeys([match["name"], *match.get("nearby", [])]))
            stops[stops.index(match)] = row
        elif norm(row["name"]) != norm(match["name"]):
            match.setdefault("nearby", []).append(row["name"])
    return stops


def _mmr_select(
    rows: Iterable[dict[str, Any]],
    target: int,
    *,
    min_score: float = 48.0,
    proximity_weight: float = 1.0,
) -> list[dict[str, Any]]:
    pool = sorted(
        [dict(row) for row in rows if float(row["score"]) >= min_score],
        key=candidate_key,
    )
    chosen: list[dict[str, Any]] = []
    while pool and len(chosen) < target:
        best = None
        best_value = -999.0
        for row in pool:
            proximity = 0.0
            for old in chosen:
                gap = abs(float(row["km"]) - float(old["km"]))
                penalty = 12 if gap < 3 else 6 if gap < 8 else 2 if gap < 15 else 0
                if float(row["score"]) >= 80:
                    penalty *= 0.5
                proximity = max(proximity, penalty)
            value = float(row["score"]) - proximity * proximity_weight
            if value > best_value:
                best, best_value = row, value
        assert best is not None
        best["selection_score"] = round(best_value, 1)
        chosen.append(best)
        pool.remove(best)
    chosen.sort(key=lambda row: float(row["km"]))
    return chosen


def candidate_key(row: dict[str, Any]) -> str:
    if row.get("qid"):
        return f"wikidata:{row['qid']}"
    if row.get("google_place_id"):
        return f"google:{row['google_place_id']}"
    if row.get("osm_ids"):
        return f"osm:{row['osm_ids'][0]}"
    payload = f"{norm(row.get('name'))}|{float(row.get('lat') or 0):.5f}|{float(row.get('lon') or 0):.5f}"
    return "local:" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def rank_candidates(
    source_rows: Iterable[dict[str, Any]],
    google_rows: Iterable[dict[str, Any]],
    wikidata: dict[str, dict[str, Any]],
    route_distance_km: float,
) -> dict[str, Any]:
    merged = dedupe(source_rows)
    scored = [value for row in merged if (value := score(row, wikidata.get(row.get("qid"), {}), google_rows))]
    stops = collapse_stops(scored)
    candidate_target = max(1, math.ceil(route_distance_km / 100.0 * CANDIDATES_PER_100_KM))
    # Kandydaci sa lista do decyzji TAK/NIE, wiec pobliskie dobre obiekty nie
    # konkuruja ze soba. Rozlozenie po trasie dotyczy dopiero rekomendacji.
    candidates = _mmr_select(stops, candidate_target, proximity_weight=0.0)
    recommendation_target = max(1, math.ceil(route_distance_km / 100.0 * RECOMMENDED_PER_100_KM))
    recommended = _mmr_select(candidates, recommendation_target)
    recommended_keys = {candidate_key(row) for row in recommended}
    result_rows = []
    for rank, row in enumerate(candidates, 1):
        key = candidate_key(row)
        result_rows.append({
            "candidate_key": key,
            "name": row["name"],
            "km": round(float(row["km"]), 1),
            "distance_m": round(float(row["dist"])),
            "category": row["category"],
            "category_label": row["category_label"],
            "visit_min": row["visit_min"],
            "score": row["score"],
            "selection_score": row["selection_score"],
            "candidate_rank": rank,
            "is_recommended": key in recommended_keys,
            "recommended_rank": next((idx for idx, item in enumerate(recommended, 1) if candidate_key(item) == key), None),
            "rating": row.get("rating"),
            "rating_count": row.get("rating_count"),
            "why": row["why"],
            "components": row["components"],
            "sources": sorted(row.get("sources") or []),
            "wiki": row.get("wiki"),
            "qid": row.get("qid"),
            "extract": str(row.get("extract") or "")[:650].strip(),
            "image": row.get("image"),
            "lat": round(float(row["lat"]), 6),
            "lon": round(float(row["lon"]), 6),
            "osm_ids": row.get("osm_ids") or [],
            "nearby": row.get("nearby") or [],
        })
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "summary": {
            "merged": len(merged), "scored": len(scored), "stops": len(stops),
            "candidates": len(result_rows), "recommended": len(recommended),
        },
        "candidates": result_rows,
    }


def result_hash(result: dict[str, Any]) -> str:
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
