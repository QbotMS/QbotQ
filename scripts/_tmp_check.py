s=open("/opt/qbot/app/qbot_web.py").read()
i=s.index("dist_km, ")
print(repr(s[i-120:i+80]))
