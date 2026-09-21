# Kalendarz: kafle i panel dnia — sleep_score zamiast sleep_h
p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()

# kafle: sen -> score
old='if(dd.sleep)slParts.push("sen "+qN(dd.sleep,1));'
assert s.count(old)==1
s=s.replace(old,'if(dd.sleep_score)slParts.push("sen "+dd.sleep_score);else if(dd.sleep)slParts.push("sen "+qN(dd.sleep,1)+"h");')

# panel dnia: grid — sleep_score
old="'<span>sen <b>'+qN(dd.sleep,1)+'</b></span>'"
assert s.count(old)==1
s=s.replace(old,"'<span>sen <b>'+(dd.sleep_score||qN(dd.sleep,1)+'h')+'</b></span>'")

open(p,"w").write(s)
print("kalendarz: sleep_score")

# Forma: dziennik
p2="/opt/qbot/web/public/forma2-data.js"
s2=open(p2).read()

old2='var well="sen "+qN(dd2.sleep,1)+" · HRV "+qN(dd2.hrv,0)'
assert s2.count(old2)==1
s2=s2.replace(old2,'var sleepLbl=dd2.sleep_score?"sen "+dd2.sleep_score:"sen "+qN(dd2.sleep,1)+"h";var well=sleepLbl+" · HRV "+qN(dd2.hrv,0)')

# Forma: karta Dziś
old3='"<span>sen <b>"+qN(T.sleep_h||T.sleep,1)+"</b></span>"'
assert s2.count(old3)==1
s2=s2.replace(old3,'"<span>sen <b>"+(T.sleep_score||qN(T.sleep_h||T.sleep,1)+"h")+"</b></span>"')

open(p2,"w").write(s2)
print("forma: sleep_score")

# Start: gotowość sub
p3="/opt/qbot/web/public/start2.js"
s3=open(p3).read()
old4='"HRV "+qN(T.hrv_night||T.hrv,0)+" · RHR "+qN(T.rhr,0)+" · sen "+qN(T.sleep_h||T.sleep,1)+" h"'
assert s3.count(old4)==1
s3=s3.replace(old4,'"HRV "+qN(T.hrv_night||T.hrv,0)+" · RHR "+qN(T.rhr,0)+" · sen "+(T.sleep_score||qN(T.sleep_h||T.sleep,1)+"h")')

open(p3,"w").write(s3)
print("start: sleep_score")
