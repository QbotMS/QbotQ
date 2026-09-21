p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# 1) zbuduj mape entries per dzien (tak jak w kalendarzu)
old='  cal=await qJSON("/api/calendar?start="+qLocalISO(new Date(Date.now()-365*864e5))+"&end="+today);'
assert s.count(old)==1
s=s.replace(old,old+'\n  var entMap={};(cal.entries||[]).forEach(function(e){entMap[e.day]=entMap[e.day]||[];entMap[e.day].push(e);});')

# 2) w renderDziennik: dodaj wpisy do kazdego dnia
old='var well="sen "+qN(dd2.sleep,1)+" · HRV "+qN(dd2.hrv,0);'
assert s.count(old)==1
s=s.replace(old,'''var ents=(entMap[ds]||[]);var entTxt=ents.map(function(e){return e.kind==="illness"?'<span style="color:#4eca6a">🤒 '+qEsc(e.title||"choroba")+"</span>":e.kind==="feel"?"😊 "+qEsc(e.title||""):"";}).filter(Boolean).join(" · ");
    var well="sen "+qN(dd2.sleep,1)+" · HRV "+qN(dd2.hrv,0)+(entTxt?" · "+entTxt:"");''')

open(p,"w").write(s)
print("fixed: entries in forma dziennik")
