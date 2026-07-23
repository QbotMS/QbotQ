"""Google Places enrichment for food POI from OSM candidates."""
from __future__ import annotations
import os, time, logging
from typing import Any
import httpx

log = logging.getLogger("google_places")
PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
CHAIN_BLACKLIST = {"mcdonald","burger king","kfc","subway","starbucks","domino","pizza hut","hard rock","autogrill","ristop"}

def _api_key():
    return os.environ.get("GOOGLE_PLACES_API_KEY")

def _search_nearby(lat, lon, radius_m, api_key):
    payload = {"includedTypes": ["restaurant","cafe","bar","bakery"],"maxResultCount": 5,"locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon},"radius": radius_m}}}
    headers = {"Content-Type": "application/json","X-Goog-Api-Key": api_key,"X-Goog-FieldMask": "places.id,places.displayName,places.rating,places.userRatingCount,places.priceLevel,places.currentOpeningHours"}
    from qbot3.routes.google_places_budget import check_and_reserve
    check_and_reserve(1)
    resp = httpx.post(PLACES_URL, json=payload, headers=headers, timeout=10.0)
    resp.raise_for_status()
    return resp.json().get("places", [])

PRICE_MAP = {"PRICE_LEVEL_FREE":0,"PRICE_LEVEL_INEXPENSIVE":1,"PRICE_LEVEL_MODERATE":2,"PRICE_LEVEL_EXPENSIVE":3,"PRICE_LEVEL_VERY_EXPENSIVE":4}

def _best_match(poi, places, min_rating, max_price):
    if not places:
        return None
    osm_name = (poi.get("name") or "").lower()
    best, best_score = None, -1
    for p in places:
        rating = float(p.get("rating") or 0)
        if 0 < rating < min_rating:
            continue
        price_num = PRICE_MAP.get(p.get("priceLevel",""), 2)
        if price_num > max_price:
            continue
        g_name = (p.get("displayName",{}).get("text") or "").lower()
        name_score = 2 if (osm_name and osm_name in g_name) else (1 if osm_name and any(w in g_name for w in osm_name.split() if len(w)>3) else 0)
        score = rating + name_score
        if score > best_score:
            best_score = score
            best = p
    return best

def enrich_food_pois(pois, radius_m=100.0, min_rating=3.8, max_price_level=2):
    """Enrich food POI with Google Places data. Drops chains and low-rated places."""
    api_key = _api_key()
    if not api_key:
        log.warning("GOOGLE_PLACES_API_KEY not set")
        return pois
    enriched = []
    for poi in pois:
        lat = float(poi.get("lat") or 0)
        lon = float(poi.get("lon") or poi.get("lng") or 0)
        if not lat or not lon:
            enriched.append(poi)
            continue
        try:
            places = _search_nearby(lat, lon, radius_m, api_key)
            place = _best_match(poi, places, min_rating, max_price_level)
            if place is None:
                enriched.append(dict(poi, google_verified=False, google_skip_reason="no_match"))
                continue
            name = place.get("displayName",{}).get("text","")
            if any(c in name.lower() for c in CHAIN_BLACKLIST):
                continue  # drop chains
            oh = place.get("currentOpeningHours") or {}
            poi = dict(poi, google_verified=True, google_name=name,
                google_rating=place.get("rating",0),
                google_price_level=PRICE_MAP.get(place.get("priceLevel",""),2),
                google_open_now=oh.get("openNow"),
                google_user_ratings_total=place.get("userRatingCount",0),
                google_place_id=place.get("id",""))
            enriched.append(poi)
            time.sleep(0.05)
        except Exception as exc:
            log.warning("Google Places error %s: %s", poi.get("name"), exc)
            enriched.append(dict(poi, google_verified=False, google_error=str(exc)[:100]))
    return enriched

def filter_local_food(pois, min_rating=3.8):
    """Keep only local, well-rated places after enrichment."""
    result = []
    for p in pois:
        if p.get("google_skip_reason") == "chain":
            continue
        if not p.get("google_verified"):
            result.append(p)
            continue
        if p.get("google_rating", 0) >= min_rating:
            result.append(p)
    return result
