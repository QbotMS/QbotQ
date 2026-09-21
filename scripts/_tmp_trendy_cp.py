p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# 1) Dodaj cpD do zbierania danych
old="var labels=[],ctlD=[],atlD=[],tsbD=[],xssD=[];"
assert s.count(old)==1
s=s.replace(old,"var labels=[],ctlD=[],atlD=[],tsbD=[],xssD=[],cpD=[];")

# 2) Dodaj CP do petli
old="var _xd=0;(rides.rides||[]).forEach(function(r){if(r.date===s2.day)_xd+=(r.xss||0);});xssD.push(_xd);"
assert s.count(old)==1
s=s.replace(old,"var _xd=0;(rides.rides||[]).forEach(function(r){if(r.date===s2.day)_xd+=(r.xss||0);});xssD.push(_xd);\n    cpD.push(s2.ftp_est_w||s2.ftp||null);")

# 3) Dodaj dataset CP + os y3 (prawa, watty)
old='{type:"bar",label:"obc. dnia"'
assert s.count(old)==1
s=s.replace(old,'{label:"CP (moc progowa)",data:cpD,borderColor:"#3b82f6",backgroundColor:"transparent",borderWidth:2,pointRadius:0,pointHoverRadius:4,tension:0.4,fill:false,yAxisID:"y3",order:0},\n      {type:"bar",label:"obc. dnia"')

# 4) Zamien y3 z display:false na prawa os z W
old='y3:{display:false,beginAtZero:true,position:"right"}'
assert s.count(old)==1
s=s.replace(old,'y3:{position:"right",ticks:{color:"#3b82f6",font:{size:10}},grid:{drawOnChartArea:false},title:{display:true,text:"CP (W)",color:"#3b82f6",font:{size:10}}}')

# 5) Dodaj os y4 (ukryta) dla slupkow XSS
old='yAxisID:"y3",order:3'
# to jest stary bar na y3, teraz y3 to CP — bar musi byc na y4
s=s.replace('type:"bar",label:"obc. dnia",data:xssD,backgroundColor:isDark?"rgba(255,255,255,0.12)":"rgba(0,0,0,0.10)",borderWidth:0,yAxisID:"y3",order:3',
            'type:"bar",label:"obc. dnia",data:xssD,backgroundColor:isDark?"rgba(255,255,255,0.12)":"rgba(0,0,0,0.10)",borderWidth:0,yAxisID:"y4",order:4')

# dodaj y4 do scales
old2='y3:{position:"right"'
# wstawiam y4 po y3
i=s.index('y3:{position:"right"')
j=s.index('}',s.index('}',s.index('}',i)+1)+1)+1  # trzecie zamkniecie
s=s[:j+1]+',\n        y4:{display:false,beginAtZero:true}'+s[j+1:]

# 6) Zmien etykiety z FTP na CP
s=s.replace('"FTP"','"CP"')
s=s.replace('FTP',  'CP')  # w statystykach

# 7) Usun caly blok FTP synced chart (dolny)
ftp_start=s.index("/* FTP chart")
ftp_end=s.index("/* statystyki */")
s=s[:ftp_start]+s[ftp_end:]

open(p,"w").write(s)
print("CP on main chart, FTP panel removed")
