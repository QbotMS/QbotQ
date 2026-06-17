#!/usr/bin/env python3
"""
Odpytaj Overpass API dla etapu 1 z buforem 2km.
Szukaj: woda pitna, sklepy spożywcze, kawiarnie, restauracje, bary.
Zaktualizuj qbot_planning_facts id=5.
"""
import httpx, json, xml.etree.ElementTree as ET, os, psycopg, subprocess
from psycopg.rows import dict_row

# Załaduj GPX etapu 1
gpx_path = '/opt/qbot/artifacts/canonical/tuscany_2026/gpx/tuscany_2026_stage_01_55395117.gpx'
tree = ET.parse(gpx_path)
ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
# Pobierz punkty trasy (co 50. punkt żeby nie przeciążać)
trkpts = tree.findall('.//gpx:trkpt', ns)
if not trkpts:
    trkpts = tree.findall('.//{http://www.topografix.com/GPX/1/0}trkpt')
points = [(float(p.get('lat')), float(p.get('lon'))) for p in trkpts[::10]]
print(f"Track points sampled: {len(points)}")

# Bbox z marginesem
lats = [p[0] for p in points]
lons = [p[1] for p in points]
bbox = f"{min(lats)-0.02},{min(lons)-0.02},{max(lats)+0.02},{max(lons)+0.02}"
print(f"BBox: {bbox}")

# Overpass query — woda, jedzenie, sklepy w bbox
query = f"""
[out:json][timeout:60];
(
  node["amenity"="drinking_water"]({bbox});
  node["amenity"="water_point"]({bbox});
  node["man_made"="water_tap"]({bbox});
  node["amenity"="restaurant"]({bbox});
  node["amenity"="cafe"]({bbox});
  node["amenity"="bar"]({bbox});
  node["shop"="supermarket"]({bbox});
  node["shop"="convenience"]({bbox});
  node["shop"="food"]({bbox});
  node["shop"="greengrocer"]({bbox});
);
out body;
"""

print("Querying Overpass API...")
resp = httpx.post("https://overpass-api.de/api/interpreter", data=query, timeout=60)
data = resp.json()
elements = data.get('elements', [])
print(f"Found {len(elements)} OSM elements")

# Oblicz dystans każdego POI do najbliższego punktu trasy
import math

def dist_m(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def nearest_km(poi_lat, poi_lon, track_points):
    """Zwróć (min_dist_m, km_along_track)"""
    best_dist = float('inf')
    best_idx = 0
    for i, (lat, lon) in enumerate(track_points):
        d = dist_m(poi_lat, poi_lon, lat, lon)
        if d < best_dist:
            best_dist = d
            best_idx = i
    # Przybliżony km wzdłuż trasy
    km = 0
    for i in range(1, best_idx + 1):
        km += dist_m(track_points[i-1][0], track_points[i-1][1],
                     track_points[i][0], track_points[i][1]) / 1000
    return round(best_dist), round(km, 1)

# Filtruj: max 2000m od trasy
water_pois = []
food_pois = []
MAX_DIST = 2000

for el in elements:
    lat, lon = el.get('lat'), el.get('lon')
    if lat is None or lon is None:
        continue
    lat, lon = float(lat), float(lon)
    tags = el.get('tags', {})
    amenity = tags.get('amenity', '')
    shop = tags.get('shop', '')
    name = tags.get('name', tags.get('amenity', tags.get('shop', 'Unknown')))
    osm_id = el.get('id')

    dist_m_val, km_val = nearest_km(lat, lon, points)
    if dist_m_val > MAX_DIST:
        continue

    poi = {
        "osm_id": osm_id,
        "name": name,
        "lat": lat,
        "lon": lon,
        "km": km_val,
        "distance_to_track_m": dist_m_val,
        "tags": tags
    }

    if amenity in ('drinking_water', 'water_point') or tags.get('man_made') == 'water_tap':
        water_pois.append(poi)
    elif amenity in ('restaurant', 'cafe', 'bar') or shop in ('supermarket', 'convenience', 'food', 'greengrocer'):
        food_pois.append(poi)

water_pois.sort(key=lambda x: x['km'])
food_pois.sort(key=lambda x: x['km'])

print(f"\nWater POI (max 2km): {len(water_pois)}")
for p in water_pois:
    print(f"  km {p['km']:5.1f} | {p['distance_to_track_m']:4}m | {p['name']}")

print(f"\nFood/Shop POI (max 2km): {len(food_pois)}")
for p in food_pois:
    amenity_type = p['tags'].get('amenity', p['tags'].get('shop', '?'))
    print(f"  km {p['km']:5.1f} | {p['distance_to_track_m']:4}m | [{amenity_type}] {p['name']}")

# Zaktualizuj planning_facts id=5
pg_pwd = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $PGPASSWORD",
    shell=True, executable='/bin/bash').decode().strip()

conn = psycopg.connect(host='127.0.0.1', port='5432', dbname='qbot', user='qbot',
    password=pg_pwd, row_factory=dict_row, autocommit=True,
    options='-c search_path=qbot_v2')

# Pobierz obecny fact_json
row = conn.execute("SELECT fact_json FROM qbot_planning_facts WHERE id=5").fetchone()
fj = row['fact_json'] if row else {}

fj['water'] = water_pois
fj['food'] = food_pois
fj['poi_buffer_m'] = MAX_DIST
fj['poi_source'] = 'overpass_api'
fj['poi_updated'] = '2026-06-02'

conn.execute("UPDATE qbot_planning_facts SET fact_json=%s WHERE id=5", (json.dumps(fj),))
conn.close()

print(f"\nUpdated planning_facts id=5: {len(water_pois)} water, {len(food_pois)} food POI")
