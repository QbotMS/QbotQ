p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# zamien xss_day na obliczenie z rides
old="xssD.push(s2.xss_day||0);"
assert s.count(old)==1
s=s.replace(old,"var _xd=0;(rides.rides||[]).forEach(function(r){if(r.date===s2.day)_xd+=(r.xss||0);});xssD.push(_xd);")

open(p,"w").write(s)
print("fixed: xss per day from rides")
