p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()

# kafle: zamien emoji na kolorowa kropke
old="h+='<div class=\"ride\">🚲 '"
assert s.count(old)==1
s=s.replace(old,"h+='<div class=\"ride\"><span style=\"color:var(--accent)\">●</span> '")

open(p,"w").write(s)
print("fixed: accent dot instead of bike emoji")
