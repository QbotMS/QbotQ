#!/usr/bin/env python3
"""Pobierz Google Places POI dla etapów 2-7 Toskanii."""
import json, os, time, subprocess, psycopg, xml.etree.ElementTree as ET, math, httpx
from psycopg.rows import dict_row

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
api_key = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $GOOGLE_PLACES_API_KEY",
    shell=True, executable='/bin/bash').decode().strip()
pg_pwd = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $PGPASSWORD",
    shell=True, executable='/bin/bash').decode().strip()

STAGES = [
    (2, "55444268", 6),
    (3, "55444735", 7),
    (4, "55395123", 8),
    (5, "55395124", 9),
    (6, "55395125", 10),
    (7, "55395129", 11),
]

CHAIN_BLACKLIST = {"mcdonald","burger king","kfc","subway","starbucks","autogrill"}
INCLUDED_TYPES = ["restaurant","cafe","bar","bakery","supermarket","convenience_store","grocery_store","food_store"]

def dist_m(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2-lat1); dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def load_gpx(route_id):
    path = f"/opt/qbot/artifacts/canonical/tuscany_2026/gpx/tuscany_2026_stage_0{route_id[-1]}_{route_id}.gpx"
    # Szukaj po route_id w nazwie
    import glob
    matches = glob.glob(f"/opt/qbot/artifacts/canonical/tuscany_2026/gpx/*{route_id}*.gpx")
    if not matches:
        return []
    tree = ET.parse(matches[0])
    pts = tree.findall('.//{http://www.topografix.com/GPX/1/1}trkpt') or \
          tree.findall('.//{http://www.topografix.com/GPX/1/0}trkpt')
    return [(float(p.get('lat')), float(p.get('lon'))) for p in pts]

def sample_points(points, step_km=8):
    result = []
    km_acc = 0
    last_km = -step_km
    for i in range(1, len(points)):
        km_acc += dist_m(points[i-1][0], points[i-1][1], points[i][0], points[i][1]) / 1000
        if km_acc - last_km >= step_km:
            result.append((points[i][0], points[i][1], round(km_acc, 1)))
            last_km = km_acc
    return result

def search_nearby(lat, lon, radius=2000):
    payload = {
        "includedTypes": INCLUDED_TYPES,
        "maxResultCount": 10,
        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": radius}}
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.rating,places.location,places.types"
    }
    try:
        resp = httpx.post(PLACES_URL, json=payload, headers=headers, timeout=10)
        return resp.json().get("places", []) if resp.status_code == 200 else []
    except:
        return []

for stage_n, route_id, fact_id in STAGES:
    print(f"\n=== Etap {stage_n} (route {route_id}, fact_id {fact_id}) ===")
    points = load_gpx(route_id)
    if not points:
        print(f"  BRAK GPX dla {route_id}")
        continue
    print(f"  GPX: {len(points)} punktów")

    samples = sample_points(points)
    print(f"  Sample co 8km: {len(samples)} punktów")

    all_food = {}
    for lat, lon, km in samples:
        places = search_nearby(lat, lon)
        for p in places:
            pid = p.get("id")
            if pid in all_food:
                continue
            name = p.get("displayName", {}).get("text", "")
            if any(c in name.lower() for c in CHAIN_BLACKLIST):
                continue
            ploc = p.get("location", {})
            plat = ploc.get("latitude", lat)
            plon = ploc.get("longitude", lon)
            min_d = min(int(dist_m(plat, plon, pt[0], pt[1])) for pt in points[::5])
            all_food[pid] = {
                "osm_id": pid, "name": name,
                "lat": plat, "lon": plon, "km": km,
                "distance_to_track_m": min_d,
                "rating": p.get("rating", 0),
                "types": p.get("types", []),
                "source": "google_places"
            }
        time.sleep(0.1)

    food_list = sorted(all_food.values(), key=lambda x: x['km'])
    print(f"  Food POI: {len(food_list)}")
    for p in food_list[:5]:
        print(f"    km {p['km']:5.1f} | {p['distance_to_track_m']:4}m | {p['name'][:40]}")
    if len(food_list) > 5:
        print(f"    ... i {len(food_list)-5} więcej")

    # Zapisz do planning_facts
    conn = psycopg.connect(host='127.0.0.1', port='5432', dbname='qbot', user='qbot',
        password=pg_pwd, row_factory=dict_row, autocommit=True,
        options='-c search_path=qbot_v2')
    row = conn.execute(f"SELECT fact_json FROM qbot_planning_facts WHERE id={fact_id}").fetchone()
    if row:
        fj = row['fact_json'] or {}
        fj['food'] = food_list
        fj['food_source'] = 'google_places'
        fj['food_updated'] = '2026-06-02'
        fj['poi_buffer_m'] = 2000
        conn.execute(f"UPDATE qbot_planning_facts SET fact_json=%s WHERE id={fact_id}", (json.dumps(fj),))
        print(f"  DB updated (fact_id={fact_id})")
    else:
        print(f"  BRAK fact_id={fact_id} w DB")
    conn.close()

print("\n=== DONE ===")
