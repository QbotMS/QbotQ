p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()
# sprawdz GROUPS
i=s.index("var GROUPS=")
print(repr(s[i:i+400]))
# sprawdz wireButtons
i2=s.index("function wireButtons")
print("---")
print(repr(s[i2:i2+500]))
# sprawdz czy renderTrendy uzywa q$
print("---")
print("q$ trendy-chart:", s.count('q$("trendy-chart")'))
print("q$ trendy-legend:", s.count('q$("trendy-legend")'))
print("q$ trendy-metrics:", s.count('q$("trendy-metrics")'))
