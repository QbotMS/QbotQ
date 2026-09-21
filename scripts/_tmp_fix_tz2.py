p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
s=s.replace("new Date().toISOString().slice(0,10)","qToday()")
s=s.replace("new Date(Date.now()-90*864e5).toISOString().slice(0,10)","qLocalISO(new Date(Date.now()-90*864e5))")
s=s.replace("new Date(Date.now()-30*864e5).toISOString().slice(0,10)","qLocalISO(new Date(Date.now()-30*864e5))")
s=s.replace("new Date(Date.now()-7*864e5).toISOString().slice(0,10)","qLocalISO(new Date(Date.now()-7*864e5))")
open(p,"w").write(s)
print("forma2 fixed, toISOString count:", s.count("toISOString"))
