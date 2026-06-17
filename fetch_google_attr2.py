#!/usr/bin/env python3
"""Pobierz Google Places ATRAKCJE (museum/winery/historical) dla etapów 1-7."""
import json, time, subprocess, psycopg, xml.etree.ElementTree as ET, math, httpx, glob
from psycopg.rows import dict_row

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
api_key = "AIzaSyA5tC4gljF_THElQUbSCQM5GT-1nDNMZZ0"
pg_pwd = subprocess.check_output(
    "source /etc/qbot/qbot-api.env && echo $PGPASSWORD",
    shell=True, executable='/bin/bash').decode().strip()

STAGES = [
    (1,"55395117",5),(2,"55444268",6),(3,"55444735",7),
    (4,"55395123",8),(5,"55395124",9),(6,"55395125",10),(7,"55395129",11),
]

# Typy które faktycznie działają w Google Places New API
ATTRACTION_TYPES = [
    "museum", "winery", "historical_landmark", "art_gallery",
    "cultural_center", "ruins", "castle", "national_park", "garden",
    "monument", "chapel", "tourist_attraction",
]

def dist_m(lat1,lon1,lat2,lon2):
    R=6371000; dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
    a=math.sin(dlat/2)**2+math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R*2*math.asin(math.sqrt(a))

def load_gpx(route_id):
    matches = glob.glob(f"/opt/qbot/artifacts/canonical/tuscany_2026/gpx/*{route_id}*.gpx")
    if not matches: return []
    tree = ET.parse(matches[0])
    pts = tree.findall('.//{http://www.topografix.com/GPX/1/1}trkpt') or \
          tree.findall('.//{http://www.topografix.com/GPX/1/0}trkpt')
    return [(float(p.get('lat')),float(p.get('lon'))) for p in pts]

def sample_points(points, step_km=10):
    result=[]; km_acc=0; last_km=-step_km
    for i in range(1,len(points)):
        km_acc += dist_m(*points[i-1],*points[i])/1000
        if km_acc-last_km>=step_km:
            result.append((points[i][0],points[i][1],round(km_acc,1))); last_km=km_acc
    return result

def search_nearby(lat,lon,types,radius=4000):
    payload={"includedTypes":types,"maxResultCount":10,
             "locationRestriction":{"circle":{"center":{"latitude":lat,"longitude":lon},"radius":radius}}}
    headers={"Content-Type":"application/json","X-Goog-Api-Key":api_key,
             "X-Goog-FieldMask":"places.id,places.displayName,places.rating,places.userRatingCount,places.location,places.types,places.editorialSummary"}
    try:
        resp=httpx.post(PLACES_URL,json=payload,headers=headers,timeout=10)
        return resp.json().get("places",[]) if resp.status_code==200 else []
    except: return []

conn = psycopg.connect(host='127.0.0.1',port='5432',dbname='qbot',user='qbot',
    password=pg_pwd,row_factory=dict_row,autocommit=True,options='-c search_path=qbot_v2')

for stage_n,route_id,fact_id in STAGES:
    print(f"\n=== Etap {stage_n} ===")
    points = load_gpx(route_id)
    if not points: print("  BRAK GPX"); continue
    samples = sample_points(points,step_km=10)
    all_attr = {}

    for lat,lon,km in samples:
        # Pytaj po 3 typy naraz (API limit)
        for type_batch in [ATTRACTION_TYPES[:5], ATTRACTION_TYPES[5:]]:
            places = search_nearby(lat,lon,type_batch,radius=4000)
            for p in places:
                pid = p.get("id")
                if pid in all_attr: continue
                name = p.get("displayName",{}).get("text","")
                ploc = p.get("location",{}); plat=ploc.get("latitude",lat); plon=ploc.get("longitude",lon)
                min_d = min(int(dist_m(plat,plon,pt[0],pt[1])) for pt in points[::5])
                if min_d > 5000: continue  # max 5km
                all_attr[pid] = {
                    "osm_id":pid,"name":name,"lat":plat,"lon":plon,"km":km,
                    "distance_to_track_m":min_d,"rating":p.get("rating",0),
                    "user_ratings":p.get("userRatingCount",0),
                    "types":p.get("types",[]),
                    "summary":p.get("editorialSummary",{}).get("text",""),
                    "source":"google_places"
                }
            time.sleep(0.05)

    attr_list = sorted(all_attr.values(), key=lambda x: x['km'])
    print(f"  Atrakcje: {len(attr_list)}")
    for a in attr_list[:5]:
        t=(a['types'][0] if a.get('types') else '?')
        print(f"    km{a['km']:5.1f} | {a['distance_to_track_m']:4}m | [{t}] {a['name'][:45]} ({a.get('rating','?')})")
    if len(attr_list)>5: print(f"    ... i {len(attr_list)-5} więcej")

    row = conn.execute(f"SELECT fact_json FROM qbot_planning_facts WHERE id={fact_id}").fetchone()
    if row:
        fj = row['fact_json'] or {}
        fj['attractions_google'] = attr_list
        fj['attractions_source'] = 'osm+google_places'
        fj['attractions_updated'] = '2026-06-02'
        conn.execute(f"UPDATE qbot_planning_facts SET fact_json=%s WHERE id={fact_id}",(json.dumps(fj),))
        print(f"  DB: {len(attr_list)} Google + {len(fj.get('attractions',[]))} OSM")

conn.close()
print("\n=== DONE ===")
