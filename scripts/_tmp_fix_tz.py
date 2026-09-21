p="/opt/qbot/web/public/start2.js"
s=open(p).read()
# zamien toISOString na localISO
s=s.replace("new Date().toISOString().slice(0,10)","qToday()")
s=s.replace("new Date(Date.now()-7*864e5).toISOString().slice(0,10)","qLocalISO(new Date(Date.now()-7*864e5))")
s=s.replace("new Date(Date.now()-30*864e5).toISOString().slice(0,10)","qLocalISO(new Date(Date.now()-30*864e5))")
s=s.replace("new Date(Date.now()-(6-di)*864e5).toISOString().slice(0,10)","qLocalISO(new Date(Date.now()-(6-di)*864e5))")
s=s.replace("new Date(Date.now()-i*864e5).toISOString().slice(0,10)","qLocalISO(new Date(Date.now()-i*864e5))")
open(p,"w").write(s)
print("start2 fixed, toISOString count:", s.count("toISOString"))
