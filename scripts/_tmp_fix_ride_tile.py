p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()

old='''rr.forEach(function(r){var km=r.dist_km?qN(r.dist_km,0)+"km":"";var x=r.xss?"obc."+r.xss:"";h+='<div class="ride">'+qEsc(r.name)+(km||x?' <small>'+km+(km&&x?" · ":"")+x+'</small>':"")+'</div>';});'''
assert s.count(old)==1
new='''rr.forEach(function(r){var km=r.dist_km?qN(r.dist_km,0)+" km":"";var dur=r.duration_s?qHM(r.duration_s):"";h+='<div class="ride">🚲 '+km+(km&&dur?" · ":"")+dur+'</div>';});'''
s=s.replace(old,new)

open(p,"w").write(s)
print("fixed: kafle jazd = 🚲 km · czas")
