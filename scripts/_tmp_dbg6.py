p="/opt/qbot/web/public/forma.html"
t=open(p).read()
i=t.index("trendy-canvas")
print(repr(t[i-100:i+200]))
j=t.index("trendy-comment")
print("---")
print(repr(t[j-100:j+50]))
