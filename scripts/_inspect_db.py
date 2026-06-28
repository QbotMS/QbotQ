import os,json
from collections import Counter
from pathlib import Path
def load_env():
    p=Path('/opt/qbot/app/.env.local')
    for line in p.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        if line.startswith('export '): line=line[7:]
        k,_,v=line.partition('=')
        v=v.strip()
        if len(v)>=2 and v[0]==v[-1] and v[0] in ("'",'"'): v=v[1:-1]
        os.environ.setdefault(k.strip(),v)
load_env()
try:
    import psycopg2
except ModuleNotFoundError:
    import psycopg as psycopg2
con=psycopg2.connect(host=os.getenv('PGHOST','127.0.0.1'),port=int(os.getenv('PGPORT','5432')),user=os.getenv('PGUSER','qbot'),dbname=os.getenv('PGDATABASE','qbot'),password=os.getenv('PGPASSWORD'))
cur=con.cursor()
cur.execute("select count(*),(select count(*) from qbot_v2.route_surface_segments where route_surface_profile_id=12 and geometry_json is not null) from qbot_v2.route_surface_segments where route_surface_profile_id=12")
print("segments total, with_geom:", cur.fetchone())
cur.execute("select surface,count(*),sum(distance_m) from qbot_v2.route_surface_segments where route_surface_profile_id=12 group by surface order by 3 desc")
print("by surface:")
for r in cur.fetchall(): print("  ",r)
cur.execute("select segment_index,distance_m,surface,confidence,start_lat,start_lon,geometry_json from qbot_v2.route_surface_segments where route_surface_profile_id=12 order by segment_index limit 3")
for r in cur.fetchall():
    gj=r[6]
    print("seg",r[0],"dist",round(r[1]),"surf",r[2],"conf",r[3],"geomtype",type(gj),"glen", (len(gj) if hasattr(gj,'__len__') else None))
    print("  geom sample:", json.dumps(gj)[:200])
