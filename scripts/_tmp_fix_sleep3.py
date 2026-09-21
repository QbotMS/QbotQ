# Forma: sleep_score
p2="/opt/qbot/web/public/forma2-data.js"
s2=open(p2).read()

# dziennik - well
old='var well=sleepLbl+" · HRV'
if s2.count(old)==1:
    print("dziennik already patched")
else:
    old='var well="sen "+qN(dd2.sleep,1)+" · HRV'
    assert s2.count(old)==1,"forma well: "+str(s2.count(old))
    s2=s2.replace(old,'var sleepLbl=dd2.sleep_score?"sen "+dd2.sleep_score:"sen "+qN(dd2.sleep,1)+"h";var well=sleepLbl+" · HRV')
    print("dziennik fixed")

# karta dzis
old2='<b>"+qN(T.sleep_h||T.sleep,1)+"</b>'
assert s2.count(old2)>=1,"forma today sleep: "+str(s2.count(old2))
s2=s2.replace(old2,'<b>"+(T.sleep_score||qN(T.sleep_h||T.sleep,1)+"h")+"</b>',1)

open(p2,"w").write(s2)
print("forma ok, sleep count:", s2.count("sleep_score"))

# Start
p3="/opt/qbot/web/public/start2.js"
s3=open(p3).read()
old5='sen "+qN(T.sleep_h||T.sleep,1)+" h"'
assert s3.count(old5)==1,"start sleep: "+str(s3.count(old5))
s3=s3.replace(old5,'sen "+(T.sleep_score||qN(T.sleep_h||T.sleep,1)+"h")')
open(p3,"w").write(s3)
print("start ok")
