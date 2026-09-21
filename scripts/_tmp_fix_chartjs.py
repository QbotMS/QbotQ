p="/opt/qbot/web/public/forma.html"
t=open(p).read()
old='src="/https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js">'
new='src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js">'
assert t.count(old)==1
t=t.replace(old,new)
t=t.replace("forma2-data.js?v=13","forma2-data.js?v=14")
open(p,"w").write(t)
print("fixed chartjs url")
