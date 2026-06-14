#!/usr/bin/env python3
"""
Odpytaj Google Places wzdłuż etapu 1 co 8km, radius 2km.
Szukaj: woda pitna, sklepy, kawiarnie, restauracje, bary, piekarnie.
Zaktualizuj planning_facts id=5.
"""
import json, os, time, subprocess, psycopg, xml.etree.ElementTree as ET, math, httpx
from psycopg.rows import dict_row

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
api_key = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $GOOGLE_PLACES_API_KEY",
    shell=True, executable='/bin/bash').decode().strip()
pg_pwd = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $PGPASSWORD",
    shell=True, executable='/bin/bash').decode().strip()

print(f"API key: {api_key[:8]}...")

# Załaduj GPX etapu 1
gpx_path = '/opt/qbot/artifacts/canonical/tuscany_2026/gpx/tuscany_2026_stage_01_55395117.gpx'
tree = ET.parse(gpx_path)
trkpts = tree.findall('.//{http://www.topografix.com/GPX/1/1}trkpt') or \
         tree.findall('.//{http://www.topografix.com/GPX/1/0}trkpt')
points = [(float(p.get('lat')), float(p.get('lon'))) for p in trkpts]
print(f"Track points: {len(points)}")

# Oblicz km wzdłuż trasy
def dist_m(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# Wybierz punkty co ~8km
sample_points = []
km_acc = 0
last_km = -8
for i in range(1, len(points)):
    km_acc += dist_m(points[i-1][0], points[i-1][1], points[i][0], points[i][1]) / 1000
    if km_acc - last_km >= 8:
        sample_points.append((points[i][0], points[i][1], round(km_acc, 1)))
        last_km = km_acc

print(f"Sample points co 8km: {len(sample_points)}")

# Zapytaj Google Places dla każdego punktu
RADIUS_M = 2000
INCLUDED_TYPES_FOOD = ["restaurant", "cafe", "bar", "bakery", "supermarket", "convenience_store", "food_store", "grocery_store"]
INCLUDED_TYPES_WATER = ["drinking_water"]

def search_nearby(lat, lon, types, radius=RADIUS_M):
    payload = {
        "includedTypes": types,
        "maxResultCount": 10,
        "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": radius}}
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.rating,places.userRatingCount,places.location,places.types"
    }
    try:
        resp = httpx.post(PLACES_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("places", [])
        else:
            print(f"  HTTP {resp.status_code}: {resp.text[:100]}")
            return []
    except Exception as e:
        print(f"  Error: {e}")
        return []

CHAIN_BLACKLIST = {"mcdonald", "burger king", "kfc", "subway", "starbucks", "autogrill"}

all_food = {}  # place_id -> poi
all_water = {}

for lat, lon, km in sample_points:
    print(f"\nKm {km:5.1f} ({lat:.4f}, {lon:.4f}):")

    # Jedzenie
    places = search_nearby(lat, lon, INCLUDED_TYPES_FOOD)
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
        d = int(dist_m(plat, plon, lat, lon))
        # Dystans do trasy — szukamy min od wszystkich punktów (uproszczone)
        min_d = min(int(dist_m(plat, plon, pt[0], pt[1])) for pt in points[::5])
        # Przybliżony km na trasie
        nearest_km = km
        all_food[pid] = {
            "osm_id": pid,
            "name": name,
            "lat": plat, "lon": plon,
            "km": nearest_km,
            "distance_to_track_m": min_d,
            "rating": p.get("rating", 0),
            "types": p.get("types", []),
            "source": "google_places"
        }
        print(f"  FOOD: {name} ({min_d}m od trasy, rating: {p.get('rating','?')})")

    time.sleep(0.1)

print(f"\n=== Wyniki ===")
food_list = sorted(all_food.values(), key=lambda x: x['km'])
print(f"Food/Shop POI: {len(food_list)}")
for p in food_list:
    t = p['types'][0] if p.get('types') else '?'
    print(f"  km {p['km']:5.1f} | {p['distance_to_track_m']:4}m | [{t}] {p['name']} (rating: {p.get('rating','?')})")

# Zaktualizuj planning_facts
conn = psycopg.connect(host='127.0.0.1', port='5432', dbname='qbot', user='qbot',
    password=pg_pwd, row_factory=dict_row, autocommit=True,
    options='-c search_path=qbot_v2')

row = conn.execute("SELECT fact_json FROM qbot_planning_facts WHERE id=5").fetchone()
fj = row['fact_json'] if row else {}

# Zachowaj obecne dane wody z OSM, dodaj Google food
existing_water = fj.get('water', [])
fj['food'] = food_list
fj['food_source'] = 'google_places'
fj['food_updated'] = '2026-06-02'
fj['poi_buffer_m'] = RADIUS_M

conn.execute("UPDATE qbot_planning_facts SET fact_json=%s WHERE id=5",
             (json.dumps(fj),))
conn.close()
print(f"\nUpdated planning_facts id=5: {len(food_list)} food POI (Google Places)")
print(f"Water POI: {len(existing_water)} (zachowane z OSM)")
