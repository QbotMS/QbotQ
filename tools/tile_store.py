import os,sys,json,math,httpx
from pathlib import Path
from datetime import datetime
from typing import Any

APP_DIR=Path("/opt/qbot/app")
TILES_CACHE=Path("/opt/qbot/artifacts/tiles")
TILES_CACHE.mkdir(parents=True,exist_ok=True)

# StatsHunters share API — zwraca kafelki zoom=14 jako lista [x,y]
STATSHUNTERS_BASE="https://statshunters.com/api/share"

def _env():
    return dict(l.strip().split("=",1) for l in open(APP_DIR/".env.local") if "=" in l and not l.startswith("#"))

# ── Tile Store ────────────────────────────────────────────────────────────────

def fetch_tiles(share_id: str, force: bool=False) -> dict:
    """Pobierz kafelki z StatsHunters share API (activities endpoint, paginated)."""
    cache_file=TILES_CACHE/"{}_tiles.json".format(share_id)
    if cache_file.exists() and not force:
        data=json.loads(cache_file.read_text())
        age_h = (datetime.now() - datetime.fromisoformat(data.get("fetched_at","2000-01-01"))).total_seconds()/3600
        if age_h < 24:
            return {"source":"cache","count":data["count"],"tiles":data["tiles"],"fetched_at":data["fetched_at"]}
    try:
        all_tiles=set()
        base="https://www.statshunters.com/share/{}/api/activities".format(share_id)
        headers={"Accept":"application/json","User-Agent":"QBot/3.0"}
        page=1
        while True:
            r=httpx.get(base,params={"page":page},timeout=30.0,headers=headers)
            r.raise_for_status()
            raw=r.json()
            activities=raw.get("activities",[])
            if not activities:
                break
            for act in activities:
                for t in act.get("tiles",[]):
                    if isinstance(t,dict):
                        all_tiles.add((t["x"],t["y"]))
                    elif isinstance(t,(list,tuple)) and len(t)==2:
                        all_tiles.add((t[0],t[1]))
            page+=1
            if page>200:  # safety limit
                break
        tiles_list=[[x,y] for x,y in sorted(all_tiles)]
        data={"share_id":share_id,"count":len(tiles_list),"tiles":tiles_list,"fetched_at":datetime.now().isoformat(),"pages_fetched":page-1}
        cache_file.write_text(json.dumps(data,ensure_ascii=False))
        return {"source":"api","count":len(tiles_list),"tiles":tiles_list,"fetched_at":data["fetched_at"],"pages":page-1}
    except Exception as exc:
        return {"_error":str(exc),"count":0,"tiles":[]}

def load_tiles_from_gpx_history(gpx_dir: str, zoom: int=14) -> set[tuple[int,int]]:
    """Wyciagnij przejechane kafelki z lokalnych plikow GPX.
    Konwertuje wspolrzedne GPS -> tile x,y przy danym zoom.
    """
    tiles=set()
    for gpx_file in Path(gpx_dir).glob("*.gpx"):
        try:
            from qbot3.artifacts.route_analyzer import _parse_gpx_file_detailed
            pts=_parse_gpx_file_detailed(gpx_file)
            for p in pts:
                lat,lon=p.get("lat",0),p.get("lon",0)
                if lat and lon:
                    tiles.add(_latlon_to_tile(lat,lon,zoom))
        except Exception: pass
    return tiles

def _latlon_to_tile(lat: float, lon: float, zoom: int=14) -> tuple[int,int]:
    """Konwertuj lat/lon na tile x,y dla danego zoom (standard OSM)."""
    n=2**zoom
    x=int((lon+180)/360*n)
    y=int((1-math.log(math.tan(math.radians(lat))+1/math.cos(math.radians(lat)))/math.pi)/2*n)
    return (x,y)

def _tile_to_latlon(x: int, y: int, zoom: int=14) -> tuple[float,float]:
    """Centrum kafelka -> lat/lon."""
    n=2**zoom
    lon=(x+0.5)/n*360-180
    lat_rad=math.atan(math.sinh(math.pi*(1-2*(y+0.5)/n)))
    return (math.degrees(lat_rad),lon)

def get_tile_set(tiles_data: list) -> set[tuple[int,int]]:
    """Konwertuj liste kafelkow do setu (x,y)."""
    result=set()
    for t in tiles_data:
        if isinstance(t,list) and len(t)>=2: result.add((int(t[0]),int(t[1])))
        elif isinstance(t,dict): result.add((int(t.get("x",t.get("tx",0))),int(t.get("y",t.get("ty",0)))))
    return result

# ── Uberkwadrat ───────────────────────────────────────────────────────────────

