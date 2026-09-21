p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# usuwam caly blok FTP chart (od "/* FTP chart" do "/* statystyki */")
i1=s.index("/* FTP chart")
i2=s.index("/* statystyki */")
s=s[:i1]+s[i2:]

# usuwam zmienne _ftpChart ktore juz nie istnieja
s=s.replace("if(window._ftpChart){window._ftpChart.destroy();window._ftpChart=null;}\n  ","")

open(p,"w").write(s)
print("FTP block removed")
