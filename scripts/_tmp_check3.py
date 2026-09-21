p="/opt/qbot/app/qbot_web.py"
s=open(p).read()
i=s.index("rides/ready")
chunk=s[i:i+600]
# find the escaped apostrophes
import re
for m in re.finditer(r"summary.{0,30}dist", chunk):
    print("MATCH:",repr(chunk[m.start()-5:m.end()+30]))
for m in re.finditer(r"\\\\|\\'" , chunk):
    print("ESC at",m.start(),":",repr(chunk[m.start()-3:m.end()+3]))
