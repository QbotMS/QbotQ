p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# 1) cpD do zbierania
old1="var labels=[],ctlD=[],atlD=[],tsbD=[],xssD=[];"
if s.count(old1)==1:
    s=s.replace(old1,"var labels=[],ctlD=[],atlD=[],tsbD=[],xssD=[],cpD=[];")
elif "cpD" not in s[:s.index("SN.forEach")]:
    s=s.replace("var labels=[],ctlD=[],atlD=[],tsbD=[],xssD=[],cpD=[];","var labels=[],ctlD=[],atlD=[],tsbD=[],xssD=[],cpD=[];")

# 2) CP w petli
if "cpD.push" not in s:
    old2="xssD.push(_xd);"
    assert s.count(old2)==1
    s=s.replace(old2,"xssD.push(_xd);cpD.push(s2.ftp_est_w||s2.ftp||null);")

# 3) dataset CP przed bar
old3='{type:"bar",label:"obc. dnia"'
if 'label:"CP"' not in s:
    assert s.count(old3)==1
    s=s.replace(old3,'{label:"CP",data:cpD,borderColor:"#3b82f6",backgroundColor:"transparent",borderWidth:2.5,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"y3",order:0},\n      {type:"bar",label:"obc. dnia"')

# 4) bar na y4
s=s.replace('yAxisID:"y3",order:3','yAxisID:"y4",order:4')

# 5) y3 = CP axis (prawa, W), y4 = bar (ukryta)
old5='y3:{display:false,beginAtZero:true,position:"right"}'
if s.count(old5)==1:
    s=s.replace(old5,'y3:{position:"right",ticks:{color:"#3b82f6",font:{size:10}},grid:{drawOnChartArea:false},title:{display:true,text:"CP (W)",color:"#3b82f6",font:{size:10}}},\n        y4:{display:false,beginAtZero:true}')

# 6) legenda: nie pokazuj "obc. dnia"
# juz jest filter

# 7) etykiety FTP -> CP w statystykach i komentarzu
s=s.replace('"FTP"','"CP"')
s=s.replace("'FTP'","'CP'")

open(p,"w").write(s)

import subprocess
r=subprocess.run(["node","--check",p],capture_output=True,text=True)
print("node:", r.returncode, r.stderr[:200] if r.stderr else "ok")
