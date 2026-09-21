p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
# sprawdzam czy renderDziennik czyści rows
i=s.index("var rows=q$(\"days\")")
print(repr(s[i:i+80]))
# sprawdzam entMap
print("entMap count:", s.count("entMap"))
# sprawdzam czy wireButtons jest wywoływany po renderach
print("wireButtons call:", s.count("wireButtons()"))
# sprawdzam sleep_score w forma/data
print("sleep_score in forma data:", s.count("sleep_score"))
