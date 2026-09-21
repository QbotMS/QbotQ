p="/opt/qbot/web/public/forma.html"
t=open(p).read()
i=t.index("var tabs=")
print(repr(t[i:i+300]))
