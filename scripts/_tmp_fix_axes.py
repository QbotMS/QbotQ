p="/opt/qbot/web/public/forma2-data.js"
s=open(p).read()

# zamieniam opcje Chart.js: dwie osie Y
old="scales:{x:{ticks:{color:txtCol,font:{size:10},maxTicksLimit:8,maxRotation:0},grid:{display:false}},\n        y:{ticks:{color:txtCol,font:{size:11}},grid:{color:gridCol},\n          afterBuildTicks:function(axis){/* linia zero */}}}"
assert s.count(old)==1

new="""scales:{x:{ticks:{color:txtCol,font:{size:10},maxTicksLimit:8,maxRotation:0},grid:{display:false}},
        y:{position:"left",ticks:{color:txtCol,font:{size:11}},grid:{color:gridCol},title:{display:true,text:"forma / zmeczenie",color:txtCol,font:{size:11}}},
        y2:{position:"right",ticks:{color:tsbCol,font:{size:11}},grid:{drawOnChartArea:false},title:{display:true,text:"swiezosc (TSB)",color:tsbCol,font:{size:11}}}}"""
s=s.replace(old,new)

# CTL i ATL na osi y (domyslna), TSB na y2
old2='{label:"swiezosc (TSB)",data:tsbD,borderColor:tsbCol,backgroundColor:tsbCol+"22",borderWidth:2,borderDash:[6,4],pointRadius:0,pointHoverRadius:5,tension:0.3,fill:true}'
assert s.count(old2)==1
s=s.replace(old2,'{label:"swiezosc (TSB)",data:tsbD,borderColor:tsbCol,backgroundColor:tsbCol+"15",borderWidth:2,borderDash:[6,4],pointRadius:0,pointHoverRadius:5,tension:0.3,fill:true,yAxisID:"y2"}')

open(p,"w").write(s)
print("fixed: dual Y axes")
