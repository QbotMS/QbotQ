s=open("/opt/qbot/app/qbot_web.py").read()
# find where entries are merged into days
i=s.index("FROM qbot_v2.calendar_entry", s.index("def calendar_entries"))
chunk=s[i:i+1500]
print(repr(chunk[:500]))
print("---")
print(repr(chunk[500:1000]))
print("---")
print(repr(chunk[1000:1500]))
