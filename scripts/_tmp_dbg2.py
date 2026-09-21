p2="/opt/qbot/web/public/forma2-data.js"
s2=open(p2).read()
i=s2.index("sleep")
print(repr(s2[i-10:i+60]))
i2=s2.index("sleep",i+10)
print(repr(s2[i2-10:i2+60]))
