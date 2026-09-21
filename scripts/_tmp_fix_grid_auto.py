# Zmieniam grid: dzień(70) | gotowość(auto) | aktywność(auto) | sen/HRV(auto) | choroba(1fr=reszta) | chev(20)
# aktywność i sen dopasowują się do treści, choroba bierze ile zostanie

for f,has_chev in [("/opt/qbot/web/public/index.html",False),("/opt/qbot/web/public/forma.html",True)]:
    t=open(f).read()
    if has_chev:
        old='grid-template-columns:70px 80px 1fr 130px 1fr 20px'
        new='grid-template-columns:70px auto auto auto 1fr 20px'
        old_m='grid-template-columns:55px 65px 1fr 20px'
        new_m='grid-template-columns:55px auto 1fr 20px'
    else:
        old='grid-template-columns:70px 80px 1fr 130px 1fr'
        new='grid-template-columns:70px auto auto auto 1fr'
        old_m='grid-template-columns:55px 65px 1fr'
        new_m='grid-template-columns:55px auto 1fr'
    assert t.count(old)==1, f+": "+str(t.count(old))
    t=t.replace(old,new)
    assert t.count(old_m)==1, f+" mobile: "+str(t.count(old_m))
    t=t.replace(old_m,new_m)
    open(f,"w").write(t)
    print(f,"done")
