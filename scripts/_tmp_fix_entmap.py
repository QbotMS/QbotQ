p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# przenies entMap na level modulu
old='var RNG=90,GRP="moc";'
assert s.count(old)==1
s=s.replace(old,'var RNG=90,GRP="moc",entMap={};')

# w load() zamien var na przypisanie
old2='var entMap={};(cal.entries||[]).forEach'
assert s.count(old2)==1
s=s.replace(old2,'entMap={};(cal.entries||[]).forEach')

open(p,"w").write(s)
print("fixed: entMap module-level")
