# Kalendarz
p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()
old='if(dd.sleep)slParts.push("sen "+qN(dd.sleep,1));'
assert s.count(old)==1, "kal: "+str(s.count(old))
s=s.replace(old,'if(dd.sleep_score)slParts.push("sen "+dd.sleep_score);else if(dd.sleep)slParts.push("sen "+qN(dd.sleep,1)+"h");')
old2="'<span>sen <b>'+qN(dd.sleep,1)+'</b></span>'"
# szukam inaczej
i=s.index("sen <b>")
chunk=repr(s[i-5:i+40])
print("found:",chunk)
s=s.replace("sen <b>'+qN(dd.sleep,1)+'</b>","sen <b>'+(dd.sleep_score||qN(dd.sleep,1)+'h')+'</b>")
open(p,"w").write(s)
print("kalendarz ok")

# Forma
p2="/opt/qbot/web/public/forma2-data.js"
s2=open(p2).read()
old3='var well="sen "+qN(dd2.sleep,1)+" · HRV "+qN(dd2.hrv,0)'
assert s2.count(old3)==1
s2=s2.replace(old3,'var sleepLbl=dd2.sleep_score?"sen "+dd2.sleep_score:"sen "+qN(dd2.sleep,1)+"h";var well=sleepLbl+" · HRV "+qN(dd2.hrv,0)')
old4='"<span>sen <b>"+qN(T.sleep_h||T.sleep,1)+"</b></span>"'
assert s2.count(old4)==1
s2=s2.replace(old4,'"<span>sen <b>"+(T.sleep_score||qN(T.sleep_h||T.sleep,1)+"h")+"</b></span>"')
open(p2,"w").write(s2)
print("forma ok")

# Start
p3="/opt/qbot/web/public/start2.js"
s3=open(p3).read()
old5='"HRV "+qN(T.hrv_night||T.hrv,0)+" · RHR "+qN(T.rhr,0)+" · sen "+qN(T.sleep_h||T.sleep,1)+" h"'
assert s3.count(old5)==1
s3=s3.replace(old5,'"HRV "+qN(T.hrv_night||T.hrv,0)+" · RHR "+qN(T.rhr,0)+" · sen "+(T.sleep_score||qN(T.sleep_h||T.sleep,1)+"h")')
open(p3,"w").write(s3)
print("start ok")
