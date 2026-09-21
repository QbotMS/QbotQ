s=open("/opt/qbot/app/qbot_web.py").read()
i=s.index("rides/ready")
j=s.index("dist_km",i)
print(repr(s[j-100:j+200]))
