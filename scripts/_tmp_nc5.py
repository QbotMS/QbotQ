import subprocess
r=subprocess.run(["node","--check","/opt/qbot/web/public/forma2-data.js"],capture_output=True,text=True)
print("exit:", r.returncode, r.stderr[:200] if r.stderr else "ok")
# bump
t=open("/opt/qbot/web/public/forma.html").read()
t=t.replace("forma2-data.js?v=20","forma2-data.js?v=21")
open("/opt/qbot/web/public/forma.html","w").write(t)
print("bumped v21")
