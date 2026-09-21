p="/opt/qbot/web/public/kalendarz2-data.js"
s=open(p).read()

old='''  if(sub)sub.innerHTML="gotowość <b>"+(typeof dd.readiness==="number"?(dd.readiness>0?"+":"")+qN(dd.readiness,2):"—")+"</b> · sen "+qN(dd.sleep,1)+" · HRV "+qN(dd.hrv,0)+(dd.weight_kg?" · waga "+qN(dd.weight_kg,1)+" kg":"");'''
assert s.count(old)==1
new='''  if(sub)sub.innerHTML='<div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 12px;font-size:14px;line-height:1.6"><span>gotowość <b>'+(typeof dd.readiness==="number"?(dd.readiness>0?"+":"")+qN(dd.readiness,2):"—")+'</b></span><span>sen <b>'+qN(dd.sleep,1)+'</b></span><span>HRV <b>'+qN(dd.hrv,0)+'</b></span>'+(dd.weight_kg?'<span>waga <b>'+qN(dd.weight_kg,1)+' kg</b></span>':'')+'</div>';'''
s=s.replace(old,new)

open(p,"w").write(s)
print("fixed: sub as grid 2x2")