def find_uberkwadrat(tile_set: set[tuple[int,int]]) -> dict:
    """Znajdz najwiekszy ciagly prostokatny blok kafelkow (Uberkwadrat).
    Algorytm: maximal rectangle in histogram (O(n*m)).
    Zwraca: {x_min, y_min, x_max, y_max, width, height, area, center_lat, center_lon}
    """
    if not tile_set: return {"area":0,"width":0,"height":0}
    xs=[t[0] for t in tile_set]; ys=[t[1] for t in tile_set]
    x0,x1,y0,y1=min(xs),max(xs),min(ys),max(ys)
    W,H=x1-x0+1,y1-y0+1
    # Macierz obecnosci
    grid=[[1 if (x0+c,y0+r) in tile_set else 0 for c in range(W)] for r in range(H)]
    # Histogram approach
    best={"area":0,"x_min":0,"y_min":0,"x_max":0,"y_max":0}
    hist=[0]*W
    for r in range(H):
        for c in range(W): hist[c]=hist[c]+1 if grid[r][c] else 0
        # Max rectangle in histogram
        stack=[]; mx=_max_rect_histogram(hist,r,x0,y0)
        if mx["area"]>best["area"]: best=mx
    cx,cy=(best["x_min"]+best["x_max"])//2,(best["y_min"]+best["y_max"])//2
    clat,clon=_tile_to_latlon(cx,cy,14)
    best["width"]=best["x_max"]-best["x_min"]+1
    best["height"]=best["y_max"]-best["y_min"]+1
    best["center_lat"]=round(clat,6); best["center_lon"]=round(clon,6)
    return best

def _max_rect_histogram(hist: list, row: int, x0: int, y0: int) -> dict:
    stack=[]; best={"area":0,"x_min":0,"y_min":0,"x_max":0,"y_max":0}
    for i,h in enumerate(hist+[0]):
        start=i
        while stack and stack[-1][1]>h:
            j,hj=stack.pop()
            area=hj*(i-j)
            if area>best["area"]:
                best={"area":area,"x_min":x0+j,"x_max":x0+i-1,"y_min":y0+row-hj+1,"y_max":y0+row}
            start=j
        stack.append((start,h))
    return best

# ── Route Builder ─────────────────────────────────────────────────────────────

def new_tiles_on_route(track_points: list, existing_tiles: set, zoom: int=14) -> list[tuple[int,int]]:
    """Zwroc liste nowych kafelkow ktore trasa by przebyla."""
    new=[]
    for p in track_points:
        lat,lon=p.get("y",0) or p.get("lat",0), p.get("x",0) or p.get("lon",0)
        if not lat or not lon: continue
        tile=_latlon_to_tile(lat,lon,zoom)
        if tile not in existing_tiles and tile not in [t for t in new]: new.append(tile)
    return new

def score_route_for_tiles(track_points: list, existing_tiles: set, target_new_pct: float=0.3) -> dict:
    """Ocen trase pod katem nowych kafelkow."""
    if not track_points: return {"score":0,"new_tiles":0,"total_tiles":0,"new_pct":0}
    seen=set(); new=0
    for p in track_points:
        lat,lon=p.get("y",0) or p.get("lat",0),p.get("x",0) or p.get("lon",0)
        if not lat or not lon: continue
        tile=_latlon_to_tile(lat,lon,14)
        if tile not in seen:
            seen.add(tile)
            if tile not in existing_tiles: new+=1
    total=len(seen); new_pct=new/total if total else 0
    score=min(1.0,new_pct/target_new_pct) if target_new_pct>0 else 0
    return {"score":round(score,3),"new_tiles":new,"total_tiles":total,"new_pct":round(new_pct,3)}

def build_route_report(share_id: str, route_id: str | None=None, gpx_path: str | None=None) -> dict:
    """Pelny raport: pobierz kafelki z SH, przeanalizuj trase, policzy Uberkwadrat."""
    tile_data=fetch_tiles(share_id)
    existing=get_tile_set(tile_data.get("tiles",[]))
    result={"share_id":share_id,"existing_tiles_count":len(existing),
            "tile_source":tile_data.get("source"),"tile_error":tile_data.get("_error")}
    uberkwadrat=find_uberkwadrat(existing)
    result["uberkwadrat"]=uberkwadrat
    if route_id or gpx_path:
        try:
            env=_env()
            if route_id:
                url="https://ridewithgps.com/routes/{}.json?apikey={}&auth_token={}&version=2".format(
                    route_id,env.get("RWGPS_API_KEY",""),env.get("RWGPS_AUTH_TOKEN",""))
                tp=httpx.get(url,timeout=15.0).json().get("route",{}).get("track_points",[])
            else:
                from qbot3.artifacts.route_analyzer import _parse_gpx_file_detailed
                pts=_parse_gpx_file_detailed(Path(gpx_path))
                tp=[{"y":p["lat"],"x":p["lon"]} for p in pts]
            score=score_route_for_tiles(tp,existing)
            result["route_tile_score"]=score
        except Exception as exc: result["route_error"]=str(exc)
    return result
