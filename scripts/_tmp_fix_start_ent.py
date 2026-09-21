p="/opt/qbot/web/public/start2.js"
s=open(p).read()

# 1) cal juz jest pobierany (30 dni), ale entries nie sa czytane. Dodaje entMap
old='var days=cal.days||{};var rmap={},seen={};'
assert s.count(old)==1
s=s.replace(old,'var days=cal.days||{};var entMap={};(cal.entries||[]).forEach(function(e){entMap[e.day]=entMap[e.day]||[];entMap[e.day].push(e);});var rmap={},seen={};')

# 2) w liście dni: dodaj wpisy kalendarza
old='var well="sen "+qN(dd3.sleep,1)+" · HRV "+qN(dd3.hrv,0);'
assert s.count(old)==1
new='''var sleepLbl=dd3.sleep_score?"sen "+dd3.sleep_score:"sen "+qN(dd3.sleep,1)+"h";
    var ents=(entMap[ds2]||[]);var entTxt=ents.map(function(e){return e.kind==="illness"?'<span style="color:#4eca6a">\U0001F915 '+qEsc(e.title||"choroba")+"</span>":e.kind==="feel"?"\U0001F60A "+qEsc(e.title||""):"";}).filter(Boolean).join(" · ");
    var well=sleepLbl+" · HRV "+qN(dd3.hrv,0)+(entTxt?" · "+entTxt:"");'''
s=s.replace(old,new)

open(p,"w").write(s)
print("start: entries + sleep_score in days list")
