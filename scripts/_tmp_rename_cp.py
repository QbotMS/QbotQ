# Zamien FTP -> CP w etykietach UI (nie w nazwach kolumn bazy)
for f in ["/opt/qbot/web/public/start2.js","/opt/qbot/web/public/forma2-data.js"]:
    s=open(f).read()
    changes=0
    for old,new in [("Moc progowa","CP (moc progowa)"),("m-ftp-v","m-ftp-v"),("m-ftp-d","m-ftp-d"),("m-ftp-s","m-ftp-s")]:
        pass  # nie zmieniamy ID-kow, tylko etykiety
    # etykiety tekstowe
    for old,new in [("Moc progowa <span","CP <span"),("Moc progowa</p>","CP (moc progowa)</p>")]:
        if old in s: s=s.replace(old,new); changes+=1
    open(f,"w").write(s)
    print(f.split("/")[-1],"changes:",changes)
