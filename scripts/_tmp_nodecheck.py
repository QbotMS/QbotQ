import subprocess
r=subprocess.run(["node","--check","/opt/qbot/web/public/forma2-data.js"],capture_output=True,text=True)
print("exit:", r.returncode)
if r.stderr: print(r.stderr[:500])
else: print("syntax ok")
