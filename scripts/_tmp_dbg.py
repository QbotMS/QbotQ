p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()
print("sleep count:", s.count("dd.sleep"))
i=s.index("slParts")
print(repr(s[i:i+120]))
