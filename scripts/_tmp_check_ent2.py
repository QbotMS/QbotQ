s=open("/opt/qbot/app/qbot_web.py").read()
i=s.index("8787" if False else "FROM qbot_v2.calendar_entry", s.index("def calendar_entries"))
print(repr(s[i-200:i+200]))
