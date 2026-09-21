p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
# szukam problematycznego apostrofu
i=s.find("Zapas W\\'")
print("escaped W':", i)
i2=s.find("Zapas W'")
print("unescaped W':", i2)
if i2>0: print("context:", repr(s[i2-20:i2+30]))
# sprawdzam czy JS parsuje sie jako modul
import subprocess
r=subprocess.run(["node","--check","/opt/qbot/web/public/forma2-data.js"],capture_output=True,text=True)
print("node:", r.returncode, r.stderr[:300] if r.stderr else "ok")
